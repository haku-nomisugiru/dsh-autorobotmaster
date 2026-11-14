# RoboMaster Studio 0.2.0 · API 桌面版

API 版与 Codex 版使用同一个 Rust / Tauri 程序，区别是启动入口的默认模型配置。API 版可独立连接模型服务，不需要安装或登录 Codex。

1. 完整解压 `RoboMaster-Studio-API-v0.2.0-win-x64.zip`，运行 `Start-API-Studio.cmd`。
2. 打开右上角「设置 → 连接与模型」，选择 **Chat Completions 兼容** 或 **Responses API**。
3. 填入服务商的 API 基础地址、可用模型 ID 和 API Key，再点击「保存并测试模型」。模型需要支持工具调用。
4. 指定已安装的 SolidWorks MCP Python 解释器和 `mcp-server/server.py`，点击「连接 / 重连 MCP」。
5. 在「模型工作区」选择读取与保存 CAD 的文件夹，返回需求页开始使用。

默认使用墨夜主题，保留五阶段工作台、结构化规格、双源组件检索、模型工作区、项目记忆、摘要、技能与机械配合功能。设置中仍可切换到 Codex 接入；API 连接本身不依赖 Codex。

便携项目数据保存在程序旁的 `data/`。已有设置优先，启动脚本只决定新数据目录的默认接入方式。API Key 由 Windows Credential Manager 保存，不写入压缩包或项目数据库。

需要 Windows 10/11 x64 与 WebView2 Runtime。执行 CAD 操作还需要本机 SolidWorks 和单独安装的 [SolidWorks MCP](https://github.com/wzyn20051216/solidworks-automation-skill)。本地 CAD RAG 默认连接 `http://127.0.0.1:8765`。

API 调用使用所配置服务商的账户与额度。模型请求和摘要会发送相关项目上下文；工具执行成功与机械验收分别记录。原型阶段只用于外形与尺寸检查。

完整说明与更新：[项目 README](https://github.com/haku-nomisugiru/autorobomaster#readme)。
