import {
  Activity,
  Check,
  CircleAlert,
  Layers3,
  LoaderCircle,
  Plug,
  RefreshCw,
  Search,
  Unplug,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { apiRequest, formatDate } from "../../core/api";
import { PageHeader } from "../../shared/page_header";
import { PageLoading } from "../../shared/page_state";
import {
  actionLabels,
  stateLabels,
  type Operation,
  type PluginAction,
  type PluginCommand,
  type PluginHost,
  type PluginInfo,
  type Preflight,
} from "./types";
import { PluginDetail } from "./plugin_detail";
import { usePluginCatalog } from "./use_plugin_catalog";
import "./plugins.css";

const categoryLabels: Record<string, string> = {
  agent: "智能体",
  storage: "运行资源",
  memory: "记忆",
  model: "模型",
  speech: "语音",
  channel: "平台",
  tool: "工具",
  live: "直播",
};
const operationLabels: Record<string, string> = {
  accepted: "已受理",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  interrupted: "曾中断",
};

function operationId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join(
    "",
  );
}

export function PluginsPage() {
  const { hosts, error, setError, load } = usePluginCatalog();
  const [hostFilter, setHostFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [command, setCommand] = useState<PluginCommand | null>(null);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (!command) {
      dialog.current?.close();
      return;
    }
    dialog.current?.showModal();
    let cancelled = false;
    setPreflight(null);
    setDialogError("");
    apiRequest<Preflight>("/plugins/preflight", {
      method: "POST",
      body: command,
    })
      .then((value) => {
        if (!cancelled) setPreflight(value);
      })
      .catch((caught) => {
        if (!cancelled)
          setDialogError(
            caught instanceof Error ? caught.message : String(caught),
          );
      });
    return () => {
      cancelled = true;
    };
  }, [command]);

  async function refresh() {
    setRefreshing(true);
    setNotice("");
    try {
      const targets = (hosts ?? []).filter(
        (host) =>
          host.online && (hostFilter === "all" || host.host === hostFilter),
      );
      await Promise.all(
        targets.map((host) =>
          apiRequest(`/plugins/hosts/${host.host}/refresh`, { method: "POST" }),
        ),
      );
      await load();
      setNotice("已刷新本地插件目录与运行状态。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRefreshing(false);
    }
  }

  function prepare(host: PluginHost, plugin: PluginInfo, action: PluginAction) {
    setCommand({
      host: host.host,
      plugin_id: plugin.id,
      action,
      operation_id: operationId(),
      expected_revision: host.revision,
      stop_dependents: false,
    });
  }

  async function submit() {
    if (!command || !preflight?.allowed) return;
    setSubmitting(true);
    try {
      const result = await apiRequest<Operation>("/plugins/operations", {
        method: "POST",
        body: command,
      });
      setNotice(`操作 ${result.id.slice(0, 8)} 已受理，实际结果会自动更新。`);
      setCommand(null);
      await load();
    } catch (caught) {
      // Keep the same command and id for uncertain responses; never double-submit a new operation.
      setDialogError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  }

  const allPlugins = (hosts ?? []).flatMap((host) =>
    host.plugins.map((plugin) => ({
      host,
      plugin,
      key: `${host.host}/${plugin.id}`,
    })),
  );
  const visible = allPlugins.filter(
    ({ host, plugin }) =>
      (hostFilter === "all" || host.host === hostFilter) &&
      `${plugin.name} ${plugin.id} ${plugin.description}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const current = visible.find((item) => item.key === selected) ?? visible[0];
  const online = (hosts ?? []).filter((host) => host.online).length;
  const active = allPlugins.filter(
    ({ plugin }) => plugin.state === "active",
  ).length;
  const failed = allPlugins.filter(
    ({ plugin }) => plugin.state === "failed",
  ).length;
  const history = (hosts ?? [])
    .flatMap((host) =>
      host.operations.map((operation) => ({ ...operation, host: host.host })),
    )
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 8);

  return (
    <div className="page plugins-page">
      <PageHeader
        eyebrow="PLUGIN STUDIO · 能力工坊"
        title="让每一种能力，自由生长"
        description="在这里装配 ai-love 的能力，查看依赖与运行状态，按需启用或停用。"
        action={
          <button
            className="secondary-button plugin-refresh"
            onClick={() => {
              void refresh();
            }}
            disabled={refreshing}
          >
            <RefreshCw size={16} className={refreshing ? "plugin-spin" : ""} />
            刷新目录
          </button>
        }
      />
      <div className="plugin-summary">
        <div>
          <span className="plugin-summary__icon">
            <Layers3 size={22} />
          </span>
          <strong>{allPlugins.length}</strong>
          <span>可管理能力</span>
        </div>
        <div>
          <span className="plugin-summary__icon is-mint">
            <Activity size={22} />
          </span>
          <strong>{active}</strong>
          <span>正在运行</span>
        </div>
        <div>
          <span className="plugin-summary__icon is-peach">
            <CircleAlert size={22} />
          </span>
          <strong>{failed}</strong>
          <span>需要关注</span>
        </div>
        <div>
          <span className="status-dot" />
          <strong>
            {online}
            <small> / {(hosts ?? []).length}</small>
          </strong>
          <span>宿主在线</span>
        </div>
      </div>
      {error && (
        <div className="plugin-alert" role="alert">
          <CircleAlert size={18} />
          {error}
        </div>
      )}
      {(hosts ?? []).flatMap((host) =>
        (host.catalog_errors ?? []).map((item) => (
          <div
            className="plugin-alert"
            role="alert"
            key={`${host.host}/${item.source}`}
          >
            {host.host} · {item.source}：{item.error}
          </div>
        )),
      )}
      {notice && (
        <div className="plugin-notice" role="status">
          <Check size={17} />
          {notice}
        </div>
      )}
      {hosts && online === 0 && (
        <div className="plugin-alert" role="status">
          暂未连接到插件宿主。请启动使用插件入口的服务后刷新。
        </div>
      )}
      <section className="plugin-workbench" aria-label="插件管理">
        <div className="plugin-toolbar">
          <label className="plugin-search">
            <Search size={17} />
            <input
              placeholder="搜索能力或插件标识…"
              aria-label="搜索插件"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label className="plugin-host-select">
            <span>运行位置</span>
            <select
              value={hostFilter}
              onChange={(event) => setHostFilter(event.target.value)}
            >
              <option value="all">全部宿主</option>
              {(hosts ?? []).map((host) => (
                <option key={host.host} value={host.host}>
                  {host.host}
                  {host.online ? "" : " · 离线"}
                </option>
              ))}
            </select>
          </label>
        </div>
        {!hosts && !error && <PageLoading label="正在连接能力工坊" />}
        <div className="plugin-workbench__body">
          <div className="plugin-list" aria-label="插件列表">
            {visible.map(({ plugin, host, key }) => (
              <button
                key={key}
                className={`plugin-row ${current?.key === key ? "is-selected" : ""}`}
                onClick={() => setSelected(key)}
                aria-pressed={current?.key === key}
              >
                <span
                  className={`plugin-tile ${plugin.state === "active" ? "is-active" : ""}`}
                >
                  <Plug size={21} />
                </span>
                <span className="plugin-row__copy">
                  <strong>{plugin.name}</strong>
                  <small>
                    {host.host} ·{" "}
                    {categoryLabels[plugin.category] ?? plugin.category}
                  </small>
                </span>
                <span className={`plugin-state is-${plugin.state}`}>
                  {stateLabels[plugin.state] ?? plugin.state}
                </span>
              </button>
            ))}
            {hosts && visible.length === 0 && (
              <div className="plugin-empty">
                <Unplug size={32} />
                <strong>这里还没有匹配的能力</strong>
                <p>
                  {query
                    ? "试试其他关键词。"
                    : "将插件准备到本地目录后，点击刷新目录。"}
                </p>
              </div>
            )}
          </div>
          {current && (
            <PluginDetail
              host={current.host}
              plugin={current.plugin}
              onAction={(action) =>
                prepare(current.host, current.plugin, action)
              }
            />
          )}
        </div>
      </section>
      <section className="plugin-history">
        <h2>
          最近的装配记录 <span>{history.length}</span>
        </h2>
        {history.length === 0 ? (
          <p className="plugin-footnote">
            第一次能力变更，会从这里开始留下记录。
          </p>
        ) : (
          history.map((operation) => (
            <div
              className="plugin-history__row"
              key={`${operation.host}/${operation.id}`}
            >
              <span className={`plugin-history__dot is-${operation.status}`} />
              <div>
                <strong>
                  {actionLabels[operation.request.action]} ·{" "}
                  {operation.request.plugin_id}
                </strong>
                <small>
                  {operation.host} · {operation.id.slice(0, 8)}
                  {operation.error && ` · ${operation.error}`}
                </small>
              </div>
              <span>
                {operationLabels[operation.status] ?? operation.status}
              </span>
              <time>{formatDate(operation.created_at)}</time>
            </div>
          ))
        )}
      </section>
      <dialog
        ref={dialog}
        className="plugin-dialog"
        onCancel={(event) => {
          if (submitting) event.preventDefault();
          else setCommand(null);
        }}
        onClose={() => {
          if (!submitting) setCommand(null);
        }}
      >
        {command && (
          <>
            <button
              className="plugin-dialog__close icon-button"
              aria-label="关闭操作预检"
              disabled={submitting}
              onClick={() => setCommand(null)}
            >
              <X size={18} />
            </button>
            <span className="eyebrow">CHANGE PREVIEW · 变更预检</span>
            <h2>
              {actionLabels[command.action]} {command.plugin_id}
            </h2>
            <p>查看本次变更涉及的能力，再执行操作。</p>
            {["disable", "remove", "restart"].includes(command.action) && (
              <label className="plugin-cascade">
                <input
                  type="checkbox"
                  checked={command.stop_dependents}
                  disabled={submitting}
                  onChange={(event) =>
                    setCommand({
                      ...command,
                      operation_id: operationId(),
                      stop_dependents: event.target.checked,
                    })
                  }
                />
                允许一并{command.action === "restart" ? "重启" : "停用"}
                依赖此能力的插件
              </label>
            )}
            {!preflight && !dialogError && (
              <p className="plugin-progress">
                <LoaderCircle size={17} className="plugin-spin" />
                正在检查依赖与状态…
              </p>
            )}
            {preflight?.allowed && (
              <div className="plugin-change-list">
                <strong>本次影响范围</strong>
                {preflight.affected.map((id) => (
                  <code key={id}>{id}</code>
                ))}
              </div>
            )}
            {preflight && !preflight.allowed && (
              <p className="plugin-alert" role="alert">
                {preflight.reason}
              </p>
            )}
            {dialogError && (
              <p className="plugin-alert" role="alert">
                {dialogError}
              </p>
            )}
            {command.action === "remove" && (
              <p className="plugin-footnote">
                移除安装记录和运行实例，保留本地交付文件与业务数据，之后可以重新安装。
              </p>
            )}
            <div className="plugin-actions">
              <button
                className="secondary-button"
                disabled={submitting}
                onClick={() => setCommand(null)}
              >
                取消
              </button>
              <button
                className="primary-button"
                disabled={submitting || !preflight?.allowed}
                onClick={() => {
                  void submit();
                }}
              >
                {submitting
                  ? "正在提交…"
                  : `确认${actionLabels[command.action]}`}
              </button>
            </div>
          </>
        )}
      </dialog>
    </div>
  );
}
