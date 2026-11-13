export type Stage =
  "requirements" | "reuse" | "prototype" | "modeling" | "mates";
export interface Tab {
  id: string;
  stage: Stage;
  ordinal: number;
  draft: string;
}
export interface Message {
  id: string;
  role: string;
  content: string;
  stage: Stage;
  createdAt: string;
}
export interface SpecItem {
  id: string;
  text: string;
  source: string;
}
export interface Spec {
  requirements: SpecItem[];
  verifiedParts: SpecItem[];
  assumptions: SpecItem[];
  relations: SpecItem[];
  acceptance: SpecItem[];
}
export interface Iteration {
  id: string;
  number: number;
  title: string;
  status: string;
  evidence: string;
  createdAt: string;
}
export interface Decision {
  callId: string;
  question: string;
  options: string[];
  context: string;
  stage: Stage;
}
export interface Project {
  id: string;
  name: string;
  tabs: Tab[];
  activeTab: string;
  messages: Message[];
  conversation: unknown[];
  spec: Spec;
  iterations: Iteration[];
  pending: Decision | null;
  summary: string;
  summarizedCount: number;
  updatedAt: string;
}
export interface Settings {
  endpoint: string;
  model: string;
  protocol: string;
  codexPath: string;
  mcpPython: string;
  mcpServer: string;
  ragUrl: string;
  modelWorkspace: string;
  theme: string;
  font: string;
  prompts: Record<Stage, string>;
  autoSummary: boolean;
  maxRounds: number;
  hasApiKey: boolean;
}
export interface Skill {
  id: string;
  name: string;
  description: string;
  body: string;
  source: string;
  status: string;
  enabled: boolean;
  updatedAt: string;
}
export interface Memory {
  id: string;
  text: string;
  kind: string;
  projectId: string;
  updatedAt: string;
}
export interface Snapshot {
  project: Project;
  projects: { id: string; name: string; updatedAt: string }[];
  settings: Settings;
  skills: Skill[];
  memories: Memory[];
  busy: boolean;
  dataDir: string;
  modelWorkspaceDir: string;
}
export const stages: {
  key: Stage;
  title: string;
  short: string;
  en: string;
  description: string;
}[] = [
  {
    key: "requirements",
    title: "确认组件需求",
    short: "需求",
    en: "DEFINE",
    description: "把想法说清楚，让每一个尺寸都有依据。",
  },
  {
    key: "reuse",
    title: "检索可复用组件",
    short: "检索",
    en: "DISCOVER",
    description: "从已有的设计出发，寻找值得复用的结构。",
  },
  {
    key: "prototype",
    title: "一次性原型机",
    short: "原型",
    en: "PROTOTYPE",
    description: "快速验证外形与空间，先让想法看得见。",
  },
  {
    key: "modeling",
    title: "建模与验收",
    short: "建模",
    en: "ITERATE",
    description: "建模、读取证据、修正，让结构逐轮成形。",
  },
  {
    key: "mates",
    title: "添加机械配合",
    short: "配合",
    en: "ASSEMBLE",
    description: "让独立的组件成为能够协同运动的机构。",
  },
];
export const specSections: { key: keyof Spec; name: string; hint: string }[] = [
  { key: "requirements", name: "用户明确要求", hint: "用途、空间、接口与约束" },
  {
    key: "verifiedParts",
    name: "已核实的零件信息",
    hint: "有来源支持的型号和尺寸",
  },
  { key: "assumptions", name: "暂定参数", hint: "待确认的尺寸与方案" },
  { key: "relations", name: "参数关系", hint: "尺寸依赖与几何关系" },
  { key: "acceptance", name: "验收条件", hint: "怎样判断这次设计已完成" },
];
