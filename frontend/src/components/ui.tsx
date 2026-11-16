import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
export const labels: Record<string, string> = {
  candidate: "待正式审核",
  completed: "已完成",
  approved: "已批准",
  running: "执行中",
  pending: "未执行",
  succeeded: "已保存",
  pause_requested: "已请求暂停",
  cancel_requested: "已请求取消",
  queued: "排队中",
  paused: "已暂停",
  cancelled: "已取消",
  blocked: "已阻断",
  interrupted: "待核查",
  registered: "数据已登记",
  verified: "已核验满足",
  issue: "已发现问题",
  unknown: "证据未知或不足",
  not_applicable: "不适用",
  not_checked: "尚未检查",
};
export const safeLink = (url: string) =>
  /^https?:\/\//.test(url) ? url : undefined;
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    menu: (
      <>
        <path d="M4 6h16M4 12h16M4 18h16" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="m6 11 6-6 6 6M12 5v14" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    panel: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="3" />
        <path d="M16 4v16" />
      </>
    ),
    search: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="m15 15 5 5" />
      </>
    ),
    clip: <path d="m8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l8-8" />,
    chevron: <path d="m9 6 6 6-6 6" />,
    brand: (
      <>
        <path d="m12 2 10 10-10 10L2 12Z" />
        <path d="m7 12 5 5 5-5" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.brand}
    </svg>
  );
}
export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        a: ({ href, children }) => (
          <a
            href={href && safeLink(href)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        ),
        img: ({ alt }) => (
          <span className="muted">
            [未自动加载外部图片{alt ? "：" + alt : ""}]
          </span>
        ),
        table: ({ children }) => (
          <div className="table-wrap">
            <table>{children}</table>
          </div>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
export function EvidenceDetails({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  return (
    <details className="source">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
