# RoboMaster Studio for DSH 0.2.0

原生 DSH 插件：五阶段 SolidWorks 工作台、结构化规格、模型工作区、记忆、摘要与可复用技能。

在 DSH 的“插件 → 添加插件”中填写本文件所在目录的完整路径，安装并启用。保持目录位置不变；修改或升级代码后重启 DSH。

在会话输入框上方点击 **ROBOMASTER / STUDIO → 展开**。在工作台设置中选择模型工作区，检查 MCP Python / server.py 路径；点击“测试 MCP”验证连接。模型登录与模型选择使用 DSH 自己的设置。插件不另存模型凭据。

默认 MCP 安装位置：`%USERPROFILE%\.codex\mcp\solidworks-automation-skill`。
默认 RAG：`http://127.0.0.1:8765`。
默认插件数据：`%LOCALAPPDATA%\RoboMasterStudio\dsh`，可用 `ROBOMASTER_DSH_DATA_DIR` 环境变量覆盖。

五类窗口共享当前 DSH 会话；规格和工作区按会话隔离。模型工具为 `robomaster_studio`，支持 `snapshot`、`spec_add`、`spec_remove`、`search`、`cad_list`、`cad_call`、`iteration`、`ask_user`、`remember`、`recall`、`summary`、`skill_save`。`cad_list` 返回准确工具 schema，随后通过 `cad_call` 串行执行。原型阶段禁止测试，需求和检索阶段禁止 CAD 操作。文件路径及目录链接不能越过选定模型工作区。

`ask_user` 会结束当前模型轮次，用户在工作台中点选后继续同一会话。选择记录为偏好技能，执行结果仍需核实。工作区、阶段、用户回答和技能启用不能由模型替用户操作。总结出的技能先保存为草稿；导入的 Markdown 需用户明确启用后才加入上下文。

界面使用 DSH 主题变量和本地字体，不加载 CDN 或单独的网页应用。图标为本项目原创 SVG。仅使用 Node 标准库和 DSH 提供的服务，无依赖安装脚本。

已在桌面快捷方式指向的 `D:\dsh\DeepSeek Harness.exe`（`0.2.1-rc.3`）上完成独立配置下的安装、原生界面和工具入口测试、MCP 握手。测试配置未登录 DeepSeek，未执行真实 DeepSeek 推理，也未修改用户 CAD 文档。

卸载或停用请使用 DSH 插件管理器；状态文件会保留，便于再次启用和恢复项目。
