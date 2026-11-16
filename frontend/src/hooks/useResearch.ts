import { useEffect, useRef, useState } from "react";
import {
  request,
  key,
  ApiError,
  type Chat,
  type Report,
  type ResearchView,
  type ResearchAction,
} from "../api";
export function shouldPollResearch(v:ResearchView|null){return !!v&&(v.active||['running','pause_requested','cancel_requested'].includes(v.task.status)||(v.task.status==='approved'&&v.jobs.length>0));}
export function useResearch(
  chat: Chat | null,
  chatId: string | null,
  onRefresh: (id: string) => Promise<unknown>,
  onSourceError: (e: unknown, id: string | null) => boolean,
) {
  const [research, setResearch] = useState<ResearchView | null>(null),
    [completion, setCompletion] = useState<Report | null>(null),
    [researchError, setResearchError] = useState(""),
    [researchBusy, setResearchBusy] = useState(false),
    [researchNotice, setResearchNotice] = useState("");
  const active = useRef(chatId),
    epoch = useRef(0),
    readSequence = useRef(0),
    pending = useRef<{ signature: string; body: object } | null>(null),
    requestRunning = useRef(false),
    refresh = useRef(onRefresh),
    reject = useRef(onSourceError);
  active.current = chatId;
  refresh.current = onRefresh;
  reject.current = onSourceError;
  const task = chat?.study?.domain === "automation_v2" ? chat.study.id : null;
  async function load(id: string, version: number) {
    const sequence = ++readSequence.current;
    const v = await request<ResearchView>("/chats/" + id + "/research");
    if (
      active.current !== id ||
      epoch.current !== version ||
      sequence !== readSequence.current
    )
      return null;
    setResearch(v);
    setResearchError("");
    if (v.task.status === "completed") {
      const r = await request<Report>("/chats/" + id + "/report");
      if (
        active.current === id &&
        epoch.current === version &&
        r.task_id === v.task.id &&
        sequence === readSequence.current
      )
        setCompletion(r);
    } else setCompletion(null);
    return v;
  }
  useEffect(() => {
    epoch.current++;
    const version = epoch.current;
    setResearch(null);
    setCompletion(null);
    setResearchError("");
    setResearchNotice("");
    pending.current = null;
    if (!chatId || !task) return;
    const id = chatId;
    let disposed = false,
      timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const v = await load(id, version);
        if (disposed || !v) return;
        if (
          chat?.binding?.id !== v.binding_id ||
          chat?.study?.status !== v.task.status
        )
          await refresh.current(id);
      } catch (e) {
        if (!disposed && active.current === id && epoch.current === version) {
          if (e instanceof ApiError && e.code === "research_updating") {
            setResearchNotice("状态正在发布，等待下一份已核验快照。");
            timer = setTimeout(poll, 1000);
            return;
          }
          setResearch(null);
          setCompletion(null);
          setResearchError((e as Error).message);
          reject.current(e, id);
        }
      }
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [chatId, task]);
  async function refreshResearch() {
    if (!chatId) return;
    const id = chatId,
      version = epoch.current;
    try {
      await load(id, version);
      await refresh.current(id);
    } catch (e) {
      if (active.current === id) {
        if (e instanceof ApiError && e.code === "research_updating") {
          setResearchNotice("状态正在发布，请稍后刷新。");
          return;
        }
        setResearch(null);
        setCompletion(null);
        setResearchError((e as Error).message);
        reject.current(e, id);
      }
    }
  }
  async function researchAction(action: ResearchAction) {
    if (!chatId || !research || requestRunning.current) return;
    const id = chatId,
      version = epoch.current;
    requestRunning.current = true;
    setResearchBusy(true);
    setResearchError("");
    setResearchNotice("正在核验当前方案与授权…");
    const signature = JSON.stringify({
      id,
      action,
      binding: research.binding_id,
      task: research.task.id,
      review: research.review_sha,
    });
    if (pending.current?.signature !== signature)
      pending.current = {
        signature,
        body: {
          task_id: research.task.id,
          expected_binding_id: research.binding_id,
          expected_plan_sha: research.task.plan_sha,
          expected_review_sha: research.review_sha,
          human_confirmed: true,
          request_key: key(),
        },
      };
    try {
      await request("/chats/" + id + "/research/" + action, {
        method: "POST",
        body: JSON.stringify(pending.current.body),
      });
      pending.current = null;
      if (active.current === id && epoch.current === version) {
        await load(id, version);
        await refresh.current(id);
        setResearchNotice(
          {
            approve: "正式批准已保存；尚未启动统计，请单独点击开始。",
            start: "启动请求已保存；进度来自后台持久化步骤。",
            pause: "暂停请求已保存；若已有步骤在运行，将在安全边界停止。",
            cancel: "取消请求已保存；保留已有结果，不再派发新步骤。",
            resume: "已提交核查恢复；服务将先调和已有Run和授权。",
          }[action],
        );
      }
    } catch (e) {
      if (active.current === id && epoch.current === version) {
        setCompletion(null);
        setResearchError((e as Error).message);
        setResearchNotice("操作未确认完成；先刷新核查，未自动重发。");
        reject.current(e, id);
        try {await refresh.current(id);} catch(readError) {setResearch(null);reject.current(readError,id);}
      }
    } finally {
      requestRunning.current = false;
      setResearchBusy(false);
    }
  }
  // Explicit operation starts another polling cycle without changing the task binding.
  useEffect(() => {
    if (!shouldPollResearch(research) || !chatId) return;
    const id = chatId,
      version = epoch.current;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const v = await load(id, version);
        if (!v) return;
        await refresh.current(id);
        if (!stopped && shouldPollResearch(v)) timer = setTimeout(tick, 1200);
      } catch (e) {
        if (!stopped && active.current === id) {
          if (e instanceof ApiError && e.code === "research_updating") {
            setResearchNotice("状态正在发布，当前显示上次核验快照。");
            timer = setTimeout(tick, 1000);
            return;
          }
          setResearch(null);
          setCompletion(null);
          setResearchError((e as Error).message);
          reject.current(e, id);
        }
      }
    }
    timer = setTimeout(tick, 1000);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [shouldPollResearch(research), chatId]);
  return {
    research,
    completion,
    researchError,
    researchBusy,
    researchNotice,
    researchAction,
    refreshResearch,
  };
}
