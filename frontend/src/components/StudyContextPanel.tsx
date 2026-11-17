import type { Study, SetupView, Artifacts } from "../api";
import { EvidenceDetails, Icon, labels } from "./ui";
export function StudyContextPanel({
  study,
  setup,
  artifacts,
  loading,
  error,
  onClose,
  onReport,
  onConfigure,
  onCandidate,
  onResearch,
  onInsights,
}: {
  study: Study | null;
  setup: SetupView | null;
  artifacts: Artifacts | null;
  loading: boolean;
  error: string;
  onClose: () => void;
  onReport: () => void;
  onConfigure: () => void;
  onCandidate: () => void;
  onResearch?: () => void;
  onInsights?:()=>void;
}) {
  const cfg = setup?.configuration?.configuration,
    metric =
      study?.scope.metric ||
      study?.scope.metric_label ||
      study?.scope.outcome ||
      cfg?.metric,
    window = study?.scope.window || study?.scope.metric_window || cfg?.window;
  return (
    <aside className="study-context" aria-label="研究产物面板">
      <header>
        <span>研究上下文</span>
        <button
          className="icon-button"
          aria-label="关闭研究面板"
          onClick={onClose}
        >
          <Icon name="close" size={18} />
        </button>
      </header>
      {error ? (
        <div className="context-empty error">
          <p>当前来源需要重新核验。</p>
          <p>{error}</p>
          <button onClick={() => location.reload()}>刷新并核对</button>
        </div>
      ) : !study ? (
        <div className="context-empty">
          <h3>研究尚未关联</h3>
          <p>提交数据或关联已有研究后，在这里查看正式口径和产物。</p>
        </div>
      ) : (
        <>
          <h2>{cfg?.objective || study.title}</h2>
          {artifacts?.diagnostic_status === "recheck_required" && (
            <section className="source-stale" role="status">
              <p>{artifacts.diagnostic_message}</p>
              {onInsights && <button onClick={onInsights}>重新检查研究证据</button>}
            </section>
          )}
          <dl className="context-facts">
            <dt>目标指标</dt>
            <dd>{metric || "待确认"}</dd>
            <dt>观察窗口</dt>
            <dd>{window || "待确认"}</dd>
            <dt>数据合同</dt>
            <dd>
              {study.contract
                ? "v" + String(study.contract.version)
                : "尚未确认"}
            </dd>
            <dt>计划状态</dt>
            <dd>
              {setup?.phase === "candidate"
                ? "候选待采纳"
                : setup?.phase === "confirmed"
                  ? "合同已确认 · 未生成候选"
                  : study.status === "registered"
                    ? "尚未生成"
                    : labels[study.status] || study.status}
            </dd>
            <dt>统计运行</dt>
            <dd>{study.run_ids.length} 个真实 Run</dd>
          </dl>
          <div className="context-actions">
            {study.report_available ? (
              <button className="primary full" onClick={onReport}>
                阅读研究报告
                <Icon name="chevron" size={16} />
              </button>
            ) : study.domain === "automation_v2" && onResearch ? (
              <button className="primary full" onClick={onResearch}>
                {study.status === "candidate"
                  ? "正式审核研究方案"
                  : "研究执行与控制"}
              </button>
            ) : setup?.phase === "adopted" ? (
              <a
                className="button-link primary"
                href={study.links.review}
                target="_blank"
                rel="noopener noreferrer"
              >
                前往正式审核 ↗
              </a>
            ) : setup?.editable ? (
              <button
                className="primary full"
                onClick={setup.configuration ? onCandidate : onConfigure}
              >
                {setup.candidate
                  ? "查看候选方案"
                  : setup.configuration
                    ? "生成受限候选"
                    : "配置研究口径"}
                <Icon name="chevron" size={16} />
              </button>
            ) : (
              <a
                href={study.links.review}
                target="_blank"
                rel="noopener noreferrer"
              >
                查看原研究工作流 ↗
              </a>
            )}
          </div>
          <section className="artifact-index">
            <h3>研究产物</h3>
            {study.domain === "automation_v2" && onResearch && (
              <button onClick={onResearch}>
                <span>审核与执行</span>
                <small>{labels[study.status] || study.status}</small>
                <Icon name="chevron" size={15} />
              </button>
            )}
            <button onClick={onConfigure}>
              <span>数据与合同</span>
              <small>{study.contract ? "已保存" : "待确认"}</small>
              <Icon name="chevron" size={15} />
            </button>
            {setup?.candidate && (
              <button onClick={onCandidate}>
                <span>候选方案</span>
                <small>{setup.phase === "adopted" ? "已采纳" : "待采纳"}</small>
                <Icon name="chevron" size={15} />
              </button>
            )}
            {onInsights?<><button onClick={onInsights}><span>研究证据诊断</span><small>显式检查</small><Icon name="chevron" size={15}/></button><button onClick={onInsights}><span>研究决定与历史</span><small>无执行权限</small><Icon name="chevron" size={15}/></button></>:<>
            <a
              href={study.links.evidence}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span>证据诊断</span>
              <small>
                {loading
                  ? "读取中"
                  : artifacts?.diagnostic
                    ? "已有报告"
                    : "原入口显式检查"}
              </small>
              <Icon name="chevron" size={15} />
            </a>
            <a
              href={study.links.decisions}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span>研究决定</span>
              <small>
                {artifacts?.decisions.length
                  ? artifacts.decisions.length + " 条记录"
                  : "原入口记录"}
              </small>
              <Icon name="chevron" size={15} />
            </a>
            </>}
          </section>
          <p className="context-boundary">
            {study.run_ids.length
              ? "历史结果只属于其保存的数据、计划和运行版本。"
              : "尚未执行统计。配置合同或采纳候选不等于获得批准。"}
          </p>
          <EvidenceDetails
            label="完整来源与技术详情"
            value={{
              task: study.id,
              data: study.data,
              contract: study.contract,
              plans: study.plan_refs,
              approval: study.approval,
              runs: study.run_ids,
              report_sha: study.report_sha,
              execution_warning: study.execution_warning,
            }}
          />
        </>
      )}
    </aside>
  );
}
