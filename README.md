# DSH AutoRoboMaster · RoboMaster 机械设计工作台

DSH AutoRoboMaster 是基于 SolidWorks MCP 的 Windows 机械设计工作台，可在 SolidWorks 原生侧栏或独立 WinForms 窗口使用。工作台把自然语言需求交给所配置的模型 API，校验生成的 JSON 计划，经用户确认后通过本机 SolidWorks MCP 逐步执行并保留验收证据。当前源码直接连接所配置的模型 API。

| 功能 | 当前范围 |
| --- | --- |
| AI 设计与执行 | 支持 Responses 和 OpenAI 兼容 Chat Completions。可新建原生单零件，以及继续修改同一任务创建的零件。 |
| 建模与验收 | 显示每步结果，修改前保留检查点。用户查看预览和实测报告后验收。 |
| 机构检索 | 连接独立 CAD RAG 服务，检索云台、底盘和轮组或轮腿，显示来源、验证范围和下载选项。 |
| 复用评估 | 从独立工作副本读取当前配置及装配引用，展示缺失或歧义项，可将结构摘要交给所配置的模型评估复用条件。 |
| 项目记忆 | 本地保存项目历史、摘要和证据，可整理成待审阅的技能草稿。 |

当前自动执行范围限于单零件。整车自动设计、复杂机构自动插入、运动和制造验证需要单独处理。

## 下载与安装

下载 [Windows x64 安装包](https://github.com/haku-nomisugiru/dsh-autorobotmaster/releases/download/v1.1.0/DSH-AutoRoboMaster-v1.1.0-win-x64.zip) · [Release 与 SHA-256](https://github.com/haku-nomisugiru/dsh-autorobotmaster/releases/tag/v1.1.0)。

1. 准备 Windows x64、.NET Framework 4.x、64 位 Python 3.10+ 和已正常启动过的 SolidWorks 2025。此预编译版使用 SolidWorks 2025 SP4 的 PIA（`33.4.0.81`）。其他 PIA 版本可按下方说明从源码构建。
2. 将 ZIP 完整解压到当前用户可写的固定目录。准备 [SolidWorks MCP](https://github.com/wzyn20051216/solidworks-automation-skill) 的本机副本。已有副本可直接使用。
3. 退出 SolidWorks，在解压目录打开 64 位 Windows PowerShell。将示例路径换成实际位置后运行。

~~~powershell
$swApi = 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
$mcp = 'C:\Projects\solidworks-automation-skill'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -SolidWorksApiDir $swApi -McpRepository $mcp
~~~

安装脚本在本机创建 Python 虚拟环境并安装依赖，从你的 SolidWorks 安装目录复制匹配的互操作组件，再通过 UAC 注册加载项。可用 `-PythonExecutable` 指定解释器，或用 `-PrepareOnly` 仅准备文件与依赖。安装包已包含工作台 DLL 和 EXE，无需编译器。

4. 打开 SolidWorks，在“工具 → 加载项”启用“RoboMaster 机械设计工作台”，点击右侧 RM 图标。然后按下文配置模型 API 和 CAD RAG。

升级时先关闭 SolidWorks，在旧目录取消注册，再安装新版。原有 `settings.json` 和 `data/` 可备份后迁移，移动目录后请更新 Python 与 MCP 路径。

## 从源码构建

需要 Windows x64、已安装并正常启动过的 SolidWorks、.NET Framework 4.x、Python 3.10+ 和 Visual Studio Build Tools 的 Roslyn C# 编译器。SolidWorks 的 API redist 目录须有 SolidWorks.Interop.sldworks.dll、SolidWorks.Interop.swconst.dll 和 SolidWorks.Interop.swpublished.dll。工作台和 SolidWorks 应由同一 Windows 用户以相容权限运行。

在用户可写的目录克隆本仓库，进入工作台目录执行。已有 [SolidWorks MCP](https://github.com/wzyn20051216/solidworks-automation-skill) 时可使用现有目录。

~~~powershell
git clone https://github.com/wzyn20051216/solidworks-automation-skill ..\solidworks-automation-skill
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r ..\solidworks-automation-skill\requirements.txt
Copy-Item settings.example.json settings.json
~~~

将 `settings.json` 中的 `python_executable`、`mcp_repository` 和 `mcp_python` 改成实际绝对路径。按本机安装位置传入 API 与编译器路径。

~~~powershell
powershell.exe -NoProfile -File .\build.ps1 -SolidWorksApiDir '<api\redist 的完整路径>' -Compiler '<csc.exe 的完整路径>'
powershell.exe -NoProfile -File .\install.ps1
~~~

注册脚本会触发 UAC。进入 SolidWorks 的“工具 → 加载项”，启用“RoboMaster 机械设计工作台”，再打开侧栏 RM 图标。构建输出为 `build-v1.1.0/`。更新前退出正在使用旧 DLL 的进程。独立窗口执行 `.\launch.ps1`，查看界面预览执行 `.\launch.ps1 -Preview`。退出 SolidWorks 后可运行 `.\uninstall.ps1` 取消注册。

## 配置模型与 CAD RAG

在“API设置”选择 `responses` 或 `chat_completions`，填写服务商的 HTTPS 基础地址、账户可用的模型 ID 和 API Key。基础地址填写协议公共前缀，例如 `https://api.openai.com/v1`。按服务商支持情况选择 `json_schema` 或 `json_object`，点击“测试”可发起一次短请求。工作台在本机校验两种模式的输出。保存的 Key 由当前 Windows 用户的 DPAPI 加密，设计和总结等请求按服务商账户计费。

按 [RoboMaster CAD RAG](https://github.com/haku-nomisugiru/robotmaster-RAG) 的 README 启动检索服务。工作台默认访问 `http://127.0.0.1:8765`，可在 `settings.json` 修改 `cad_library_url`。默认地址连接失败时，工作台会尝试启动相邻 `RoboMasterCADLibrary` 目录下的服务。下载前须在 RAG 中准备本地资产。

## 从需求到验收

1. 输入有明确尺寸和验收目标的需求，例如“制作一块 80×50×6 mm 的无孔矩形安装板，创建原生零件并核验三向尺寸”。
2. 审阅设计回复、可复用候选和结构化计划，再点击“开始建模”。暂停或取消在当前 COM 调用返回后生效。
3. 查看原生模型、预览和实测报告，再决定是否“验收通过”。后续修改在原任务内提出。
4. 如需复用已有机构，从“模型库”下载候选并检查结构与依赖。提供目标接口、载荷和空间条件后，再发起复用评估。

[模型打开、依赖检查与复用评估](docs/model-reuse.md)列出了报告中的证据、检查范围及送给模型的数据。

## 本地数据与验证

配置保存在 `settings.json`。运行信息、CAD、对话、报告、SQLite 记忆和加密 Key 保存在 `data/`，学习或导入的技能保存在 `skills/learned/`。生成计划及总结时，输入、选取的记忆和文字证据可能发送到所配置的模型 API。

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
powershell.exe -NoProfile -File .\diagnose.ps1
~~~

Python 回归使用本地桩与临时目录，无需模型 Key 或启动 SolidWorks。诊断检查本机依赖、构建、注册、服务和脱敏配置。Windows COM 和真实模型服务需要对应环境验证。

- `native/` 为侧栏、独立窗口和对话框。
- `backend/` 为模型协议、本机 HTTP 服务、计划校验、MCP 执行、项目记忆及模型库客户端。
- `skills/bundled/` 为随附的 RoboMaster 建模技能。
- `tests/` 与 `docs/` 为测试和说明。

第三方声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。上游 SolidWorks MCP 单独安装。
