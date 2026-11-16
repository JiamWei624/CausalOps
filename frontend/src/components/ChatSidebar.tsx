import type { Session } from "../api";
import { Icon } from "./ui";
export function ChatSidebar({
  sessions,
  current,
  search,
  onSearch,
  onSelect,
  onNew,
  onHome,
  busy,
  open,
  onClose,
  showDemo,
  onDemo,
  legacyUrl,
}: {
  sessions: Session[];
  current: string | null;
  search: string;
  onSearch: (v: string) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onHome: () => void;
  busy: boolean;
  open: boolean;
  onClose: () => void;
  showDemo: boolean;
  onDemo: (v: boolean) => void;
  legacyUrl: string | undefined;
}) {
  const rows = sessions.filter(
    (x) =>
      (showDemo || !x.demo_hidden || x.id === current) &&
      (!search ||
        (x.label + " " + x.title).toLowerCase().includes(search.toLowerCase())),
  );
  return (
    <aside
      className={"chat-navigation" + (open ? " open" : "")}
      aria-label="研究会话导航"
    >
      <div className="brand-row">
        <button className="brand" onClick={onHome}>
          <Icon name="brand" size={25} />
          <span>CausalOps</span>
        </button>
        <button
          className="icon-button mobile-only"
          aria-label="收起会话导航"
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      <button
        className="new-research"
        aria-label="新建研究"
        onClick={onNew}
        disabled={busy}
      >
        <Icon name="plus" size={18} />
        <span>新建研究</span>
        <kbd aria-hidden="true">↗</kbd>
      </button>
      <label className="session-search">
        <Icon name="search" size={16} />
        <input
          aria-label="搜索会话"
          placeholder="搜索研究会话"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </label>
      <p className="navigation-label">最近研究</p>
      <nav className="session-list">
        {rows.map((s, i) => (
          <button
            key={s.id}
            data-session-id={s.id}
            aria-current={s.id === current ? "page" : undefined}
            className={"session" + (s.id === current ? " selected" : "")}
            onClick={() => onSelect(s.id)}
            title={s.label}
          >
            <span>{s.label}</span>
            <small>
              <i className={s.active_binding_id ? "bound-dot" : "empty-dot"} />
              {s.active_binding_id ? "已有研究上下文" : "尚未关联数据"}
              {rows.filter((x) => x.label === s.label).length > 1
                ? " · " + (i + 1)
                : ""}
            </small>
          </button>
        ))}
        {!rows.length && <p className="empty-navigation">暂无匹配会话</p>}
      </nav>
      <footer className="navigation-footer">
        {sessions.some((s) => s.demo_hidden) && (
          <label className="demo-filter">
            <input
              type="checkbox"
              checked={showDemo}
              onChange={(e) => onDemo(e.target.checked)}
            />
            显示验收记录
          </label>
        )}
        <a href={legacyUrl} target="_blank" rel="noopener noreferrer">
          <Icon name="panel" size={16} />
          完整工作台与专业工具<span>↗</span>
        </a>
        <p>本地单用户 · 研究需正式审核</p>
      </footer>
    </aside>
  );
}
