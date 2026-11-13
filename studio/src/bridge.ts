import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { Snapshot, Stage, Settings, Spec } from "./types";
import { stages } from "./types";
export const native = isTauri();
const key = "rm-studio-preview-v1";
const emptySpec = (): Spec => ({
  requirements: [],
  verifiedParts: [],
  assumptions: [],
  relations: [],
  acceptance: [],
});
const defaultSettings: Settings = {
  endpoint: "https://api.openai.com/v1",
  model: "",
  protocol: "chat_completions",
  codexPath: "",
  mcpPython: "",
  mcpServer: "",
  ragUrl: "http://127.0.0.1:8765",
  modelWorkspace: "",
  theme: "night",
  font: "sans",
  hasApiKey: false,
  autoSummary: true,
  maxRounds: 24,
  prompts: {
    requirements:
      "讨论用途、空间、接口与验收目标；维护结构化规格，不确定时让用户点选。",
    reuse: "先检索本地 CAD RAG 与 step.parts，明确证据和复用边界。",
    prototype: "只创建外形原型并读取包围盒，不进行任何测试或工程验收。",
    modeling: "逐轮建模、验收、修正并记录真实证据。",
    mates: "识别装配组件、选面与自由度，逐步添加机械配合，歧义时让用户点选。",
  },
};
function project(name: string) {
  const tabs = stages.map((s) => ({
    id: crypto.randomUUID(),
    stage: s.key,
    ordinal: 1,
    draft: "",
  }));
  return {
    id: crypto.randomUUID(),
    name,
    tabs,
    activeTab: tabs[0].id,
    messages: [],
    conversation: [],
    spec: emptySpec(),
    iterations: [],
    pending: null,
    summary: "",
    summarizedCount: 0,
    updatedAt: new Date().toISOString(),
  };
}
function initial(): Snapshot {
  const p = project("我的机械设计项目");
  return {
    project: p,
    projects: [{ id: p.id, name: p.name, updatedAt: p.updatedAt }],
    settings: defaultSettings,
    skills: [],
    memories: [],
    busy: false,
    dataDir: "浏览器界面预览 · 本地存储",
    modelWorkspaceDir: "桌面版默认项目目录",
  };
}
let preview: Snapshot;
try {
  preview = JSON.parse(localStorage.getItem(key) || "null") || initial();
} catch {
  preview = initial();
}
preview.settings = { ...defaultSettings, ...preview.settings };
preview.modelWorkspaceDir ??=
  preview.settings.modelWorkspace || "桌面版默认项目目录";
const previewProjects = new Map<string, Snapshot["project"]>([
  [preview.project.id, preview.project],
]);
export async function call<T>(
  command: string,
  args: Record<string, unknown> = {},
): Promise<T> {
  if (native) return invoke<T>(command, args);
  const p = preview.project;
  if (command === "bootstrap") return structuredClone(preview) as T;
  if (command === "edit_workspace") {
    const data = args.payload as Record<string, any>;
    switch (args.action) {
      case "add_tab": {
        const stage = data.stage as Stage;
        const ordinal =
          Math.max(
            ...p.tabs.filter((t) => t.stage === stage).map((t) => t.ordinal),
          ) + 1;
        const tab = { id: crypto.randomUUID(), stage, ordinal, draft: "" };
        p.tabs.push(tab);
        p.activeTab = tab.id;
        break;
      }
      case "close_tab": {
        const t = p.tabs.find((t) => t.id === data.id);
        if (!t || p.tabs.filter((x) => x.stage === t.stage).length === 1)
          throw Error("每种工作窗口至少保留一个");
        p.tabs = p.tabs.filter((x) => x.id !== t.id);
        if (p.activeTab === t.id)
          p.activeTab = p.tabs.find((x) => x.stage === t.stage)!.id;
        break;
      }
      case "select_tab":
        p.activeTab = data.id;
        break;
      case "draft":
        p.tabs.find((t) => t.id === data.id)!.draft = data.text;
        break;
      case "spec":
        p.spec = data as Spec;
        break;
      case "rename":
        p.name = data.name;
        break;
      case "new_project":
        previewProjects.set(p.id, structuredClone(p));
        preview.project = project(data.name || "新机械设计项目");
        preview.projects.unshift({
          id: preview.project.id,
          name: preview.project.name,
          updatedAt: preview.project.updatedAt,
        });
        break;
      case "switch_project":
        previewProjects.set(p.id, structuredClone(p));
        if (!previewProjects.has(data.id))
          throw Error("此预览项目需在同一次页面访问中打开");
        preview.project = structuredClone(previewProjects.get(data.id)!);
        break;
      default:
        throw Error("此功能需在 Rust 桌面版使用");
    }
  } else if (command === "save_settings") {
    if (args.apiKey) throw Error("浏览器预览不保存 API Key，请使用桌面版");
    const settings = args.settings as Settings;
    const path = settings.modelWorkspace.trim().replace(/^"|"$/g, "");
    if (path && !/^(?:[a-z]:[\\/]|\\\\[^\\]+\\[^\\]+)/i.test(path))
      throw Error("模型工作区需要完整的文件夹路径，例如 D:\\RoboMaster\\CAD");
    preview.settings = { ...settings, modelWorkspace: path, hasApiKey: false };
    preview.modelWorkspaceDir = path || "桌面版默认项目目录";
  } else if (command === "save_skill") {
    const skill = args.skill as Snapshot["skills"][number];
    preview.skills = preview.skills
      .filter((s) => s.id !== skill.id)
      .concat(skill);
  } else if (command === "open_external") {
    window.open(args.url as string, "_blank", "noopener,noreferrer");
    return undefined as T;
  } else
    throw Error(
      "当前为界面预览。模型 API、MCP、RAG 与记忆总结请在 Rust 桌面版中使用。",
    );
  localStorage.setItem(key, JSON.stringify(preview));
  return structuredClone(preview) as T;
}
export async function subscribe(
  fn: (event: { phase: string; projectId?: string }) => void,
) {
  if (!native) return () => {};
  return listen<{ phase: string; projectId?: string }>("agent-event", (e) =>
    fn(e.payload),
  );
}
