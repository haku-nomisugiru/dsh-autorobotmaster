# Hermes 源码研究与 Rust 映射

核对日期：2026-11-11。上游 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)，固定研究提交 `3bcd071226d3d605a2bb3b4f3933e7d583e189d6`，MIT License。

这不是 Hermes 的完整移植。本项目以 Rust 独立实现适合机械设计桌面的相关机制，避免把 Python agent、桌面服务和 SolidWorks COM 同时作为多个调度核心。

| 上游研究入口 | 关注机制 | 本项目实现 |
|---|---|---|
| `tools/memory_tool.py`、`tools/memory_tool_store.py` | 持久事实 / 用户偏好、有限提示词预算、文件持久化 | `Store::remember`、项目隔离、去重、最多 16 条当前记忆进入本轮提示词 |
| `tools/session_search_tool.py` | SQLite 历史检索与有限结果读取 | FTS5 trigram 表，中文 / 英文短语检索，最多 12 条匹配 |
| `tools/skills_tool.py` | skill 目录先返回名称与描述，按需读取全文 | 系统上下文注入启用目录，`skill_view` 加载单个技能 |
| `tools/skill_manager_tool.py` | 将操作经验写入 SKILL.md，区分程序性经验与陈述性记忆 | `learn_skill`、手动经验总结、可编辑 Markdown 文件，来源和草稿状态 |
| `agent/context_compressor_summary.py` 及相关 context compressor 模块 | 摘要调度、失败保持原状态、完整历史边界 | `summarize` 在用户轮次处截断，保留原始历史和最近上下文，失败不更新摘要 |

研究原件保存在 `docs/research/`，只作开发依据，不参与运行；上游版权与许可附在该目录的 `LICENSE`。

## 为 RoboMaster 工作流增加的行为

不确定时调用 `ask_user`，暂停模型 / CAD 回路。用户选择后追加原始工具结果，自动创建同项目的情境偏好 skill。这个 skill 描述的是“用户在此情境选了什么”，而非“这个选项已经通过机械验证”。

可重复的实际操作经验通过 `learn_skill` 生成，必须有本轮 CAD 工具证据，否则只能写为项目记忆。待审阅内容默认不启用。自动或手动总结都必须保留失败和未验证范围，不把探索结论变成已验证工艺。

用户设置的各阶段提示词保留更高优先的当前任务范围。skill 内容、RAG 元数据和历史检索结果均作为参考资料，不能打开原型阶段禁用的工具。

## 其他接口依据

- [SolidWorks MCP 上游](https://github.com/wzyn20051216/solidworks-automation-skill)：stdio server、动态工具发现、串行 COM 交互。
- [MCP stdio 传输规范](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)：逐行 UTF-8 JSON-RPC；stderr 与协议输出分离。
- [step.parts 官方 API 指南](https://github.com/earthtojake/step.parts/blob/main/skills/step-parts/references/step-parts-api.md)：`https://api.step.parts/v1/parts`、`q` / `pageSize`、文件指纹、来源 URL。
- [Tauri 2 官方文档](https://v2.tauri.app/start/create-project/)：Rust 原生层与 WebView UI。
