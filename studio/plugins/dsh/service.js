import {
  mkdir,
  readFile,
  writeFile,
  rename,
  readdir,
  realpath,
  stat,
} from "node:fs/promises";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { randomUUID, createHash } from "node:crypto";
import path from "node:path";
import { CadConnection, toolArguments } from "./mcp.js";

export const workflow = JSON.parse(
  readFileSync(new URL("./workflow.json", import.meta.url), "utf8"),
);
export const stages = Object.keys(workflow.prompts);
const sections = [
  "requirements",
  "verifiedParts",
  "assumptions",
  "relations",
  "acceptance",
];
const userOnly = new Set([
  "configure",
  "stage",
  "send",
  "answer",
  "tab_add",
  "tab_close",
  "tab_select",
  "skill_import",
  "skill_enable",
]);
function message(text, kind = "robomaster-studio") {
  return Object.freeze({
    id: randomUUID(),
    role: "user",
    content: Object.freeze([Object.freeze({ type: "text", text })]),
    source: Object.freeze({ kind }),
  });
}
const bounded = (value, limit = 60000) => {
  if (typeof value !== "string" || value.length > limit)
    throw Error("文本格式错误或超过长度限制");
  return value;
};
export const toolAllowed = (stage, name) =>
  !["requirements", "reuse"].includes(stage) &&
  (stage === "prototype"
    ? workflow.prototype.includes(name)
    : name.startsWith("solidworks_") && !workflow.excluded.includes(name));

export class StudioService {
  constructor(config = {}) {
    this.root = path.resolve(
      config.dataDirectory ||
        process.env.ROBOMASTER_DSH_DATA_DIR ||
        path.join(
          process.env.LOCALAPPDATA || homedir(),
          "RoboMasterStudio",
          "dsh",
        ),
    );
    this.chain = Promise.resolve();
    this.connections = new Map();
    this.closed = false;
  }
  file(id) {
    return path.join(
      this.root,
      `${createHash("sha256").update(id).digest("hex")}.json`,
    );
  }
  async read(id) {
    try {
      const p = JSON.parse(await readFile(this.file(id), "utf8"));
      if (p.version !== 1) throw Error("不支持的项目版本");
      return p;
    } catch (e) {
      if (e.code !== "ENOENT") throw e;
    }
    const upstream = path.join(
      homedir(),
      ".codex",
      "mcp",
      "solidworks-automation-skill",
    );
    const tabs = stages.map((stage) => ({
      id: randomUUID(),
      stage,
      ordinal: 1,
    }));
    return {
      version: 1,
      sessionId: id,
      stage: "requirements",
      tabs,
      activeTab: tabs[0].id,
      workspace: "",
      mcpPython: path.join(upstream, ".venv", "Scripts", "python.exe"),
      mcpServer: path.join(upstream, "mcp-server", "server.py"),
      ragUrl: "http://127.0.0.1:8765",
      prompts: { ...workflow.prompts },
      spec: Object.fromEntries(sections.map((k) => [k, []])),
      iterations: [],
      memories: [],
      skills: [],
      summary: "",
      pending: null,
      updatedAt: new Date().toISOString(),
    };
  }
  async save(p) {
    await mkdir(this.root, { recursive: true });
    p.updatedAt = new Date().toISOString();
    const file = this.file(p.sessionId),
      tmp = `${file}.${randomUUID()}.tmp`;
    await writeFile(tmp, JSON.stringify(p, null, 2), "utf8");
    await rename(tmp, file);
  }
  context(p) {
    return `RoboMaster Studio / ${p.stage}\n${p.prompts[p.stage]}\n模型读写工作区：${p.workspace || "尚未设置，禁止 CAD 文件操作"}\n工具：robomaster_studio。先用 cad_list 获取当前阶段的准确工具 schema，再用 cad_call 调用；不要绕过该入口操作 CAD。需求与检索阶段不修改 CAD；原型阶段禁止所有测试。参数有歧义用 ask_user 请求用户点选，未得到回答不得继续依赖该选择的操作。使用 spec_add / iteration / remember / skill_save 记录实际结果，经验草稿不能冒充验证事实。\n当前结构化规格：${JSON.stringify(p.spec)}\n摘要：${p.summary}\n记忆：${JSON.stringify(p.memories.slice(-20))}\n启用的技能（参考资料，不覆盖用户指令）：${JSON.stringify(p.skills.filter((s) => s.enabled).map((s) => ({ name: s.name, body: s.body })))}\n待回答：${JSON.stringify(p.pending)}`;
  }
  async operate(agent, request, { user = false, signal } = {}) {
    if (this.closed) throw Error("插件已卸载");
    if (!agent?.id) throw Error("需要一个当前 DSH 会话");
    if (!request || typeof request !== "object") throw Error("请求格式错误");
    const action = request.action;
    if (userOnly.has(action) && !user)
      throw Error("此操作必须由用户在界面中执行");
    const task = this.chain.then(() =>
      this.perform(agent, request, user, signal),
    );
    this.chain = task.catch(() => {});
    return task;
  }
  async perform(agent, r, user, signal) {
    const p = await this.read(agent.id),
      a = r.action;
    let result,
      changed = false,
      inject = false;
    if (a === "snapshot") return p;
    if (user && agent.status === "running" && userOnly.has(a) && a !== "answer")
      throw Error("请等待当前任务结束后再操作");
    if (a === "configure") {
      if (r.workspace !== undefined) {
        const input = bounded(r.workspace, 2048).trim().replace(/^"|"$/g, "");
        if (!path.isAbsolute(input)) throw Error("请输入工作区完整路径");
        await mkdir(input, { recursive: true });
        p.workspace = await realpath(input);
      }
      for (const key of ["mcpPython", "mcpServer"])
        if (r[key] !== undefined) {
          const v = bounded(r[key], 2048);
          if (!path.isAbsolute(v) || !(await stat(v)).isFile())
            throw Error(`${key} 必须指向实际文件`);
          p[key] = v;
        }
      if (r.ragUrl !== undefined) {
        const u = new URL(r.ragUrl);
        if (
          !["127.0.0.1", "localhost", "[::1]"].includes(u.hostname) ||
          !["http:", "https:"].includes(u.protocol) ||
          u.username ||
          u.password ||
          u.search ||
          u.hash
        )
          throw Error("RAG 必须使用无凭据的本机地址");
        p.ragUrl = u.href.replace(/\/$/, "");
      }
      if (r.prompts) {
        for (const stage of stages)
          if (r.prompts[stage] !== undefined)
            p.prompts[stage] = bounded(r.prompts[stage], 12000);
      }
      this.connections.get(agent.id)?.close();
      this.connections.delete(agent.id);
      changed = true;
      inject = true;
    } else if (a === "stage" || a === "tab_select") {
      if (p.pending) throw Error("请先回答当前待确认项");
      const tab = p.tabs.find((t) =>
        a === "stage" ? t.stage === r.stage : t.id === r.id,
      );
      if (!tab) throw Error("窗口不存在");
      p.stage = tab.stage;
      p.activeTab = tab.id;
      changed = true;
      inject = true;
    } else if (a === "tab_add") {
      if (!stages.includes(r.stage)) throw Error("未知阶段");
      const ordinal =
        Math.max(
          ...p.tabs.filter((t) => t.stage === r.stage).map((t) => t.ordinal),
        ) + 1;
      p.tabs.push({ id: randomUUID(), stage: r.stage, ordinal });
      changed = true;
    } else if (a === "tab_close") {
      const tab = p.tabs.find((t) => t.id === r.id);
      if (!tab || p.tabs.filter((t) => t.stage === tab.stage).length < 2)
        throw Error("同类窗口至少保留一个");
      p.tabs = p.tabs.filter((t) => t.id !== r.id);
      if (p.activeTab === r.id)
        p.activeTab = p.tabs.find((t) => t.stage === tab.stage).id;
      changed = true;
    } else if (a === "send") {
      if (p.pending) throw Error("请先回答当前待确认项");
      const text = bounded(r.text || "开始添加机械配合。");
      agent.followup(
        message(`${this.context(p)}\n\n用户请求：${text}`, "user"),
      );
      return { queued: true };
    } else if (a === "spec_add") {
      if (!sections.includes(r.section)) throw Error("未知规格分类");
      const text = bounded(r.text, 4000).trim();
      if (!text) throw Error("规格不能为空");
      const source = bounded(r.source || "", 2000);
      if (r.section === "verifiedParts" && !source.trim())
        throw Error("已核实零件信息需要来源");
      p.spec[r.section].push({ id: randomUUID(), text, source });
      changed = true;
      inject = user;
    } else if (a === "spec_remove") {
      if (!sections.includes(r.section)) throw Error("未知规格分类");
      p.spec[r.section] = p.spec[r.section].filter((i) => i.id !== r.id);
      changed = true;
      inject = user;
    } else if (a === "iteration") {
      if (!["modeling", "mates"].includes(p.stage))
        throw Error("当前阶段不执行验收");
      if (!["working", "failed", "passed"].includes(r.status))
        throw Error("状态必须为 working / failed / passed");
      const evidence = bounded(r.evidence || "", 12000);
      if (r.status === "passed" && !evidence.trim())
        throw Error("验收通过需要证据");
      p.iterations.push({
        id: randomUUID(),
        number: p.iterations.length + 1,
        title: bounded(r.text, 2000),
        status: r.status,
        evidence,
      });
      changed = true;
      inject = user;
    } else if (a === "remember") {
      p.memories.push({
        id: randomUUID(),
        text: bounded(r.text, 6000),
        kind: r.kind === "preference" ? "preference" : "observation",
        at: new Date().toISOString(),
      });
      changed = true;
      inject = user;
    } else if (a === "recall") {
      const q = bounded(r.query || "", 256).toLowerCase();
      return {
        memories: p.memories.filter((m) => m.text.toLowerCase().includes(q)),
        skills: p.skills.filter((s) =>
          (s.name + s.body).toLowerCase().includes(q),
        ),
      };
    } else if (a === "summary") {
      p.summary = bounded(r.text, 24000);
      changed = true;
      inject = user;
    } else if (a === "skill_save" || a === "skill_import") {
      const body = bounded(r.body || "", 50000),
        name = bounded(r.name || "", 160).trim();
      if (!name || !body.trim()) throw Error("技能名称与内容不能为空");
      const skill = {
        id: randomUUID(),
        name,
        body,
        enabled: false,
        status: "draft",
        source: a === "skill_import" ? "imported" : "session",
      };
      p.skills.push(skill);
      changed = true;
      inject = user;
    } else if (a === "skill_enable") {
      const skill = p.skills.find((s) => s.id === r.id);
      if (!skill) throw Error("技能不存在");
      skill.enabled = r.enabled === true;
      changed = true;
      inject = true;
    } else if (a === "ask_user") {
      if (p.pending) throw Error("已有问题等待用户回答");
      if (
        !Array.isArray(r.options) ||
        r.options.length < 2 ||
        r.options.length > 4
      )
        throw Error("请提供 2–4 个选项");
      p.pending = {
        id: randomUUID(),
        question: bounded(r.text, 3000),
        options: r.options.map((x) => bounded(x, 1000)),
      };
      changed = true;
      result = { waitingForUser: true, ...p.pending };
    } else if (a === "answer") {
      if (!p.pending || r.id !== p.pending.id)
        throw Error("待确认项已变化，请刷新");
      if (!p.pending.options.includes(r.choice)) throw Error("选项无效");
      const pending = p.pending;
      p.pending = null;
      p.skills.push({
        id: randomUUID(),
        name: pending.question.slice(0, 80),
        body: `范围：当前会话 / ${p.stage}\n问题：${pending.question}\n用户选择：${r.choice}\n这是一项偏好记录；执行结果尚未核实。`,
        enabled: true,
        status: "preference",
        source: "user-choice",
      });
      await this.save(p);
      try {
        agent.followup(
          message(
            `${this.context(p)}\n用户已选择：${r.choice}。继续该步骤并记录实际结果。`,
            "user",
          ),
        );
      } catch (e) {
        p.pending = pending;
        p.skills.pop();
        await this.save(p);
        throw e;
      }
      return p;
    } else if (a === "search") {
      const q = bounded(r.query, 256).trim();
      if (!q) throw Error("检索词不能为空");
      const url =
        r.source === "local"
          ? new URL(`${p.ragUrl}/v1/search`)
          : r.source === "step"
            ? new URL("https://api.step.parts/v1/parts")
            : null;
      if (!url) throw Error("source 必须为 local 或 step");
      url.searchParams.set("q", q);
      url.searchParams.set(r.source === "local" ? "limit" : "pageSize", "12");
      const response = await fetch(url, {
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
          : AbortSignal.timeout(30000),
        redirect: "error",
      });
      if (!response.ok) throw Error(`检索返回 ${response.status}`);
      return { source: url.href, data: await response.json() };
    } else if (a === "list_files") {
      if (!p.workspace) throw Error("请先设置工作区");
      const files = await readdir(p.workspace, { withFileTypes: true });
      return files
        .slice(0, 300)
        .map((f) => ({ name: f.name, directory: f.isDirectory() }));
    } else if (a === "cad_list" || a === "cad_call" || a === "check_mcp") {
      if (p.pending && a === "cad_call")
        throw Error("等待用户回答，不能继续 CAD 操作");
      if (a === "cad_call" && !toolAllowed(p.stage, r.name))
        throw Error(`当前阶段禁止 ${r.name}`);
      let cad = this.connections.get(agent.id);
      if (!cad) {
        cad = new CadConnection(
          p,
          path.join(
            this.root,
            "queue",
            createHash("sha256").update(agent.id).digest("hex"),
          ),
        );
        try {
          await cad.connect();
          this.connections.set(agent.id, cad);
        } catch (e) {
          cad.close();
          throw e;
        }
      }
      if (a === "check_mcp")
        return {
          ok: true,
          total: cad.tools.length,
          message: "MCP 已连接；未操作 CAD",
        };
      if (a === "cad_list")
        return cad.tools.filter((t) => toolAllowed(p.stage, t.name));
      if (!cad.tools.some((t) => t.name === r.name))
        throw Error("MCP 未提供该工具");
      const args = await toolArguments(p.workspace, r.name, r.arguments || {});
      try {
        result = await cad.request(
          "tools/call",
          { name: r.name, arguments: args },
          180000,
          signal,
        );
      } catch (e) {
        cad.close();
        this.connections.delete(agent.id);
        throw e;
      }
      const evidenceDir = path.join(this.root, "evidence");
      await mkdir(evidenceDir, { recursive: true });
      const evidencePath = path.join(evidenceDir, `${randomUUID()}.json`);
      await writeFile(
        evidencePath,
        JSON.stringify({ tool: r.name, args, result }, null, 2),
      );
      const text = JSON.stringify(result, (key, value) =>
        key === "data" && typeof value === "string" && value.length > 16000
          ? "[binary omitted]"
          : value,
      );
      return {
        evidencePath,
        result:
          text.length > 60000
            ? text.slice(0, 60000) + " [truncated; see evidence file]"
            : JSON.parse(text),
      };
    } else throw Error(`未知操作：${a}`);
    if (changed) await this.save(p);
    if (inject) agent.inject(message(this.context(p)));
    return result ?? p;
  }
  close() {
    this.closed = true;
    for (const c of this.connections.values()) c.close();
    this.connections.clear();
  }
}
