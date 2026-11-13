use crate::domain::Settings;
use serde_json::{json, Value};
use std::{path::Path, process::Stdio};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    time::{timeout, Duration},
};

pub struct McpClient {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    id: u64,
    pub tools: Vec<Value>,
    pub signature: String,
    pub poisoned: bool,
}
impl McpClient {
    pub async fn connect(s: &Settings, root: &Path) -> Result<Self, String> {
        if !Path::new(&s.mcp_server).is_file() {
            return Err("找不到 MCP server.py，请在设置中选择上游路径".into());
        }
        let server = Path::new(&s.mcp_server);
        let cwd = server
            .parent()
            .and_then(|p| p.parent())
            .ok_or("MCP 路径无效")?;
        let model_root = crate::workspace::mcp_root(s, root);
        std::fs::create_dir_all(&model_root).map_err(|e| e.to_string())?;
        let mut cmd = Command::new(&s.mcp_python);
        cmd.arg(server)
            .current_dir(cwd)
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUNBUFFERED", "1")
            .env("SW_MCP_OUTPUT_ROOT", &model_root)
            .env("SW_MCP_QUEUE_DIR", root.join("mcp_queue"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::from(
                std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(root.join("mcp.log"))
                    .map_err(|e| e.to_string())?,
            ))
            .kill_on_drop(true);
        #[cfg(windows)]
        cmd.creation_flags(0x08000000);
        let mut child = cmd.spawn().map_err(|e| format!("启动 MCP 失败：{e}"))?;
        let input = child.stdin.take().ok_or("MCP stdin 缺失")?;
        let output = BufReader::new(child.stdout.take().ok_or("MCP stdout 缺失")?);
        let mut c = Self {
            child,
            input,
            output,
            id: 0,
            tools: vec![],
            signature: format!("{}|{}|{}", s.mcp_python, s.mcp_server, model_root.display()),
            poisoned: false,
        };
        c.request("initialize",json!({"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"robomaster-studio","version":"0.1.0"}}),40).await?;
        c.send(json!({"jsonrpc":"2.0","method":"notifications/initialized"}))
            .await?;
        let mut cursor: Option<String> = None;
        for _ in 0..30 {
            let p = cursor
                .as_ref()
                .map(|x| json!({"cursor":x}))
                .unwrap_or(json!({}));
            let list = c.request("tools/list", p, 40).await?;
            c.tools.extend(
                list["tools"]
                    .as_array()
                    .ok_or("MCP tools/list 缺少 tools")?
                    .iter()
                    .cloned(),
            );
            cursor = list["nextCursor"].as_str().map(str::to_string);
            if cursor.is_none() {
                break;
            }
        }
        Ok(c)
    }
    async fn send(&mut self, msg: Value) -> Result<(), String> {
        let mut data = serde_json::to_vec(&msg).map_err(|e| e.to_string())?;
        data.push(b'\n');
        self.input
            .write_all(&data)
            .await
            .map_err(|e| e.to_string())?;
        self.input.flush().await.map_err(|e| e.to_string())
    }
    pub async fn request(
        &mut self,
        method: &str,
        params: Value,
        seconds: u64,
    ) -> Result<Value, String> {
        if self.poisoned {
            return Err("MCP 上一次调用结果未知，需检查 SolidWorks 后在设置中重连".into());
        }
        self.id += 1;
        let id = self.id;
        self.send(json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}))
            .await?;
        let result=timeout(Duration::from_secs(seconds),async {loop{let mut line=String::new();let n=self.output.read_line(&mut line).await.map_err(|e|e.to_string())?;if n==0{return Err(format!("MCP 进程退出：{:?}",self.child.try_wait().ok().flatten()));}if line.len()>24_000_000{return Err("MCP 响应超过限制".into())}let v:Value=serde_json::from_str(&line).map_err(|e|format!("MCP 返回非 JSON：{e}"))?;if v.get("id")==Some(&json!(id)) {if let Some(err)=v.get("error"){return Err(err.to_string())}return Ok(v["result"].clone())}if v.get("method").is_some()&&v.get("id").is_some(){let response=if v["method"]=="ping"{json!({"jsonrpc":"2.0","id":v["id"],"result":{}})}else{json!({"jsonrpc":"2.0","id":v["id"],"error":{"code":-32601,"message":"Client capability unavailable"}})};self.send(response).await?;}}}).await;
        match result {
            Ok(Ok(v)) => Ok(v),
            Ok(Err(e)) => {
                self.poisoned = true;
                Err(e)
            }
            Err(_) => {
                self.poisoned = true;
                Err("MCP 调用超时，操作可能已经执行；请检查 CAD 后重连，不会自动重试此操作".into())
            }
        }
    }
    pub async fn call(&mut self, name: &str, args: Value) -> Result<Value, String> {
        if !self.tools.iter().any(|t| t["name"] == name) {
            return Err("MCP 未提供此工具".into());
        }
        self.request("tools/call", json!({"name":name,"arguments":args}), 180)
            .await
    }
}
