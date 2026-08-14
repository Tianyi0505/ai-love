from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import secrets
import threading
import time
import uuid
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import asyncpg

from shared.infrastructure.run_repo import AgentRunRepository

logger = logging.getLogger("ailove.ops-panel")

DEFAULT_USERNAME = "ai-love"
DEFAULT_PASSWORD = "ai-love"
PBKDF2_ITERATIONS = 100_000
SESSION_TTL_SEC = int(os.environ.get("PANEL_SESSION_TTL_SEC", "86400"))
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


# 生成密码哈希
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


# 校验密码哈希
def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != "pbkdf2":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


# 包装连接池接口
class _PoolDB:
    # 初始化当前实例
    def __init__(self, pool) -> None:
        self._pool = pool

    async def fetch(self, query, *args):
        return await self._pool.fetch(query, *args)

    async def fetchrow(self, query, *args):
        return await self._pool.fetchrow(query, *args)

    async def execute(self, query, *args):
        return await self._pool.execute(query, *args)


# 保存面板状态
class PanelState:
    # 初始化当前实例
    def __init__(self) -> None:
        self.username = DEFAULT_USERNAME
        self.password_hash = hash_password(DEFAULT_PASSWORD)
        self.sessions: dict[str, float] = {}
        self.repo: AgentRunRepository | None = None
        self.db_ready = False
        self._db: _PoolDB | None = None

    # 创建会话令牌
    def create_session(self) -> str:
        token = secrets.token_hex(24)
        self.sessions[token] = time.time() + SESSION_TTL_SEC
        return token

    # 校验会话令牌
    def check_session(self, token: str) -> bool:
        now = time.time()
        expired = [key for key, expire_at in self.sessions.items() if expire_at <= now]
        for key in expired:
            self.sessions.pop(key, None)
        return token in self.sessions

    # 持久化凭据
    async def persist_credentials(self) -> None:
        if self._db is None:
            return
        await self._db.execute(
            "INSERT INTO panel_settings(key,value) VALUES('username',$1),('password_hash',$2) "
            "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            self.username,
            self.password_hash,
        )


# 初始化数据库与凭据
async def init_database(state: PanelState) -> None:
    url = os.environ.get("AILOVE_DATABASE_URL", "").strip()
    if not url:
        logger.warning("[panel] 未配置数据库，退回内存模式")
        return
    pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
    db = _PoolDB(pool)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS panel_settings(key text PRIMARY KEY, value text NOT NULL)"
    )
    row = await db.fetchrow("SELECT value FROM panel_settings WHERE key='username'")
    if row:
        state.username = str(row["value"])
    row = await db.fetchrow("SELECT value FROM panel_settings WHERE key='password_hash'")
    if row:
        state.password_hash = str(row["value"])
    else:
        await db.execute(
            "INSERT INTO panel_settings(key,value) VALUES('username',$1),('password_hash',$2) "
            "ON CONFLICT(key) DO NOTHING",
            state.username,
            state.password_hash,
        )
    state._db = db
    state.repo = AgentRunRepository(db)
    state.db_ready = True
    logger.info("[panel] 数据库就绪，追溯查询可用")


# 处理面板请求
class PanelHandler(BaseHTTPRequestHandler):
    server_version = "ailove-ops-panel"
    state: PanelState
    loop: asyncio.AbstractEventLoop

    # 初始化当前实例
    def __init__(self, *args, state: PanelState, loop: asyncio.AbstractEventLoop, **kwargs) -> None:
        self.state = state
        self.loop = loop
        super().__init__(*args, **kwargs)

    # 记录访问日志
    def log_message(self, fmt, *args) -> None:
        logger.info("[panel] %s %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self._handle_api_get(path)
        else:
            self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        self._handle_api_post(urlparse(self.path).path)

    # 处理读取接口
    def _handle_api_get(self, path: str) -> None:
        if path == "/api/links":
            if not self._authorized():
                return
            self._send_json(200, {
                "nacos_url": os.environ.get("PANEL_NACOS_URL", "http://127.0.0.1:8848/nacos"),
                "k3s_url": os.environ.get("PANEL_K3S_URL", "http://127.0.0.1:8001"),
            })
            return
        if path == "/api/runs":
            if not self._authorized():
                return
            query = parse_qs(urlparse(self.path).query)
            try:
                result = self._submit(self._list_runs(query))
            except Exception:
                logger.exception("[panel] 查询执行记录失败")
                result = {"runs": [], "db": False, "error": "查询执行记录失败"}
            self._send_json(200, result)
            return
        if path.startswith("/api/runs/"):
            if not self._authorized():
                return
            try:
                result = self._submit(self._replay_run(path.rsplit("/", 1)[-1]))
            except Exception:
                logger.exception("[panel] 回放执行记录失败")
                result = {"run": None, "steps": [], "db": False, "error": "回放执行记录失败"}
            self._send_json(200, result)
            return
        if path == "/api/conversations":
            if not self._authorized():
                return
            try:
                result = self._submit(self._list_conversations())
            except Exception:
                logger.exception("[panel] 查询会话失败")
                result = {"conversations": [], "db": False, "error": "查询会话失败"}
            self._send_json(200, result)
            return
        if path == "/api/messages":
            if not self._authorized():
                return
            query = parse_qs(urlparse(self.path).query)
            try:
                result = self._submit(self._list_messages(query))
            except Exception:
                logger.exception("[panel] 查询消息失败")
                result = {"messages": [], "db": False, "error": "查询消息失败"}
            self._send_json(200, result)
            return
        if path == "/api/persons":
            if not self._authorized():
                return
            try:
                result = self._submit(self._list_persons())
            except Exception:
                logger.exception("[panel] 查询人物失败")
                result = {"persons": [], "db": False, "error": "查询人物失败"}
            self._send_json(200, result)
            return
        self._send_json(404, {"error": "接口不存在"})

    # 处理写入接口
    def _handle_api_post(self, path: str) -> None:
        if path == "/api/login":
            payload = self._read_json()
            username = str(payload.get("username") or "")
            password = str(payload.get("password") or "")
            if (
                username == self.state.username
                and verify_password(password, self.state.password_hash)
            ):
                token = self.state.create_session()
                self._send_json(200, {"ok": True, "token": token, "username": username, "db": self.state.db_ready})
            else:
                self._send_json(401, {"ok": False, "error": "账号或密码错误"})
            return
        if path == "/api/credentials":
            if not self._authorized():
                return
            payload = self._read_json()
            if not verify_password(
                str(payload.get("current_password") or ""), self.state.password_hash
            ):
                self._send_json(401, {"ok": False, "error": "当前密码错误"})
                return
            new_username = str(payload.get("username") or "").strip()
            new_password = str(payload.get("password") or "")
            if new_username:
                self.state.username = new_username
            if new_password:
                self.state.password_hash = hash_password(new_password)
            try:
                self._submit(self.state.persist_credentials())
            except Exception:
                logger.exception("[panel] 保存凭据失败")
                self._send_json(500, {"ok": False, "error": "保存凭据失败"})
                return
            self.state.sessions.clear()
            self._send_json(200, {"ok": True, "message": "凭据已更新，请重新登录"})
            return
        if path == "/api/logout":
            token = self._token()
            if token:
                self.state.sessions.pop(token, None)
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "接口不存在"})

    # 列出执行记录
    async def _list_runs(self, query: dict) -> dict:
        if self.state.repo is None:
            return {"runs": [], "db": False}
        try:
            runs = await self.state.repo.search_runs(
                ai_id=str((query.get("ai_id") or [""])[0]).strip(),
                conversation_id=str((query.get("conversation_id") or [""])[0]).strip(),
                source=str((query.get("source") or [""])[0]).strip(),
                limit=int((query.get("limit") or ["50"])[0]),
                offset=int((query.get("offset") or ["0"])[0]),
            )
            return {"runs": runs, "db": True}
        except Exception as exc:
            logger.exception("[panel] 查询执行记录失败")
            return {"runs": [], "db": False, "error": str(exc)}

    # 回放单轮执行
    async def _replay_run(self, run_id: str) -> dict:
        if self.state.repo is None:
            return {"run": None, "steps": [], "db": False}
        try:
            result = await self.state.repo.replay(run_id)
            return {"run": result["run"], "steps": result["steps"], "db": True}
        except Exception as exc:
            logger.exception("[panel] 回放执行记录失败")
            return {"run": None, "steps": [], "db": False, "error": str(exc)}

    # 列出会话
    async def _list_conversations(self) -> dict:
        if self.state._db is None:
            return {"conversations": [], "db": False}
        rows = await self.state._db.fetch(
            "SELECT c.conversation_id::text, c.platform, c.chat_type, c.platform_chat_id, "
            "COUNT(m.message_id) AS message_count, MAX(m.occurred_at) AS last_at, "
            "MIN(m.occurred_at) AS first_at, COALESCE(cs.summary, '') AS summary "
            "FROM conversations c "
            "LEFT JOIN messages m ON m.conversation_id = c.conversation_id "
            "LEFT JOIN conversation_summaries cs ON cs.conversation_id = c.conversation_id "
            "GROUP BY c.conversation_id, c.platform, c.chat_type, c.platform_chat_id, cs.summary "
            "ORDER BY last_at DESC NULLS LAST LIMIT 200"
        )
        return {
            "conversations": [
                {
                    "conversation_id": row["conversation_id"],
                    "platform": row["platform"],
                    "chat_type": row["chat_type"],
                    "platform_chat_id": row["platform_chat_id"],
                    "message_count": int(row["message_count"] or 0),
                    "last_at": str(row["last_at"]) if row["last_at"] else "",
                    "first_at": str(row["first_at"]) if row["first_at"] else "",
                    "summary": row["summary"] or "",
                }
                for row in rows
            ],
            "db": True,
        }

    # 查询历史消息
    async def _list_messages(self, query: dict) -> dict:
        if self.state._db is None:
            return {"messages": [], "db": False}
        conditions: list[str] = []
        args: list = []
        conversation_id = str((query.get("conversation_id") or [""])[0]).strip()
        if conversation_id:
            try:
                uuid.UUID(conversation_id)
            except (ValueError, TypeError, AttributeError):
                return {"messages": [], "db": False, "error": "conversation_id 无效"}
            args.append(conversation_id)
            conditions.append(f"m.conversation_id=${len(args)}::uuid")
        person_id = str((query.get("person_id") or [""])[0]).strip()
        if person_id:
            try:
                uuid.UUID(person_id)
            except (ValueError, TypeError, AttributeError):
                return {"messages": [], "db": False, "error": "person_id 无效"}
            args.append(person_id)
            conditions.append(f"pi.person_id=${len(args)}::uuid")
        role = str((query.get("role") or [""])[0]).strip()
        if role in ("user", "assistant"):
            args.append(role)
            conditions.append(f"m.role=${len(args)}")
        keyword = str((query.get("keyword") or [""])[0]).strip()
        if keyword:
            args.append(f"%{keyword}%")
            conditions.append(f"COALESCE(m.content->>'text','') ILIKE ${len(args)}")
        since = str((query.get("since") or [""])[0]).strip()
        if since:
            args.append(since)
            conditions.append(f"m.occurred_at >= ${len(args)}::timestamptz")
        until = str((query.get("until") or [""])[0]).strip()
        if until:
            args.append(until)
            conditions.append(f"m.occurred_at <= ${len(args)}::timestamptz")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.append(int(max(1, min(200, int((query.get("limit") or ["50"])[0])))))
        args.append(int(max(0, int((query.get("offset") or ["0"])[0]))))
        rows = await self.state._db.fetch(
            "SELECT m.message_id::text, m.conversation_id::text, m.ai_id, m.role, "
            "c.platform, c.chat_type, c.platform_chat_id, "
            "pi.person_id::text AS person_id, "
            "COALESCE(NULLIF(p.display_name,''), pi.platform_user_id, '') AS display_name, "
            "m.content, m.occurred_at "
            "FROM messages m "
            "JOIN conversations c ON c.conversation_id = m.conversation_id "
            "LEFT JOIN platform_identities pi ON pi.identity_id = m.platform_identity_id "
            "LEFT JOIN persons p ON p.person_id = pi.person_id "
            f"{where} "
            f"ORDER BY m.occurred_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}",
            *args,
        )
        return {
            "messages": [
                {
                    "message_id": row["message_id"],
                    "conversation_id": row["conversation_id"],
                    "ai_id": row["ai_id"],
                    "role": row["role"],
                    "platform": row["platform"],
                    "chat_type": row["chat_type"],
                    "platform_chat_id": row["platform_chat_id"],
                    "person_id": row["person_id"],
                    "display_name": row["display_name"],
                    "content": row["content"],
                    "occurred_at": str(row["occurred_at"]),
                }
                for row in rows
            ],
            "db": True,
        }

    # 列出人物
    async def _list_persons(self) -> dict:
        if self.state._db is None:
            return {"persons": [], "db": False}
        rows = await self.state._db.fetch(
            "SELECT pi.person_id::text, "
            "COALESCE(NULLIF(p.display_name,''), pi.platform_user_id, '') AS display_name, "
            "COUNT(m.message_id) AS message_count, MAX(m.occurred_at) AS last_at "
            "FROM platform_identities pi "
            "JOIN persons p ON p.person_id = pi.person_id "
            "LEFT JOIN messages m ON m.platform_identity_id = pi.identity_id "
            "GROUP BY pi.person_id, p.display_name, pi.platform_user_id "
            "ORDER BY last_at DESC NULLS LAST LIMIT 300"
        )
        return {
            "persons": [
                {
                    "person_id": row["person_id"],
                    "display_name": row["display_name"],
                    "message_count": int(row["message_count"] or 0),
                    "last_at": str(row["last_at"]) if row["last_at"] else "",
                }
                for row in rows
            ],
            "db": True,
        }

    # 同步执行异步任务
    def _submit(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=15)

    # 校验请求授权
    def _authorized(self) -> bool:
        token = self._token()
        if token and self.state.check_session(token):
            return True
        self._send_json(401, {"ok": False, "error": "未登录或会话已过期"})
        return False

    # 提取会话令牌
    def _token(self) -> str:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[len("Bearer "):].strip()
        return ""

    # 解析请求体
    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    # 返回JSON响应
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # 返回静态文件
    def _serve_static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(os.path.normpath(WEB_DIR)) or not os.path.isfile(full):
            self.send_error(404, "文件不存在")
            return
        content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as handle:
            body = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# 启动面板
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    port = int(os.environ.get("PANEL_PORT", "8090"))
    state = PanelState()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    future = asyncio.run_coroutine_threadsafe(init_database(state), loop)
    try:
        future.result(timeout=15)
    except Exception as exc:
        logger.warning("[panel] 初始化数据库失败，退回内存模式: %s", exc)
    handler = partial(PanelHandler, state=state, loop=loop)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    logger.info("[panel] 运维面板已启动: http://0.0.0.0:%s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    main()
