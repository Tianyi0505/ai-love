(function () {
  "use strict";

  var h = React.createElement;
  var TOKEN_KEY = "ailove_panel_token";

  function request(path, options) {
    options = options || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    var token = localStorage.getItem(TOKEN_KEY);
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetch(path, Object.assign({}, options, { headers: headers })).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (data) {
        if (resp.status === 401 && !options.keepToken) {
          localStorage.removeItem(TOKEN_KEY);
          var err = new Error(data.error || "未登录或会话已过期");
          err.unauthorized = true;
          throw err;
        }
        if (!resp.ok) throw new Error(data.error || "请求失败");
        return data;
      });
    });
  }

  function formatTime(value) {
    if (!value) return "-";
    try {
      var date = new Date(String(value).replace(" ", "T"));
      if (isNaN(date.getTime())) return String(value).slice(0, 19);
      return date.toLocaleString("zh-CN", { hour12: false });
    } catch (e) {
      return String(value);
    }
  }

  function shortId(value) {
    return String(value || "").slice(0, 8);
  }

  var OUTCOME_BADGE = {
    sent: ["green", "已回复"],
    send_failed: ["red", "发送失败"],
    failed: ["red", "执行失败"],
    policy_no_response: ["gray", "策略不回复"],
    group_turn_busy: ["gray", "群回合占用"],
    empty_plan: ["gray", "空计划"],
    no_response: ["gray", "未回复"]
  };

  var STEP_LABEL = { context: "上下文", tool: "工具", final: "生成", send: "发送" };

  function LoginView(props) {
    var _useState = React.useState("ai-love"), username = _useState[0], setUsername = _useState[1];
    var _useState2 = React.useState(""), password = _useState2[0], setPassword = _useState2[1];
    var _useState3 = React.useState(""), error = _useState3[0], setError = _useState3[1];
    var _useState4 = React.useState(false), busy = _useState4[0], setBusy = _useState4[1];

    function submit(event) {
      event.preventDefault();
      setError("");
      setBusy(true);
      request("/api/login", {
        method: "POST",
        body: JSON.stringify({ username: username, password: password })
      }).then(function (data) {
        props.onLogin(data);
      }).catch(function (err) {
        setError(err.message);
      }).finally(function () {
        setBusy(false);
      });
    }

    return h("div", { className: "login-wrap" },
      h("form", { className: "login-card", onSubmit: submit },
        h("h1", null, "AI-Love 运维面板"),
        h("label", null, "账号"),
        h("input", { value: username, onChange: function (e) { setUsername(e.target.value); }, autoFocus: true }),
        h("label", null, "密码"),
        h("input", { type: "password", value: password, onChange: function (e) { setPassword(e.target.value); } }),
        h("button", { type: "submit", disabled: busy }, busy ? "登录中…" : "登录"),
        h("div", { className: "hint" }, "默认账号密码均为 ai-love，登录后可在设置中修改"),
        error ? h("div", { className: "error" }, error) : null
      )
    );
  }

  function MainView(props) {
    var _useState = React.useState("runs"), tab = _useState[0], setTab = _useState[1];
    var _useState2 = React.useState({}), links = _useState2[0], setLinks = _useState2[1];

    React.useEffect(function () {
      request("/api/links").then(setLinks).catch(function () {});
    }, []);

    return h("div", null,
      h("div", { className: "topbar" },
        h("div", { className: "title" }, "AI-Love 运维面板"),
        h("a", { className: "link", href: links.nacos_url || "#", target: "_blank", rel: "noreferrer" }, "Nacos"),
        h("a", { className: "link", href: links.k3s_url || "#", target: "_blank", rel: "noreferrer" }, "K3s"),
        h("div", { className: "spacer" }),
        h("div", { className: "user" }, props.username),
        h("button", { className: "ghost", onClick: props.onLogout }, "退出")
      ),
      h("div", { className: "tabs" },
        h("button", { className: tab === "runs" ? "active" : "", onClick: function () { setTab("runs"); } }, "运行追溯"),
        h("button", { className: tab === "settings" ? "active" : "", onClick: function () { setTab("settings"); } }, "设置")
      ),
      h("div", { className: "page" },
        props.db ? null : h("div", { className: "banner" }, "未连接数据库，运行追溯数据暂不可用（凭据修改也不会持久化）"),
        tab === "runs" ? h(RunsView, null) : h(SettingsView, { onLogout: props.onLogout })
      )
    );
  }

  function RunsView() {
    var _useState = React.useState(""), aiId = _useState[0], setAiId = _useState[1];
    var _useState2 = React.useState(""), convId = _useState2[0], setConvId = _useState2[1];
    var _useState3 = React.useState(""), source = _useState3[0], setSource = _useState3[1];
    var _useState4 = React.useState("50"), limit = _useState4[0], setLimit = _useState4[1];
    var _useState5 = React.useState([]), runs = _useState5[0], setRuns = _useState5[1];
    var _useState6 = React.useState(false), loading = _useState6[0], setLoading = _useState6[1];
    var _useState7 = React.useState(""), error = _useState7[0], setError = _useState7[1];
    var _useState8 = React.useState(0), offset = _useState8[0], setOffset = _useState8[1];
    var _useState9 = React.useState(null), selected = _useState9[0], setSelected = _useState9[1];

    function load(nextOffset, append) {
      setLoading(true);
      setError("");
      var query = "limit=" + encodeURIComponent(limit) + "&offset=" + encodeURIComponent(nextOffset) +
        "&ai_id=" + encodeURIComponent(aiId) + "&conversation_id=" + encodeURIComponent(convId) +
        "&source=" + encodeURIComponent(source);
      request("/api/runs?" + query).then(function (data) {
        setRuns(append ? runs.concat(data.runs) : data.runs);
        setOffset(nextOffset);
      }).catch(function (err) {
        setError(err.message);
      }).finally(function () {
        setLoading(false);
      });
    }

    React.useEffect(function () { load(0, false); }, []);

    if (selected) {
      return h(RunDetailView, { runId: selected, onBack: function () { setSelected(null); } });
    }

    return h("div", null,
      h("div", { className: "filters" },
        h("input", { placeholder: "ai_id（可选）", value: aiId, onChange: function (e) { setAiId(e.target.value); } }),
        h("input", { placeholder: "conversation_id（可选）", value: convId, onChange: function (e) { setConvId(e.target.value); } }),
        h("select", { value: source, onChange: function (e) { setSource(e.target.value); } },
          h("option", { value: "" }, "全部来源"),
          h("option", { value: "social" }, "social"),
          h("option", { value: "proactive" }, "proactive"),
          h("option", { value: "compensate" }, "compensate")
        ),
        h("select", { value: limit, onChange: function (e) { setLimit(e.target.value); } },
          h("option", { value: "20" }, "20 条"),
          h("option", { value: "50" }, "50 条"),
          h("option", { value: "100" }, "100 条")
        ),
        h("button", { onClick: function () { load(0, false); } }, "查询"),
        h("button", { className: "ghost", disabled: runs.length === 0, onClick: function () { load(offset + parseInt(limit, 10), true); } }, "加载更多")
      ),
      error ? h("div", { className: "error" }, error) : null,
      loading && runs.length === 0 ? h("div", { className: "empty" }, "加载中…") : null,
      !loading && runs.length === 0 ? h("div", { className: "empty" }, "暂无执行记录") : null,
      runs.length > 0 ? h("table", null,
        h("thead", null, h("tr", null,
          h("th", null, "时间"),
          h("th", null, "run_id"),
          h("th", null, "AI"),
          h("th", null, "类型"),
          h("th", null, "来源"),
          h("th", null, "结果"),
          h("th", null, "工具轮"),
          h("th", null, "回复摘要")
        )),
        h("tbody", null, runs.map(function (run) {
          var badge = OUTCOME_BADGE[run.outcome] || ["gray", run.outcome || "-"];
          return h("tr", { key: run.run_id, onClick: function () { setSelected(run.run_id); } },
            h("td", { className: "mono" }, formatTime(run.started_at)),
            h("td", { className: "mono", title: run.run_id }, shortId(run.run_id)),
            h("td", null, run.ai_id || "-"),
            h("td", null, run.chat_type || "-"),
            h("td", null, run.source || "-"),
            h("td", null, h("span", { className: "badge " + badge[0] }, badge[1])),
            h("td", null, run.tool_rounds),
            h("td", { className: "wrap" }, run.response_text || "-")
          );
        }))
      ) : null
    );
  }

  function RunDetailView(props) {
    var _useState = React.useState(null), data = _useState[0], setData = _useState[1];
    var _useState2 = React.useState(""), error = _useState2[0], setError = _useState2[1];

    React.useEffect(function () {
      request("/api/runs/" + encodeURIComponent(props.runId)).then(setData).catch(function (err) {
        setError(err.message);
      });
    }, [props.runId]);

    if (error) {
      return h("div", null, h("button", { className: "ghost", onClick: props.onBack }, "← 返回"), h("div", { className: "error" }, error));
    }
    if (!data) return h("div", { className: "empty" }, "加载中…");

    var run = data.run;
    if (!run) return h("div", null, h("button", { className: "ghost", onClick: props.onBack }, "← 返回"), h("div", { className: "empty" }, "执行记录不存在"));
    var badge = OUTCOME_BADGE[run.outcome] || ["gray", run.outcome || "-"];

    return h("div", null,
      h("div", { className: "filters" },
        h("button", { className: "ghost", onClick: props.onBack }, "← 返回列表")
      ),
      h("div", { className: "kv" },
        kv("run_id", run.run_id), kv("AI", run.ai_id), kv("会话", shortId(run.conversation_id)), kv("类型", run.chat_type),
        kv("聊天 ID", run.chat_id), kv("来源", run.source), kv("消息 ID", run.message_id), kv("引用消息", run.reply_to_message_id),
        kv("开始", formatTime(run.started_at)), kv("结束", formatTime(run.finished_at)),
        kv("结果", h("span", { className: "badge " + badge[0] }, badge[1])), kv("工具轮", String(run.tool_rounds))
      ),
      run.response_text ? h("div", { className: "kv" }, kv("回复内容", run.response_text)) : null,
      h("h3", null, "执行步骤"),
      data.steps.length === 0 ? h("div", { className: "empty" }, "暂无步骤记录") : null,
      data.steps.map(function (step) {
        var label = STEP_LABEL[step.step_type] || step.step_type;
        var content = step.content;
        if (typeof content === "string") { try { content = JSON.parse(content); } catch (e) {} }
        return h("div", { className: "step", key: step.step_id || step.step_index + "-" + step.occurred_at },
          h("div", { className: "step-head" },
            h("span", { className: "badge " + (step.status === "ok" ? "green" : "red") }, String(step.step_index)),
            h("span", { className: "type" }, label),
            h("span", { className: "meta" }, step.status + " · " + step.duration_ms + "ms · " + formatTime(step.occurred_at)),
            step.error ? h("span", { className: "meta", style: { color: "var(--red)" } }, step.error) : null
          ),
          content && Object.keys(content).length > 0 ? h("details", null,
            h("summary", null, "查看内容"),
            h("pre", null, JSON.stringify(content, null, 2))
          ) : null
        );
      })
    );
  }

  function kv(key, value) {
    return h("div", null, h("div", { className: "k" }, key), h("div", { className: "v" }, value));
  }

  function SettingsView(props) {
    var _useState = React.useState(""), current = _useState[0], setCurrent = _useState[1];
    var _useState2 = React.useState(""), newUser = _useState2[0], setNewUser = _useState2[1];
    var _useState3 = React.useState(""), newPass = _useState3[0], setNewPass = _useState3[1];
    var _useState4 = React.useState(""), message = _useState4[0], setMessage = _useState4[1];
    var _useState5 = React.useState(""), error = _useState5[0], setError = _useState5[1];

    function submit(event) {
      event.preventDefault();
      setError("");
      setMessage("");
      if (!newUser && !newPass) { setError("新账号和新密码至少填写一项"); return; }
      request("/api/credentials", {
        method: "POST",
        body: JSON.stringify({ current_password: current, username: newUser, password: newPass })
      }).then(function (data) {
        setMessage(data.message || "已更新");
        setTimeout(props.onLogout, 1200);
      }).catch(function (err) {
        setError(err.message);
      });
    }

    return h("form", { className: "settings-card", onSubmit: submit },
      h("h3", { style: { marginTop: 0 } }, "修改账号密码"),
      h("label", null, "当前密码"),
      h("input", { type: "password", value: current, onChange: function (e) { setCurrent(e.target.value); } }),
      h("label", null, "新账号（留空不修改）"),
      h("input", { value: newUser, onChange: function (e) { setNewUser(e.target.value); } }),
      h("label", null, "新密码（留空不修改）"),
      h("input", { type: "password", value: newPass, onChange: function (e) { setNewPass(e.target.value); } }),
      h("button", { type: "submit" }, "保存"),
      message ? h("div", { className: "ok" }, message) : null,
      error ? h("div", { className: "error" }, error) : null
    );
  }

  function App() {
    var _useState = React.useState(localStorage.getItem(TOKEN_KEY)), token = _useState[0], setToken = _useState[1];
    var _useState2 = React.useState(""), username = _useState2[0], setUsername = _useState2[1];
    var _useState3 = React.useState(true), db = _useState3[0], setDb = _useState3[1];

    function onLogin(data) {
      localStorage.setItem(TOKEN_KEY, data.token);
      setToken(data.token);
      setUsername(data.username);
      setDb(!!data.db);
    }

    function onLogout() {
      request("/api/logout", { method: "POST", keepToken: true }).catch(function () {});
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
    }

    return token
      ? h(MainView, { username: username, db: db, onLogout: onLogout })
      : h(LoginView, { onLogin: onLogin });
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
