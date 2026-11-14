# RoboMaster Studio 0.2.0 · API / Codex / DSH

提供 API 桌面版、Codex 桌面版与 DSH 原生插件三个入口。API 与 Codex 包使用同一个 0.2.0 Rust / Tauri 程序，API 接入可独立使用。新版源码位于 `studio/`；旧 C# 工作台 v1.1.0 及其下载保留。Studio 使用独立版本号。

![墨夜工作台](https://raw.githubusercontent.com/haku-nomisugiru/autorobomaster/studio-v0.2.0/studio/docs/screenshots/themes/night-home.png)

## 下载

| 附件 | 用途 | 启动方式 |
| --- | --- | --- |
| `RoboMaster-Studio-API-v0.2.0-win-x64.zip` | 使用自己的模型 API，不需要 Codex | 解压后运行 `Start-API-Studio.cmd` |
| `RoboMaster-Studio-Codex-v0.2.0-win-x64.zip` | Windows x64 独立桌面工作台 | 解压后运行 `Start-Codex-Studio.cmd` |
| `RoboMaster-Studio-DSH-v0.2.0.zip` | DeepSeek Harness 原生插件 | 解压到固定目录，通过 DSH 插件管理器安装 |
| `SHA256SUMS.txt` | 三个 ZIP 的 SHA-256 | 下载后可用 `Get-FileHash -Algorithm SHA256` 核对 |

API 与 Codex 包仅启动脚本的默认接入方式不同，两者都可在设置中切换 Chat Completions、Responses API 或 Codex；已有设置保留。API 包中的主程序与已发布的 Codex 程序完全一致。

DSH 也可直接在插件管理器安装 `https://github.com/haku-nomisugiru/autorobomaster`。仓库已补齐根目录组合包声明，解决“这个包没有声明组合包，不能作为插件管理”的安装错误。

详细安装、环境要求与界面介绍见 [README](https://github.com/haku-nomisugiru/autorobomaster/blob/main/README.md) 和 [接入说明](https://github.com/haku-nomisugiru/autorobomaster/blob/main/studio/docs/INTEGRATIONS.md)。本次补充发布保留原有标签和两个 ZIP，只增加 API 下载并更新校验文件与说明。

## 本次内容

- API 桌面包默认使用兼容模型 API，使用当前 0.2.0 Rust 程序，保留全部工作台功能。
- Codex 版复用本机登录，以结构化决策接入现有工具循环；仍可切换 Responses 与 Chat Completions API。
- DSH 插件在当前会话打开完整工作台，注册原生 `robomaster_studio` 工具，主题跟随 DSH。
- 五阶段共享对话、可多开窗口与结构化规格：需求、复用检索、外形原型、建模验收、机械配合。
- 可选择模型读取与保存工作区；支持本地 CAD RAG 和 step.parts 目录搜索。
- 持久记忆、历史检索、长对话摘要、技能草稿、外部 Markdown 技能导入和不确定操作点选。
- 墨夜默认主题、OCR A Extended / Noto Sans SC Thin 本机字体、机械爆炸图、缓慢流光与主题一致性修复。

## 已验证

23 项 Rust 回归、17 项界面回归、2 项 DSH 状态与路径测试通过；另行完成真实 Codex 工具往返。最终桌面程序使用真实 Codex 将「底盘外宽 420 mm」写入规格并验证重载保留。DSH `0.2.1-rc.3` 完成独立测试配置下的安装、界面操作、工具入口和 MCP 握手。

本次补充验证：API 与 Codex 的主程序 SHA-256 相同，API 包在独立数据目录默认选择 Chat Completions，Responses 设置可保存并重载。DSH `0.2.2-rc.3` 使用 GitHub 仓库 URL 安装成功，组合包、Host、命令、模型工具及 Client 模块均通过检查。

## 使用边界

- Windows 桌面版需要 WebView2；实际 CAD 操作需要本机 SolidWorks、Python 与单独安装的 SolidWorks MCP。
- 已测试 Codex CLI `0.167.0-alpha.4.1`，升级后请先执行连接测试。
- DSH 测试配置未登录 DeepSeek，未完成真实 DeepSeek 推理测试。
- 本次未完成模型驱动真实整车 / 复杂装配的端到端机械验收。原型阶段不执行工程测试。
- 不包含用户项目、登录凭据、字体、SolidWorks 或 CAD 资产库；API 调用使用用户自己的账户额度。
- 旧 C# 工作台与新 Studio 数据格式不同，不自动迁移。旧 Studio 便携数据可先备份，再按接入说明迁移。

发布附件由本机已验证的程序打包，只补入仓库 MIT 许可证；上传流程校验 SHA-256 后发布原始 ZIP。
