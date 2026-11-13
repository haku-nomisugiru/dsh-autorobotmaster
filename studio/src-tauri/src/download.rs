use crate::{
    api,
    domain::{id, Settings},
};
use futures_util::StreamExt;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::Path;
use tokio::io::AsyncWriteExt;

pub async fn part(
    s: &Settings,
    root: &Path,
    project: &str,
    source: &str,
    part_id: &str,
    kind: &str,
) -> Result<Value, String> {
    if part_id.is_empty()
        || part_id.len() > 180
        || !part_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
    {
        return Err("无效的组件 ID".into());
    }
    if !["file", "package"].contains(&kind) {
        return Err("未知下载类型".into());
    }
    let client = api::http_client()?;
    let metadata_url = if source == "local" {
        api::validate_url(&s.rag_url, true)?;
        format!("{}/v1/models/{}", s.rag_url.trim_end_matches('/'), part_id)
    } else if source == "step" {
        format!("https://api.step.parts/v1/parts/{part_id}")
    } else {
        return Err("未知来源".into());
    };
    let response = client
        .get(metadata_url)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !response.status().is_success() {
        return Err(format!("组件详情读取失败：{}", response.status()));
    }
    let raw: Value = response.json().await.map_err(|e| e.to_string())?;
    let meta = if raw.get("item").is_some() {
        &raw["item"]
    } else if raw.get("part").is_some() {
        &raw["part"]
    } else {
        &raw
    };
    let (url, expected, extension) = if source == "local" {
        let hash = if kind == "package" {
            meta["downloads"]["package_sha256"].as_str()
        } else {
            meta["entry"]["sha256"].as_str()
        }
        .ok_or("目录缺少 SHA-256，无法核验下载")?;
        let ext = if kind == "package" {
            Path::new(
                meta["downloads"]["package_name"]
                    .as_str()
                    .unwrap_or("package.zip"),
            )
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("zip")
            .to_string()
        } else {
            meta["entry"]["extension"]
                .as_str()
                .unwrap_or(".step")
                .trim_start_matches('.')
                .to_string()
        };
        (
            format!(
                "{}/v1/models/{part_id}/{kind}",
                s.rag_url.trim_end_matches('/')
            ),
            hash.to_string(),
            ext,
        )
    } else {
        if kind == "package" {
            return Err("step.parts 提供独立 STEP 文件".into());
        }
        let u = meta["stepUrl"].as_str().ok_or("组件未提供 STEP 下载")?;
        let parsed = url::Url::parse(u).map_err(|e| e.to_string())?;
        if parsed.scheme() != "https"
            || !matches!(
                parsed.host_str(),
                Some(
                    "media.githubusercontent.com" | "raw.githubusercontent.com" | "www.step.parts"
                )
            )
        {
            return Err("STEP 下载来源不在已支持的官方资源域中".into());
        }
        (
            u.into(),
            meta["sha256"]
                .as_str()
                .ok_or("STEP 记录缺少 SHA-256")?
                .into(),
            "step".into(),
        )
    };
    if expected.len() != 64
        || !expected.bytes().all(|b| b.is_ascii_hexdigit())
        || !extension.bytes().all(|b| b.is_ascii_alphanumeric())
    {
        return Err("组件指纹或扩展名无效".into());
    }
    let response = client.get(url).send().await.map_err(|e| e.to_string())?;
    if !response.status().is_success() {
        return Err(format!("下载失败：{}", response.status()));
    }
    let limit = 512 * 1024 * 1024u64;
    if response.content_length().unwrap_or(0) > limit {
        return Err("此资源超过 512 MB，请使用原始来源单独下载".into());
    }
    let dir = crate::workspace::downloads(s, root, project);
    tokio::fs::create_dir_all(&dir)
        .await
        .map_err(|e| e.to_string())?;
    let target = dir.join(format!("{part_id}-{}.{}", id(), extension));
    let temp = target.with_extension(format!("{extension}.partial"));
    let mut file = tokio::fs::File::create(&temp)
        .await
        .map_err(|e| e.to_string())?;
    let mut stream = response.bytes_stream();
    let mut hash = Sha256::new();
    let mut size = 0u64;
    let write_result: Result<(), String> = async {
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|e| e.to_string())?;
            size += chunk.len() as u64;
            if size > limit {
                return Err("下载超过 512 MB 限制".into());
            }
            hash.update(&chunk);
            file.write_all(&chunk).await.map_err(|e| e.to_string())?;
        }
        file.flush().await.map_err(|e| e.to_string())?;
        Ok(())
    }
    .await;
    drop(file);
    if let Err(e) = write_result {
        let _ = tokio::fs::remove_file(&temp).await;
        return Err(e);
    }
    let actual = format!("{:x}", hash.finalize());
    if actual != expected.to_lowercase() {
        let _ = tokio::fs::remove_file(&temp).await;
        return Err("文件 SHA-256 与目录不符，下载未交付".into());
    }
    tokio::fs::rename(&temp, &target)
        .await
        .map_err(|e| e.to_string())?;
    Ok(
        json!({"path":target,"sha256":actual,"bytes":size,"source":source,"id":part_id,"kind":kind,"verification":"file_integrity_only","note":"文件完整性已核验，几何、接口及装配依赖尚需复核。压缩包保留原文件，未自动解压。"}),
    )
}
