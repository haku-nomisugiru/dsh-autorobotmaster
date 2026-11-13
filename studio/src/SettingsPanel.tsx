import { useEffect, useState } from "react";
import {
  X,
  ArrowLeft,
  Plug,
  MessageSquare,
  BookOpen,
  Palette,
  Check,
  LoaderCircle,
  Upload,
  FolderOpen,
  Search,
  Save,
  Database,
  FileText,
  ExternalLink,
  ArrowUpRight,
} from "lucide-react";
import { call, native } from "./bridge";
import {
  stages,
  type Snapshot,
  type Settings,
  type Skill,
  type Stage,
} from "./types";
import { RichText } from "./App";
import { MechanicalArt } from "./MechanicalArt";
const sections = [
  { id: "connections", name: "连接与模型", Icon: Plug },
  { id: "workspace", name: "模型工作区", Icon: FolderOpen },
  { id: "prompts", name: "工作流提示词", Icon: MessageSquare },
  { id: "skills", name: "Skills 与记忆", Icon: BookOpen },
  { id: "appearance", name: "主题与字体", Icon: Palette },
];
export function SettingsPanel({
  data,
  busy,
  onClose,
  onUpdate,
  notify,
}: {
  data: Snapshot;
  busy: boolean;
  onClose: () => void;
  onUpdate: (d: Snapshot) => void;
  notify: (text: string, error?: boolean) => void;
}) {
  const [page, setPage] = useState("connections");
  const [draft, setDraft] = useState<Settings>(structuredClone(data.settings));
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState("");
  const [checkResult, setCheckResult] = useState<Record<string, string>>({});
  const [prompt, setPrompt] = useState<Stage>("requirements");
  const [selected, setSelected] = useState<Skill | null>(null);
  const [skillFilter, setSkillFilter] = useState("");
  const [editing, setEditing] = useState(false);
  const blocked = busy || saving || !!checking;
  useEffect(() => {
    document.documentElement.dataset.theme = draft.theme;
    document.documentElement.dataset.font = draft.font;
  }, [draft.theme, draft.font]);
  useEffect(() => {
    const old = document.activeElement as HTMLElement;
    document.querySelector<HTMLElement>(".settings-close")?.focus();
    return () => old?.focus();
  }, []);
  const change = <K extends keyof Settings>(field: K, value: Settings[K]) =>
    setDraft((s) => ({ ...s, [field]: value }));
  const save = async (close = false) => {
    if (blocked) return;
    setSaving(true);
    try {
      const next = await call<Snapshot>("save_settings", {
        settings: draft,
        apiKey: key || null,
      });
      onUpdate(next);
      setDraft(next.settings);
      setKey("");
      notify(
        draft.modelWorkspace !== data.settings.modelWorkspace
          ? native
            ? "设置已保存，后续模型读写将使用新的工作区"
            : "工作区偏好已保存；目录读写检查需使用桌面版"
          : "设置已保存",
      );
      if (close) onClose();
      return next;
    } catch (e) {
      notify(String(e), true);
    } finally {
      setSaving(false);
    }
  };
  const check = async (kind: string) => {
    const next = await save();
    if (!next) return;
    setChecking(kind);
    setCheckResult((r) => ({ ...r, [kind]: "正在连接…" }));
    try {
      const result = await call<{ message: string }>("check_connection", {
        kind,
      });
      setCheckResult((r) => ({ ...r, [kind]: result.message }));
      notify(result.message);
    } catch (e) {
      setCheckResult((r) => ({ ...r, [kind]: String(e) }));
      notify(String(e), true);
    } finally {
      setChecking("");
    }
  };
  const updateSkill = async (skill: Skill) => {
    try {
      onUpdate(await call<Snapshot>("save_skill", { skill }));
      setSelected(skill);
      setEditing(false);
      notify("skill 已保存");
    } catch (e) {
      notify(String(e), true);
    }
  };
  const chooseWorkspace = async () => {
    setChecking("workspace");
    try {
      const path = await call<string | null>("choose_model_workspace", {
        initial: draft.modelWorkspace || data.modelWorkspaceDir,
      });
      if (path) {
        change("modelWorkspace", path);
        notify("已选择文件夹，保存设置后生效");
      }
    } catch (e) {
      notify(String(e), true);
    } finally {
      setChecking("");
    }
  };
  return (
    <div
      className="settings-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="设置"
      onKeyDown={(e) => {
        if (e.key === "Tab") {
          const items = Array.from(
            e.currentTarget.querySelectorAll<HTMLElement>(
              'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
            ),
          ).filter((x) => x.offsetParent !== null);
          const first = items[0],
            last = items.at(-1);
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last?.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first?.focus();
          }
        }
      }}
    >
      <div className="settings-header">
        <button className="plain settings-close" onClick={onClose}>
          <ArrowLeft size={17} />
          返回工作区
        </button>
        <span className="eyebrow">STUDIO PREFERENCES</span>
        <button className="icon-button" aria-label="关闭设置" onClick={onClose}>
          <X size={21} />
        </button>
      </div>
      <div className="settings-layout">
        <aside className="settings-nav">
          <h1>
            SETTINGS<span className="sr-only">设置</span>
          </h1>
          <nav>
            {sections.map((s) => (
              <button
                key={s.id}
                className={page === s.id ? "active" : ""}
                onClick={() => {
                  setPage(s.id);
                  setSelected(null);
                }}
              >
                <s.Icon size={17} />
                {s.name}
                <span aria-hidden="true">↗</span>
              </button>
            ))}
          </nav>
          <div className="settings-nav-foot">
            <span className="brand-star">✳</span>
            <span>
              RoboMaster Studio<small>LOCAL FIRST · 0.1.0</small>
            </span>
          </div>
          <div className="settings-art">
            <MechanicalArt variant="control" />
          </div>
        </aside>
        <section className="settings-content" key={page}>
          {page === "connections" && (
            <>
              <div className="settings-page-heading">
                <p className="eyebrow">01 / CONNECTIONS</p>
                <h2>连接</h2>
              </div>
              <div className="settings-section">
                <div className="section-heading">
                  <h3>
                    <Plug size={17} />
                    模型连接
                  </h3>
                  <span className="subtle-tag">
                    {data.settings.protocol === "codex" ? "Codex 本机登录" : data.settings.hasApiKey ? "凭据已保存" : "尚未配置"}
                  </span>
                </div>
                <div className="form-grid">
                  <label>
                    接入方式
                    <select
                      value={draft.protocol}
                      onChange={(e) => change("protocol", e.target.value)}
                      disabled={blocked}
                    >
                      <option value="chat_completions">
                        Chat Completions 兼容
                      </option>
                      <option value="responses">Responses API</option>
                      <option value="codex">Codex · 本机登录</option>
                    </select>
                  </label>
                  <label>
                    模型 ID
                    <input
                      placeholder={draft.protocol === "codex" ? "留空使用 Codex 默认模型" : "填写服务商可用的模型 ID"}
                      value={draft.model}
                      onChange={(e) => change("model", e.target.value)}
                      disabled={blocked}
                    />
                  </label>
                  {draft.protocol === "codex" ? <label className="full-width">
                    Codex 程序路径
                    <input value={draft.codexPath || ""} onChange={(e) => change("codexPath", e.target.value)} disabled={blocked} placeholder="自动查找 codex.exe · 也可输入完整路径" />
                    <small>复用 Codex 登录 · 模型调用计入当前 Codex 账户</small>
                  </label> : <><label className="full-width">
                    API 基础地址
                    <input
                      value={draft.endpoint}
                      onChange={(e) => change("endpoint", e.target.value)}
                      disabled={blocked}
                      placeholder="https://api.example.com/v1"
                    />
                  </label>
                  <label className="full-width">
                    API Key
                    <input
                      type="password"
                      autoComplete="off"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      disabled={blocked || !native}
                      placeholder={
                        data.settings.hasApiKey
                          ? "已保存 · 留空保留现有凭据"
                          : "输入 API Key"
                      }
                    />
                    <small>Windows 凭据库保存 · 对话发送至所选模型服务</small>
                  </label>
                  </>}
                </div>
                <div className="connection-actions">
                  <button
                    className="secondary"
                    disabled={blocked}
                    onClick={() => void check("api")}
                  >
                    {checking === "api" ? (
                      <LoaderCircle size={14} className="spin" />
                    ) : (
                      <Plug size={14} />
                    )}
                    保存并测试模型
                  </button>
                  <small>会发送一次简短请求</small>
                </div>
                {checkResult.api && (
                  <p className="connection-result">{checkResult.api}</p>
                )}
              </div>
              <div className="settings-section">
                <div className="section-heading">
                  <h3>
                    <Database size={17} />
                    SolidWorks MCP
                  </h3>
                  <button
                    className="text-link"
                    onClick={() =>
                      void call("open_external", {
                        url: "https://github.com/wzyn20051216/solidworks-automation-skill",
                      })
                    }
                  >
                    上游项目
                    <ExternalLink size={12} />
                  </button>
                </div>
                <label>
                  Python 解释器
                  <input
                    value={draft.mcpPython}
                    onChange={(e) => change("mcpPython", e.target.value)}
                    disabled={blocked}
                    placeholder="C:\Projects\solidworks-automation-skill\.venv\Scripts\python.exe"
                  />
                </label>
                <label>
                  MCP 服务入口
                  <input
                    value={draft.mcpServer}
                    onChange={(e) => change("mcpServer", e.target.value)}
                    disabled={blocked}
                    placeholder="C:\Projects\solidworks-automation-skill\mcp-server\server.py"
                  />
                </label>
                <button
                  className="secondary"
                  disabled={blocked}
                  onClick={() => void check("mcp")}
                >
                  {checking === "mcp" ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Plug size={14} />
                  )}
                  保存并连接 / 重连 MCP
                </button>
                {checkResult.mcp && (
                  <p className="connection-result">{checkResult.mcp}</p>
                )}
              </div>
              <div className="settings-section">
                <h3>
                  <Search size={17} />
                  本地 CAD RAG
                </h3>
                <label>
                  服务地址
                  <input
                    value={draft.ragUrl}
                    onChange={(e) => change("ragUrl", e.target.value)}
                    disabled={blocked}
                  />
                </label>
                <button
                  className="secondary"
                  disabled={blocked}
                  onClick={() => void check("rag")}
                >
                  {checking === "rag" ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Plug size={14} />
                  )}
                  保存并检查 RAG
                </button>
                {checkResult.rag && (
                  <p className="connection-result">{checkResult.rag}</p>
                )}
              </div>
              <div className="settings-section">
                <h3>运行与上下文</h3>
                <div className="form-grid">
                  <label>
                    单轮最大模型请求数
                    <input
                      type="number"
                      min={1}
                      max={80}
                      value={draft.maxRounds}
                      onChange={(e) =>
                        change("maxRounds", Number(e.target.value))
                      }
                      disabled={blocked}
                    />
                  </label>
                  <label className="toggle-label">
                    <span>自动整理长对话与验收经验</span>
                    <input
                      type="checkbox"
                      checked={draft.autoSummary}
                      disabled={blocked}
                      onChange={(e) => change("autoSummary", e.target.checked)}
                    />
                  </label>
                </div>
                <small>摘要与经验总结使用模型 API。</small>
              </div>
            </>
          )}
          {page === "workspace" && (
            <>
              <div className="settings-page-heading">
                <p className="eyebrow">02 / MODEL WORKSPACE</p>
                <h2>模型工作区</h2>
              </div>
              <div className="settings-section">
                <div className="section-heading">
                  <h3>
                    <FolderOpen size={17} />
                    读取与保存目录
                  </h3>
                  <span className="subtle-tag">所有项目共用</span>
                </div>
                <label>
                  模型工作区路径
                  <input
                    value={draft.modelWorkspace}
                    onChange={(e) => change("modelWorkspace", e.target.value)}
                    disabled={blocked}
                    placeholder="D:\RoboMaster\CAD"
                    spellCheck={false}
                  />
                </label>
                <div className="workspace-actions">
                  <button
                    className="secondary"
                    disabled={blocked}
                    onClick={() => void chooseWorkspace()}
                  >
                    {checking === "workspace" ? (
                      <LoaderCircle size={14} className="spin" />
                    ) : (
                      <FolderOpen size={14} />
                    )}
                    选择文件夹
                  </button>
                  <button
                    className="text-link"
                    disabled={blocked || !draft.modelWorkspace}
                    onClick={() => change("modelWorkspace", "")}
                  >
                    恢复默认目录
                  </button>
                </div>
                <small>
                  填写完整路径。目录不存在时创建；留空使用项目默认目录。
                </small>
              </div>
              <div className="settings-section">
                <div className="section-heading">
                  <h3>当前生效目录</h3>
                  <button
                    className="text-link"
                    disabled={blocked}
                    onClick={() =>
                      void call("open_model_workspace").catch((e) =>
                        notify(String(e), true),
                      )
                    }
                  >
                    打开目录 <ExternalLink size={12} />
                  </button>
                </div>
                <p className="workspace-location">{data.modelWorkspaceDir}</p>
                {draft.modelWorkspace !== data.settings.modelWorkspace && (
                  <p className="connection-result">
                    路径已修改，点击右下角「保存设置」后生效。
                  </p>
                )}
                <small>用于模型读写与下载；已有文件不迁移。</small>
                {!native && (
                  <p className="connection-result">
                    浏览器仅预览路径；实际读写请使用桌面版。
                  </p>
                )}
              </div>
            </>
          )}
          {page === "prompts" && (
            <>
              <div className="settings-page-heading">
                <p className="eyebrow">03 / WORKFLOW PROMPTS</p>
                <h2>工作流提示词</h2>
              </div>
              <div className="prompt-tabs">
                {stages.map((s) => (
                  <button
                    key={s.key}
                    className={s.key === prompt ? "active" : ""}
                    onClick={() => setPrompt(s.key)}
                  >
                    {s.short}
                  </button>
                ))}
              </div>
              <div className="prompt-editor">
                <div className="section-heading">
                  <h3>{stages.find((s) => s.key === prompt)?.title}</h3>
                  <span className="eyebrow">SYSTEM INSTRUCTION</span>
                </div>
                <textarea
                  aria-label="阶段提示词"
                  value={draft.prompts[prompt]}
                  onChange={(e) =>
                    change("prompts", {
                      ...draft.prompts,
                      [prompt]: e.target.value,
                    })
                  }
                  disabled={blocked}
                  spellCheck={false}
                />
                <p>
                  <FileText size={14} />
                  原型阶段仅开放外形建模工具。
                </p>
              </div>
            </>
          )}
          {page === "skills" && (
            <>
              <div className="settings-page-heading">
                <p className="eyebrow">04 / ACCUMULATED KNOWLEDGE</p>
                <h2>技能与记忆</h2>
              </div>
              {selected ? (
                <div className="skill-detail">
                  <div className="section-heading">
                    <button className="plain" onClick={() => setSelected(null)}>
                      <ArrowLeft size={14} />
                      返回技能库
                    </button>
                    <label className="toggle-label">
                      <span>启用此 skill</span>
                      <input
                        type="checkbox"
                        checked={selected.enabled}
                        disabled={blocked}
                        onChange={(e) =>
                          void updateSkill({
                            ...selected,
                            enabled: e.target.checked,
                          })
                        }
                      />
                    </label>
                  </div>
                  <h2>{selected.name}</h2>
                  <p className="muted">{selected.description}</p>
                  <div className="skill-meta">
                    <span className="subtle-tag">{selected.status}</span>
                    <span>{selected.source}</span>
                  </div>
                  {editing ? (
                    <>
                      <label>
                        名称
                        <input
                          value={selected.name}
                          onChange={(e) =>
                            setSelected({ ...selected, name: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        描述
                        <input
                          value={selected.description}
                          onChange={(e) =>
                            setSelected({
                              ...selected,
                              description: e.target.value,
                            })
                          }
                        />
                      </label>
                      <textarea
                        className="skill-body-editor"
                        value={selected.body}
                        onChange={(e) =>
                          setSelected({ ...selected, body: e.target.value })
                        }
                      />
                      <button
                        className="primary"
                        disabled={blocked || !selected.name.trim()}
                        onClick={() => void updateSkill(selected)}
                      >
                        <Save size={15} />
                        保存 skill
                      </button>
                    </>
                  ) : (
                    <>
                      <RichText text={selected.body} />
                      <button
                        className="secondary"
                        disabled={blocked}
                        onClick={() => setEditing(true)}
                      >
                        编辑内容
                      </button>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <div className="skill-toolbar">
                    <div className="search-inline">
                      <Search size={15} />
                      <input
                        aria-label="搜索技能"
                        value={skillFilter}
                        onChange={(e) => setSkillFilter(e.target.value)}
                        placeholder="按名称或描述查找 skill…"
                      />
                    </div>
                    <button
                      className="secondary"
                      disabled={blocked}
                      onClick={() =>
                        void call<Snapshot>("import_skill")
                          .then((d) => {
                            onUpdate(d);
                            notify("skill 已导入，请查看内容后启用");
                          })
                          .catch((e) => notify(String(e), true))
                      }
                    >
                      <Upload size={14} />
                      导入 SKILL.md
                    </button>
                  </div>
                  {data.skills.length ? (
                    <div className="skill-grid">
                      {data.skills
                        .filter((s) =>
                          (s.name + s.description)
                            .toLowerCase()
                            .includes(skillFilter.toLowerCase()),
                        )
                        .map((s) => (
                          <button
                            className="skill-card"
                            key={s.id}
                            onClick={() => {
                              setSelected(structuredClone(s));
                              setEditing(false);
                            }}
                          >
                            <div>
                              <BookOpen size={20} />
                              <span
                                className={`subtle-tag ${s.enabled ? "enabled" : ""}`}
                              >
                                {s.enabled ? "已启用" : "未启用"}
                              </span>
                            </div>
                            <h3>{s.name}</h3>
                            <p>{s.description}</p>
                            <span>
                              {s.status === "preference"
                                ? "用户选择"
                                : s.status === "imported"
                                  ? "外部导入"
                                  : "经验草稿"}
                              <ArrowUpRight size={15} />
                            </span>
                          </button>
                        ))}
                    </div>
                  ) : (
                    <div className="knowledge-empty">
                      <BookOpen size={35} strokeWidth={1} />
                      <h3>暂无 skill</h3>
                    </div>
                  )}
                  <div className="memory-section">
                    <div className="section-heading">
                      <h3>
                        <Database size={17} />
                        当前项目记忆
                      </h3>
                      <span className="count">{data.memories.length}</span>
                    </div>
                    {data.memories.length ? (
                      data.memories.map((m) => (
                        <div className="memory-item" key={m.id}>
                          <span className="subtle-tag">{m.kind}</span>
                          <p>{m.text}</p>
                        </div>
                      ))
                    ) : (
                      <p className="muted">暂无记忆</p>
                    )}
                  </div>
                  <div className="memory-section">
                    <h3>对话压缩摘要</h3>
                    {data.project.summary ? (
                      <RichText text={data.project.summary} />
                    ) : (
                      <p className="muted">暂无摘要</p>
                    )}
                    <button
                      className="secondary"
                      disabled={blocked}
                      onClick={() =>
                        void call<Snapshot>("summarize_project", {
                          mode: "context",
                        })
                          .then((d) => {
                            onUpdate(d);
                            notify(
                              d.project.summary
                                ? "对话摘要已更新"
                                : "当前历史较短，无需压缩",
                            );
                          })
                          .catch((e) => notify(String(e), true))
                      }
                    >
                      <FileText size={14} />
                      整理当前对话
                    </button>
                  </div>
                </>
              )}
              <button
                className="plain data-folder"
                onClick={() =>
                  void call("open_data_dir").catch((e) =>
                    notify(String(e), true),
                  )
                }
              >
                <FolderOpen size={15} />
                打开本地数据目录<span>{data.dataDir}</span>
              </button>
            </>
          )}
          {page === "appearance" && (
            <>
              <div className="settings-page-heading">
                <p className="eyebrow">05 / MAKE IT YOURS</p>
                <h2>主题与字体</h2>
              </div>
              <div className="settings-section">
                <h3>主题色</h3>
                <div className="theme-grid">
                  {[
                    {
                      id: "night",
                      name: "墨夜 · Graphite",
                      colors: ["#101018", "#b9abff", "#e9e8f3"],
                    },
                    {
                      id: "paper",
                      name: "研究白 · Research",
                      colors: ["#f3f3f5", "#3633f4", "#181827"],
                    },
                    {
                      id: "blue",
                      name: "蓝图 · Cobalt",
                      colors: ["#e9eef9", "#184cdc", "#172b51"],
                    },
                    {
                      id: "clay",
                      name: "陶土 · Terracotta",
                      colors: ["#f2eae2", "#9d563e", "#45362f"],
                    },
                  ].map((t) => (
                    <button
                      key={t.id}
                      className={`theme-card ${draft.theme === t.id ? "selected" : ""}`}
                      onClick={() => change("theme", t.id)}
                    >
                      <span
                        className="theme-preview"
                        style={{ background: t.colors[0] }}
                      >
                        <i style={{ background: t.colors[1] }} />
                        <b style={{ background: t.colors[2] }} />
                        <em style={{ background: t.colors[2] }} />
                      </span>
                      <span>
                        {t.name}
                        {draft.theme === t.id && <Check size={15} />}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="settings-section">
                <h3>界面字体</h3>
                <div className="font-options">
                  {[
                    {
                      id: "sans",
                      title: "OCR A + 思源黑体 · 默认",
                      desc: "OCR A Extended / Noto Sans SC Thin",
                      sample: "Aa 0123 结构",
                    },
                    {
                      id: "serif",
                      title: "人文宋体",
                      desc: "Georgia / 宋体",
                      sample: "Aa  结构与秩序",
                    },
                    {
                      id: "mono",
                      title: "工程等宽",
                      desc: "Consolas / 微软雅黑",
                      sample: "Aa  结构与秩序",
                    },
                  ].map((f) => (
                    <button
                      key={f.id}
                      className={`font-card font-${f.id} ${draft.font === f.id ? "selected" : ""}`}
                      onClick={() => change("font", f.id)}
                    >
                      <span>{f.sample}</span>
                      <strong>{f.title}</strong>
                      <small>{f.desc}</small>
                      {draft.font === f.id && <Check size={16} />}
                    </button>
                  ))}
                </div>
                {native &&
                  document.documentElement.dataset.interfaceFonts?.includes(
                    "fallback",
                  ) && (
                    <small className="font-load-note">
                      本机缺少部分默认字体，已使用回退字体。
                    </small>
                  )}
              </div>
            </>
          )}
        </section>
      </div>
      <div className="settings-footer">
        <span>
          {blocked ? "当前有操作正在进行" : "所有偏好保存在本机"}
          {!native && " · 浏览器预览"}
        </span>
        <div>
          <button className="secondary" onClick={onClose}>
            返回
          </button>
          <button
            className="primary"
            disabled={blocked}
            onClick={() => void save(true)}
          >
            {saving ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Check size={15} />
            )}
            保存设置
          </button>
        </div>
      </div>
    </div>
  );
}
