import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useResearch } from "./useResearch";
import {
  bootstrap,
  request,
  key,
  ApiError,
  type Session,
  type Chat,
  type StudyOption,
  type Report,
  type Artifacts,
  type Bootstrap,
  type SetupView,
  type BinaryConfig,
} from "../api";
export function useWorkspace() {
  type View = "chat" | "configure" | "candidate" | "report" | "research" | "insights";
  const initialView = new URLSearchParams(location.search).get("view");
  const [view, setView] = useState<View>(
    initialView === "configure" ||
      initialView === "candidate" ||
      initialView === "research" ||
      initialView === "insights"
      ? initialView
      : "chat",
  );
  const [setup, setSetup] = useState<SetupView | null>(null),
    [setupLoading, setSetupLoading] = useState(false),
    [setupBusy, setSetupBusy] = useState(false),
    [setupError, setSetupError] = useState("");
  const operationKeys = useRef<
    Record<string, { signature: string; key: string }>
  >({});
  const [boot, setBoot] = useState<Bootstrap | null>(null),
    [sessions, setSessions] = useState<Session[]>([]),
    [chatId, setChatId] = useState<string | null>(
      new URLSearchParams(location.search).get("chat") ||
        localStorage.getItem("co-chat"),
    );
  const [chat, setChat] = useState<Chat | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [search, setSearch] = useState(""),
    [panel, setPanel] = useState(false),
    [sidebar, setSidebar] = useState(false),
    [draft, setDraft] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [feedback, setFeedback] = useState(""),
    [newMessages, setNewMessages] = useState(false);
  const [options, setOptions] = useState<StudyOption[] | null>(null),
    [selectedStudy, setSelectedStudy] = useState(""),
    [binding, setBinding] = useState(false),
    [report, setReport] = useState<Report | null>(null),
    [reportError, setReportError] = useState(""),
    [artifacts, setArtifacts] = useState<Artifacts | null>(null),
    [artifactError, setArtifactError] = useState(""),
    [artifactLoading, setArtifactLoading] = useState(false),
    [showDemo, setShowDemo] = useState(false);
  const reader = useRef<HTMLDivElement>(null),
    textarea = useRef<HTMLTextAreaElement>(null),
    fileInput = useRef<HTMLInputElement>(null),
    active = useRef(chatId),
    generation = useRef(0),
    positions = useRef<Record<string, number>>({}),
    loaded = useRef(""),
    nearBottom = useRef(true),
    forceBottom = useRef(false),
    pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const study = chat?.study;
  active.current = chatId;
  function persistPosition() {
    if (active.current && reader.current)
      positions.current[active.current] = reader.current.scrollTop;
  }
  function rejectStaleSource(e: unknown, id: string | null) {
    if (
      active.current !== id ||
      !(e instanceof ApiError) ||
      !["source_conflict", "binding_changed", "not_found"].includes(e.code)
    )
      return false;
    generation.current++;
    setChat(null);
    setReport(null);
    setArtifacts(null);
    setOptions(null);
    setSetup(null);
    setView("chat");
    setError(e.message);
    return true;
  }
  function select(id: string | null) {
    persistPosition();
    generation.current++;
    setChat(null);
    setReport(null);
    setReportError("");
    setArtifacts(null);
    setArtifactError("");
    setOptions(null);
    setError("");
    setFeedback("");
    setChatId(id);
    setSidebar(false);
    setPanel(false);
    setDraft("");
    setFile(null);
    setSetup(null);
    setSetupError("");
    setView("chat");
    pending.current = null;
    const u = new URL(location.href);
    u.searchParams.delete("view");
    u.searchParams.delete("diagnostic");
    if (id) {
      u.searchParams.set("chat", id);
      localStorage.setItem("co-chat", id);
    } else {
      u.searchParams.delete("chat");
      localStorage.removeItem("co-chat");
    }
    history.replaceState({}, "", u);
  }
  async function refreshSessions() {
    const rows = await request<Session[]>("/chats");
    setSessions(rows);
  }
  useEffect(() => {
    bootstrap()
      .then((b) => {
        setBoot(b);
        return refreshSessions();
      })
      .catch((e) => setError(e.message));
  }, []);
  async function loadChat(id: string, signal?: AbortSignal) {
    const epoch = generation.current;
    const result = await request<Chat>("/chats/" + id, { signal });
    if (active.current === id && generation.current === epoch) {
      setChat(result);
      setError("");
    }
    return result;
  }
  function changeView(next: View) {
    persistPosition();
    loaded.current = "";
    setView(next);
    const u = new URL(location.href);
    if (next === "chat") u.searchParams.delete("view");
    else u.searchParams.set("view", next);
    history.replaceState({}, "", u);
  }
  async function loadSetup(id: string, signal?: AbortSignal) {
    const epoch = generation.current;
    const result = await request<SetupView>("/chats/" + id + "/setup", {
      signal,
    });
    if (active.current === id && generation.current === epoch) {
      setSetup(result);
      setSetupError("");
    }
    return result;
  }
  useEffect(() => {
    setSetup(null);
    setSetupError("");
    if (!chat?.study) return;
    const id = chat.session.id,
      controller = new AbortController();
    setSetupLoading(true);
    loadSetup(id, controller.signal)
      .catch((e) => {
        if (e.name !== "AbortError" && active.current === id) {
          rejectStaleSource(e, id);
          setSetupError(e.message);
        }
      })
      .finally(() => {
        if (active.current === id && !controller.signal.aborted)
          setSetupLoading(false);
      });
    return () => controller.abort();
  }, [chat?.session.id, chat?.binding?.id]);
  function operationKey(operation: string, body: unknown) {
    const signature = JSON.stringify(body);
    const old = operationKeys.current[operation];
    if (old?.signature === signature) return old.key;
    const value = { signature, key: key() };
    operationKeys.current[operation] = value;
    return value.key;
  }
  async function openConfigure() {
    if (!chatId || !chat?.study) {
      setFeedback("请先明确提交一份CSV/Parquet数据附件。");
      return;
    }
    changeView("configure");
    setSetupLoading(true);
    try {
      await loadSetup(chatId);
    } catch (e) {
      rejectStaleSource(e, chatId);
      setSetupError((e as Error).message);
    } finally {
      setSetupLoading(false);
    }
  }
  async function confirmContract(configuration: BinaryConfig) {
    if (!chatId || !setup) return;
    const id = chatId,
      epoch = generation.current;
    setSetupBusy(true);
    setSetupError("");
    try {
      const body = {
        configuration,
        expected_binding_id: setup.binding_id,
        expected_data_sha: setup.data.frame_sha,
        expected_contract_sha: setup.contract?.sha ?? null,
        human_confirmed: true,
      };
      await request("/chats/" + id + "/contract", {
        method: "POST",
        body: JSON.stringify({
          ...body,
          request_key: operationKey("contract", body),
        }),
      });
      if (active.current === id && generation.current === epoch) {
        await loadChat(id);
        await loadSetup(id);
        setFeedback("数据合同已保存，尚未生成批准或统计运行。");
      }
      await refreshSessions();
    } catch (e) {
      if (active.current === id) {
        rejectStaleSource(e, id);
        setSetupError((e as Error).message);
      }
    } finally {
      setSetupBusy(false);
    }
  }
  async function openCandidate() {
    if (!chatId) return;
    const id = chatId,
      epoch = generation.current;
    setSetupBusy(true);
    setSetupError("");
    try {
      const current = await loadSetup(id);
      if (!current.configuration) throw new Error("请先明确确认当前数据合同。");
      if (!current.candidate) {
        const body = {
          configuration_ref: current.configuration.id,
          expected_binding_id: current.binding_id,
        };
        await request("/chats/" + id + "/candidates", {
          method: "POST",
          body: JSON.stringify({
            ...body,
            request_key: operationKey("candidate", body),
          }),
        });
      }
      if (active.current === id && generation.current === epoch) {
        await loadSetup(id);
        changeView("candidate");
      }
    } catch (e) {
      if (active.current === id) {
        rejectStaleSource(e, id);
        setSetupError((e as Error).message);
      }
    } finally {
      setSetupBusy(false);
    }
  }
  async function adoptCandidate() {
    if (!chatId || !setup?.candidate) return;
    const id = chatId,
      epoch = generation.current;
    setSetupBusy(true);
    setSetupError("");
    try {
      const body = {
        expected_binding_id: setup.binding_id,
        human_confirmed: true,
      };
      await request(
        "/chats/" + id + "/candidates/" + setup.candidate.id + "/adopt",
        {
          method: "POST",
          body: JSON.stringify({
            ...body,
            request_key: operationKey("adoption", {
              ...body,
              candidate: setup.candidate.id,
            }),
          }),
        },
      );
      if (active.current === id && generation.current === epoch) {
        await loadChat(id);
        await loadSetup(id);
        setFeedback("采纳回执：当时仅形成待审方案，未授予批准或执行权限；当前进度见研究状态。");
        changeView("candidate");
      }
      await refreshSessions();
    } catch (e) {
      if (active.current === id) {
        rejectStaleSource(e, id);
        setSetupError((e as Error).message);
      }
    } finally {
      setSetupBusy(false);
    }
  }
  useEffect(() => {
    if (!boot || !chatId) return;
    const controller = new AbortController();
    setLoading(true);
    loadChat(chatId, controller.signal)
      .catch((e) => {
        if (e.name !== "AbortError" && active.current === chatId) {
          setChat(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (active.current === chatId) setLoading(false);
      });
    return () => controller.abort();
  }, [boot, chatId]);
  useEffect(() => {
    setArtifacts(null);
    setArtifactError("");
    setArtifactLoading(false);
    if (!panel || !chat?.study) return;
    setArtifactLoading(true);
    const id = chat.session.id,
      epoch = generation.current,
      c = new AbortController();
    request<Artifacts>("/chats/" + id + "/artifacts", { signal: c.signal })
      .then((v) => {
        if (active.current === id && generation.current === epoch)
          setArtifacts(v);
      })
      .catch((e) => {
        if (e.name !== "AbortError" && active.current === id) {
          rejectStaleSource(e, id);
          setArtifactError(e.message);
        }
      })
      .finally(() => {
        if (
          !c.signal.aborted &&
          active.current === id &&
          generation.current === epoch
        )
          setArtifactLoading(false);
      });
    return () => c.abort();
  }, [panel, chat?.session.id, chat?.binding?.id]);
  useLayoutEffect(() => {
    const el = reader.current;
    if (!el || !chat || view !== "chat") return;
    if (loaded.current !== chat.session.id) {
      el.scrollTop = positions.current[chat.session.id] ?? el.scrollHeight;
      loaded.current = chat.session.id;
      nearBottom.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    } else if (forceBottom.current || nearBottom.current) {
      el.scrollTop = el.scrollHeight;
      forceBottom.current = false;
      setNewMessages(false);
    } else setNewMessages(true);
  }, [chat, view]);
  useEffect(() => {
    const save = () => {
      if (active.current && reader.current)
        sessionStorage.setItem(
          "co-scroll-" + active.current,
          String(reader.current.scrollTop),
        );
    };
    window.addEventListener("beforeunload", save);
    return () => window.removeEventListener("beforeunload", save);
  }, []);
  useEffect(() => {
    if (chatId && positions.current[chatId] === undefined) {
      const n = sessionStorage.getItem("co-scroll-" + chatId);
      if (n !== null) positions.current[chatId] = Number(n);
    }
  }, [chatId]);
  async function newChat() {
    if (busy) return;
    setBusy(true);
    try {
      const c = await request<Session>("/chats", {
        method: "POST",
        body: JSON.stringify({ title: "新研究", request_key: key() }),
      });
      select(c.id);
      await refreshSessions();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function send() {
    if (busy || (!draft.trim() && !file) || !boot || error) return;
    setBusy(true);
    setFeedback("正在核验来源并保存本轮消息…");
    let id = chatId;
    const text = draft.trim(),
      attachment = file;
    try {
      if (!id) {
        const c = await request<Session>("/chats", {
          method: "POST",
          body: JSON.stringify({ title: "新研究", request_key: key() }),
        });
        select(c.id);
        id = c.id;
        active.current = id;
      }
      let bound = chat?.binding?.id ?? null;
      const fingerprint = JSON.stringify([
        id,
        bound,
        text,
        attachment?.name,
        attachment?.size,
        attachment?.lastModified,
      ]);
      if (pending.current?.fingerprint !== fingerprint)
        pending.current = { fingerprint, key: key() };
      const requestKey = pending.current.key;
      if (attachment) {
        const imported = await request<{ turn: { status: string } }>(
          "/chats/" + id + "/attachment",
          {
            method: "POST",
            headers: {
              "Content-Type": "application/octet-stream",
              "X-Filename": encodeURIComponent(attachment.name),
              "X-Request-Key": requestKey + ":file",
              "X-Expected-Binding": bound ?? "none",
            },
            body: attachment,
          },
        );
        const updated = await loadChat(id);
        bound = updated.binding?.id ?? null;
        if (imported.turn.status !== "completed")
          throw new Error("附件未通过登记，本轮文字未发送；旧研究保持不变。");
      }
      if (text)
        await request("/chats/" + id + "/messages", {
          method: "POST",
          body: JSON.stringify({
            question: text,
            request_key: requestKey + ":text",
            expected_binding_id: bound,
            mode: "local",
          }),
        });
      if (active.current === id) {
        setDraft("");
        setFile(null);
        pending.current = null;
        forceBottom.current = true;
        const updated = await loadChat(id);
        const last = updated.messages.at(-1);
        setFeedback(
          last?.status === "completed"
            ? "本轮已保存"
            : "本轮未完成，请查看保存的原因。",
        );
        textarea.current?.focus();
      }
      await refreshSessions();
    } catch (e) {
      if (active.current === id) {
        rejectStaleSource(e, id);
        setFeedback(
          (e as Error).message +
            " 若请求已发出，刷新核对后再重试，不会自动重发。",
        );
      }
    } finally {
      setBusy(false);
    }
  }
  async function openBinding() {
    try {
      setOptions(await request<StudyOption[]>("/studies"));
      setSelectedStudy("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function bindStudy() {
    if (!chatId || !selectedStudy) return;
    const id = chatId;
    const target = options?.find(
      (x) => x.domain + ":" + x.id === selectedStudy,
    );
    if (!target) return;
    setBinding(true);
    try {
      await request("/chats/" + id + "/binding", {
        method: "POST",
        body: JSON.stringify({
          domain: target.domain,
          subject_id: target.id,
          expected_binding_id: chat?.binding?.id ?? null,
        }),
      });
      if (active.current === id) {
        setOptions(null);
        await loadChat(id);
        setPanel(true);
      }
      await refreshSessions();
    } catch (e) {
      if (active.current === id) {
        rejectStaleSource(e, id);
        setFeedback((e as Error).message);
      }
    } finally {
      setBinding(false);
    }
  }
  async function openReport() {
    if (!chatId) return;
    const id = chatId,
      epoch = generation.current;
    setReportError("");
    setReport(null);
    try {
      const r = await request<Report>("/chats/" + id + "/report");
      if (active.current === id && generation.current === epoch) {
        setReport(r);
        changeView("report");
      }
    } catch (e) {
      if (active.current === id) {
        rejectStaleSource(e, id);
        setReportError((e as Error).message);
      }
    }
  }
  function pickFile(f: File | undefined) {
    if (!f) return;
    if (f.size > 20 * 1024 * 1024 || !/\.(csv|parquet)$/i.test(f.name)) {
      setFeedback("仅支持20MB以内的CSV/Parquet。");
      return;
    }
    setFile(f);
    setFeedback("附件尚未提交；导入后可在研究配置中确认数据合同。");
  }

  const researchState = useResearch(
    chat,
    chatId,
    async (id) => {
      await loadChat(id);
      await refreshSessions();
    },
    rejectStaleSource,
  );
  return {
    ...researchState,
    boot,
    sessions,
    chatId,
    chat,
    loading,
    error,
    search,
    setSearch,
    panel,
    setPanel,
    sidebar,
    setSidebar,
    draft,
    setDraft,
    file,
    setFile,
    busy,
    feedback,
    setFeedback,
    newMessages,
    setNewMessages,
    options,
    setOptions,
    selectedStudy,
    setSelectedStudy,
    binding,
    report,
    setReport,
    reportError,
    artifacts,
    artifactError,
    artifactLoading,
    showDemo,
    setShowDemo,
    reader,
    textarea,
    fileInput,
    active,
    generation,
    positions,
    loaded,
    nearBottom,
    forceBottom,
    select,
    refreshSessions,
    loadChat,
    newChat,
    send,
    openBinding,
    bindStudy,
    openReport,
    pickFile,
    rejectStaleSource,
    view,
    changeView,
    setup,
    setupLoading,
    setupBusy,
    setupError,
    openConfigure,
    confirmContract,
    openCandidate,
    adoptCandidate,
  };
}
