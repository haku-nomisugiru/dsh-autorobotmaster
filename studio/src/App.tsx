import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowUpRight,
  ArrowRight,
  Plus,
  X,
  Settings2,
  FolderOpen,
  ChevronDown,
  MessageSquare,
  Search,
  Box,
  Layers,
  Link2,
  Check,
  CheckCheck,
  LoaderCircle,
  Square,
  BookOpen,
  PanelRightClose,
  PanelRightOpen,
  SlidersHorizontal,
  Download,
  Command,
  Info,
  AlertCircle,
  Pencil,
  Trash2,
  ExternalLink,
} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { call, native, subscribe } from "./bridge";
import {
  stages,
  specSections,
  type Snapshot,
  type Stage,
  type Spec,
  type SpecItem,
} from "./types";
import { Robot } from "./Robot";
import { MechanicalArt, MechanicalHero } from "./MechanicalArt";
import { SettingsPanel } from "./SettingsPanel";
const icons = {
  requirements: MessageSquare,
  reuse: Search,
  prototype: Box,
  modeling: Layers,
  mates: Link2,
};
const statusNames: Record<string, string> = {
  running: "进行中",
  failed: "需修正",
  needs_review: "待审阅",
  passed: "证据已就绪",
  accepted: "人工验收通过",
};
export default function App() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [fatal, setFatal] = useState("");
  const [settings, setSettings] = useState(false);
  const [working, setWorking] = useState(false);
  const [phase, setPhase] = useState("");
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  const [showSpec, setShowSpec] = useState(true);
  const [allHistory, setAllHistory] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [projects, setProjects] = useState(false);
  const [projectDialog, setProjectDialog] = useState<"new" | "rename" | null>(
    null,
  );
  const [projectName, setProjectName] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notify = (text: string, error = false) => setToast({ text, error });
  const refresh = async () => {
    const d = await call<Snapshot>("bootstrap");
    setData(d);
    return d;
  };
  useEffect(() => {
    void refresh().catch((e) => setFatal(String(e)));
    let cleanup = () => {};
    let dead = false;
    void subscribe((e) => {
      setPhase(e.phase);
      void refresh();
    }).then((fn) => {
      if (dead) fn();
      else cleanup = fn;
    });
    return () => {
      dead = true;
      cleanup();
    };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.error ? 9000 : 4000);
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    if (data && !settings) {
      document.documentElement.dataset.theme = data.settings.theme;
      document.documentElement.dataset.font = data.settings.font;
    }
  }, [data?.settings.theme, data?.settings.font, settings]);
  useEffect(() => {
    const project = data?.project;
    const stage = project?.tabs.find(
      (tab) => tab.id === project.activeTab,
    )?.stage;
    if (
      project?.messages.some((message) => allHistory || message.stage === stage)
    ) {
      bottom.current?.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "nearest",
      });
    }
  }, [data?.project.messages.length, data?.project.pending]);
  useEffect(() => {
    scrollArea.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [data?.project.activeTab]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSettings(false);
        setProjects(false);
        setProjectDialog(null);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === ",") {
        e.preventDefault();
        setSettings((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  if (fatal)
    return (
      <div className="boot">
        <AlertCircle />
        <h2>工作区未能打开</h2>
        <pre>{fatal}</pre>
        <button onClick={() => location.reload()}>重新加载</button>
      </div>
    );
  if (!data)
    return (
      <div className="boot">
        <LoaderCircle className="spin" />
        <p>正在打开机械设计工作台…</p>
      </div>
    );
  const p = data.project;
  const active = p.tabs.find((t) => t.id === p.activeTab) || p.tabs[0];
  const stage = active.stage;
  const info = stages.find((s) => s.key === stage)!;
  const busy = working || data.busy;
  const draft = drafts[active.id] ?? active.draft;
  const messages = p.messages.filter((m) => allHistory || m.stage === stage);
  const edit = async (action: string, payload: unknown) => {
    try {
      if (draftTimer.current) {
        clearTimeout(draftTimer.current);
        draftTimer.current = null;
        await call("edit_workspace", {
          action: "draft",
          payload: { id: active.id, text: draft },
        });
      }
      const next = await call<Snapshot>("edit_workspace", { action, payload });
      setData(next);
      return next;
    } catch (e) {
      notify(String(e), true);
    }
  };
  const changeDraft = (text: string) => {
    setDrafts((d) => ({ ...d, [active.id]: text }));
    if (draftTimer.current) clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => {
      draftTimer.current = null;
      void call("edit_workspace", {
        action: "draft",
        payload: { id: active.id, text },
      }).catch((e) => notify(String(e), true));
    }, 500);
  };
  const send = async (text = draft, choice?: string) => {
    if (busy || (!text.trim() && !choice)) return;
    if (draftTimer.current) {
      clearTimeout(draftTimer.current);
      draftTimer.current = null;
    }
    setWorking(true);
    setPhase("thinking");
    try {
      const next = await call<Snapshot>("send_message", {
        text: choice ? null : text,
        choice: choice || null,
      });
      setData(next);
      setDrafts((d) => ({ ...d, [active.id]: "" }));
      notify(next.project.pending ? "需要你选择一个操作" : "本轮处理完成");
    } catch (e) {
      notify(String(e), true);
    } finally {
      setWorking(false);
      await refresh();
    }
  };
  const summarize = async () => {
    setWorking(true);
    try {
      setData(await call<Snapshot>("summarize_project", { mode: "skill" }));
      notify("经验已总结为 skill 草稿，可在设置中查看");
    } catch (e) {
      notify(String(e), true);
    } finally {
      setWorking(false);
    }
  };
  return (
    <div className="app-shell">
      <header className="app-header">
        <button
          className="brand"
          onClick={() =>
            void edit("select_tab", {
              id: p.tabs.find((t) => t.stage === "requirements")!.id,
            })
          }
          disabled={busy}
          aria-label="返回需求窗口"
        >
          <span className="brand-icon">
            <Robot small />
          </span>
          <span>
            <span className="brand-wordmark">
              ROBOMASTER<span className="brand-light"> STUDIO</span>
            </span>
            <small>DESIGN SYSTEM / MECHANICAL INTELLIGENCE</small>
          </span>
        </button>
        <div className="header-right">
          <span className="version">
            WORKBENCH <span>01</span>
          </span>
          <span
            className={`connection ${data.settings.hasApiKey ? "ready" : ""}`}
          >
            <i />
            {native
              ? data.settings.hasApiKey
                ? data.settings.protocol === "codex" ? "Codex 已检测" : "API 已配置"
                : "等待连接 API"
              : "界面预览"}
          </span>
          <button
            className="icon-button settings-trigger"
            onClick={() => setSettings(true)}
            aria-label="打开设置"
            title="设置 Ctrl+,"
          >
            <Settings2 size={19} />
          </button>
        </div>
      </header>
      <div className="project-row">
        <div className="project-picker">
          <button
            className="plain"
            onClick={() => setProjects(!projects)}
            disabled={busy}
          >
            <FolderOpen size={15} />
            <span>{p.name}</span>
            <ChevronDown size={14} />
          </button>
          {projects && (
            <div className="project-menu">
              {data.projects.map((x) => (
                <button
                  key={x.id}
                  onClick={() => {
                    void edit("switch_project", { id: x.id });
                    setProjects(false);
                  }}
                >
                  <FolderOpen size={14} />
                  <span>{x.name}</span>
                  {x.id === p.id && <Check size={14} />}
                </button>
              ))}
              <button
                onClick={() => {
                  setProjectDialog("new");
                  setProjectName("");
                  setProjects(false);
                }}
              >
                <Plus size={14} />
                新建项目
              </button>
              <button
                onClick={() => {
                  setProjectDialog("rename");
                  setProjectName(p.name);
                  setProjects(false);
                }}
              >
                <Pencil size={14} />
                重命名当前项目
              </button>
            </div>
          )}
        </div>
        <div className="project-meta">
          <span>
            <span className="tiny-dot" />
            本地自动保存
          </span>
          <span className="divider" />
          <span>
            共享对话 · {p.messages.filter((m) => m.role === "user").length}{" "}
            次交流
          </span>
          <button
            className="plain"
            onClick={() =>
              void call<string>("export_project")
                .then(() => notify("项目已导出"))
                .catch((e) => notify(String(e), true))
            }
            title="导出项目"
            aria-label="导出项目"
          >
            <Download size={15} />
          </button>
        </div>
      </div>
      <nav className="workflow-tabs" aria-label="设计工作窗口">
        {stages.map((s, i) => {
          const tabs = p.tabs.filter((t) => t.stage === s.key);
          const Icon = icons[s.key];
          return (
            <div
              key={s.key}
              className={`tab-group ${s.key === stage ? "current" : ""}`}
            >
              <div className="tab-group-top">
                <span className="step-index">
                  0{i + 1}
                  <span className="step-en">{s.en}</span>
                </span>
                <button
                  aria-label={`新建${s.title}窗口`}
                  title={`新建${s.title}窗口`}
                  className="add-tab"
                  disabled={busy}
                  onClick={() => void edit("add_tab", { stage: s.key })}
                >
                  <Plus size={14} />
                </button>
              </div>
              <div className="tab-instances">
                {tabs.map((t) => (
                  <div
                    className={`tab-item ${t.id === active.id ? "active" : ""}`}
                    key={t.id}
                  >
                    <button
                      role="tab"
                      aria-selected={t.id === active.id}
                      disabled={busy}
                      onClick={() => void edit("select_tab", { id: t.id })}
                    >
                      <Icon size={16} />
                      <span>
                        {s.title}
                        {t.ordinal > 1 && <sup>{t.ordinal}</sup>}
                      </span>
                    </button>
                    {tabs.length > 1 && (
                      <button
                        className="close-tab"
                        aria-label={`关闭${s.title}窗口 ${t.ordinal}`}
                        disabled={busy}
                        onClick={() => void edit("close_tab", { id: t.id })}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </nav>
      <main
        className={`workspace ${showSpec && stage === "requirements" ? "with-spec" : ""}`}
      >
        <section className="main-panel">
          <div className="panel-top">
            <div className="eyebrow">
              <span className="live-square" />
              {info.en}
              <span className="slash">/</span>WORKSPACE{" "}
              {String(stages.indexOf(info) + 1).padStart(2, "0")}
            </div>
            <div className="panel-tools">
              {stage !== "mates" && (
                <button
                  className={`plain ${allHistory ? "active-text" : ""}`}
                  onClick={() => setAllHistory(!allHistory)}
                  title="切换当前阶段与全部共享对话"
                >
                  <MessageSquare size={14} />
                  {allHistory ? "全部对话" : "当前阶段"}
                </button>
              )}
              {stage === "requirements" && (
                <button
                  className="icon-button"
                  aria-label={showSpec ? "隐藏规格" : "显示规格"}
                  onClick={() => setShowSpec(!showSpec)}
                >
                  {showSpec ? (
                    <PanelRightClose size={16} />
                  ) : (
                    <PanelRightOpen size={16} />
                  )}
                </button>
              )}
            </div>
          </div>
          <div className="workspace-scroll" ref={scrollArea}>
            <div className="stage-content" key={active.id}>
              {stage === "mates" ? (
                <div className="mates-view">
                  <MechanicalArt variant="drive" />
                  <p className="eyebrow">GIVE YOUR DESIGN MOTION</p>
                  <div className="mates-display" aria-hidden="true">
                    ASSEMBLE.
                    <br />
                    CONNECT.
                  </div>
                  <h1 className="sr-only">添加机械配合</h1>
                  <button
                    className="primary start-mates"
                    disabled={busy || !!p.pending}
                    onClick={() =>
                      void send(
                        "开始为当前装配体添加机械配合。遵循已确认规格与本阶段配合提示词。",
                      )
                    }
                  >
                    {busy ? (
                      <LoaderCircle className="spin" size={17} />
                    ) : (
                      <Link2 size={17} />
                    )}{" "}
                    {busy ? "正在添加机械配合…" : "开始"}{" "}
                    {!busy && <ArrowRight size={16} />}
                  </button>
                  {phase.startsWith("tool:") && busy && (
                    <span className="muted">{phase.slice(5)}</span>
                  )}
                  {p.messages
                    .filter(
                      (m) => m.stage === "mates" && m.role === "assistant",
                    )
                    .slice(-1)
                    .map((m) => (
                      <div className="mates-result" key={m.id}>
                        <RichText text={m.content} />
                      </div>
                    ))}
                </div>
              ) : (
                <>
                  {stage === "reuse" && (
                    <SearchPanel
                      busy={busy}
                      notify={notify}
                      onUse={(text) => void send(text)}
                    />
                  )}
                  {stage === "modeling" && (
                    <div className="iteration-panel">
                      <div className="iteration-banner">
                        <MechanicalArt variant="motor" />
                        <span className="eyebrow">
                          PROGRESS THROUGH ITERATION
                        </span>
                        <div className="banner-display">
                          BUILD. TEST. REFINE.
                        </div>
                      </div>
                      <div className="section-heading">
                        <div>
                          <p className="eyebrow">BUILD · OBSERVE · REFINE</p>
                          <h2>迭代记录</h2>
                        </div>
                        <button
                          className="secondary"
                          disabled={busy || !p.messages.length}
                          onClick={() => void summarize()}
                        >
                          <BookOpen size={15} />
                          总结为 skill
                        </button>
                      </div>
                      {p.iterations.length ? (
                        <div className="iterations">
                          {p.iterations.map((it) => (
                            <details
                              key={it.id}
                              className={`iteration ${it.status}`}
                              open={it.id === p.iterations.at(-1)?.id}
                            >
                              <summary>
                                <span className="iteration-num">
                                  {String(it.number).padStart(2, "0")}
                                </span>
                                <strong>{it.title}</strong>
                                <span className={`status-tag ${it.status}`}>
                                  {statusNames[it.status] || it.status}
                                </span>
                                <ChevronDown size={15} />
                              </summary>
                              <div className="iteration-evidence">
                                <RichText
                                  text={it.evidence || "等待本轮证据"}
                                />
                              </div>
                            </details>
                          ))}
                        </div>
                      ) : (
                        <div className="iteration-empty">
                          <Layers size={23} />
                          <p>等待第 01 轮</p>
                        </div>
                      )}
                      {["passed", "needs_review"].includes(
                        p.iterations.at(-1)?.status || "",
                      ) && (
                        <button
                          className="secondary accept-button"
                          disabled={busy}
                          onClick={async () => {
                            const next = await edit("accept", {});
                            if (next) {
                              notify("已记录人工验收");
                              if (next.settings.autoSummary) await summarize();
                            }
                          }}
                        >
                          <CheckCheck size={16} />
                          已审阅证据，验收本轮
                        </button>
                      )}
                    </div>
                  )}
                  {messages.length === 0 &&
                    stage !== "reuse" &&
                    stage !== "modeling" && (
                      <MechanicalHero prototype={stage === "prototype"} />
                    )}
                  {stage === "prototype" && (
                    <div className="scope-note">
                      <Info size={15} />
                      <span>外形原型 · 仅核对包络尺寸</span>
                    </div>
                  )}
                  {messages.length === 0 && stage === "requirements" && (
                    <div className="starter-list">
                      <span className="eyebrow">START A CONVERSATION</span>
                      {[
                        {
                          title: "设计一块电机安装板",
                          text: "我想设计一块电机安装板。先帮我梳理需要确认的接口、安装空间和验收要求。",
                          tag: "组件设计",
                        },
                        {
                          title: "讨论一个底盘方案",
                          text: "我想讨论一个 RoboMaster 轮式底盘方案。先梳理空间、重量、轮组、维护方式和验收目标，不要直接开始建模。",
                          tag: "方案探索",
                        },
                        {
                          title: "基于现有零件做设计",
                          text: "我想基于现有零件设计连接件。先列出需要提供或测量的零件信息，再检索可复用组件。",
                          tag: "复用优先",
                        },
                      ].map((x) => (
                        <button
                          key={x.title}
                          onClick={() => changeDraft(x.text)}
                          disabled={busy}
                        >
                          <span className="starter-title">{x.title}</span>
                          <span className="starter-tag">{x.tag}</span>
                          <ArrowUpRight size={17} />
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="messages" aria-live="polite">
                    {messages.map((m) =>
                      m.role === "tool" ? (
                        <details className="tool-message" key={m.id}>
                          <summary>
                            <Command size={13} />
                            {m.content.split("\n")[0]}
                            <ChevronDown size={13} />
                          </summary>
                          <pre>
                            {m.content.slice(m.content.indexOf("\n") + 1)}
                          </pre>
                        </details>
                      ) : (
                        <article key={m.id} className={`message ${m.role}`}>
                          <div className="message-label">
                            {m.role === "user" ? (
                              <>
                                <span className="avatar">你</span>你
                              </>
                            ) : m.role === "assistant" ? (
                              <>
                                <span className="avatar assistant-avatar">
                                  ✳
                                </span>
                                STUDIO
                              </>
                            ) : (
                              <>
                                <Info size={14} />
                                {m.role === "error"
                                  ? "操作未完成"
                                  : "工作区记录"}
                              </>
                            )}
                            {allHistory && (
                              <span className="message-stage">
                                {stages.find((s) => s.key === m.stage)?.short}
                              </span>
                            )}
                            <time>
                              {new Date(m.createdAt).toLocaleTimeString(
                                "zh-CN",
                                {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                },
                              )}
                            </time>
                          </div>
                          <RichText text={m.content} />
                        </article>
                      ),
                    )}
                    {busy && (
                      <div className="thinking">
                        <span className="thinking-dot" />
                        <span>
                          {phase.startsWith("tool:")
                            ? `正在执行 ${phase.slice(5)}`
                            : phase === "summarizing"
                              ? "正在整理对话记忆…"
                              : "正在理解需求与处理任务…"}
                        </span>
                      </div>
                    )}
                    <div ref={bottom} />
                  </div>
                </>
              )}
            </div>
          </div>
          {p.pending && (
            <DecisionCard
              pending={p.pending}
              disabled={busy}
              onChoice={(choice) => void send("", choice)}
            />
          )}
          {stage !== "mates" && (
            <div className="composer-area">
              {!data.settings.hasApiKey && (
                <button
                  className="setup-hint"
                  onClick={() => setSettings(true)}
                >
                  <span>
                    <span className="tiny-dot" />
                    {native
                      ? "连接模型 API"
                      : "浏览器预览 · CAD 操作请使用桌面版"}
                  </span>
                  <ArrowUpRight size={14} />
                </button>
              )}
              <div className={`composer ${busy ? "is-busy" : ""}`}>
                <textarea
                  aria-label="设计消息"
                  placeholder={
                    stage === "requirements"
                      ? "描述组件需求…"
                      : stage === "reuse"
                        ? "讨论候选零件…"
                        : stage === "prototype"
                          ? "描述原型形状与外形尺寸…"
                          : "描述建模目标或修改…"
                  }
                  value={draft}
                  disabled={busy || !!p.pending}
                  onChange={(e) => changeDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <span className="composer-mode">
                    <span className="mode-star">✳</span>
                    {info.title}
                    <span className="muted">/</span>
                    {data.settings.model || (data.settings.protocol === "codex" ? "Codex 默认模型" : "尚未选择模型")}
                  </span>
                  {busy ? (
                    <button
                      className="send-button stop"
                      aria-label="停止任务"
                      onClick={() =>
                        void call("cancel_run").then(() =>
                          notify(
                            "已请求停止；正在执行的 CAD 操作返回后停止后续步骤",
                          ),
                        )
                      }
                    >
                      <Square size={15} />
                    </button>
                  ) : (
                    <button
                      className="send-button"
                      aria-label="发送消息"
                      disabled={!draft.trim() || !!p.pending}
                      onClick={() => void send()}
                    >
                      <ArrowUp size={19} />
                    </button>
                  )}
                </div>
              </div>
              <div className="composer-caption">
                <span>
                  <Link2 size={11} />
                  共享上下文
                </span>
                <span>
                  Enter 发送 <span className="key-divider">·</span> Shift +
                  Enter 换行
                </span>
              </div>
            </div>
          )}
          {stage === "mates" && busy && (
            <div className="mates-stop">
              <button
                className="secondary"
                onClick={() =>
                  void call("cancel_run").then(() =>
                    notify("已请求停止后续操作"),
                  )
                }
              >
                <Square size={13} />
                停止后续操作
              </button>
            </div>
          )}
        </section>
        {showSpec && stage === "requirements" && (
          <SpecPanel
            spec={p.spec}
            disabled={busy}
            onSave={(spec) => void edit("spec", spec)}
            summary={p.summary}
          />
        )}
      </main>
      <footer className="app-footer">
        <span>
          <span className="footer-mark">✳</span> BUILT FOR THE NEXT ITERATION.
        </span>
        <div>
          <span>
            {data.skills.filter((s) => s.enabled).length} SKILLS ACTIVE
          </span>
          <span className="divider" />
          <span>{data.memories.length} MEMORIES</span>
          <span className="footer-local">LOCAL FIRST</span>
        </div>
      </footer>
      {settings && (
        <SettingsPanel
          data={data}
          busy={busy}
          onClose={() => setSettings(false)}
          onUpdate={setData}
          notify={notify}
        />
      )}
      {projectDialog && (
        <div className="modal-backdrop">
          <form
            className="small-dialog"
            onSubmit={async (e) => {
              e.preventDefault();
              const next = await edit(
                projectDialog === "new" ? "new_project" : "rename",
                { name: projectName },
              );
              if (next) setProjectDialog(null);
            }}
          >
            <div className="section-heading">
              <h2>
                {projectDialog === "new" ? "开始一个新项目" : "重命名项目"}
              </h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setProjectDialog(null)}
                aria-label="关闭"
              >
                <X size={18} />
              </button>
            </div>
            <label>
              项目名称
              <input
                autoFocus
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                maxLength={100}
                placeholder="例如：2027 步兵底盘"
                required
              />
            </label>
            <button className="primary" type="submit">
              {projectDialog === "new" ? "创建项目" : "保存名称"}
              <ArrowRight size={15} />
            </button>
          </form>
        </div>
      )}
      {toast && (
        <div className={`toast ${toast.error ? "error" : ""}`} role="status">
          {toast.error ? <AlertCircle size={18} /> : <Check size={18} />}
          <span>{toast.text}</span>
          <button onClick={() => setToast(null)} aria-label="关闭通知">
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
export function RichText({ text }: { text: string }) {
  return (
    <div className="markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <button
              className="text-link"
              onClick={() => {
                if (href) void call("open_external", { url: href });
              }}
            >
              {children}
              <ExternalLink size={11} />
            </button>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
function SpecPanel({
  spec,
  disabled,
  onSave,
  summary,
}: {
  spec: Spec;
  disabled: boolean;
  onSave: (spec: Spec) => void;
  summary: string;
}) {
  const [edit, setEdit] = useState<{
    section: keyof Spec;
    item: SpecItem;
  } | null>(null);
  const count = Object.values(spec).flat().length;
  return (
    <aside className="spec-panel">
      <div className="spec-heading">
        <div>
          <span className="eyebrow">LIVING DOCUMENT</span>
          <h2>
            结构化规格<span className="count">{count}</span>
          </h2>
        </div>
        <SlidersHorizontal size={17} />
      </div>
      <div className="spec-content">
        {specSections.map((section, i) => (
          <section className="spec-section" key={section.key}>
            <div className="spec-section-title">
              <span className="spec-index">0{i + 1}</span>
              <h3>{section.name}</h3>
              {section.key === "assumptions" && (
                <span className="assumption-dot" />
              )}
              <button
                className="icon-button"
                aria-label={`添加${section.name}`}
                disabled={disabled}
                onClick={() =>
                  setEdit({
                    section: section.key,
                    item: {
                      id: crypto.randomUUID(),
                      text: "",
                      source:
                        section.key === "requirements" ? "用户明确输入" : "",
                    },
                  })
                }
              >
                <Plus size={14} />
              </button>
            </div>
            {spec[section.key].length ? (
              spec[section.key].map((item) => (
                <button
                  key={item.id}
                  className="spec-item"
                  disabled={disabled}
                  onClick={() =>
                    setEdit({ section: section.key, item: { ...item } })
                  }
                >
                  <span className="item-marker">
                    {section.key === "verifiedParts" ? (
                      <Check size={12} />
                    ) : (
                      "—"
                    )}
                  </span>
                  <span>
                    {item.text}
                    {item.source && <small>{item.source}</small>}
                  </span>
                  <Pencil size={12} />
                </button>
              ))
            ) : (
              <p className="spec-placeholder" title={section.hint}>
                —
              </p>
            )}
          </section>
        ))}
        {summary && (
          <details className="summary-block">
            <summary>
              <BookOpen size={14} />
              项目摘要
              <ChevronDown size={14} />
            </summary>
            <RichText text={summary} />
          </details>
        )}
      </div>
      {edit && (
        <div className="modal-backdrop">
          <form
            className="small-dialog"
            onSubmit={(e) => {
              e.preventDefault();
              const list = spec[edit.section];
              const next = list.some((x) => x.id === edit.item.id)
                ? list.map((x) => (x.id === edit.item.id ? edit.item : x))
                : [...list, edit.item];
              onSave({ ...spec, [edit.section]: next });
              setEdit(null);
            }}
          >
            <div className="section-heading">
              <h2>{specSections.find((s) => s.key === edit.section)?.name}</h2>
              <button
                type="button"
                className="icon-button"
                aria-label="关闭规格编辑"
                onClick={() => setEdit(null)}
              >
                <X size={18} />
              </button>
            </div>
            <label>
              规格内容
              <textarea
                autoFocus
                required
                rows={4}
                value={edit.item.text}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    item: { ...edit.item, text: e.target.value },
                  })
                }
              />
            </label>
            <label>
              来源 / 证据{edit.section === "verifiedParts" && "（必填）"}
              <input
                value={edit.item.source}
                required={edit.section === "verifiedParts"}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    item: { ...edit.item, source: e.target.value },
                  })
                }
                placeholder="用户要求、实测结果或资料链接"
              />
            </label>
            <div className="dialog-actions">
              {spec[edit.section].some((x) => x.id === edit.item.id) && (
                <button
                  type="button"
                  className="danger plain"
                  onClick={() => {
                    onSave({
                      ...spec,
                      [edit.section]: spec[edit.section].filter(
                        (x) => x.id !== edit.item.id,
                      ),
                    });
                    setEdit(null);
                  }}
                >
                  <Trash2 size={15} />
                  删除条目
                </button>
              )}
              <button type="submit" className="primary">
                <Check size={15} />
                保存规格
              </button>
            </div>
          </form>
        </div>
      )}
    </aside>
  );
}
function DecisionCard({
  pending,
  disabled,
  onChoice,
}: {
  pending: NonNullable<Snapshot["project"]["pending"]>;
  disabled: boolean;
  onChoice: (x: string) => void;
}) {
  const [other, setOther] = useState("");
  return (
    <div className="decision-card">
      <div className="decision-title">
        <span className="decision-symbol">?</span>
        <div>
          <span className="eyebrow">需要你的判断</span>
          <h3>{pending.question}</h3>
        </div>
      </div>
      <p>{pending.context}</p>
      <div className="decision-options">
        {pending.options.map((x, i) => (
          <button key={i} disabled={disabled} onClick={() => onChoice(x)}>
            <span>{String(i + 1).padStart(2, "0")}</span>
            {x}
            <ArrowRight size={14} />
          </button>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (other.trim()) onChoice(other);
        }}
      >
        <input
          value={other}
          onChange={(e) => setOther(e.target.value)}
          placeholder="或输入你的处理方式…"
          disabled={disabled}
        />
        <button
          className="icon-button"
          aria-label="提交自定义选择"
          disabled={disabled || !other.trim()}
        >
          <ArrowUp size={17} />
        </button>
      </form>
    </div>
  );
}
function SearchPanel({
  busy,
  notify,
  onUse,
}: {
  busy: boolean;
  notify: (text: string, error?: boolean) => void;
  onUse: (text: string) => void;
}) {
  const [source, setSource] = useState("local");
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<Record<string, any>[] | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Record<string, any> | null>(null);
  const [downloading, setDownloading] = useState(false);
  const search = async () => {
    setSearching(true);
    setError("");
    setResults(null);
    try {
      const raw = await call<Record<string, any>>("search_parts", {
        source,
        query,
      });
      const rows =
        raw.items ??
        raw.parts ??
        raw.results ??
        raw.data ??
        (Array.isArray(raw) ? raw : null);
      if (!Array.isArray(rows)) throw Error("搜索响应格式未识别");
      setResults(rows);
    } catch (e) {
      setError(String(e));
    } finally {
      setSearching(false);
    }
  };
  return (
    <div className="search-panel">
      <div className="search-banner">
        <MechanicalArt variant="control" />
        <p className="eyebrow">DON’T REINVENT. REDISCOVER.</p>
        <div className="banner-display" aria-hidden="true">
          ALREADY BUILT.
          <br />
          READY TO ADAPT.
        </div>
        <h1 className="sr-only">检索可复用组件</h1>
      </div>
      <div className="search-sources">
        <button
          className={`source-card ${source === "local" ? "selected" : ""}`}
          onClick={() => {
            setSource("local");
            setResults(null);
            setError("");
          }}
        >
          <span className="source-icon">
            <Layers size={24} />
          </span>
          <span>
            <strong>本地 CAD RAG</strong>
          </span>
          <span className="radio-dot" />
        </button>
        <button
          className={`source-card ${source === "step" ? "selected" : ""}`}
          onClick={() => {
            setSource("step");
            setResults(null);
            setError("");
          }}
        >
          <span className="source-icon">
            <Box size={25} />
          </span>
          <span>
            <strong>
              step.parts <ArrowUpRight size={12} />
            </strong>
          </span>
          <span className="radio-dot" />
        </button>
      </div>
      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <Search size={18} />
        <input
          aria-label="组件检索词"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={256}
          placeholder={
            source === "local"
              ? "搜索机构功能、组件名称或型号…"
              : "Search parts, e.g. bearing, M3, motor…"
          }
        />
        <button className="primary" disabled={searching || !query.trim()}>
          {searching ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <>
              检索
              <ArrowRight size={15} />
            </>
          )}
        </button>
      </form>
      <div className="search-foot">
        <span>
          <Info size={12} />
          候选待核实
        </span>
        {source === "step" && (
          <button
            className="plain"
            onClick={() =>
              void call("open_external", {
                url: `https://www.step.parts/?q=${encodeURIComponent(query)}`,
              }).catch((e) => notify(String(e), true))
            }
          >
            在网站中打开
            <ExternalLink size={12} />
          </button>
        )}
      </div>
      {error && (
        <div className="inline-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
      {results && (
        <div className="search-results">
          <span className="eyebrow">{results.length} 个候选</span>
          {results.length === 0 ? (
            <p className="muted">
              没有找到匹配结果，试试型号或更具体的机构名称。
            </p>
          ) : (
            results.map((r, i) => (
              <button
                key={r.id || i}
                className="result-card"
                onClick={() => setSelected(r)}
              >
                <span className="result-number">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>
                  <strong>{r.name || r.title || r.id || "未命名组件"}</strong>
                  <small>
                    {r.description ||
                      r.summary ||
                      r.category ||
                      "查看原始资料与复用边界"}
                  </small>
                </span>
                <ArrowUpRight size={17} />
              </button>
            ))
          )}
        </div>
      )}
      {selected && (
        <div className="modal-backdrop">
          <div className="candidate-dialog">
            <div className="section-heading">
              <div>
                <p className="eyebrow">CANDIDATE · 待核实</p>
                <h2>{selected.name || selected.title || selected.id}</h2>
              </div>
              <button
                className="icon-button"
                aria-label="关闭候选详情"
                onClick={() => setSelected(null)}
              >
                <X size={19} />
              </button>
            </div>
            <div className="candidate-content">
              <p className="candidate-description">
                {selected.description ||
                  selected.summary ||
                  "该候选暂无说明，请核对来源资料。"}
              </p>
              <dl className="candidate-facts">
                <div>
                  <dt>来源</dt>
                  <dd>
                    {source === "local"
                      ? "本地 CAD RAG"
                      : "step.parts 开放目录"}
                  </dd>
                </div>
                <div>
                  <dt>组件类别</dt>
                  <dd>
                    {selected.category || selected.section_label || "未分类"}
                  </dd>
                </div>
                <div>
                  <dt>文件类型</dt>
                  <dd>{selected.entry?.extension?.toUpperCase() || "STEP"}</dd>
                </div>
                <div>
                  <dt>目标适配</dt>
                  <dd>待核实</dd>
                </div>
              </dl>
              {selected.attributes && (
                <div className="candidate-attributes">
                  {Object.entries(selected.attributes).map(([k, v]) => (
                    <span key={k}>
                      {k}
                      <strong>{String(v)}</strong>
                    </span>
                  ))}
                </div>
              )}
              {selected.limitations?.length > 0 && (
                <div className="candidate-limits">
                  <h3>复用前需要确认</h3>
                  <ul>
                    {selected.limitations.map((x: string, i: number) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </div>
              )}
              <details className="candidate-raw">
                <summary>查看完整来源与证据记录</summary>
                <pre>{JSON.stringify(selected, null, 2)}</pre>
              </details>
            </div>
            <div className="dialog-actions">
              {(selected.source?.url ||
                selected.productPage ||
                selected.pageUrl) && (
                <button
                  className="secondary"
                  onClick={() =>
                    void call("open_external", {
                      url:
                        selected.source?.url ||
                        selected.productPage ||
                        selected.pageUrl,
                    }).catch((e) => notify(String(e), true))
                  }
                >
                  原始来源
                  <ExternalLink size={13} />
                </button>
              )}
              {selected.id && (
                <button
                  className="secondary"
                  disabled={busy || downloading}
                  onClick={async () => {
                    setDownloading(true);
                    try {
                      const result = await call<{ path: string }>(
                        "download_part",
                        {
                          source,
                          partId: selected.id,
                          kind:
                            source === "local" &&
                            selected.entry?.extension?.toLowerCase() ===
                              ".sldasm"
                              ? "package"
                              : "file",
                        },
                      );
                      notify(`下载完成，文件指纹已核对：${result.path}`);
                    } catch (e) {
                      notify(String(e), true);
                    } finally {
                      setDownloading(false);
                    }
                  }}
                >
                  {downloading ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Download size={14} />
                  )}
                  下载工作副本
                </button>
              )}
              <button
                className="primary"
                disabled={busy || downloading}
                onClick={() => {
                  onUse(
                    `请评估这个 ${source === "local" ? "本地 CAD RAG" : "step.parts"} 候选的复用条件。它尚未核实，不要直接当作可用零件。候选资料：\n${JSON.stringify(selected)}`,
                  );
                  setSelected(null);
                }}
              >
                交给模型评估
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
