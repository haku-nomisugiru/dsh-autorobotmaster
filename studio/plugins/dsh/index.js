import { StudioService } from "./service.js";

export const inject = ["commands", "tools"];
export function apply(ctx, config) {
  const studio = new StudioService(config);
  ctx.effect(() => () => studio.close());
  ctx.effect(() =>
    ctx.commands.register({
      name: "robomaster",
      description:
        "RoboMaster Studio：读取项目、设置工作区、切换阶段与发送建模请求",
      input: { hint: "<JSON action>" },
      handler: async ({ agent, rawInput, signal }) => {
        try {
          const value = await studio.operate(
            agent,
            JSON.parse(rawInput.trim() || '{"action":"snapshot"}'),
            { user: true, signal },
          );
          return { kind: "success", text: JSON.stringify(value) };
        } catch (e) {
          return { kind: "error", text: e.message };
        }
      },
    }),
  );
  ctx.effect(() =>
    ctx.tools.register({
      name: "robomaster_studio",
      description:
        "RoboMaster CAD 工作台。用 snapshot 查看当前阶段、工作区与规格；spec_add/spec_remove 维护五类规格；search 检索 local CAD RAG 或 step.parts；cad_list 获取该阶段允许的 MCP 工具 schema，cad_call 以 name+arguments 串行调用；iteration 记录建模验收证据；ask_user 让用户点选 2–4 项，之后等待；remember/recall/summary/skill_save 保存记忆、摘要与技能草稿。不能替用户回答、改变阶段、工作区或启用技能。",
      parameters: {
        type: "object",
        properties: {
          action: {
            type: "string",
            enum: [
              "snapshot",
              "spec_add",
              "spec_remove",
              "search",
              "cad_list",
              "cad_call",
              "check_mcp",
              "list_files",
              "iteration",
              "ask_user",
              "remember",
              "recall",
              "summary",
              "skill_save",
            ],
          },
          section: { type: "string" },
          text: { type: "string" },
          source: { type: "string" },
          query: { type: "string" },
          name: { type: "string" },
          arguments: { type: "object", additionalProperties: true },
          options: { type: "array", items: { type: "string" } },
          status: { type: "string" },
          evidence: { type: "string" },
          body: { type: "string" },
          id: { type: "string" },
          kind: { type: "string" },
        },
        required: ["action"],
        additionalProperties: false,
      },
      output: {
        schema: {},
        render: (_args, value) => [
          { type: "text", text: JSON.stringify(value) },
        ],
      },
      async execute(args, exec) {
        const value = await studio.operate(exec.agent, args, {
          signal: exec.signal,
        });
        if (args.action === "ask_user") exec.concludeTurn();
        return value;
      },
      presentCall: (args) => ({
        card: "generic",
        kind: [
          "snapshot",
          "recall",
          "search",
          "cad_list",
          "list_files",
          "check_mcp",
        ].includes(args.action)
          ? "read"
          : "write",
        title: `RoboMaster · ${args.action}`,
      }),
    }),
  );
}
