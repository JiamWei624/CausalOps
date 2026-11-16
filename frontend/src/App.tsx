import { useInsights } from "./hooks/useInsights";
import { InsightsReader } from "./components/InsightsReader";
import { useWorkspace } from "./hooks/useWorkspace";
import { AppShell } from "./components/AppShell";
import { ChatSidebar } from "./components/ChatSidebar";
import { ConversationView } from "./components/ConversationView";
import { ChatComposer } from "./components/ChatComposer";
import { StudyContextPanel } from "./components/StudyContextPanel";
import { DataContractEditor } from "./components/DataContractEditor";
import { CandidatePlanView } from "./components/CandidatePlanView";
import { ReportReader } from "./components/ReportReader";
import { ResearchFlow } from "./components/ResearchFlow";
import { Icon, labels } from "./components/ui";
export function App() {
  const w = useWorkspace(),
    study = w.chat?.study ?? null;
  const insights = useInsights(w.chatId,!!w.boot,w.chat?.binding?.id);
  const openInsights=()=>{w.setPanel(false);w.changeView("insights")};
  const metric =
    study?.scope.metric ||
    study?.scope.metric_label ||
    study?.scope.outcome ||
    w.setup?.configuration?.configuration.metric ||
    "";
  const status =
    w.research?.task.id === study?.id && w.research
      ? labels[w.research.task.status] || w.research.task.status
      : w.setup?.phase === "candidate"
        ? "候选待采纳"
        : w.setup?.phase === "confirmed"
          ? "合同已确认"
          : study
            ? labels[study.status] || study.status
            : "本地研究";
  let focus = null;
  if (w.view === "configure")
    focus = w.setup ? (
      <DataContractEditor
        key={w.chatId + ":" + w.setup.binding_id}
        setup={w.setup}
        busy={w.setupBusy}
        error={w.setupError}
        onBack={() => w.changeView("chat")}
        onConfirm={w.confirmContract}
        onCandidate={w.openCandidate}
      />
    ) : (
      <div className="focus-loading">
        <button onClick={() => w.changeView("chat")}>← 返回对话</button>
        <p role="status">{w.setupError || "正在读取数据与合同来源…"}</p>
      </div>
    );
  if (w.view === "candidate")
    focus = w.setup ? (
      <CandidatePlanView
        key={w.setup.candidate?.id || "empty"}
        setup={w.setup}
        study={study}
        busy={w.setupBusy}
        error={w.setupError}
        onBack={() => w.changeView("chat")}
        onConfigure={w.openConfigure}
        onGenerate={w.openCandidate}
        onAdopt={w.adoptCandidate}
        onReview={() => w.changeView("research")}
      />
    ) : (
      <div className="focus-loading">
        <button onClick={() => w.changeView("chat")}>← 返回对话</button>
        <p>{w.setupError || "正在核对候选来源…"}</p>
      </div>
    );
  if (w.view === "report" && w.report)
    focus = (
      <ReportReader
        report={w.report}
        study={study}
        onClose={() => w.changeView("chat")}
        onInsights={openInsights}
      />
    );
  if (w.view === "research")
    focus = (
      <ResearchFlow
        key={w.research?.task.plan_sha || w.chatId}
        value={w.error?null:w.research}
        busy={w.researchBusy}
        error={w.error||w.researchError}
        notice={w.researchNotice}
        onAction={w.researchAction}
        onRefresh={w.refreshResearch}
        onBack={() => w.changeView("chat")}
        onReport={w.openReport}
      />
    );
  if(w.view === "insights") focus=(<InsightsReader key={w.chatId} value={insights.value} error={insights.error} notice={insights.notice} busy={insights.busy} onGenerate={insights.generate} onSave={insights.save} onSelect={insights.refresh} onRefresh={()=>insights.refresh(insights.value?.report?.report_id)} onBack={()=>w.changeView("chat")} onReport={w.openReport}/>);
  const sidebar = (
    <ChatSidebar
      sessions={w.sessions}
      current={w.chatId}
      search={w.search}
      onSearch={w.setSearch}
      onSelect={w.select}
      onNew={w.newChat}
      onHome={() => w.select(null)}
      busy={w.busy || !w.boot}
      open={w.sidebar}
      onClose={() => w.setSidebar(false)}
      showDemo={w.showDemo}
      onDemo={w.setShowDemo}
      legacyUrl={w.boot?.streamlit_url}
    />
  );
  return (
    <>
      <AppShell
        sidebar={sidebar}
        sidebarOpen={w.sidebar}
        onSidebarOpen={() => w.setSidebar(true)}
        onSidebarClose={() => w.setSidebar(false)}
        title={
          w.sessions.find((x) => x.id === w.chatId)?.label || "新的研究对话"
        }
        status={status}
        panelOpen={w.panel}
        onPanelToggle={() => w.setPanel((x) => !x)}
        focus={focus}
        artifacts={
          <StudyContextPanel
            study={study}
            setup={w.setup}
            artifacts={w.artifacts}
            loading={w.artifactLoading}
            error={w.error || w.artifactError || w.reportError}
            onClose={() => w.setPanel(false)}
            onReport={w.openReport}
            onConfigure={w.openConfigure}
            onCandidate={w.openCandidate}
            onResearch={() => w.changeView("research")}
            onInsights={openInsights}
          />
        }
      >
        <ConversationView
          chat={w.chat}
          chatId={w.chatId}
          loading={w.loading}
          error={w.error}
          reader={w.reader}
          onScroll={() => {
            const e = w.reader.current;
            if (e) {
              w.nearBottom.current =
                e.scrollHeight - e.scrollTop - e.clientHeight < 80;
              if (w.chatId) w.positions.current[w.chatId] = e.scrollTop;
            }
          }}
          onDraft={w.setDraft}
          onConfigure={w.openConfigure}
          onCandidate={w.openCandidate}
          setup={w.setup}
          research={w.research}
          completion={w.completion}
          onResearch={() => w.changeView("research")}
            onInsights={openInsights}
          onReport={w.openReport}
        />
        {w.newMessages && (
          <button
            className="new-message-notice"
            onClick={() => {
              if (w.reader.current)
                w.reader.current.scrollTop = w.reader.current.scrollHeight;
              w.setNewMessages(false);
            }}
          >
            查看最新消息 ↓
          </button>
        )}
        <ChatComposer
          draft={w.draft}
          onDraft={w.setDraft}
          file={w.file}
          onFileRemove={() => w.setFile(null)}
          onPick={w.pickFile}
          textarea={w.textarea}
          fileInput={w.fileInput}
          onSend={w.send}
          busy={w.busy}
          disabled={
            w.busy || !w.boot || !!w.error || w.loading || !!w.research?.active
          }
          feedback={
            w.research?.active
              ? "研究后台执行中；可查看步骤、暂停或取消。"
              : w.feedback
          }
          metric={metric}
          onBind={w.openBinding}
          hasChat={!!w.chatId}
          onConfigure={w.openConfigure}
          hasData={!!study}
        />
      </AppShell>
      {w.options && (
        <div className="modal-backdrop">
          <section
            className="binding-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="binding-title"
          >
            <header>
              <h2 id="binding-title">关联已有研究</h2>
              <button
                className="icon-button"
                aria-label="关闭研究选择"
                onClick={() => w.setOptions(null)}
              >
                <Icon name="close" />
              </button>
            </header>
            <p>选择来源可核验的研究。原消息保留发送时的绑定。</p>
            <select
              aria-label="选择研究任务"
              value={w.selectedStudy}
              onChange={(e) => w.setSelectedStudy(e.target.value)}
            >
              <option value="">请选择研究任务</option>
              {w.options.map((x) => (
                <option
                  key={x.domain + x.id}
                  value={x.domain + ":" + x.id}
                  disabled={!x.available}
                >
                  {x.title}
                  {x.metric ? " · " + x.metric : ""}
                  {!x.available ? "（来源待核对）" : ""}
                </option>
              ))}
            </select>
            <p className="small muted">
              关联不批准、不执行，也不覆盖历史报告。
            </p>
            <button
              className="primary"
              disabled={!w.selectedStudy || w.binding}
              onClick={w.bindStudy}
            >
              {w.binding ? "正在核验…" : "确认关联"}
            </button>
          </section>
        </div>
      )}
    </>
  );
}
