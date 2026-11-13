mod agent;
mod api;
mod codex;
mod domain;
mod download;
mod interface_fonts;
#[cfg(test)]
mod integration_tests;
mod mcp;
mod store;
mod workspace;
use domain::*;
use serde_json::{json, Value};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Mutex,
};
use tauri::{Emitter, Manager};

pub struct AppState {
    db: Mutex<store::Store>,
    mcp: tokio::sync::Mutex<Option<mcp::McpClient>>,
    busy: AtomicBool,
    cancel: AtomicBool,
    cancel_notify: tokio::sync::Notify,
}
struct BusyGuard<'a>(&'a AtomicBool);
impl Drop for BusyGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}
impl AppState {
    fn idle(&self) -> Result<(), String> {
        if self.busy.load(Ordering::SeqCst) {
            Err("任务正在执行，请等待完成或停止后再修改".into())
        } else {
            Ok(())
        }
    }
    fn begin(&self) -> Result<BusyGuard<'_>, String> {
        self.busy
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "已有任务在执行")?;
        self.cancel.store(false, Ordering::SeqCst);
        Ok(BusyGuard(&self.busy))
    }
    fn snapshot(&self) -> Result<Snapshot, String> {
        let db = self.db.lock().map_err(|_| "数据锁失败")?;
        let p = db.active()?;
        let mut settings = db.settings();
        settings.has_api_key = if settings.protocol == "codex" { codex::executable(&settings.codex_path).is_ok() } else { api::api_key(&settings.endpoint).is_ok() };
        let model_workspace_dir = workspace::models(&settings, &db.root, &p.id)
            .to_string_lossy()
            .into();
        Ok(Snapshot {
            projects: db.projects()?,
            skills: db.skills()?,
            memories: db.memories(&p.id)?,
            project: p,
            settings,
            busy: self.busy.load(Ordering::SeqCst),
            data_dir: db.root.to_string_lossy().into(),
            model_workspace_dir,
        })
    }
}
#[tauri::command]
fn bootstrap(state: tauri::State<AppState>) -> Result<Snapshot, String> {
    state.snapshot()
}
#[tauri::command]
fn edit_workspace(
    state: tauri::State<AppState>,
    action: String,
    payload: Value,
) -> Result<Snapshot, String> {
    state.idle()?;
    {
        let db = state.db.lock().map_err(|_| "数据锁失败")?;
        let mut p = db.active()?;
        match action.as_str() {
            "add_tab" => p.add_tab(
                serde_json::from_value(payload["stage"].clone()).map_err(|e| e.to_string())?,
            ),
            "close_tab" => p.close_tab(payload["id"].as_str().ok_or("缺少窗口 ID")?)?,
            "select_tab" => {
                let id = payload["id"].as_str().ok_or("缺少窗口 ID")?;
                if !p.tabs.iter().any(|t| t.id == id) {
                    return Err("窗口不存在".into());
                }
                p.active_tab = id.into();
            }
            "draft" => {
                let tab = p
                    .tabs
                    .iter_mut()
                    .find(|t| t.id == payload["id"])
                    .ok_or("窗口不存在")?;
                tab.draft = payload["text"]
                    .as_str()
                    .unwrap_or("")
                    .chars()
                    .take(60_000)
                    .collect();
            }
            "rename" => {
                let name = payload["name"].as_str().unwrap_or("").trim();
                if name.is_empty() {
                    return Err("项目名不能为空".into());
                }
                p.name = name.chars().take(100).collect();
            }
            "spec" => {
                let spec: Spec = serde_json::from_value(payload).map_err(|e| e.to_string())?;
                if spec
                    .verified_parts
                    .iter()
                    .any(|x| x.source.trim().is_empty())
                {
                    return Err("已核实零件必须填写来源".into());
                }
                p.spec = spec;
            }
            "new_project" => {
                p = Project::new(
                    payload["name"]
                        .as_str()
                        .filter(|s| !s.trim().is_empty())
                        .unwrap_or("新机械设计项目")
                        .chars()
                        .take(100)
                        .collect(),
                );
                db.save_project(&p)?;
                db.set_active(&p.id)?;
            }
            "switch_project" => {
                db.set_active(payload["id"].as_str().ok_or("项目 ID 缺失")?)?;
                p = db.active()?;
            }
            "accept" => {
                if p.iterations.is_empty() {
                    return Err("还没有可验收的建模迭代".into());
                }
                let it = p.iterations.last_mut().unwrap();
                if !["passed", "needs_review"].contains(&it.status.as_str())
                    || it.evidence.trim().is_empty()
                {
                    return Err("当前轮次尚无可审阅的验收证据".into());
                }
                it.status = "accepted".into();
                p.messages.push(Message::new(
                    "user",
                    format!("已人工验收第 {} 轮：{}", it.number, it.title),
                    Stage::Modeling,
                ));
                p.conversation.push(json!({"role":"user","content":format!("我已审阅证据并验收第 {} 轮。",it.number)}));
                db.remember(
                    &p.id,
                    &format!(
                        "用户人工验收第 {} 轮：{}。证据：{}",
                        it.number, it.title, it.evidence
                    ),
                    "acceptance",
                )?;
            }
            _ => return Err("未知工作区操作".into()),
        }
        db.save_project(&p)?;
    }
    state.snapshot()
}

#[tauri::command]
async fn save_settings(
    state: tauri::State<'_, AppState>,
    mut settings: Settings,
    api_key: Option<String>,
) -> Result<Snapshot, String> {
    let guard = state.begin()?;
    if settings.protocol != "codex" { api::validate_url(&settings.endpoint, false)?; }
    api::validate_url(&settings.rag_url, true)?;
    if !["chat_completions", "responses", "codex"].contains(&settings.protocol.as_str()) {
        return Err("不支持的 API 协议".into());
    }
    if !(1..=80).contains(&settings.max_rounds) {
        return Err("请求轮数需在 1–80 之间".into());
    }
    settings.model_workspace = workspace::prepare(&settings.model_workspace)?;
    if let Some(key) = api_key {
        if !key.trim().is_empty() {
            api::key_entry(&settings.endpoint)?
                .set_password(key.trim())
                .map_err(|e| format!("保存 Windows 凭据失败：{e}"))?;
        }
    }
    {
        let db = state.db.lock().map_err(|_| "数据锁失败")?;
        db.save_settings(&settings)?;
    }
    *state.mcp.lock().await = None;
    drop(guard);
    state.snapshot()
}

#[tauri::command]
async fn choose_model_workspace(initial: Option<String>) -> Result<Option<String>, String> {
    let mut dialog = rfd::AsyncFileDialog::new().set_title("选择模型读取与保存的工作区");
    if let Some(path) = initial.filter(|p| std::path::Path::new(p).is_dir()) {
        dialog = dialog.set_directory(path);
    }
    Ok(dialog
        .pick_folder()
        .await
        .map(|folder| folder.path().to_string_lossy().into()))
}

#[tauri::command]
fn list_model_files(
    state: tauri::State<AppState>,
    directory: Option<String>,
) -> Result<Value, String> {
    let db = state.db.lock().map_err(|_| "数据锁失败")?;
    let root = workspace::models(&db.settings(), &db.root, &db.active()?.id);
    workspace::list(&root, directory.as_deref().unwrap_or(""))
}

#[tauri::command]
fn open_model_workspace(state: tauri::State<AppState>) -> Result<(), String> {
    let db = state.db.lock().map_err(|_| "数据锁失败")?;
    let root = workspace::models(&db.settings(), &db.root, &db.active()?.id);
    std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    std::process::Command::new("explorer.exe")
        .arg(root)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
async fn send_message(
    state: tauri::State<'_, AppState>,
    app: tauri::AppHandle,
    text: Option<String>,
    choice: Option<String>,
) -> Result<Snapshot, String> {
    let guard = state.begin()?;
    let settings = state
        .db
        .lock()
        .map_err(|_| "数据锁失败")?
        .settings();
    let result = match api::credential(&settings) {
        Ok(key) => agent::run(&state, Some(&app), text, choice, &key).await,
        Err(e) => Err(e),
    };
    if let Err(ref e) = result {
        let db = state.db.lock().map_err(|_| "数据锁失败")?;
        let mut p = db.active()?;
        p.messages.push(Message::new("error", e.clone(), p.stage()));
        db.save_project(&p)?;
    }
    drop(guard);
    let _ = app.emit("agent-event", json!({"phase":"idle"}));
    result?;
    state.snapshot()
}
#[tauri::command]
fn cancel_run(state: tauri::State<AppState>) {
    state.cancel.store(true, Ordering::SeqCst);
    state.cancel_notify.notify_waiters();
}
#[tauri::command]
async fn search_parts(
    state: tauri::State<'_, AppState>,
    source: String,
    query: String,
) -> Result<Value, String> {
    let s = state.db.lock().map_err(|_| "数据锁失败")?.settings();
    api::search_parts(&s, &source, &query).await
}
#[tauri::command]
async fn download_part(
    state: tauri::State<'_, AppState>,
    app: tauri::AppHandle,
    source: String,
    part_id: String,
    kind: String,
) -> Result<Value, String> {
    let guard = state.begin()?;
    let (s, root, mut p) = {
        let db = state.db.lock().map_err(|_| "数据锁失败")?;
        (db.settings(), db.root.clone(), db.active()?)
    };
    let result = download::part(&s, &root, &p.id, &source, &part_id, &kind).await?;
    p.messages.push(Message::new(
        "notice",
        format!(
            "组件已下载并核对文件指纹：{}\n{}",
            part_id,
            result["path"].as_str().unwrap_or("")
        ),
        Stage::Reuse,
    ));
    p.conversation.push(json!({"role":"user","content":format!("我已下载候选组件，文件完整性已核对；尚未确认适配。下载记录：{}",result)}));
    state
        .db
        .lock()
        .map_err(|_| "数据锁失败")?
        .save_project(&p)?;
    drop(guard);
    agent::emit(Some(&app), &p, "downloaded");
    Ok(result)
}
#[tauri::command]
async fn check_connection(
    state: tauri::State<'_, AppState>,
    kind: String,
) -> Result<Value, String> {
    let guard = state.begin()?;
    let (s, root) = {
        let db = state.db.lock().map_err(|_| "数据锁失败")?;
        (db.settings(), db.root.clone())
    };
    let result = match kind.as_str() {
        "mcp" => {
            let mut mc = state.mcp.lock().await;
            let new = mcp::McpClient::connect(&s, &root).await?;
            let count = new.tools.len();
            let signature = new.signature.clone();
            *mc = Some(new);
            Ok(
                json!({"ok":true,"message":format!("MCP 已连接，发现 {count} 个工具；未操作 CAD"),"signature":signature}),
            )
        }
        "rag" => {
            api::validate_url(&s.rag_url, true)?;
            let r = api::http_client()?
                .get(format!("{}/health", s.rag_url.trim_end_matches('/')))
                .send()
                .await
                .map_err(|e| e.to_string())?;
            if !r.status().is_success() {
                return Err(format!("RAG 返回 {}", r.status()));
            }
            let v: Value = r.json().await.map_err(|e| e.to_string())?;
            Ok(json!({"ok":true,"message":"本地 RAG 已连接","detail":v}))
        }
        "api" => {
            let key = api::credential(&s)?;
            let out = api::complete(
                &s,
                &key,
                &[json!({"role":"user","content":"请只回复：连接成功"})],
                &[],
            )
            .await?;
            Ok(json!({"ok":true,"message":out["content"]}))
        }
        _ => Err("未知连接类型".into()),
    };
    drop(guard);
    result
}
#[tauri::command]
async fn summarize_project(
    state: tauri::State<'_, AppState>,
    app: tauri::AppHandle,
    mode: String,
) -> Result<Snapshot, String> {
    let guard = state.begin()?;
    if mode == "skill" {
        agent::distill(&state, &app).await?;
    } else {
        let (mut p, s) = {
            let db = state.db.lock().map_err(|_| "数据锁失败")?;
            (db.active()?, db.settings())
        };
        agent::summarize(&state, &mut p, &s, &api::credential(&s)?).await?;
    }
    drop(guard);
    state.snapshot()
}
#[tauri::command]
fn save_skill(state: tauri::State<AppState>, mut skill: Skill) -> Result<Snapshot, String> {
    state.idle()?;
    skill.updated_at = now();
    state
        .db
        .lock()
        .map_err(|_| "数据锁失败")?
        .save_skill(&skill)?;
    state.snapshot()
}
#[tauri::command]
async fn import_skill(state: tauri::State<'_, AppState>) -> Result<Snapshot, String> {
    state.idle()?;
    let file = rfd::AsyncFileDialog::new()
        .add_filter("Skill Markdown", &["md"])
        .pick_file()
        .await
        .ok_or("已取消导入")?;
    let path = file.path();
    let meta = std::fs::metadata(path).map_err(|e| e.to_string())?;
    if meta.len() > 100_000 {
        return Err("仅导入不超过 100 KB 的 Markdown skill".into());
    }
    let content = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut name = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("导入的 skill")
        .to_string();
    let mut description = "外部导入 · 阅读并启用后可供模型参考".to_string();
    if content.starts_with("---") {
        for line in content.lines().skip(1).take_while(|x| *x != "---") {
            if let Some(v) = line.strip_prefix("name:") {
                name = v.trim().trim_matches('"').into()
            }
            if let Some(v) = line.strip_prefix("description:") {
                description = v.trim().trim_matches('"').into()
            }
        }
    }
    state.idle()?;
    let skill = Skill {
        id: id(),
        name,
        description,
        body: content,
        source: "import".into(),
        status: "imported".into(),
        enabled: false,
        updated_at: now(),
    };
    state
        .db
        .lock()
        .map_err(|_| "数据锁失败")?
        .save_skill(&skill)?;
    state.snapshot()
}
#[tauri::command]
async fn export_project(state: tauri::State<'_, AppState>) -> Result<String, String> {
    let p = state.db.lock().map_err(|_| "数据锁失败")?.active()?;
    let file = rfd::AsyncFileDialog::new()
        .set_file_name("robomaster-project.json")
        .add_filter("项目 JSON", &["json"])
        .save_file()
        .await
        .ok_or("已取消导出")?;
    std::fs::write(file.path(), serde_json::to_vec_pretty(&p).unwrap())
        .map_err(|e| e.to_string())?;
    Ok(file.path().to_string_lossy().into())
}
#[tauri::command]
fn open_external(url: String) -> Result<(), String> {
    let u = url::Url::parse(&url).map_err(|_| "链接无效")?;
    if !["http", "https"].contains(&u.scheme())
        || !u.username().is_empty()
        || u.password().is_some()
    {
        return Err("仅允许 HTTP(S) 来源链接".into());
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        std::process::Command::new("rundll32.exe")
            .arg("url.dll,FileProtocolHandler")
            .arg(u.as_str())
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}
#[tauri::command]
fn open_data_dir(state: tauri::State<AppState>) -> Result<(), String> {
    let root = state.db.lock().map_err(|_| "数据锁失败")?.root.clone();
    #[cfg(windows)]
    {
        std::process::Command::new("explorer.exe")
            .arg(root)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn recover_interrupted(db: &store::Store) -> Result<(), String> {
    for meta in db.projects()? {
        let mut p = db.project(meta["id"].as_str().unwrap())?;
        let mut unresolved = std::collections::BTreeSet::new();
        for m in &p.conversation {
            if let Some(calls) = m["tool_calls"].as_array() {
                for c in calls {
                    if let Some(id) = c["id"].as_str() {
                        unresolved.insert(id.to_string());
                    }
                }
            }
            if m["role"] == "tool" {
                if let Some(id) = m["tool_call_id"].as_str() {
                    unresolved.remove(id);
                }
            }
        }
        if let Some(d) = &p.pending {
            unresolved.remove(&d.call_id);
        }
        for cid in &unresolved {
            p.conversation.push(json!({"role":"tool","tool_call_id":cid,"content":"应用在此操作期间退出，执行结果未知。必须先检查实际 CAD 状态，禁止盲目重复操作。"}));
        }
        if !unresolved.is_empty() {
            p.messages.push(Message::new(
                "notice",
                "已恢复中断会话；有操作结果未知，请先检查 SolidWorks 状态。".into(),
                p.stage(),
            ));
            db.save_project(&p)?;
        }
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let root = if let Ok(custom) = std::env::var("ROBOMASTER_STUDIO_DATA_DIR") {
                std::path::PathBuf::from(custom)
            } else {
                app.path().app_data_dir()?
            };
            let db = store::Store::open(&root).map_err(std::io::Error::other)?;
            recover_interrupted(&db).map_err(std::io::Error::other)?;
            app.manage(AppState {
                db: Mutex::new(db),
                mcp: tokio::sync::Mutex::new(None),
                busy: AtomicBool::new(false),
                cancel: AtomicBool::new(false),
                cancel_notify: tokio::sync::Notify::new(),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap,
            interface_fonts::load_interface_font,
            edit_workspace,
            save_settings,
            choose_model_workspace,
            open_model_workspace,
            list_model_files,
            send_message,
            cancel_run,
            search_parts,
            download_part,
            check_connection,
            summarize_project,
            save_skill,
            import_skill,
            export_project,
            open_external,
            open_data_dir
        ])
        .run(tauri::generate_context!())
        .expect("无法启动 RoboMaster Studio");
}
