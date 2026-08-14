"use strict";
const TOKEN_KEY = "ailove_panel_token";
class UnauthorizedError extends Error {
}
async function request(path, options = {}, keepToken = false) {
    const headers = Object.assign({ "Content-Type": "application/json" }, options.headers);
    const token = localStorage.getItem(TOKEN_KEY);
    if (token)
        headers["Authorization"] = `Bearer ${token}`;
    const resp = await fetch(path, Object.assign(Object.assign({}, options), { headers }));
    const data = (await resp.json().catch(() => ({})));
    if (resp.status === 401 && !keepToken) {
        localStorage.removeItem(TOKEN_KEY);
        throw new UnauthorizedError(data.error || "未登录或会话已过期");
    }
    if (!resp.ok)
        throw new Error(data.error || "请求失败");
    return data;
}
function formatTime(value) {
    if (!value)
        return "-";
    try {
        const date = new Date(value.replace(" ", "T"));
        if (isNaN(date.getTime()))
            return value.slice(0, 19);
        return date.toLocaleString("zh-CN", { hour12: false });
    }
    catch (_a) {
        return value;
    }
}
function shortId(value) {
    return value.slice(0, 8);
}
const OUTCOME_BADGES = {
    sent: ["green", "已回复"],
    send_failed: ["red", "发送失败"],
    failed: ["red", "执行失败"],
    policy_no_response: ["gray", "策略不回复"],
    group_turn_busy: ["gray", "群回合占用"],
    empty_plan: ["gray", "空计划"],
    no_response: ["gray", "未回复"],
};
const STEP_LABELS = {
    context: "上下文",
    tool: "工具",
    final: "生成",
    send: "发送",
};
function LoginView({ onLogin }) {
    const [username, setUsername] = React.useState("ai-love");
    const [password, setPassword] = React.useState("");
    const [error, setError] = React.useState("");
    const [busy, setBusy] = React.useState(false);
    function submit(event) {
        event.preventDefault();
        setError("");
        setBusy(true);
        request("/api/login", {
            method: "POST",
            body: JSON.stringify({ username, password }),
        })
            .then(onLogin)
            .catch((err) => setError(err.message))
            .finally(() => setBusy(false));
    }
    return (React.createElement("div", { className: "login-wrap" },
        React.createElement("form", { className: "login-card", onSubmit: submit },
            React.createElement("h1", null, "AI-Love \u8FD0\u7EF4\u9762\u677F"),
            React.createElement("label", null, "\u8D26\u53F7"),
            React.createElement("input", { value: username, onChange: (e) => setUsername(e.target.value), autoFocus: true }),
            React.createElement("label", null, "\u5BC6\u7801"),
            React.createElement("input", { type: "password", value: password, onChange: (e) => setPassword(e.target.value) }),
            React.createElement("button", { type: "submit", disabled: busy }, busy ? "登录中…" : "登录"),
            React.createElement("div", { className: "hint" }, "\u9ED8\u8BA4\u8D26\u53F7\u5BC6\u7801\u5747\u4E3A ai-love\uFF0C\u767B\u5F55\u540E\u53EF\u5728\u8BBE\u7F6E\u4E2D\u4FEE\u6539"),
            error ? React.createElement("div", { className: "error" }, error) : null)));
}
function MainView({ username, db, onLogout }) {
    const [tab, setTab] = React.useState("history");
    const [links, setLinks] = React.useState({ nacos_url: "", k3s_url: "" });
    React.useEffect(() => {
        request("/api/links").then(setLinks).catch(() => undefined);
    }, []);
    return (React.createElement("div", null,
        React.createElement("div", { className: "topbar" },
            React.createElement("div", { className: "title" }, "AI-Love \u8FD0\u7EF4\u9762\u677F"),
            React.createElement("a", { className: "link", href: links.nacos_url || "#", target: "_blank", rel: "noreferrer" }, "Nacos"),
            React.createElement("a", { className: "link", href: links.k3s_url || "#", target: "_blank", rel: "noreferrer" }, "K3s"),
            React.createElement("div", { className: "spacer" }),
            React.createElement("div", { className: "user" }, username),
            React.createElement("button", { className: "ghost", onClick: onLogout }, "\u9000\u51FA")),
        React.createElement("div", { className: "tabs" },
            React.createElement("button", { className: tab === "history" ? "active" : "", onClick: () => setTab("history") }, "\u5386\u53F2\u6D88\u606F"),
            React.createElement("button", { className: tab === "runs" ? "active" : "", onClick: () => setTab("runs") }, "\u8FD0\u884C\u8FFD\u6EAF"),
            React.createElement("button", { className: tab === "settings" ? "active" : "", onClick: () => setTab("settings") }, "\u8BBE\u7F6E")),
        React.createElement("div", { className: "page" },
            db ? null : (React.createElement("div", { className: "banner" }, "\u672A\u8FDE\u63A5\u6570\u636E\u5E93\uFF0C\u5386\u53F2\u6570\u636E\u6682\u4E0D\u53EF\u7528\uFF08\u51ED\u636E\u4FEE\u6539\u4E5F\u4E0D\u4F1A\u6301\u4E45\u5316\uFF09")),
            tab === "history" ? (React.createElement(HistoryView, null)) : tab === "runs" ? (React.createElement(RunsView, null)) : (React.createElement(SettingsView, { onLogout: onLogout })))));
}
function messageText(content) {
    let parsed = content;
    if (typeof parsed === "string") {
        try {
            parsed = JSON.parse(parsed);
        }
        catch (_a) {
            return parsed;
        }
    }
    if (!parsed || typeof parsed !== "object")
        return "";
    const item = parsed;
    const text = typeof item.text === "string" ? item.text : "";
    if (text)
        return text;
    const type = typeof item.type === "string" ? item.type : "";
    if (type === "image")
        return "[图片]";
    if (type === "voice")
        return "[语音]";
    if (type === "sticker")
        return "[表情]";
    return JSON.stringify(item).slice(0, 120);
}
function HistoryView() {
    const [conversations, setConversations] = React.useState([]);
    const [persons, setPersons] = React.useState([]);
    const [convId, setConvId] = React.useState("");
    const [personId, setPersonId] = React.useState("");
    const [role, setRole] = React.useState("");
    const [keyword, setKeyword] = React.useState("");
    const [since, setSince] = React.useState("");
    const [until, setUntil] = React.useState("");
    const [limit, setLimit] = React.useState("50");
    const [messages, setMessages] = React.useState([]);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState("");
    const [offset, setOffset] = React.useState(0);
    React.useEffect(() => {
        request("/api/conversations")
            .then((data) => setConversations(data.conversations))
            .catch(() => undefined);
        request("/api/persons")
            .then((data) => setPersons(data.persons))
            .catch(() => undefined);
    }, []);
    function load(nextOffset, append) {
        setLoading(true);
        setError("");
        const query = "limit=" + encodeURIComponent(limit) + "&offset=" + encodeURIComponent(String(nextOffset)) +
            "&conversation_id=" + encodeURIComponent(convId) + "&person_id=" + encodeURIComponent(personId) +
            "&role=" + encodeURIComponent(role) + "&keyword=" + encodeURIComponent(keyword) +
            "&since=" + encodeURIComponent(since) + "&until=" + encodeURIComponent(until);
        request("/api/messages?" + query)
            .then((data) => {
            setMessages(append ? messages.concat(data.messages) : data.messages);
            setOffset(nextOffset);
        })
            .catch((err) => setError(err.message))
            .finally(() => setLoading(false));
    }
    React.useEffect(() => {
        load(0, false);
    }, []);
    return (React.createElement("div", null,
        React.createElement("div", { className: "filters" },
            React.createElement("select", { value: convId, onChange: (e) => setConvId(e.target.value) },
                React.createElement("option", { value: "" }, "\u5168\u90E8\u4F1A\u8BDD"),
                conversations.map((c) => (React.createElement("option", { key: c.conversation_id, value: c.conversation_id, title: c.summary },
                    c.chat_type,
                    " \u00B7 ",
                    c.platform_chat_id,
                    "\uFF08",
                    c.message_count,
                    " \u6761\uFF09")))),
            React.createElement("select", { value: personId, onChange: (e) => setPersonId(e.target.value) },
                React.createElement("option", { value: "" }, "\u5168\u90E8\u4EBA\u7269"),
                persons.map((p) => (React.createElement("option", { key: p.person_id, value: p.person_id },
                    p.display_name,
                    "\uFF08",
                    p.message_count,
                    " \u6761\uFF09")))),
            React.createElement("select", { value: role, onChange: (e) => setRole(e.target.value) },
                React.createElement("option", { value: "" }, "\u5168\u90E8\u89D2\u8272"),
                React.createElement("option", { value: "user" }, "\u7528\u6237"),
                React.createElement("option", { value: "assistant" }, "AI")),
            React.createElement("input", { placeholder: "\u5173\u952E\u8BCD", value: keyword, onChange: (e) => setKeyword(e.target.value) }),
            React.createElement("input", { type: "datetime-local", title: "\u5F00\u59CB\u65F6\u95F4", value: since, onChange: (e) => setSince(e.target.value) }),
            React.createElement("input", { type: "datetime-local", title: "\u7ED3\u675F\u65F6\u95F4", value: until, onChange: (e) => setUntil(e.target.value) }),
            React.createElement("select", { value: limit, onChange: (e) => setLimit(e.target.value) },
                React.createElement("option", { value: "50" }, "50 \u6761"),
                React.createElement("option", { value: "100" }, "100 \u6761"),
                React.createElement("option", { value: "200" }, "200 \u6761")),
            React.createElement("button", { onClick: () => load(0, false) }, "\u67E5\u8BE2"),
            React.createElement("button", { className: "ghost", disabled: messages.length === 0, onClick: () => load(offset + parseInt(limit, 10), true) }, "\u52A0\u8F7D\u66F4\u591A")),
        error ? React.createElement("div", { className: "error" }, error) : null,
        loading && messages.length === 0 ? React.createElement("div", { className: "empty" }, "\u52A0\u8F7D\u4E2D\u2026") : null,
        !loading && messages.length === 0 ? React.createElement("div", { className: "empty" }, "\u6CA1\u6709\u5339\u914D\u7684\u6D88\u606F") : null,
        messages.length > 0 ? (React.createElement("table", null,
            React.createElement("thead", null,
                React.createElement("tr", null,
                    React.createElement("th", null, "\u65F6\u95F4"),
                    React.createElement("th", null, "\u4F1A\u8BDD"),
                    React.createElement("th", null, "\u89D2\u8272"),
                    React.createElement("th", null, "\u53D1\u9001\u8005"),
                    React.createElement("th", null, "\u5185\u5BB9"))),
            React.createElement("tbody", null, messages.map((msg) => (React.createElement("tr", { key: msg.message_id },
                React.createElement("td", { className: "mono" }, formatTime(msg.occurred_at)),
                React.createElement("td", { className: "mono", title: msg.conversation_id },
                    msg.chat_type,
                    " \u00B7 ",
                    msg.platform_chat_id),
                React.createElement("td", null,
                    React.createElement("span", { className: "badge " + (msg.role === "assistant" ? "green" : "gray") }, msg.role === "assistant" ? "AI" : "用户")),
                React.createElement("td", null, msg.display_name || msg.person_id || "-"),
                React.createElement("td", { className: "wrap" },
                    messageText(msg.content),
                    React.createElement("details", null,
                        React.createElement("summary", null, "\u8BE6\u60C5"),
                        React.createElement("pre", null, JSON.stringify(msg.content, null, 2)))))))))) : null));
}
function RunsView() {
    const [aiId, setAiId] = React.useState("");
    const [convId, setConvId] = React.useState("");
    const [source, setSource] = React.useState("");
    const [limit, setLimit] = React.useState("50");
    const [runs, setRuns] = React.useState([]);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState("");
    const [offset, setOffset] = React.useState(0);
    const [selected, setSelected] = React.useState(null);
    function load(nextOffset, append) {
        setLoading(true);
        setError("");
        const query = `limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(String(nextOffset))}` +
            `&ai_id=${encodeURIComponent(aiId)}&conversation_id=${encodeURIComponent(convId)}` +
            `&source=${encodeURIComponent(source)}`;
        request(`/api/runs?${query}`)
            .then((data) => {
            setRuns(append ? [...runs, ...data.runs] : data.runs);
            setOffset(nextOffset);
        })
            .catch((err) => setError(err.message))
            .finally(() => setLoading(false));
    }
    React.useEffect(() => {
        load(0, false);
    }, []);
    if (selected) {
        return React.createElement(RunDetailView, { runId: selected, onBack: () => setSelected(null) });
    }
    return (React.createElement("div", null,
        React.createElement("div", { className: "filters" },
            React.createElement("input", { placeholder: "ai_id\uFF08\u53EF\u9009\uFF09", value: aiId, onChange: (e) => setAiId(e.target.value) }),
            React.createElement("input", { placeholder: "conversation_id\uFF08\u53EF\u9009\uFF09", value: convId, onChange: (e) => setConvId(e.target.value) }),
            React.createElement("select", { value: source, onChange: (e) => setSource(e.target.value) },
                React.createElement("option", { value: "" }, "\u5168\u90E8\u6765\u6E90"),
                React.createElement("option", { value: "social" }, "social"),
                React.createElement("option", { value: "proactive" }, "proactive"),
                React.createElement("option", { value: "compensate" }, "compensate")),
            React.createElement("select", { value: limit, onChange: (e) => setLimit(e.target.value) },
                React.createElement("option", { value: "20" }, "20 \u6761"),
                React.createElement("option", { value: "50" }, "50 \u6761"),
                React.createElement("option", { value: "100" }, "100 \u6761")),
            React.createElement("button", { onClick: () => load(0, false) }, "\u67E5\u8BE2"),
            React.createElement("button", { className: "ghost", disabled: runs.length === 0, onClick: () => load(offset + parseInt(limit, 10), true) }, "\u52A0\u8F7D\u66F4\u591A")),
        error ? React.createElement("div", { className: "error" }, error) : null,
        loading && runs.length === 0 ? React.createElement("div", { className: "empty" }, "\u52A0\u8F7D\u4E2D\u2026") : null,
        !loading && runs.length === 0 ? React.createElement("div", { className: "empty" }, "\u6682\u65E0\u6267\u884C\u8BB0\u5F55") : null,
        runs.length > 0 ? (React.createElement("table", null,
            React.createElement("thead", null,
                React.createElement("tr", null,
                    React.createElement("th", null, "\u65F6\u95F4"),
                    React.createElement("th", null, "run_id"),
                    React.createElement("th", null, "AI"),
                    React.createElement("th", null, "\u7C7B\u578B"),
                    React.createElement("th", null, "\u6765\u6E90"),
                    React.createElement("th", null, "\u7ED3\u679C"),
                    React.createElement("th", null, "\u5DE5\u5177\u8F6E"),
                    React.createElement("th", null, "\u56DE\u590D\u6458\u8981"))),
            React.createElement("tbody", null, runs.map((run) => {
                const badge = OUTCOME_BADGES[run.outcome] || ["gray", run.outcome || "-"];
                return (React.createElement("tr", { key: run.run_id, onClick: () => setSelected(run.run_id) },
                    React.createElement("td", { className: "mono" }, formatTime(run.started_at)),
                    React.createElement("td", { className: "mono", title: run.run_id }, shortId(run.run_id)),
                    React.createElement("td", null, run.ai_id || "-"),
                    React.createElement("td", null, run.chat_type || "-"),
                    React.createElement("td", null, run.source || "-"),
                    React.createElement("td", null,
                        React.createElement("span", { className: `badge ${badge[0]}` }, badge[1])),
                    React.createElement("td", null, run.tool_rounds),
                    React.createElement("td", { className: "wrap" }, run.response_text || "-")));
            })))) : null));
}
function RunDetailView({ runId, onBack }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState("");
    React.useEffect(() => {
        request(`/api/runs/${encodeURIComponent(runId)}`)
            .then(setData)
            .catch((err) => setError(err.message));
    }, [runId]);
    if (error) {
        return (React.createElement("div", null,
            React.createElement("button", { className: "ghost", onClick: onBack }, "\u2190 \u8FD4\u56DE"),
            React.createElement("div", { className: "error" }, error)));
    }
    if (!data)
        return React.createElement("div", { className: "empty" }, "\u52A0\u8F7D\u4E2D\u2026");
    const run = data.run;
    if (!run) {
        return (React.createElement("div", null,
            React.createElement("button", { className: "ghost", onClick: onBack }, "\u2190 \u8FD4\u56DE"),
            React.createElement("div", { className: "empty" }, "\u6267\u884C\u8BB0\u5F55\u4E0D\u5B58\u5728")));
    }
    const badge = OUTCOME_BADGES[run.outcome] || ["gray", run.outcome || "-"];
    return (React.createElement("div", null,
        React.createElement("div", { className: "filters" },
            React.createElement("button", { className: "ghost", onClick: onBack }, "\u2190 \u8FD4\u56DE\u5217\u8868")),
        React.createElement("div", { className: "kv" },
            kv("run_id", run.run_id),
            kv("AI", run.ai_id),
            kv("会话", shortId(run.conversation_id)),
            kv("类型", run.chat_type),
            kv("聊天 ID", run.chat_id),
            kv("来源", run.source),
            kv("消息 ID", run.message_id),
            kv("引用消息", run.reply_to_message_id),
            kv("开始", formatTime(run.started_at)),
            kv("结束", formatTime(run.finished_at)),
            kv("结果", React.createElement("span", { className: `badge ${badge[0]}` }, badge[1])),
            kv("工具轮", String(run.tool_rounds))),
        run.response_text ? React.createElement("div", { className: "kv" }, kv("回复内容", run.response_text)) : null,
        React.createElement("h3", null, "\u6267\u884C\u6B65\u9AA4"),
        data.steps.length === 0 ? React.createElement("div", { className: "empty" }, "\u6682\u65E0\u6B65\u9AA4\u8BB0\u5F55") : null,
        data.steps.map((step) => {
            const label = STEP_LABELS[step.step_type] || step.step_type;
            let content = step.content;
            if (typeof content === "string") {
                try {
                    content = JSON.parse(content);
                }
                catch (_a) {
                }
            }
            const hasContent = content !== null &&
                typeof content === "object" &&
                Object.keys(content).length > 0;
            return (React.createElement("div", { className: "step", key: step.step_id || `${step.step_index}-${step.occurred_at}` },
                React.createElement("div", { className: "step-head" },
                    React.createElement("span", { className: `badge ${step.status === "ok" ? "green" : "red"}` }, String(step.step_index)),
                    React.createElement("span", { className: "type" }, label),
                    React.createElement("span", { className: "meta" },
                        step.status,
                        " \u00B7 ",
                        step.duration_ms,
                        "ms \u00B7 ",
                        formatTime(step.occurred_at)),
                    step.error ? (React.createElement("span", { className: "meta", style: { color: "var(--red)" } }, step.error)) : null),
                hasContent ? (React.createElement("details", null,
                    React.createElement("summary", null, "\u67E5\u770B\u5185\u5BB9"),
                    React.createElement("pre", null, JSON.stringify(content, null, 2)))) : null));
        })));
}
function kv(key, value) {
    return (React.createElement("div", null,
        React.createElement("div", { className: "k" }, key),
        React.createElement("div", { className: "v" }, value)));
}
function SettingsView({ onLogout }) {
    const [current, setCurrent] = React.useState("");
    const [newUser, setNewUser] = React.useState("");
    const [newPass, setNewPass] = React.useState("");
    const [message, setMessage] = React.useState("");
    const [error, setError] = React.useState("");
    function submit(event) {
        event.preventDefault();
        setError("");
        setMessage("");
        if (!newUser && !newPass) {
            setError("新账号和新密码至少填写一项");
            return;
        }
        request("/api/credentials", {
            method: "POST",
            body: JSON.stringify({ current_password: current, username: newUser, password: newPass }),
        })
            .then((data) => {
            setMessage(data.message || "已更新");
            window.setTimeout(onLogout, 1200);
        })
            .catch((err) => setError(err.message));
    }
    return (React.createElement("form", { className: "settings-card", onSubmit: submit },
        React.createElement("h3", { style: { marginTop: 0 } }, "\u4FEE\u6539\u8D26\u53F7\u5BC6\u7801"),
        React.createElement("label", null, "\u5F53\u524D\u5BC6\u7801"),
        React.createElement("input", { type: "password", value: current, onChange: (e) => setCurrent(e.target.value) }),
        React.createElement("label", null, "\u65B0\u8D26\u53F7\uFF08\u7559\u7A7A\u4E0D\u4FEE\u6539\uFF09"),
        React.createElement("input", { value: newUser, onChange: (e) => setNewUser(e.target.value) }),
        React.createElement("label", null, "\u65B0\u5BC6\u7801\uFF08\u7559\u7A7A\u4E0D\u4FEE\u6539\uFF09"),
        React.createElement("input", { type: "password", value: newPass, onChange: (e) => setNewPass(e.target.value) }),
        React.createElement("button", { type: "submit" }, "\u4FDD\u5B58"),
        message ? React.createElement("div", { className: "ok" }, message) : null,
        error ? React.createElement("div", { className: "error" }, error) : null));
}
function App() {
    const [token, setToken] = React.useState(localStorage.getItem(TOKEN_KEY));
    const [username, setUsername] = React.useState("");
    const [db, setDb] = React.useState(true);
    function onLogin(data) {
        localStorage.setItem(TOKEN_KEY, data.token);
        setToken(data.token);
        setUsername(data.username);
        setDb(data.db);
    }
    function onLogout() {
        void request("/api/logout", { method: "POST" }, true).catch(() => undefined);
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
    }
    return token ? (React.createElement(MainView, { username: username, db: db, onLogout: onLogout })) : (React.createElement(LoginView, { onLogin: onLogin }));
}
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(React.createElement(App, null));
