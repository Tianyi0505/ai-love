import { Heart, LogOut, PanelLeftClose } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import type { Session } from "../core/api";
import { apiRequest } from "../core/api";
import { LoveSprite } from "../shared/love_sprite";
import { navigation } from "./navigation";

type PanelShellProps = {
  session: Session;
  onLogout: () => void;
};

export function PanelShell({ session, onLogout }: PanelShellProps) {
  const [compact, setCompact] = useState(false);

  async function logout() {
    await apiRequest<{ message: string }>("/logout", { method: "POST" });
    onLogout();
  }

  return (
    <div className={compact ? "app-shell app-shell--compact" : "app-shell"}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <LoveSprite size="small" />
          </span>
          <div className="brand__copy">
            <strong>ai-love</strong>
            <span>心与记忆的小窝</span>
          </div>
        </div>

        <nav className="navigation" aria-label="功能列表">
          {navigation.map(({ label, caption, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                isActive ? "navigation__item navigation__item--active" : "navigation__item"
              }
            >
              <span className="navigation__icon"><Icon size={18} strokeWidth={2.2} /></span>
              <span className="navigation__copy"><strong>{label}</strong><small>{caption}</small></span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-note" aria-hidden="true">
          <Heart size={16} fill="currentColor" />
          <span>把每一份记忆<br />好好收起来</span>
        </div>

        <div className="sidebar__footer">
          <div className="current-ai">
            <span className="status-dot" />
            <div>
              <strong>{session.ai_id}</strong>
              <span>守护者 · {session.username}</span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={logout} aria-label="退出登录">
            <LogOut size={18} />
          </button>
        </div>

        <button
          className="sidebar__toggle"
          type="button"
          onClick={() => setCompact((value) => !value)}
          aria-label={compact ? "展开侧边栏" : "收起侧边栏"}
        >
          <PanelLeftClose size={17} />
        </button>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
