import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdir, realpath, access } from "node:fs/promises";
import path from "node:path";

export async function workspacePath(root, input) {
  if (typeof input !== "string" || !input.trim() || input.includes("\0"))
    throw Error("模型路径不能为空");
  const base = await realpath(root);
  const target = path.resolve(base, input);
  const relative = path.relative(base, target);
  if (relative.startsWith("..") || path.isAbsolute(relative))
    throw Error("模型路径超出当前工作区");
  let ancestor = target;
  while (true) {
    try {
      await access(ancestor);
      break;
    } catch (e) {
      if (e.code !== "ENOENT") throw e;
      const parent = path.dirname(ancestor);
      if (parent === ancestor) throw e;
      ancestor = parent;
    }
  }
  const actual = path.relative(base, await realpath(ancestor));
  if (actual.startsWith("..") || path.isAbsolute(actual))
    throw Error("链接指向工作区以外");
  return target;
}
export async function toolArguments(root, tool, input) {
  const args = structuredClone(input);
  if (!args || typeof args !== "object" || Array.isArray(args))
    throw Error("工具参数必须是对象");
  if (tool === "solidworks_save_document" && !args.path)
    throw Error("保存必须指定工作区内的新文件名");
  const fields = new Set([
    "path",
    "output_path",
    "output_dir",
    "input_path",
    "source_path",
    "spec_path",
    "template_path",
    "drawing_path",
    "pdf_path",
    "brep_evidence_path",
  ]);
  for (const [key, value] of Object.entries(args)) {
    if (fields.has(key) && typeof value === "string" && value)
      args[key] = await workspacePath(root, value);
    if (["file_paths", "profile_paths"].includes(key) && Array.isArray(value))
      args[key] = await Promise.all(value.map((p) => workspacePath(root, p)));
  }
  return args;
}

export class CadConnection {
  #child;
  #reader;
  #id = 0;
  #pending = new Map();
  #closed = false;
  constructor(settings, queueDir) {
    this.settings = settings;
    this.queueDir = queueDir;
    this.tools = [];
  }
  async connect() {
    const s = this.settings;
    if (!s.workspace) throw Error("请先在面板设置模型工作区");
    await access(s.mcpPython);
    await access(s.mcpServer);
    await mkdir(this.queueDir, { recursive: true });
    this.#child = spawn(s.mcpPython, [s.mcpServer], {
      cwd: path.dirname(path.dirname(s.mcpServer)),
      windowsHide: true,
      stdio: ["pipe", "pipe", "ignore"],
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
        SW_MCP_OUTPUT_ROOT: s.workspace,
        SW_MCP_QUEUE_DIR: this.queueDir,
      },
    });
    this.#reader = createInterface({ input: this.#child.stdout });
    this.#child.on("error", (e) => this.close(e));
    this.#child.on("exit", () => this.close(Error("SolidWorks MCP 已退出")));
    this.#reader.on("line", (line) => {
      if (line.length > 16 * 1024 * 1024) {
        this.close(Error("MCP 响应过大"));
        return;
      }
      let value;
      try {
        value = JSON.parse(line);
      } catch {
        this.close(Error("MCP 返回无效 JSON"));
        return;
      }
      if (value.method && value.id !== undefined) {
        this.#child.stdin.write(
          JSON.stringify({
            jsonrpc: "2.0",
            id: value.id,
            error: { code: -32601, message: "Client requests unsupported" },
          }) + "\n",
        );
        return;
      }
      const pending = this.#pending.get(value.id);
      if (!pending) return;
      this.#pending.delete(value.id);
      clearTimeout(pending.timer);
      value.error
        ? pending.reject(Error(value.error.message))
        : pending.resolve(value.result);
    });
    await this.request(
      "initialize",
      {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "robomaster-dsh", version: "0.2.0" },
      },
      40000,
    );
    this.#child.stdin.write(
      '{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
    );
    let cursor;
    for (let i = 0; i < 30; i++) {
      const result = await this.request(
        "tools/list",
        cursor ? { cursor } : {},
        40000,
      );
      if (!Array.isArray(result.tools)) throw Error("MCP 未返回工具目录");
      this.tools.push(...result.tools);
      cursor = result.nextCursor;
      if (!cursor) return this;
    }
    throw Error("MCP 工具分页过多");
  }
  request(method, params, limit = 180000, signal) {
    if (this.#closed || !this.#child)
      return Promise.reject(Error("MCP 连接不可用"));
    if (signal?.aborted) return Promise.reject(Error("已取消"));
    return new Promise((resolve, reject) => {
      const id = ++this.#id;
      const cancel = () =>
        this.close(Error("MCP 调用已中断，CAD 执行结果未知；请先检查实际文档"));
      const done = (fn) => (value) => {
        signal?.removeEventListener("abort", cancel);
        fn(value);
      };
      const timer = setTimeout(
        () =>
          this.close(Error("MCP 调用超时，CAD 执行结果未知；请先检查实际文档")),
        limit,
      );
      this.#pending.set(id, {
        resolve: done(resolve),
        reject: done(reject),
        timer,
      });
      signal?.addEventListener("abort", cancel, { once: true });
      this.#child.stdin.write(
        JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n",
        (e) => {
          if (e) this.close(e);
        },
      );
    });
  }
  close(error = Error("MCP 连接已关闭")) {
    if (this.#closed) return;
    this.#closed = true;
    for (const p of this.#pending.values()) {
      clearTimeout(p.timer);
      p.reject(error);
    }
    this.#pending.clear();
    this.#reader?.close();
    this.#child?.kill();
  }
}
