use crate::{agent, api, domain::*, mcp, store::Store, AppState};
use serde_json::{json, Value};
use std::sync::{atomic::AtomicBool, Mutex};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

async fn model_server(replies: Vec<Value>) -> (String, tokio::task::JoinHandle<Vec<Value>>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let handle = tokio::spawn(async move {
        let mut requests = vec![];
        for reply in replies {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut bytes = vec![];
            let mut chunk = [0; 4096];
            let (header_end, length) = loop {
                let n = socket.read(&mut chunk).await.unwrap();
                assert!(n > 0);
                bytes.extend_from_slice(&chunk[..n]);
                if let Some(pos) = bytes.windows(4).position(|x| x == b"\r\n\r\n") {
                    let header = String::from_utf8_lossy(&bytes[..pos]).to_lowercase();
                    let length = header
                        .lines()
                        .find_map(|line| {
                            line.strip_prefix("content-length:")
                                .map(|s| s.trim().parse::<usize>().unwrap())
                        })
                        .unwrap_or(0);
                    break (pos + 4, length);
                }
            };
            while bytes.len() < header_end + length {
                let n = socket.read(&mut chunk).await.unwrap();
                assert!(n > 0);
                bytes.extend_from_slice(&chunk[..n]);
            }
            requests.push(
                serde_json::from_slice::<Value>(&bytes[header_end..header_end + length]).unwrap(),
            );
            let body = json!({"choices":[{"message":reply,"finish_reason":"stop"}]}).to_string();
            socket.write_all(format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",body.len(),body).as_bytes()).await.unwrap();
        }
        requests
    });
    (format!("http://{address}/v1"), handle)
}
fn reply_call(id: &str, name: &str, args: Value) -> Value {
    json!({"role":"assistant","content":null,"tool_calls":[{"id":id,"type":"function","function":{"name":name,"arguments":args.to_string()}}]})
}

#[tokio::test]
async fn choice_pauses_resumes_and_creates_scoped_skill() {
    let (dir, root) = {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().to_path_buf();
        (d, p)
    };
    let db = Store::open(&root).unwrap();
    let (endpoint, server) = model_server(vec![
        reply_call(
            "choice1",
            "ask_user",
            json!({"question":"选择安装方向","options":["水平","竖直"],"context":"安装板姿态未知"}),
        ),
        reply_call(
            "spec1",
            "update_spec",
            json!({"section":"requirements","text":"安装方向：水平","source":"用户点选"}),
        ),
        json!({"role":"assistant","content":"已记录水平安装方向。"}),
    ])
    .await;
    let mut settings = Settings::default();
    settings.endpoint = endpoint;
    settings.model = "fixture".into();
    db.save_settings(&settings).unwrap();
    let state = AppState {
        db: Mutex::new(db),
        mcp: tokio::sync::Mutex::new(None),
        busy: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        cancel_notify: tokio::sync::Notify::new(),
    };
    agent::run(
        &state,
        None,
        Some("讨论安装板".into()),
        None,
        "test-only-key",
    )
    .await
    .unwrap();
    let p = state.db.lock().unwrap().active().unwrap();
    assert!(p.pending.is_some());
    assert_eq!(p.messages.iter().filter(|m| m.role == "user").count(), 1);
    agent::run(&state, None, None, Some("水平".into()), "test-only-key")
        .await
        .unwrap();
    let db = state.db.lock().unwrap();
    let p = db.active().unwrap();
    assert!(p.pending.is_none());
    assert_eq!(p.spec.requirements[0].text, "安装方向：水平");
    assert_eq!(db.skills().unwrap()[0].status, "preference");
    assert!(db.skills().unwrap()[0].body.contains("已记录水平安装方向"));
    assert!(db
        .root
        .join("skills")
        .join(&db.skills().unwrap()[0].id)
        .join("SKILL.md")
        .exists());
    assert_eq!(db.memories(&p.id).unwrap().len(), 1);
    drop(db);
    let requests = server.await.unwrap();
    assert_eq!(requests.len(), 3);
    assert!(requests[1]["messages"]
        .as_array()
        .unwrap()
        .iter()
        .any(|m| m["tool_call_id"] == "choice1"));
    drop(dir);
}

#[test]
fn api_credentials_are_bound_to_endpoint() {
    assert_ne!(
        api::credential_account("https://one.example/v1"),
        api::credential_account("https://two.example/v1")
    );
    assert_eq!(
        api::credential_account("https://one.example/v1/"),
        api::credential_account("https://one.example/v1")
    );
}

#[tokio::test]
async fn unauthorized_cad_call_becomes_error_without_connecting() {
    let tmp = tempfile::tempdir().unwrap();
    let db = Store::open(tmp.path()).unwrap();
    let (endpoint, server) = model_server(vec![
        reply_call(
            "bad",
            "solidworks_create_basic_part",
            json!({"shape":"box"}),
        ),
        json!({"role":"assistant","content":"需求阶段先讨论。"}),
    ])
    .await;
    let mut s = Settings::default();
    s.endpoint = endpoint;
    s.model = "fixture".into();
    db.save_settings(&s).unwrap();
    let state = AppState {
        db: Mutex::new(db),
        mcp: tokio::sync::Mutex::new(None),
        busy: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        cancel_notify: tokio::sync::Notify::new(),
    };
    agent::run(&state, None, Some("讨论".into()), None, "test")
        .await
        .unwrap();
    assert!(state.mcp.lock().await.is_none());
    let requests = server.await.unwrap();
    let tool = requests[1]["messages"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["role"] == "tool")
        .unwrap();
    assert!(tool["content"]
        .as_str()
        .unwrap()
        .contains("当前阶段未提供此工具"));
}

#[tokio::test]
async fn context_summary_preserves_tool_pairs_and_recent_history() {
    let tmp = tempfile::tempdir().unwrap();
    let db = Store::open(tmp.path()).unwrap();
    let (endpoint, server) = model_server(vec![
        json!({"role":"assistant","content":"历史摘要：安装孔距仍待测量，不能视为已核实。"}),
    ])
    .await;
    let mut s = Settings::default();
    s.endpoint = endpoint;
    s.model = "fixture".into();
    let mut p = db.active().unwrap();
    for i in 0..15 {
        p.conversation.extend([
            json!({"role":"user","content":format!("问题{i}")}),
            reply_call(&format!("c{i}"), "remember", json!({})),
            json!({"role":"tool","tool_call_id":format!("c{i}"),"content":"{}"}),
            json!({"role":"assistant","content":"记录"}),
        ]);
    }
    let total = p.conversation.len();
    let state = AppState {
        db: Mutex::new(db),
        mcp: tokio::sync::Mutex::new(None),
        busy: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        cancel_notify: tokio::sync::Notify::new(),
    };
    agent::summarize(&state, &mut p, &s, "test").await.unwrap();
    assert_eq!(p.conversation.len(), total);
    assert!(p.summarized_count > 0);
    assert_eq!(p.conversation[p.summarized_count]["role"], "user");
    assert!(p.summary.contains("待测量"));
    server.await.unwrap();
}

#[tokio::test]
async fn mcp_stdio_pagination_unicode_and_tool_failure() {
    let tmp = tempfile::tempdir().unwrap();
    let mut s = Settings::default();
    s.model_workspace =
        crate::workspace::prepare(&tmp.path().join("自选 CAD").to_string_lossy()).unwrap();
    s.mcp_python = "python".into();
    s.mcp_server = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/server.py")
        .to_string_lossy()
        .into();
    let mut client = mcp::McpClient::connect(&s, tmp.path()).await.unwrap();
    assert_eq!(client.tools.len(), 3);
    let result = client
        .call("fixture_echo", json!({"name":"中文轴承"}))
        .await
        .unwrap();
    assert!(result["content"][0]["text"]
        .as_str()
        .unwrap()
        .contains("中文轴承"));
    assert!(!client.poisoned);
    assert_eq!(result["outputRoot"], s.model_workspace);
    let error = client.call("fixture_failure", json!({})).await.unwrap();
    assert_eq!(error["isError"], true);
    assert!(!client.poisoned);
    assert!(client.call("not_listed", json!({})).await.is_err());
}

#[tokio::test]
async fn agent_discovers_models_in_persisted_workspace() {
    let tmp = tempfile::tempdir().unwrap();
    let db = Store::open(tmp.path()).unwrap();
    let workspace =
        crate::workspace::prepare(&tmp.path().join("设计 文件").to_string_lossy()).unwrap();
    std::fs::write(
        std::path::Path::new(&workspace).join("安装板.step"),
        "fixture",
    )
    .unwrap();
    std::fs::write(
        std::path::Path::new(&workspace).join("ignored.txt"),
        "fixture",
    )
    .unwrap();
    let (endpoint, server) = model_server(vec![
        reply_call("files", "list_workspace_files", json!({"directory":""})),
        json!({"role":"assistant","content":"工作区中发现安装板.step。"}),
    ])
    .await;
    db.save_settings(&Settings {
        endpoint,
        model: "fixture".into(),
        model_workspace: workspace.clone(),
        ..Settings::default()
    })
    .unwrap();
    let state = AppState {
        db: Mutex::new(db),
        mcp: tokio::sync::Mutex::new(None),
        busy: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        cancel_notify: tokio::sync::Notify::new(),
    };
    agent::run(
        &state,
        None,
        Some("查找当前工作区的模型".into()),
        None,
        "test",
    )
    .await
    .unwrap();
    let requests = server.await.unwrap();
    assert!(requests[0]["messages"][0]["content"]
        .as_str()
        .unwrap()
        .contains(&workspace));
    let result = requests[1]["messages"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["role"] == "tool")
        .unwrap();
    let listing: Value = serde_json::from_str(result["content"].as_str().unwrap()).unwrap();
    assert_eq!(listing["entries"].as_array().unwrap().len(), 1);
    assert_eq!(listing["entries"][0]["name"], "安装板.step");
}

#[tokio::test]
async fn agent_forwards_resolved_save_path_and_rejects_previous_workspace() {
    let tmp = tempfile::tempdir().unwrap();
    let db = Store::open(tmp.path()).unwrap();
    let workspace =
        crate::workspace::prepare(&tmp.path().join("新模型目录").to_string_lossy()).unwrap();
    let (endpoint, server) = model_server(vec![
        reply_call(
            "old",
            "solidworks_save_document",
            json!({"path":tmp.path().join("old.sldprt")}),
        ),
        reply_call(
            "new",
            "solidworks_save_document",
            json!({"path":"安装板.sldprt"}),
        ),
        json!({"role":"assistant","content":"已使用所选工作区。"}),
    ])
    .await;
    let s = Settings {
        endpoint,
        model: "fixture".into(),
        model_workspace: workspace.clone(),
        mcp_python: "python".into(),
        mcp_server: std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/server.py")
            .to_string_lossy()
            .into(),
        ..Settings::default()
    };
    db.save_settings(&s).unwrap();
    let mut p = db.active().unwrap();
    p.active_tab = p
        .tabs
        .iter()
        .find(|t| t.stage == Stage::Modeling)
        .unwrap()
        .id
        .clone();
    db.save_project(&p).unwrap();
    let state = AppState {
        db: Mutex::new(db),
        mcp: tokio::sync::Mutex::new(None),
        busy: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        cancel_notify: tokio::sync::Notify::new(),
    };
    agent::run(&state, None, Some("保存到工作区".into()), None, "test")
        .await
        .unwrap();
    let requests = server.await.unwrap();
    let results: Vec<Value> = requests[2]["messages"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|m| m["role"] == "tool")
        .map(|m| serde_json::from_str(m["content"].as_str().unwrap()).unwrap())
        .collect();
    assert!(results[0]["error"]
        .as_str()
        .unwrap()
        .contains("不在当前模型工作区"));
    assert_eq!(results[1]["result"]["callCount"], 1);
    let args: Value =
        serde_json::from_str(results[1]["result"]["content"][0]["text"].as_str().unwrap()).unwrap();
    assert_eq!(
        args["path"],
        json!(std::path::Path::new(&workspace).join("安装板.sldprt"))
    );
    assert_eq!(results[1]["result"]["outputRoot"], workspace);
}

#[test]
fn interrupted_tool_call_is_repaired_but_pending_choice_survives() {
    let tmp = tempfile::tempdir().unwrap();
    let db = Store::open(tmp.path()).unwrap();
    let mut p = db.active().unwrap();
    p.conversation
        .push(reply_call("unknown", "solidworks_save_document", json!({})));
    db.save_project(&p).unwrap();
    crate::recover_interrupted(&db).unwrap();
    let recovered = db.active().unwrap();
    assert_eq!(
        recovered.conversation.last().unwrap()["tool_call_id"],
        "unknown"
    );
    assert!(recovered.conversation.last().unwrap()["content"]
        .as_str()
        .unwrap()
        .contains("结果未知"));
}

#[tokio::test]
async fn compatible_api_keeps_tool_call_arguments() {
    let (endpoint, server) = model_server(vec![reply_call(
        "one",
        "ask_user",
        json!({"question":"方向？","options":["A","B"]}),
    )])
    .await;
    let mut s = Settings::default();
    s.endpoint = endpoint;
    s.model = "fixture".into();
    let out = api::complete(
        &s,
        "test",
        &[json!({"role":"user","content":"test"})],
        &agent::builtins(),
    )
    .await
    .unwrap();
    assert_eq!(out["tool_calls"][0]["id"], "one");
    let req = server.await.unwrap();
    assert_eq!(req[0]["parallel_tool_calls"], false);
}

#[tokio::test]
#[ignore = "Requires the installed upstream MCP, no CAD writes"]
async fn live_upstream_mcp_handshake() {
    let tmp = tempfile::tempdir().unwrap();
    let s = Settings::default();
    let client = mcp::McpClient::connect(&s, tmp.path()).await.unwrap();
    assert!(client
        .tools
        .iter()
        .any(|t| t["name"] == "solidworks_bounding_box"));
    assert!(client
        .tools
        .iter()
        .any(|t| t["name"] == "solidworks_add_concentric_mate"));
    println!(
        "Live upstream MCP handshake: {} tools discovered",
        client.tools.len()
    );
}

#[tokio::test]
#[ignore = "Requires live local RAG and public step.parts network"]
async fn live_retrieval_and_step_download() {
    let tmp = tempfile::tempdir().unwrap();
    let s = Settings::default();
    let local = api::search_parts(&s, "local", "3508 舵轮").await.unwrap();
    assert!(!local["items"].as_array().unwrap().is_empty());
    let remote = api::search_parts(&s, "step", "bearing").await.unwrap();
    assert!(!remote["items"].as_array().unwrap().is_empty());
    let id = remote["items"][0]["id"].as_str().unwrap();
    let download = crate::download::part(&s, tmp.path(), "live-test", "step", id, "file")
        .await
        .unwrap();
    assert!(std::path::Path::new(download["path"].as_str().unwrap()).is_file());
    assert_eq!(download["verification"], "file_integrity_only");
    println!(
        "Live RAG: {}; step.parts: {}; verified STEP download: {} bytes",
        local["items"].as_array().unwrap().len(),
        remote["total"],
        download["bytes"]
    );
}
