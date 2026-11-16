import type { RefObject } from "react";
import { Icon } from "./ui";
export function ChatComposer({
  draft,
  onDraft,
  file,
  onFileRemove,
  onPick,
  textarea,
  fileInput,
  onSend,
  busy,
  disabled,
  feedback,
  metric,
  onBind,
  hasChat,
  onConfigure,
  hasData,
}: {
  draft: string;
  onDraft: (v: string) => void;
  file: File | null;
  onFileRemove: () => void;
  onPick: (f: File | undefined) => void;
  textarea: RefObject<HTMLTextAreaElement | null>;
  fileInput: RefObject<HTMLInputElement | null>;
  onSend: () => void;
  busy: boolean;
  disabled: boolean;
  feedback: string;
  metric: string;
  onBind: () => void;
  hasChat: boolean;
  onConfigure: () => void;
  hasData: boolean;
}) {
  return (
    <footer className="composer-shell">
      <div className="composer-column">
        <div className="composer-context">
          <span>
            <i className="local-dot" />
            {hasData ? "当前研究 · " + metric : "尚未选择研究"}
          </span>
          <div>
            {hasData && (
              <button type="button" onClick={onConfigure} disabled={disabled}>
                研究配置
              </button>
            )}
            {hasChat && (
              <button type="button" onClick={onBind} disabled={disabled}>
                关联研究
              </button>
            )}
          </div>
        </div>
        {feedback && (
          <p className="feedback" role="status">
            {feedback}
          </p>
        )}
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            onSend();
          }}
        >
          {file && (
            <div className="attachment">
              <Icon name="clip" size={15} />
              <span>{file.name}</span>
              <small>尚未提交</small>
              <button
                type="button"
                aria-label="移除附件"
                onClick={onFileRemove}
              >
                <Icon name="close" size={14} />
              </button>
            </div>
          )}
          <textarea
            aria-label="研究消息"
            ref={textarea}
            rows={2}
            value={draft}
            placeholder="提出研究问题，或添加一份数据"
            disabled={disabled}
            onChange={(e) => {
              onDraft(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height =
                Math.min(e.target.scrollHeight, 176) + "px";
            }}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                onSend();
              }
            }}
          />
          <div className="composer-actions">
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.parquet"
              hidden
              onChange={(e) => {
                onPick(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              className="attach-button"
              aria-label="添加数据附件"
              onClick={() => fileInput.current?.click()}
              disabled={disabled}
            >
              <Icon name="plus" size={20} />
            </button>
            <span>CSV / Parquet · 仅在本机处理</span>
            <button
              className="send-button"
              type="submit"
              aria-label={busy ? "正在处理" : "发送消息"}
              disabled={disabled || (!draft.trim() && !file)}
            >
              {busy ? (
                <span className="busy-dot" />
              ) : (
                <Icon name="arrow" size={18} />
              )}
            </button>
          </div>
        </form>
        <p className="composer-note">
          候选建议、采纳、正式批准与统计执行始终分开。
        </p>
      </div>
    </footer>
  );
}
