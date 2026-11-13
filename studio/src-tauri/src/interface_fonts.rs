use std::path::PathBuf;

fn font_names(name: &str) -> Result<&'static [&'static str], String> {
    match name {
        "ocr" => Ok(&["OCRAEXT.TTF"]),
        "noto" => Ok(&[
            "NotoSansSC-VF.ttf",
            "NotoSansSC[wght].ttf",
            "NotoSansSC-Thin.ttf",
            "NotoSansSC-Thin.otf",
        ]),
        _ => Err("未知界面字体".into()),
    }
}

fn read_installed_font(name: &str, roots: &[PathBuf]) -> Result<Vec<u8>, String> {
    let names = font_names(name)?;
    for root in roots {
        for file in names {
            let path = root.join(file);
            let Ok(meta) = std::fs::metadata(&path) else {
                continue;
            };
            if !meta.is_file() || meta.len() > 32 * 1024 * 1024 {
                continue;
            }
            if let Ok(bytes) = std::fs::read(&path) {
                return Ok(bytes);
            }
        }
    }
    Err(format!("本机未安装界面字体 {name}"))
}

// Only the two interface font families are readable, from Windows font folders.
// Binary IPC avoids expanding a CJK font into a large JSON byte array.
#[tauri::command]
pub async fn load_interface_font(name: String) -> Result<tauri::ipc::Response, String> {
    let mut roots =
        vec![
            PathBuf::from(std::env::var_os("WINDIR").unwrap_or_else(|| "C:\\Windows".into()))
                .join("Fonts"),
        ];
    if let Some(local) = std::env::var_os("LOCALAPPDATA") {
        roots.push(PathBuf::from(local).join("Microsoft/Windows/Fonts"));
    }
    read_installed_font(&name, &roots).map(tauri::ipc::Response::new)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_supported_fonts_are_read_and_missing_fonts_can_fall_back() {
        let dir = tempfile::tempdir().unwrap();
        let roots = [dir.path().to_path_buf()];
        assert!(read_installed_font("../OCRAEXT.TTF", &roots).is_err());
        assert!(read_installed_font("ocr", &roots).is_err());
        std::fs::write(dir.path().join("OCRAEXT.TTF"), b"installed-font").unwrap();
        assert_eq!(
            read_installed_font("ocr", &roots).unwrap(),
            b"installed-font"
        );
        assert!(read_installed_font("noto", &roots).is_err());
        std::fs::write(dir.path().join("NotoSansSC[wght].ttf"), b"variable-font").unwrap();
        assert_eq!(
            read_installed_font("noto", &roots).unwrap(),
            b"variable-font"
        );
    }
}
