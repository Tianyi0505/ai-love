
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# 处理语音合成请求
class SynthesisHandler(BaseHTTPRequestHandler):
    server_version = "ailove-gptsovits"
    service = None
    loop: asyncio.AbstractEventLoop | None = None

    # 记录访问日志
    def log_message(self, fmt, *args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/synthesize":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "请求体无效"})
            return
        future = asyncio.run_coroutine_threadsafe(
            self.service.synthesize(str(req.get("ai_id", "")), str(req.get("text", ""))),
            self.loop,
        )
        try:
            result = future.result(timeout=180)
        except Exception as exc:
            self._send_json(502, {"ok": False, "error": str(exc)[:200]})
            return
        self._send_json(200, result)

    # 返回JSON响应
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# 提供合成HTTP服务
class SynthesisHTTPServer:
    # 初始化当前实例
    def __init__(self, port: int, bind: str = "127.0.0.1") -> None:
        self._port = int(port)
        self._bind = str(bind)
        self._server: ThreadingHTTPServer | None = None

    # 启动服务
    def start(self, service, loop: asyncio.AbstractEventLoop) -> None:
        SynthesisHandler.service = service
        SynthesisHandler.loop = loop
        self._server = ThreadingHTTPServer((self._bind, self._port), SynthesisHandler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    # 停止服务
    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
