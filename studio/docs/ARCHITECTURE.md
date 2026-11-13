# 架构与扩展契约

```text
React 工作视图 / 设置 / 规格 / 候选
                 ↓ Tauri typed commands / agent-event
Rust AppState ── SQLite Store + skill 文件
       │
       ├─ Agent loop ── API adapter (Chat Completions / Responses)
       │      ├─ builtins (规格 / 检索 / 下载 / 记忆 / skill / 人工选择 / 迭代)
       │      └─ stage policy ── serialized MCP stdio ── upstream Python ── SolidWorks COM
       └─ HTTP retrieval ── local CAD RAG / api.step.parts
```

## 模块

- `src-tauri/src/domain.rs`：版本化的领域对象与阶段工具权限。窗口数、阶段、规格、迭代、待选问题与配置在此定义。
- `store.rs`：SQLite WAL 持久化。保存项目和检索索引使用事务。记忆按项目隔离、去重。skill 以 UUID 目录写入 Markdown，目录遍历不能成为写入路径。
- `api.rs`：HTTP 地址验证、两类模型协议转译、官方检索接口。API Key 只由 Rust 读取。
- `mcp.rs`：stdio JSON-RPC 生命周期、初始化、分页工具发现、通知、请求匹配、超时失效标记。请求在同一实例中串行执行，服务 stderr 写日志，stdout 只处理协议消息。
- `agent.rs`：工具回路、阶段提示词与规格注入、人工选择暂停/恢复、摘要、经验总结。模型只看当前阶段允许的 MCP 工具，执行前再次检查名字。
- `download.rs`：按来源与组件 ID 重新读取可信目录记录，下载工作副本，限流量并核对 SHA-256；不接受模型给出的任意下载 URL 或目标路径。
- `workspace.rs`：全局模型目录偏好、保存前读写检查、默认项目路径回退、模型文件发现、MCP 相对路径解析和自定义工作区内的输出约束。新设置字段使用 serde default 兼容旧数据库；目录切换不迁移已有数据。MCP 的 `SW_MCP_OUTPUT_ROOT` 与下载根目录均取同一配置，工具证据仍保存在应用数据目录。
- `lib.rs`：Tauri 命令、独占任务状态、停止信号、启动时修复中断的工具结果配对。
- `src/bridge.ts`：唯一前端命令入口；浏览器预览和原生调用明确区分。
- `src/App.tsx`：工作区与五类窗口。`SettingsPanel.tsx`：设置与 skill 管理。`types.ts`：前端领域类型。

## 状态和执行原则

1. 同一时刻最多一个模型 / CAD 任务。共享对话禁止并发写入。开始任务前获取 busy guard，所有正常或错误退出都会释放。
2. API 请求可停止；CAD 调用不直接丢弃 future，以便记录真实结果。MCP 失败后的连接被标记为不可继续，须在检查实际 CAD 状态后明确重连。
3. `ask_user` 的原始 tool-call ID 和问题持久保存，回答回到同一对话。后续同批工具不会提前执行。重启后该选择仍可回答。
4. 五类规格不可互相自动降格/升格。已核实信息至少需要非空来源；真实性仍需人工及工具证据核验。
5. 工具原始返回保存为项目 JSON 证据。转发模型时剥离大块图片二进制并限制过长工具文本，提供完整证据路径。
6. 摘要只替换发送给模型的历史前缀，不删除数据库原始对话；压缩边界必须从用户轮次开始，避免留下无配对工具结果。
7. 学到的操作 skill 默认为草稿、未启用。用户选择存为 preference，其正文明确不代表几何验证，只在同项目 / 同情境适用；选择之后的实际消息、工具结果及失败会自动附入同一 skill。
8. 项目导出只导出项目状态，不导出 API Key。技能导入文本不具备新增工具能力。
9. API 凭据按服务地址隔离。Responses 协议按[官方格式](https://developers.openai.com/api/docs/guides/migrate-to-responses)保留和续接加密 reasoning items，与工具结果一起发送；切换服务地址或模型后不复用旧加密项。摘要与 Chat Completions 请求剥离 Responses 专用字段。

## 后续拓展

- 新检索源：增加 provider adapter 并规范为带 ID、来源、证据、限制的候选；下载继续走按 ID 复查和指纹核对。
- 新模型服务：在 `api.rs` 适配到内部统一的 assistant tool-calls 消息格式；把协议转译测试加入集成测试。
- 新建模工具：沿用 MCP 动态发现，再在 `tool_allowed` 中决定哪些阶段可见。原型白名单默认拒绝新增未知工具。
- 工程迭代与证据：`Iteration` 可增加 `artifacts`、验收项逐条状态、检查点以及 CAD 版本 ID。不要把模型生成的状态直接当成机械安全结论。
- 新数据字段：后续版本应新增数据库 `user_version` 迁移，给旧 JSON 增加 serde defaults，并提供往返兼容测试。
- skill 包：可在当前 Markdown 导入上增加 manifest、引用文件及签名；脚本应拥有独立的执行与权限策略，不默认运行。

## 当前设计取舍

Tauri 用系统 WebView2 绘制界面，Rust 执行全部桌面业务；React/TypeScript 用于界面布局和交互。现有 Python MCP 继续负责其专长的 SolidWorks COM 行为。这样可独立更新 UI、模型适配层与上游建模工具，无需重写 SolidWorks 自动化实现。
