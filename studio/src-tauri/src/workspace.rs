use crate::domain::{id, Settings};
use serde_json::{json, Value};
use std::path::{Component, Path, PathBuf};

/// An empty preference preserves the original per-project directory for old installations.
pub fn models(s: &Settings, data: &Path, project: &str) -> PathBuf {
    if s.model_workspace.trim().is_empty() {
        data.join("cad").join(project)
    } else {
        PathBuf::from(&s.model_workspace)
    }
}

pub fn mcp_root(s: &Settings, data: &Path) -> PathBuf {
    if s.model_workspace.trim().is_empty() {
        data.join("cad")
    } else {
        PathBuf::from(&s.model_workspace)
    }
}

pub fn downloads(s: &Settings, data: &Path, project: &str) -> PathBuf {
    let root = models(s, data, project).join("downloads");
    if s.model_workspace.trim().is_empty() {
        root
    } else {
        root.join(project)
    }
}

fn display_path(path: &Path) -> String {
    let text = path.to_string_lossy();
    if let Some(unc) = text.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc}")
    } else {
        text.strip_prefix(r"\\?\").unwrap_or(&text).into()
    }
}

/// Called on save, before changing persisted preferences or reconnecting MCP.
pub fn prepare(input: &str) -> Result<String, String> {
    let text = input.trim().trim_matches('"');
    if text.is_empty() {
        return Ok(String::new());
    }
    let path = Path::new(text);
    if !path.is_absolute() {
        return Err("模型工作区需要完整的文件夹路径，例如 D:\\RoboMaster\\CAD".into());
    }
    std::fs::create_dir_all(path).map_err(|e| format!("无法创建或访问模型工作区：{e}"))?;
    let path = path
        .canonicalize()
        .map_err(|e| format!("无法读取模型工作区：{e}"))?;
    std::fs::read_dir(&path).map_err(|e| format!("模型工作区不可读取：{e}"))?;
    let probe = path.join(format!(".robomaster-write-check-{}", id()));
    let file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&probe)
        .map_err(|e| format!("模型工作区不可写入：{e}"))?;
    drop(file);
    std::fs::remove_file(&probe).map_err(|e| format!("无法清理模型工作区检查文件：{e}"))?;
    Ok(display_path(&path))
}

fn resolve(base: &Path, input: &str) -> Result<PathBuf, String> {
    let path = Path::new(input);
    if path.is_absolute() {
        return Ok(path.into());
    }
    let mut relative = PathBuf::new();
    for part in path.components() {
        match part {
            Component::Normal(name) => relative.push(name),
            Component::CurDir => {}
            Component::ParentDir if relative.pop() => {}
            _ => return Err("相对路径不能越出模型工作区，请使用工作区内的文件名".into()),
        }
    }
    Ok(base.join(relative))
}

/// Check existing ancestors as well, so junctions cannot redirect writes outside the selection.
fn within(base: &Path, path: &Path) -> Result<(), String> {
    let base = base
        .canonicalize()
        .map_err(|e| format!("无法访问模型工作区：{e}"))?;
    let mut existing = path;
    while !existing.exists() {
        existing = existing.parent().ok_or("模型路径无效")?;
    }
    let actual = existing.canonicalize().map_err(|e| e.to_string())?;
    if !actual.starts_with(base) {
        return Err("保存路径不在当前模型工作区内，请使用工作区内的新文件名".into());
    }
    // Reject unresolved parent traversal after the nearest existing ancestor.
    if path
        .strip_prefix(existing)
        .map_err(|e| e.to_string())?
        .components()
        .any(|part| matches!(part, Component::ParentDir))
    {
        return Err("模型路径包含未解析的上级目录".into());
    }
    Ok(())
}

/// Resolve only MCP filesystem fields; component/feature identifiers remain untouched.
pub fn tool_arguments(
    s: &Settings,
    base: &Path,
    tool: &str,
    mut args: Value,
) -> Result<Value, String> {
    let custom = !s.model_workspace.trim().is_empty();
    let fields = args.as_object_mut().ok_or("工具参数必须是对象")?;
    if custom
        && tool == "solidworks_save_document"
        && fields
            .get("path")
            .and_then(Value::as_str)
            .is_none_or(|v| v.trim().is_empty())
    {
        return Err("已设置模型工作区；保存时请提供工作区内的文件名和正确扩展名，不能省略 path 保存回旧位置".into());
    }
    for (name, value) in fields.iter_mut() {
        let output = matches!(name.as_str(), "output_path" | "output_dir")
            || (tool == "solidworks_save_document" && name == "path");
        let path_field = matches!(
            name.as_str(),
            "path"
                | "output_path"
                | "output_dir"
                | "input_path"
                | "source_path"
                | "spec_path"
                | "template_path"
                | "drawing_path"
                | "pdf_path"
                | "brep_evidence_path"
        );
        if path_field {
            if let Some(text) = value.as_str().filter(|v| !v.is_empty()) {
                let resolved = resolve(base, text)?;
                if custom && output {
                    within(base, &resolved)?;
                }
                *value = json!(display_path(&resolved));
            }
        } else if matches!(name.as_str(), "file_paths" | "profile_paths") {
            if let Some(paths) = value.as_array_mut() {
                for value in paths {
                    if let Some(text) = value.as_str() {
                        *value = json!(display_path(&resolve(base, text)?));
                    }
                }
            }
        }
    }
    Ok(args)
}

pub fn list(base: &Path, directory: &str) -> Result<Value, String> {
    let path = resolve(base, directory)?;
    within(base, &path)?;
    let mut files = Vec::new();
    let mut scanned = 0;
    let mut truncated = false;
    for entry in std::fs::read_dir(&path).map_err(|e| format!("无法读取模型目录：{e}"))? {
        let entry = entry.map_err(|e| e.to_string())?;
        scanned += 1;
        if files.len() >= 300 || scanned > 5000 {
            truncated = true;
            break;
        }
        let kind = entry.file_type().map_err(|e| e.to_string())?;
        let path = entry.path();
        let ext = path
            .extension()
            .unwrap_or_default()
            .to_string_lossy()
            .to_lowercase();
        if kind.is_dir()
            || matches!(
                ext.as_str(),
                "sldprt"
                    | "sldasm"
                    | "slddrw"
                    | "step"
                    | "stp"
                    | "iges"
                    | "igs"
                    | "stl"
                    | "dxf"
                    | "dwg"
                    | "x_t"
                    | "x_b"
                    | "prt"
                    | "asm"
                    | "json"
            )
        {
            files.push(json!({"name":entry.file_name().to_string_lossy(),"path":display_path(&path),"directory":kind.is_dir()}));
        }
    }
    files.sort_by_key(|f| {
        (
            f["directory"] != true,
            f["name"].as_str().unwrap_or("").to_lowercase(),
        )
    });
    Ok(
        json!({"workspace":display_path(base),"directory":display_path(&path),"entries":files,"truncated":truncated}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_settings_keep_preferences_and_project_paths() {
        let tmp = tempfile::tempdir().unwrap();
        let db = crate::store::Store::open(tmp.path()).unwrap();
        let mut old = serde_json::to_value(Settings::default()).unwrap();
        old.as_object_mut().unwrap().remove("modelWorkspace");
        old["theme"] = json!("night");
        old["model"] = json!("existing-model");
        db.conn
            .execute("INSERT INTO settings VALUES(1,?1)", [old.to_string()])
            .unwrap();
        let mut s = db.settings();
        assert_eq!(s.theme, "night");
        assert_eq!(s.model, "existing-model");
        assert!(s.model_workspace.is_empty());
        assert_eq!(models(&s, tmp.path(), "one"), tmp.path().join("cad/one"));
        s.model_workspace = prepare(&tmp.path().join("模型 工作区").to_string_lossy()).unwrap();
        db.save_settings(&s).unwrap();
        assert_eq!(db.settings().model_workspace, s.model_workspace);
        assert_eq!(models(&s, tmp.path(), "one"), models(&s, tmp.path(), "two"));
        assert_eq!(
            downloads(&s, tmp.path(), "one"),
            Path::new(&s.model_workspace).join("downloads/one")
        );
    }

    #[test]
    fn workspace_validation_creates_directory_and_rejects_invalid_input() {
        let tmp = tempfile::tempdir().unwrap();
        let target = tmp.path().join("含 空格/nested");
        let configured = prepare(&format!("  \"{}\"  ", target.display())).unwrap();
        assert!(Path::new(&configured).is_dir());
        assert_eq!(std::fs::read_dir(&target).unwrap().count(), 0);
        assert!(prepare("relative/path").is_err());
        assert!(prepare("https://example.com/models").is_err());
        let file = tmp.path().join("not-a-directory.step");
        std::fs::write(&file, "fixture").unwrap();
        assert!(prepare(&file.to_string_lossy()).is_err());
        assert_eq!(prepare("   ").unwrap(), "");
    }

    #[test]
    fn model_paths_resolve_under_selection_and_old_output_is_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let s = Settings {
            model_workspace: prepare(&tmp.path().join("models").to_string_lossy()).unwrap(),
            ..Settings::default()
        };
        let base = Path::new(&s.model_workspace);
        let input = tool_arguments(
            &s,
            base,
            "solidworks_open_document",
            json!({"path":"零件.step","read_only":true}),
        )
        .unwrap();
        assert_eq!(input["path"], json!(base.join("零件.step")));
        let saved = tool_arguments(
            &s,
            base,
            "solidworks_save_document",
            json!({"path":"底盘.sldasm"}),
        )
        .unwrap();
        assert_eq!(saved["path"], json!(base.join("底盘.sldasm")));
        assert!(tool_arguments(&s, base, "solidworks_save_document", json!({})).is_err());
        assert!(tool_arguments(
            &s,
            base,
            "solidworks_save_document",
            json!({"path":tmp.path().join("old.sldprt")})
        )
        .is_err());
        assert!(tool_arguments(
            &s,
            base,
            "solidworks_export_active",
            json!({"output_path":"../outside.step"})
        )
        .is_err());
        let external = tmp.path().join("template.prtdot");
        assert!(tool_arguments(
            &s,
            base,
            "solidworks_new_document",
            json!({"template_path":external})
        )
        .is_ok());
        let batch = tool_arguments(
            &s,
            base,
            "solidworks_batch_export_files",
            json!({"file_paths":["零件.sldprt"],"output_dir":"exports"}),
        )
        .unwrap();
        assert_eq!(batch["file_paths"][0], json!(base.join("零件.sldprt")));
        assert_eq!(batch["output_dir"], json!(base.join("exports")));
        let listed = list(base, "").unwrap();
        assert_eq!(listed["entries"], json!([]));
        assert!(list(base, "..").is_err());
    }
}
