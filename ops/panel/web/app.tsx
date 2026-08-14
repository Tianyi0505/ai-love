const TOKEN_KEY = "ailove_panel_token";

interface ApiErrorBody {
  error?: string;
}

interface LoginResponse {
  ok: boolean;
  token: string;
  username: string;
  db: boolean;
}

interface LinksResponse {
  nacos_url: string;
  k3s_url: string;
}

interface RunRecord {
  run_id: string;
  ai_id: string;
  account_id: string;
  conversation_id: string;
  platform: string;
  chat_type: string;
  chat_id: string;
  sender_person_id: string;
  source: string;
  message_id: string;
  reply_to_message_id: string;
  status: string;
  outcome: string;
  tool_rounds: number;
  response_text: string;
  started_at: string;
  finished_at: string;
}

interface StepRecord {
  step_id?: string;
  step_index: number;
  step_type: string;
  status: string;
  content: unknown;
  duration_ms: number;
  error: string;
  occurred_at: string;
}

interface RunsResponse {
  runs: RunRecord[];
  db: boolean;
  error?: string;
}

interface ReplayResponse {
  run: RunRecord | null;
  steps: StepRecord[];
  db: boolean;
  error?: string;
}

class UnauthorizedError extends Error {}

async function request<T>(path: string, options: RequestInit = {}, keepToken = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(path, { ...options, headers });
  const data = (await resp.json().catch(() => ({}))) as T & ApiErrorBody;
  if (resp.status === 401 && !keepToken) {
    localStorage.removeItem(TOKEN_KEY);
    throw new UnauthorizedError(data.error || "未登录或会话已过期");
  }
  if (!resp.ok) throw new Error(data.error || "请求失败");
  return data;
}

function formatTime(value: string): string {
  if (!value) return "-";
  try {
    const date = new Date(value.replace(" ", "T"));
    if (isNaN(date.getTime())) return value.slice(0, 19);
    return date.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}

function shortId(value: string): string {
  return value.slice(0, 8);
}

const OUTCOME_BADGES: Record<string, [string, string]> = {
  sent: ["green", "已回复"],
  send_failed: ["red", "发送失败"],
  failed: ["red", "执行失败"],
  policy_no_response: ["gray", "策略不回复"],
  group_turn_busy: ["gray", "群回合占用"],
  empty_plan: ["gray", "空计划"],
  no_response: ["gray", "未回复"],
};

const STEP_LABELS: Record<string, string> = {
  context: "上下文",
  tool: "工具",
  final: "生成",
  send: "发送",
};

function LoginView({ onLogin }: { onLogin: (data: LoginResponse) => void }) {
  const [username, setUsername] = React.useState("ai-love");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    request<LoginResponse>("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    })
      .then(onLogin)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>AI-Love 运维面板</h1>
        <label>账号</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        <label>密码</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
        <div className="hint">默认账号密码均为 ai-love，登录后可在设置中修改</div>
        {error ? <div className="error">{error}</div> : null}
      </form>
    </div>
  );
}

interface MainViewProps {
  username: string;
  db: boolean;
  onLogout: () => void;
}

function MainView({ username, db, onLogout }: MainViewProps) {
  const [tab, setTab] = React.useState<"runs" | "settings">("runs");
  const [links, setLinks] = React.useState<LinksResponse>({ nacos_url: "", k3s_url: "" });

  React.useEffect(() => {
    request<LinksResponse>("/api/links").then(setLinks).catch(() => undefined);
  }, []);

  return (
    <div>
      <div className="topbar">
        <div className="title">AI-Love 运维面板</div>
        <a className="link" href={links.nacos_url || "#"} target="_blank" rel="noreferrer">
          Nacos
        </a>
        <a className="link" href={links.k3s_url || "#"} target="_blank" rel="noreferrer">
          K3s
        </a>
        <div className="spacer" />
        <div className="user">{username}</div>
        <button className="ghost" onClick={onLogout}>
          退出
        </button>
      </div>
      <div className="tabs">
        <button className={tab === "runs" ? "active" : ""} onClick={() => setTab("runs")}>
          运行追溯
        </button>
        <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
          设置
        </button>
      </div>
      <div className="page">
        {db ? null : (
          <div className="banner">未连接数据库，运行追溯数据暂不可用（凭据修改也不会持久化）</div>
        )}
        {tab === "runs" ? <RunsView /> : <SettingsView onLogout={onLogout} />}
      </div>
    </div>
  );
}

function RunsView() {
  const [aiId, setAiId] = React.useState("");
  const [convId, setConvId] = React.useState("");
  const [source, setSource] = React.useState("");
  const [limit, setLimit] = React.useState("50");
  const [runs, setRuns] = React.useState<RunRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [selected, setSelected] = React.useState<string | null>(null);

  function load(nextOffset: number, append: boolean) {
    setLoading(true);
    setError("");
    const query = `limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(String(nextOffset))}` +
      `&ai_id=${encodeURIComponent(aiId)}&conversation_id=${encodeURIComponent(convId)}` +
      `&source=${encodeURIComponent(source)}`;
    request<RunsResponse>(`/api/runs?${query}`)
      .then((data) => {
        setRuns(append ? [...runs, ...data.runs] : data.runs);
        setOffset(nextOffset);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  React.useEffect(() => {
    load(0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (selected) {
    return <RunDetailView runId={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <div>
      <div className="filters">
        <input placeholder="ai_id（可选）" value={aiId} onChange={(e) => setAiId(e.target.value)} />
        <input placeholder="conversation_id（可选）" value={convId} onChange={(e) => setConvId(e.target.value)} />
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">全部来源</option>
          <option value="social">social</option>
          <option value="proactive">proactive</option>
          <option value="compensate">compensate</option>
        </select>
        <select value={limit} onChange={(e) => setLimit(e.target.value)}>
          <option value="20">20 条</option>
          <option value="50">50 条</option>
          <option value="100">100 条</option>
        </select>
        <button onClick={() => load(0, false)}>查询</button>
        <button
          className="ghost"
          disabled={runs.length === 0}
          onClick={() => load(offset + parseInt(limit, 10), true)}
        >
          加载更多
        </button>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {loading && runs.length === 0 ? <div className="empty">加载中…</div> : null}
      {!loading && runs.length === 0 ? <div className="empty">暂无执行记录</div> : null}
      {runs.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>run_id</th>
              <th>AI</th>
              <th>类型</th>
              <th>来源</th>
              <th>结果</th>
              <th>工具轮</th>
              <th>回复摘要</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const badge = OUTCOME_BADGES[run.outcome] || ["gray", run.outcome || "-"];
              return (
                <tr key={run.run_id} onClick={() => setSelected(run.run_id)}>
                  <td className="mono">{formatTime(run.started_at)}</td>
                  <td className="mono" title={run.run_id}>
                    {shortId(run.run_id)}
                  </td>
                  <td>{run.ai_id || "-"}</td>
                  <td>{run.chat_type || "-"}</td>
                  <td>{run.source || "-"}</td>
                  <td>
                    <span className={`badge ${badge[0]}`}>{badge[1]}</span>
                  </td>
                  <td>{run.tool_rounds}</td>
                  <td className="wrap">{run.response_text || "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

function RunDetailView({ runId, onBack }: { runId: string; onBack: () => void }) {
  const [data, setData] = React.useState<ReplayResponse | null>(null);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    request<ReplayResponse>(`/api/runs/${encodeURIComponent(runId)}`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [runId]);

  if (error) {
    return (
      <div>
        <button className="ghost" onClick={onBack}>
          ← 返回
        </button>
        <div className="error">{error}</div>
      </div>
    );
  }
  if (!data) return <div className="empty">加载中…</div>;

  const run = data.run;
  if (!run) {
    return (
      <div>
        <button className="ghost" onClick={onBack}>
          ← 返回
        </button>
        <div className="empty">执行记录不存在</div>
      </div>
    );
  }
  const badge = OUTCOME_BADGES[run.outcome] || ["gray", run.outcome || "-"];

  return (
    <div>
      <div className="filters">
        <button className="ghost" onClick={onBack}>
          ← 返回列表
        </button>
      </div>
      <div className="kv">
        {kv("run_id", run.run_id)}
        {kv("AI", run.ai_id)}
        {kv("会话", shortId(run.conversation_id))}
        {kv("类型", run.chat_type)}
        {kv("聊天 ID", run.chat_id)}
        {kv("来源", run.source)}
        {kv("消息 ID", run.message_id)}
        {kv("引用消息", run.reply_to_message_id)}
        {kv("开始", formatTime(run.started_at))}
        {kv("结束", formatTime(run.finished_at))}
        {kv("结果", <span className={`badge ${badge[0]}`}>{badge[1]}</span>)}
        {kv("工具轮", String(run.tool_rounds))}
      </div>
      {run.response_text ? <div className="kv">{kv("回复内容", run.response_text)}</div> : null}
      <h3>执行步骤</h3>
      {data.steps.length === 0 ? <div className="empty">暂无步骤记录</div> : null}
      {data.steps.map((step) => {
        const label = STEP_LABELS[step.step_type] || step.step_type;
        let content: unknown = step.content;
        if (typeof content === "string") {
          try {
            content = JSON.parse(content);
          } catch {
            // keep raw string
          }
        }
        const hasContent =
          content !== null &&
          typeof content === "object" &&
          Object.keys(content as Record<string, unknown>).length > 0;
        return (
          <div className="step" key={step.step_id || `${step.step_index}-${step.occurred_at}`}>
            <div className="step-head">
              <span className={`badge ${step.status === "ok" ? "green" : "red"}`}>{String(step.step_index)}</span>
              <span className="type">{label}</span>
              <span className="meta">
                {step.status} · {step.duration_ms}ms · {formatTime(step.occurred_at)}
              </span>
              {step.error ? (
                <span className="meta" style={{ color: "var(--red)" }}>
                  {step.error}
                </span>
              ) : null}
            </div>
            {hasContent ? (
              <details>
                <summary>查看内容</summary>
                <pre>{JSON.stringify(content, null, 2)}</pre>
              </details>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function kv(key: string, value: React.ReactNode): React.ReactElement {
  return (
    <div>
      <div className="k">{key}</div>
      <div className="v">{value}</div>
    </div>
  );
}

function SettingsView({ onLogout }: { onLogout: () => void }) {
  const [current, setCurrent] = React.useState("");
  const [newUser, setNewUser] = React.useState("");
  const [newPass, setNewPass] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (!newUser && !newPass) {
      setError("新账号和新密码至少填写一项");
      return;
    }
    request<{ ok: boolean; message?: string }>("/api/credentials", {
      method: "POST",
      body: JSON.stringify({ current_password: current, username: newUser, password: newPass }),
    })
      .then((data) => {
        setMessage(data.message || "已更新");
        window.setTimeout(onLogout, 1200);
      })
      .catch((err: Error) => setError(err.message));
  }

  return (
    <form className="settings-card" onSubmit={submit}>
      <h3 style={{ marginTop: 0 }}>修改账号密码</h3>
      <label>当前密码</label>
      <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      <label>新账号（留空不修改）</label>
      <input value={newUser} onChange={(e) => setNewUser(e.target.value)} />
      <label>新密码（留空不修改）</label>
      <input type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} />
      <button type="submit">保存</button>
      {message ? <div className="ok">{message}</div> : null}
      {error ? <div className="error">{error}</div> : null}
    </form>
  );
}

function App() {
  const [token, setToken] = React.useState(localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = React.useState("");
  const [db, setDb] = React.useState(true);

  function onLogin(data: LoginResponse) {
    localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setUsername(data.username);
    setDb(data.db);
  }

  function onLogout() {
    void request<unknown>("/api/logout", { method: "POST" }, true).catch(() => undefined);
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }

  return token ? (
    <MainView username={username} db={db} onLogout={onLogout} />
  ) : (
    <LoginView onLogin={onLogin} />
  );
}

interface ReactRoot {
  render(element: React.ReactElement): void;
}

declare const ReactDOM: {
  createRoot(container: Element): ReactRoot;
};

const root = ReactDOM.createRoot(document.getElementById("root")!);
root.render(<App />);
