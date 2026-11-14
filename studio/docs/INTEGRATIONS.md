# RoboMaster Studio 0.2 — API、Codex 与 DSH

三个入口都保留五阶段工作流、结构化规格、模型工作区、记忆与技能。API 与 Codex 桌面包使用同一个 0.2.0 Rust / Tauri 程序，只是新数据目录的默认接入方式不同；已有设置优先。DSH 版作为原生插件运行在 DSH 当前会话内。

## API 桌面版

1. 解压 `RoboMaster-Studio-API-v0.2.0-win-x64.zip`，运行 `Start-API-Studio.cmd`。
2. 打开右上角设置 → 连接与模型，选择 Chat Completions 兼容或 Responses API，填写 API 地址、模型 ID 与 API Key，点击“保存并测试模型”。
3. 配置 SolidWorks MCP，并在“模型工作区”选择模型读取与保存目录。

API 接入可以独立使用，不需要安装或登录 Codex。两种桌面包均可在设置中切换 API / Codex，功能相同；便携项目数据保存到程序旁的 `data/`。详细步骤见 [API 使用说明](API.md)。

## Codex 桌面版

1. 解压 `RoboMaster-Studio-Codex-v0.2.0-win-x64.zip`。
2. 先安装并登录 Codex，再运行 `Start-Codex-Studio.cmd`。首次启动默认选择 Codex 接入。
3. 打开右上角设置 → 连接与模型，点击“保存并测试模型”。模型 ID 留空时使用本机 Codex 默认模型；也可以填写自己账户可用的模型 ID。
4. 如果自动查找失败，填写实际 `codex.exe` 的完整路径。不要填写桌面快捷方式或整个命令行。
5. 在“模型工作区”选择模型读取与保存目录，并检查 SolidWorks MCP 的 Python 和 `server.py` 路径。

此模式复用 Codex 自己的登录，不要求把 ChatGPT 登录凭据或 API Key 粘贴到 Studio。调用使用当前 Codex 账户的额度。原来的 Chat Completions 和 Responses API 接入仍可在同一设置中选择。

便携数据保存在程序旁的 `data`。新版本压缩包不含旧版本项目、登录凭据或测试数据。迁移旧项目时，先关闭旧版和新版，再自行备份并复制旧版 `data` 至新版目录；保留原设置的项目需要在设置中切换到 Codex。

### 接入边界

实现使用官方 [Codex App Server](https://learn.chatgpt.com/docs/app-server) 的 stdio JSON-RPC 和结构化输出。Studio 保存完整的项目会话、摘要及工具证据，每次模型请求提供当前上下文和允许的工具目录。Codex 返回下一步决策，Studio 校验并执行工具，再把真实工具结果回传。

这不会接管 Codex 桌面中已有的聊天。适配器使用临时线程，不在 Codex 聊天列表中另存 Studio 项目。当前版本使用 `experimentalApi` 的环境隔离字段，已验证的本机 CLI 版本为 `0.167.0-alpha.4.1`；升级后如出现协议错误，应先使用“保存并测试模型”验证兼容性。

请求最长 240 秒；停止任务或请求失败时关闭本次 App Server 进程。适配器拒绝额外的 Codex 执行/权限请求；CAD 操作仍由 Studio 的阶段规则与 SolidWorks MCP 入口处理。

## DSH 插件版

已验证的程序：桌面 `DeepSeek Harness.lnk` 指向的 `D:\dsh\DeepSeek Harness.exe`。原生界面与 MCP 检查使用 `0.2.1-rc.3`；Git 仓库组合包安装、命令、工具与 Client 加载已在 `0.2.2-rc.3` 复测。

1. 打开 DSH → **插件** → **添加插件**，输入 `https://github.com/haku-nomisugiru/autorobomaster`。仓库根目录已声明 DSH 组合包，之前出现“没有声明组合包”时可重新添加同一地址。
2. 点击安装，然后启用。也可以将 `RoboMaster-Studio-DSH-v0.2.0.zip` 解压到固定目录，输入含 `package.json` 的文件夹完整路径进行本地安装；安装后不要移动该目录，DSH 会使用目录链接。
3. 打开一个会话，输入框上方会出现 **ROBOMASTER / STUDIO**。点击“展开”打开完整工作台；关闭弹窗后仍停留在原会话。
4. 工作台设置中填写模型工作区、MCP Python 路径和 MCP `server.py` 路径。“测试 MCP”只执行连接握手和工具发现。
5. 在 DSH 自身完成模型登录或 API 配置。插件中的“发送”“开始”和“总结本会话”会驱动当前 DSH 会话所选模型；插件不另存 DSH 的凭据。

默认上游 MCP 路径为 `%USERPROFILE%\.codex\mcp\solidworks-automation-skill`。如果放在其他目录，在插件设置中修改。RAG 默认地址为 `http://127.0.0.1:8765`。

插件的五类窗口共享当前 DSH 会话，同类窗口可以添加，最后一个不能关闭。规格、工作区和技能以 DSH 会话为项目隔离。主题色随 DSH 当前主题变化。设置内可以编辑阶段提示词、查看摘要、导入 Markdown 技能并启用或停用；模型总结的技能先保存为草稿。

模型遇到歧义时可以调用 `ask_user`，任务停止在用户选择处。用户点选后记录一份会话范围的偏好技能，继续原会话；选择本身不会被写成“已经验收”的事实。

### 模型工具与数据

原生工具名为 `robomaster_studio`。主要操作：

| 操作 | 用途 |
| --- | --- |
| `snapshot` / `spec_add` / `spec_remove` | 读取项目和维护五类结构化规格 |
| `search` | 搜索本地 CAD RAG 或 step.parts |
| `cad_list` / `cad_call` | 发现当前阶段允许的 SolidWorks 工具并调用 |
| `iteration` | 记录迭代编号、状态与验收证据 |
| `ask_user` | 请求 2–4 个用户选项并结束当前模型轮次 |
| `remember` / `recall` / `summary` / `skill_save` | 保存和检索记忆、摘要、技能草稿 |

工作区、阶段切换、用户回答和技能启用仅开放给用户界面。需求和检索阶段禁止 CAD 调用；原型阶段使用与 Rust 桌面版一致的工具白名单，不开放测试与工程验收。模型文件路径限制在选定工作区内，并检查目录链接；CAD 超时或取消会报告“执行结果未知”，不会自动重试。

默认状态目录为 `%LOCALAPPDATA%\RoboMasterStudio\dsh`。其中的 JSON 项目、队列与 CAD 证据不包含模型账户凭据。可通过启动环境变量 `ROBOMASTER_DSH_DATA_DIR` 指定独立数据目录。DSH 自己的聊天和模型上下文由 DSH 保存。

更新本地插件代码后，需要重启 DSH，以加载新的 Host/Client 模块；仅刷新页面可能仍使用旧的模块清单。停用或卸载通过 DSH 插件管理器进行，不需要手工编辑其配置文件。

## 验证说明

- API：安装包内主程序与已发布的 Codex 0.2.0 程序 SHA-256 完全一致。独立数据目录默认使用 Chat Completions，可切换并保存 Responses 设置；未使用真实 API Key 或发起付费模型调用。
- DSH Git 仓库安装：使用 `0.2.2-rc.3` 的实际运行时，在独立配置中直接安装上述 GitHub URL，验证组合包登记、Host 加载、`/robomaster` 命令、`robomaster_studio` 工具和 Client 模块。
- Codex：使用本机真实登录完成结构化回答和两轮工具往返；工具返回 `42.75`，模型能引用该实际结果。最终 Rust 桌面程序也已通过真实调用：模型将“底盘外宽 420 mm”通过 `update_spec` 写入结构化规格，刷新后仍保留。另有 Rust 校验，拒绝当前阶段未开放的工具和无效参数。
- DSH：使用实际安装的 DSH 在独立测试配置中安装插件，验证原生 Client 注册、命令和模型工具入口、工作区持久化、阶段切换、增删窗口、规格编辑、技能导入与启停、MCP 握手。
- DSH 路径与状态测试覆盖工作区越界、Windows 目录链接、用户回答权限、待确认项阻止 CAD 操作和重启后状态恢复。
- 自动检查：23 项 Rust 测试通过，另行执行的 1 项真实 Codex 工具往返测试通过；16 项原有界面测试和新增的 1 项 Codex 设置测试通过；2 项 DSH 状态与路径测试通过。

DSH 原生弹窗已完成控件操作和尺寸检查（1120 × 740，无内容裁切），浅色与深色的计算样式随宿主切换。当前 Electron 目标在截图接口上出现超时，因此没有将弹窗截图列为已通过的视觉验证。该限制不影响已通过的界面操作和状态持久化检查。

测试配置与现有 DSH 账户分离，因此未使用用户的 DeepSeek 凭据，也未声称完成真实 DeepSeek 推理测试。已有 Codex 登录用于 Codex 的真实模型测试。集成测试不在用户现有 CAD 文档中建模或添加配合；真实机械设计和验收仍需在用户选定的模型工作区执行。

## 开发与复测

```powershell
node scripts/sync-dsh-workflow.mjs
npm.cmd run build
node --test tests/dsh-service.test.mjs
# 如 Windows 沙箱禁止目录链接，链接检查需在允许创建测试目录链接的环境运行。
. ./scripts/build-env.ps1
cargo test --manifest-path src-tauri/Cargo.toml --lib
cargo test --manifest-path src-tauri/Cargo.toml --lib codex::tests::live_codex_tool_roundtrip -- --ignored
./build.ps1
./scripts/package-integrations.ps1
```

`scripts/dsh-native-smoke.mjs` 只对明确准备的独立 DSH 测试实例运行，默认连接 `127.0.0.1:9472`。它会修改该测试会话的规格和技能，不应指向用户的工作会话。
