import type { ReactNode } from "react";
import { Icon } from "./ui";
export function AppShell({
  sidebar,
  sidebarOpen,
  onSidebarOpen,
  onSidebarClose,
  title,
  status,
  panelOpen,
  onPanelToggle,
  focus,
  children,
  artifacts,
}: {
  sidebar: ReactNode;
  sidebarOpen: boolean;
  onSidebarOpen: () => void;
  onSidebarClose: () => void;
  title: string;
  status: string;
  panelOpen: boolean;
  onPanelToggle: () => void;
  focus: ReactNode;
  children: ReactNode;
  artifacts: ReactNode;
}) {
  return (
    <div className={"app-shell" + (panelOpen ? " panel-is-open" : "")}>
      {sidebarOpen && (
        <button
          className="navigation-scrim"
          onClick={onSidebarClose}
          aria-label="关闭会话导航"
        />
      )}
      {sidebar}
      <section className="workspace-surface">
        <header className="workspace-header">
          <button
            className="icon-button mobile-only"
            aria-label="打开会话导航"
            onClick={onSidebarOpen}
          >
            <Icon name="menu" />
          </button>
          <div className="workspace-identity">
            <span>{title}</span>
            <small>{status}</small>
          </div>
          {!focus && (
            <button
              className={"artifact-toggle" + (panelOpen ? " selected" : "")}
              aria-label={panelOpen ? "收起研究面板" : "展开研究面板"}
              aria-expanded={panelOpen}
              onClick={onPanelToggle}
            >
              <Icon name="panel" size={18} />
              <span>研究产物</span>
            </button>
          )}
        </header>
        <div className="workspace-body">
          <div className={"conversation-stage" + (focus ? " concealed" : "")}>
            {children}
          </div>
          {!focus && panelOpen && artifacts}
          {focus && <div className="focus-stage">{focus}</div>}
        </div>
      </section>
    </div>
  );
}
