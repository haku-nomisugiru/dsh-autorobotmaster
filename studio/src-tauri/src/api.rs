use crate::domain::Settings;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::Duration;

pub fn http_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(180))
        .connect_timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|e| e.to_string())
}
pub fn validate_url(raw: &str, local_only: bool) -> Result<url::Url, String> {
    let u = url::Url::parse(raw).map_err(|_| "地址必须包含 http:// 或 https://")?;
    let local = matches!(u.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"));
    if !u.username().is_empty()
        || u.password().is_some()
        || u.query().is_some()
        || u.fragment().is_some()
    {
        return Err("地址不能包含凭据、查询或片段".into());
    }
    if local_only && !local {
        return Err("CAD RAG 只连接本机地址".into());
    }
    if u.scheme() != "https" && !(local && u.scheme() == "http") {
        return Err("远程 API 必须使用 HTTPS；本机允许 HTTP".into());
    }
    Ok(u)
}
pub fn credential_account(endpoint: &str) -> String {
    format!(
        "model-api-{:x}",
        Sha256::digest(endpoint.trim_end_matches('/').as_bytes())
    )
}
pub fn key_entry(endpoint: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new("RoboMasterStudio", &credential_account(endpoint))
        .map_err(|e| e.to_string())
}
pub fn api_key(endpoint: &str) -> Result<String, String> {
    key_entry(endpoint)?
        .get_password()
        .map_err(|_| "请先在设置中保存当前 API 地址的 Key".into())
}
pub fn credential(s: &Settings) -> Result<String, String> {
    if s.protocol == "codex" { Ok(String::new()) } else { api_key(&s.endpoint) }
}

pub fn to_responses(messages: &[Value]) -> Vec<Value> {
    let mut out = vec![];
    for m in messages {
        if m["role"] == "assistant" {
            if let Some(items) = m["response_items"].as_array() {
                out.extend(items.iter().cloned());
                continue;
            }
        }
        match m["role"].as_str().unwrap_or("") {"tool"=>out.push(json!({"type":"function_call_output","call_id":m["tool_call_id"],"output":m["content"]})),"assistant"=>{if let Some(s)=m["content"].as_str(){if !s.is_empty(){out.push(json!({"role":"assistant","content":s}));}}if let Some(calls)=m["tool_calls"].as_array(){for c in calls {out.push(json!({"type":"function_call","call_id":c["id"],"name":c["function"]["name"],"arguments":c["function"]["arguments"]}));}}},_=>out.push(m.clone())}
    }
    out
}
pub fn chat_messages(messages: &[Value]) -> Vec<Value> {
    messages
        .iter()
        .map(|m| {
            let mut clean = m.clone();
            if let Some(object) = clean.as_object_mut() {
                object.remove("response_items");
                object.remove("response_endpoint");
                object.remove("response_model");
            }
            clean
        })
        .collect()
}
pub async fn complete(
    s: &Settings,
    key: &str,
    messages: &[Value],
    tools: &[Value],
) -> Result<Value, String> {
    if s.protocol == "codex" { return crate::codex::complete(s, messages, tools).await; }
    validate_url(&s.endpoint, false)?;
    if s.model.trim().is_empty() {
        return Err("请先填写模型 ID".into());
    }
    let responses = s.protocol == "responses";
    let suffix = if responses {
        "responses"
    } else {
        "chat/completions"
    };
    let url = format!("{}/{}", s.endpoint.trim_end_matches('/'), suffix);
    let compatible_history: Vec<Value> = messages
        .iter()
        .map(|m| {
            let mut value = m.clone();
            if m.get("response_items").is_some()
                && (m["response_endpoint"] != s.endpoint || m["response_model"] != s.model)
            {
                value.as_object_mut().unwrap().remove("response_items");
            }
            value
        })
        .collect();
    let mut body = if responses {
        json!({"model":s.model,"input":to_responses(&compatible_history),"store":false,"include":["reasoning.encrypted_content"]})
    } else {
        json!({"model":s.model,"messages":chat_messages(messages),"stream":false,"store":false})
    };
    if !tools.is_empty() {
        body["tools"] = if responses {
            Value::Array(
                tools
                    .iter()
                    .map(|t| {
                        let mut f = t["function"].clone();
                        f["type"] = json!("function");
                        f["strict"] = json!(false);
                        f
                    })
                    .collect(),
            )
        } else {
            json!(tools)
        };
        body["tool_choice"] = json!("auto");
        body["parallel_tool_calls"] = json!(false);
    }
    let response = http_client()?
        .post(url)
        .bearer_auth(key)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("模型连接失败：{e}"))?;
    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err(format!(
            "模型 API {}：{}",
            status.as_u16(),
            body.replace(key, "[REDACTED]")
                .chars()
                .take(600)
                .collect::<String>()
        ));
    }
    let v: Value = response
        .json()
        .await
        .map_err(|e| format!("模型返回非 JSON：{e}"))?;
    if responses {
        if matches!(
            v["status"].as_str(),
            Some("incomplete" | "failed" | "cancelled")
        ) {
            return Err(format!(
                "模型响应未完成：{}。未执行其中的工具调用。",
                v["status"]
            ));
        }
        let mut text = String::new();
        let mut calls = vec![];
        let output = v["output"].as_array().ok_or("模型缺少 output")?;
        for item in output {
            if item["type"] == "function_call" {
                calls.push(json!({"id":item["call_id"],"type":"function","function":{"name":item["name"],"arguments":item["arguments"]}}));
            }
            if let Some(parts) = item["content"].as_array() {
                for p in parts {
                    if p["type"] == "output_text" {
                        text.push_str(p["text"].as_str().unwrap_or(""));
                    } else if p["type"] == "refusal" {
                        text.push_str(p["refusal"].as_str().unwrap_or(""));
                    }
                }
            }
        }
        if text.is_empty() && calls.is_empty() {
            return Err("模型未返回文本或工具调用".into());
        }
        let mut m = json!({"role":"assistant","content":text});
        m["response_items"] = json!(output);
        m["response_endpoint"] = json!(s.endpoint);
        m["response_model"] = json!(s.model);
        if !calls.is_empty() {
            m["tool_calls"] = json!(calls)
        }
        Ok(m)
    } else {
        let m = v["choices"][0]["message"].clone();
        if !m.is_object() {
            return Err("模型缺少 choices[0].message".into());
        }
        if v["choices"][0]["finish_reason"] == "length" {
            return Err("模型输出被截断，请提高服务端输出限制或缩小任务".into());
        }
        let mut clean = json!({"role":"assistant","content":m["content"]});
        if let Some(c) = m.get("tool_calls") {
            clean["tool_calls"] = c.clone();
        }
        if let Some(r) = m.get("reasoning_content") {
            clean["reasoning_content"] = r.clone();
        }
        Ok(clean)
    }
}

pub async fn search_parts(s: &Settings, source: &str, q: &str) -> Result<Value, String> {
    if q.trim().is_empty() || q.chars().count() > 256 {
        return Err("检索词需为 1–256 字".into());
    }
    if source == "local" {
        validate_url(&s.rag_url, true)?;
        let url = format!("{}/v1/search", s.rag_url.trim_end_matches('/'));
        let response = http_client()?
            .get(url)
            .query(&[("q", q), ("limit", "12")])
            .send()
            .await
            .map_err(|e| format!("本地 CAD RAG 无法连接，请启动服务：{e}"))?;
        if !response.status().is_success() {
            return Err(format!("RAG 返回 {}", response.status()));
        }
        response.json().await.map_err(|e| e.to_string())
    } else if source == "step" {
        let response = http_client()?
            .get("https://api.step.parts/v1/parts")
            .query(&[("q", q), ("pageSize", "12")])
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !response.status().is_success() {
            return Err(format!(
                "step.parts 搜索接口返回 {}，可使用网站入口检索",
                response.status()
            ));
        }
        response
            .json()
            .await
            .map_err(|_| "step.parts 返回格式变化，请使用网站入口".into())
    } else {
        Err("未知检索来源".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_remote_plaintext_or_credentials() {
        assert!(validate_url("http://example.com/v1", false).is_err());
        assert!(validate_url("http://127.0.0.1:8765", true).is_ok());
        assert!(validate_url("https://example.com", true).is_err());
        assert!(validate_url("https://key@example.com", false).is_err());
    }
    #[test]
    fn tool_results_survive_responses_conversion() {
        let r = to_responses(&[
            json!({"role":"assistant","content":null,"tool_calls":[{"id":"c1","function":{"name":"ask_user","arguments":"{}"}}]}),
            json!({"role":"tool","tool_call_id":"c1","content":"yes"}),
        ]);
        assert_eq!(r[0]["call_id"], "c1");
        assert_eq!(r[1]["type"], "function_call_output");
    }
    #[test]
    fn encrypted_reasoning_survives_responses_but_not_chat_conversion() {
        let messages = [json!({"role":"assistant","content":"", "response_items":[
            {"type":"reasoning","id":"rs1","summary":[],"encrypted_content":"opaque"},
            {"type":"function_call","call_id":"c1","name":"ask_user","arguments":"{}"}
        ],"response_endpoint":"https://example.com/v1","response_model":"fixture"})];
        let input = to_responses(&messages);
        assert_eq!(input[0]["encrypted_content"], "opaque");
        assert_eq!(input[1]["call_id"], "c1");
        assert!(chat_messages(&messages)[0].get("response_items").is_none());
        assert!(chat_messages(&messages)[0]
            .get("response_endpoint")
            .is_none());
    }
}
