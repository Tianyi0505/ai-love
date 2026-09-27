export type PluginAction =
  "install" | "enable" | "disable" | "restart" | "remove";

export type PluginInfo = {
  id: string;
  name: string;
  description: string;
  category: string;
  provides: string[];
  requires: string[];
  installed: boolean;
  enabled: boolean;
  available: boolean;
  state: string;
  error: string | null;
  active_calls: number;
};

export type Operation = {
  id: string;
  status: string;
  error: string | null;
  created_at: string;
  request: { plugin_id: string; action: PluginAction };
};

export type PluginHost = {
  host: string;
  online: boolean;
  revision: number;
  busy: boolean;
  error?: string;
  plugins: PluginInfo[];
  operations: Operation[];
  catalog_errors?: { source: string; error: string }[];
};

export type PluginCommand = {
  host: string;
  plugin_id: string;
  action: PluginAction;
  operation_id: string;
  expected_revision: number;
  stop_dependents: boolean;
};

export type Preflight = {
  allowed: boolean;
  affected: string[];
  reason: string | null;
};

export const actionLabels: Record<PluginAction, string> = {
  install: "安装",
  enable: "启用",
  disable: "停用",
  restart: "重新启动",
  remove: "移除",
};

export const stateLabels: Record<string, string> = {
  active: "运行中",
  disabled: "已停用",
  removed: "已移除",
  starting: "启动中",
  draining: "排空中",
  failed: "异常",
};
