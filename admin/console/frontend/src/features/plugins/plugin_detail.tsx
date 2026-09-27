import {
  ArrowDownToLine,
  LoaderCircle,
  Plug,
  Power,
  RefreshCw,
} from "lucide-react";
import {
  stateLabels,
  type PluginAction,
  type PluginHost,
  type PluginInfo,
} from "./types";

interface PluginDetailProps {
  host: PluginHost;
  plugin: PluginInfo;
  onAction: (action: PluginAction) => void;
}

export function PluginDetail({ host, plugin, onAction }: PluginDetailProps) {
  return (
    <article className="plugin-detail" aria-label={`${plugin.name}详情`}>
      <div className="plugin-detail__heading">
        <span className="plugin-tile is-large">
          <Plug size={30} />
        </span>
        <span className={`plugin-state is-${plugin.state}`}>
          {stateLabels[plugin.state] ?? plugin.state}
        </span>
      </div>
      <h2>{plugin.name}</h2>
      <code>{plugin.id}</code>
      <p>{plugin.description}</p>
      <dl className="plugin-facts">
        <div>
          <dt>运行位置</dt>
          <dd>{host.host}</dd>
        </div>
        <div>
          <dt>期望状态</dt>
          <dd>{plugin.enabled ? "启用" : "停用"}</dd>
        </div>
        <div>
          <dt>在途调用</dt>
          <dd>{plugin.active_calls}</dd>
        </div>
      </dl>
      <div className="plugin-capabilities">
        <h3>提供的能力</h3>
        <div>
          {plugin.provides.map((value) => (
            <code key={value}>{value}</code>
          ))}
          {plugin.provides.length === 0 && <span>无</span>}
        </div>
        <h3>依赖的能力</h3>
        <div>
          {plugin.requires.map((value) => (
            <code key={value}>{value}</code>
          ))}
          {plugin.requires.length === 0 && <span>可独立启停</span>}
        </div>
      </div>
      {plugin.error && (
        <p className="plugin-alert" role="alert">
          {plugin.error}
        </p>
      )}
      {!plugin.available && (
        <p className="plugin-alert">
          本地清单已不可用，请恢复插件文件或移除安装记录。
        </p>
      )}
      <div className="plugin-actions">
        {!plugin.installed ? (
          <button
            className="primary-button"
            disabled={!plugin.available || host.busy}
            onClick={() => onAction("install")}
          >
            <ArrowDownToLine size={16} />
            安装
          </button>
        ) : (
          <>
            {plugin.state === "active" || plugin.state === "failed" ? (
              <button
                className="secondary-button"
                disabled={host.busy}
                onClick={() => onAction("disable")}
              >
                <Power size={16} />
                停用
              </button>
            ) : (
              <button
                className="primary-button"
                disabled={!plugin.available || host.busy}
                onClick={() => onAction("enable")}
              >
                <Power size={16} />
                启用能力
              </button>
            )}
            <button
              className="secondary-button"
              disabled={!plugin.available || host.busy}
              onClick={() => onAction("restart")}
            >
              <RefreshCw size={16} />
              重新启动
            </button>
            <button
              className="plugin-remove"
              disabled={host.busy}
              onClick={() => onAction("remove")}
            >
              移除
            </button>
          </>
        )}
      </div>
      <p className="plugin-footnote">
        停用会先排空在途工作。记忆、身份与历史消息会保留。
      </p>
      {host.busy && (
        <p className="plugin-progress" role="status">
          <LoaderCircle size={16} className="plugin-spin" />
          宿主正在执行变更，请等待结果。
        </p>
      )}
    </article>
  );
}
