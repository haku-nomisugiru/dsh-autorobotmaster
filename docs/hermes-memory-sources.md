# Hermes 记忆与 Skill 总结机制参考

本工作台采用本地轻量适配：SQLite 保存项目历史、显式记忆和冻结总结来源，受控文本文件保存可复用 Skill；通过模型 API 的结构化 JSON 调用生成总结候选（v1.0.0 起使用 ApiProvider 直连）。没有安装或导入 Hermes 运行时，没有读取用户的 Hermes 私人目录。

## 核实的上游版本

- 官方仓库：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- 默认分支：main。
- 研究固定提交：[000861be39aa261671b197f374aa032a51c59f3e](https://github.com/NousResearch/hermes-agent/commit/000861be39aa261671b197f374aa032a51c59f3e)。
- 提交者时间：2026-10-26 04:57:29 UTC。
- 许可：[MIT License](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/LICENSE)，版权归 Nous Research，2025。

本模块是围绕下列机制编写的独立实现。上游代码若被进一步直接复制或实质性改编，应随复制部分保留上游版权及 MIT 许可。

## 源码与适配范围

| 上游实现 | 源码中实际存在的机制 | 本工作台采用的模式 |
|---|---|---|
| [memory_tool_store.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/tools/memory_tool_store.py#L177) | 有界 USER/MEMORY 条目、重复检测、加锁重读、原子修改、冻结提示快照 | 区分项目与全局显式记忆，字符预算、去重、事务写入 |
| [context_compressor.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/agent/context_compressor.py#L3880) | 结构化摘要、旧摘要增量更新、来源与过期任务检查 | 冻结 source_hash、覆盖消息数、保留原始历史、拒绝旧来源覆盖新项目事实 |
| [background_review.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/agent/background_review.py#L370) | 事实与技能分流、按主题更新、去重、限定复盘工具、前台抢占 | AI 仅产生 JSON 候选；文件路径和证据由 Python 校验，学习不操作 CAD |
| [turn_finalizer.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/agent/turn_finalizer.py#L830) | 回复交付后按条件触发复盘，跳过中断轮次 | 在用户明确总结或验收后的受控时机调用总结 |
| [learn_prompt.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/agent/learn_prompt.py#L136) | /learn 将来源和要求组织成正常模型轮次，优先更新已有技能 | 摘要包含适用条件、过程、验证、陷阱和证据，重复内容不生成新版本 |
| [skill_manager_tool.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/tools/skill_manager_tool.py#L468) | 合法命名、frontmatter 检查、支持目录限制、原子文件写入、变更账本 | 项目受控 Skill 目录、文本导入、内容指纹、版本备份及写失败回滚 |
| [skill_manager_guards.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/tools/skill_manager_guards.py#L211) | 后台修改前重新读取实际目标 | 生成时检查数据库版本，原子写之前读取现有文件并备份 |
| [skills_tool.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/tools/skills_tool.py) | 按需列举和加载技能正文 | 仅将相关且已启用的技能载入有限上下文，中文使用二元词片段匹配 |
| [session_search_tool.py](https://github.com/NousResearch/hermes-agent/blob/000861be39aa261671b197f374aa032a51c59f3e/tools/session_search_tool.py#L354) | 会话发现、血缘去重、相关历史展开 | 保留完整可见会话，先呈现项目元数据与相关内容，历史可单独查看 |

## 工作台证据约束

- 只有当前项目输出目录内、实际存在且含 JSON result 的记录文件，才能进入总结证据包。
- 证据 ID 由项目内相对路径和原文件 SHA-256 派生；重复捕获相同证据得到相同 ID。
- 成功、失败和待复核从真实 JSON 计算；聊天或模型的成功声明不能改变文件中的失败。
- 未知证据 ID、未知来源哈希、跨项目来源哈希和已过期总结均拒绝保存。
- 未完成项目或存在未通过证据的经验生成停用草稿。完成项目且所引用证据全部通过，才可默认启用。
- 来源项目的数值留在来源范围中；复用 Skill 时还需核对当前机构、接口、版本和工艺条件。
- 用户可显式启用或停用 Skill；再次生成不会撤销用户的停用选择。

## 依赖边界

没有嵌入 Hermes 的 AIAgent、外部 MemoryProvider、网关、自动策展、模型路由或原生 CJK FTS 扩展。模块使用 Python 标准库；AI 调用由独立 ApiProvider 完成，支持 Responses 与 Chat Completions；不依赖 Codex CLI。用户全局技能目录与 Hermes 文件均保持独立，导入仅复制有界文本，执行脚本不随导入复制。
