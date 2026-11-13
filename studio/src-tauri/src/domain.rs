use serde::{Deserialize, Serialize};
use serde_json::Value;

pub fn id() -> String {
    uuid::Uuid::new_v4().to_string()
}
pub fn now() -> String {
    chrono::Utc::now().to_rfc3339()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Stage {
    Requirements,
    Reuse,
    Prototype,
    Modeling,
    Mates,
}
impl Stage {
    pub fn key(&self) -> &'static str {
        match self {
            Self::Requirements => "requirements",
            Self::Reuse => "reuse",
            Self::Prototype => "prototype",
            Self::Modeling => "modeling",
            Self::Mates => "mates",
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Tab {
    pub id: String,
    pub stage: Stage,
    pub ordinal: usize,
    pub draft: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Message {
    pub id: String,
    pub role: String,
    pub content: String,
    pub stage: Stage,
    pub created_at: String,
}
impl Message {
    pub fn new(role: &str, content: String, stage: Stage) -> Self {
        Self {
            id: id(),
            role: role.into(),
            content,
            stage,
            created_at: now(),
        }
    }
}

#[derive(Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct Spec {
    pub requirements: Vec<SpecItem>,
    pub verified_parts: Vec<SpecItem>,
    pub assumptions: Vec<SpecItem>,
    pub relations: Vec<SpecItem>,
    pub acceptance: Vec<SpecItem>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SpecItem {
    pub id: String,
    pub text: String,
    #[serde(default)]
    pub source: String,
}
impl Spec {
    pub fn section_mut(&mut self, key: &str) -> Result<&mut Vec<SpecItem>, String> {
        match key {
            "requirements" => Ok(&mut self.requirements),
            "verifiedParts" => Ok(&mut self.verified_parts),
            "assumptions" => Ok(&mut self.assumptions),
            "relations" => Ok(&mut self.relations),
            "acceptance" => Ok(&mut self.acceptance),
            _ => Err("未知规格分类".into()),
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Iteration {
    pub id: String,
    pub number: usize,
    pub title: String,
    pub status: String,
    pub evidence: String,
    pub created_at: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Decision {
    pub call_id: String,
    pub question: String,
    pub options: Vec<String>,
    pub context: String,
    pub stage: Stage,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Project {
    pub id: String,
    pub name: String,
    pub tabs: Vec<Tab>,
    pub active_tab: String,
    pub messages: Vec<Message>,
    pub conversation: Vec<Value>,
    pub spec: Spec,
    pub iterations: Vec<Iteration>,
    pub pending: Option<Decision>,
    pub summary: String,
    pub summarized_count: usize,
    pub updated_at: String,
}
impl Project {
    pub fn new(name: String) -> Self {
        let tabs = vec![
            Stage::Requirements,
            Stage::Reuse,
            Stage::Prototype,
            Stage::Modeling,
            Stage::Mates,
        ]
        .into_iter()
        .map(|stage| Tab {
            id: id(),
            stage,
            ordinal: 1,
            draft: String::new(),
        })
        .collect::<Vec<_>>();
        Self {
            id: id(),
            name,
            tabs: tabs.clone(),
            active_tab: tabs[0].id.clone(),
            messages: vec![],
            conversation: vec![],
            spec: Spec::default(),
            iterations: vec![],
            pending: None,
            summary: String::new(),
            summarized_count: 0,
            updated_at: now(),
        }
    }
    pub fn stage(&self) -> Stage {
        self.tabs
            .iter()
            .find(|t| t.id == self.active_tab)
            .map(|t| t.stage.clone())
            .unwrap_or(Stage::Requirements)
    }
    pub fn close_tab(&mut self, tab_id: &str) -> Result<(), String> {
        let tab = self
            .tabs
            .iter()
            .find(|t| t.id == tab_id)
            .ok_or("窗口不存在")?;
        if self.tabs.iter().filter(|t| t.stage == tab.stage).count() == 1 {
            return Err("每种工作窗口至少保留一个".into());
        }
        let stage = tab.stage.clone();
        self.tabs.retain(|t| t.id != tab_id);
        if self.active_tab == tab_id {
            self.active_tab = self
                .tabs
                .iter()
                .find(|t| t.stage == stage)
                .unwrap()
                .id
                .clone();
        }
        Ok(())
    }
    pub fn add_tab(&mut self, stage: Stage) {
        let ordinal = self
            .tabs
            .iter()
            .filter(|t| t.stage == stage)
            .map(|t| t.ordinal)
            .max()
            .unwrap_or(0)
            + 1;
        let tab = Tab {
            id: id(),
            stage,
            ordinal,
            draft: String::new(),
        };
        self.active_tab = tab.id.clone();
        self.tabs.push(tab);
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    pub endpoint: String,
    pub model: String,
    pub protocol: String,
    #[serde(default)]
    pub codex_path: String,
    pub mcp_python: String,
    pub mcp_server: String,
    pub rag_url: String,
    #[serde(default)]
    pub model_workspace: String,
    pub theme: String,
    pub font: String,
    pub prompts: std::collections::BTreeMap<String, String>,
    pub auto_summary: bool,
    pub max_rounds: usize,
    #[serde(default)]
    pub has_api_key: bool,
}
impl Default for Settings {
    fn default() -> Self {
        let root = std::path::PathBuf::from(std::env::var("USERPROFILE").unwrap_or_default())
            .join(".codex/mcp/solidworks-automation-skill");
        Self{endpoint:"https://api.openai.com/v1".into(),model:String::new(),protocol:if std::env::var("ROBOMASTER_STUDIO_PROVIDER").as_deref() == Ok("codex") { "codex".into() } else { "chat_completions".into() },codex_path:String::new(),mcp_python:root.join(".venv/Scripts/python.exe").to_string_lossy().into(),mcp_server:root.join("mcp-server/server.py").to_string_lossy().into(),rag_url:"http://127.0.0.1:8765".into(),model_workspace:String::new(),theme:"night".into(),font:"sans".into(),auto_summary:true,max_rounds:24,has_api_key:false,prompts:[
 ("requirements","你是 RoboMaster 机械设计搭档。先讨论用途、空间、接口、材料和验收目标。主动维护五类结构化规格：用户明确要求、已核实零件信息、暂定参数、参数关系、验收条件。用户未确认的数字只能放入暂定参数；已核实信息必须有来源。遇到实质性不确定调用 ask_user，给出 2–4 个明确选项。需求阶段不修改 CAD。"),
 ("reuse","先检索再建模。调用 search_parts 对本地 CAD RAG 与 step.parts 检索，说明来源、已验证范围、待核实接口和复用限制。候选不是已核实零件；禁止把文件名当作尺寸或承载能力证据。选择候选后与用户讨论适配条件。"),
 ("prototype","用 SolidWorks 制作一次性外形原型。只关心外形与包络尺寸是否明显异常。不要运行单元测试、干涉检测、运动仿真、FEA、DFM、制造或验收测试；只允许必要的几何读取、包围盒和外观预览。不要宣称原型可制造或已验收。保存到本项目的新文件，不覆盖原件。"),
 ("modeling","依据结构化规格逐步建模与验收。调用 report_iteration 记录第 1、2、3…轮的目标、失败、修正和证据。工具调用成功不等于验收成功，必须将实测结果与验收条件比较。失败后根据证据修正；不重复盲目执行。缺少证据时写明未验证。用户最终验收后再形成可复用经验。"),
 ("mates","为当前 SolidWorks 装配体添加机械配合。先读取组件、位置与几何，识别基准件、运动自由度及配合意图，再串行添加同心、重合、距离等受支持配合。保持应有自由度，避免过约束。零件或选面有歧义时调用 ask_user 让用户点选；配合后回读并报告证据。不得把固定组件当作完成机械配合。")].into_iter().map(|(k,v)|(k.into(),v.into())).collect()}
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Skill {
    pub id: String,
    pub name: String,
    pub description: String,
    pub body: String,
    pub source: String,
    pub status: String,
    pub enabled: bool,
    pub updated_at: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Memory {
    pub id: String,
    pub text: String,
    pub kind: String,
    pub project_id: String,
    pub updated_at: String,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub project: Project,
    pub projects: Vec<Value>,
    pub settings: Settings,
    pub skills: Vec<Skill>,
    pub memories: Vec<Memory>,
    pub busy: bool,
    pub data_dir: String,
    pub model_workspace_dir: String,
}

pub fn tool_allowed(stage: &Stage, name: &str) -> bool {
    if matches!(stage, Stage::Requirements | Stage::Reuse) {
        return false;
    }
    if *stage == Stage::Prototype {
        return matches!(
            name,
            "solidworks_connect"
                | "solidworks_new_document"
                | "solidworks_open_document"
                | "solidworks_create_basic_part"
                | "solidworks_sketch_and_extrude"
                | "solidworks_revolve"
                | "solidworks_pattern"
                | "solidworks_mirror_feature"
                | "solidworks_shell"
                | "solidworks_fillet"
                | "solidworks_chamfer"
                | "solidworks_list_edges"
                | "solidworks_create_hole_feature"
                | "solidworks_set_appearance"
                | "solidworks_save_document"
                | "solidworks_export_active"
                | "solidworks_bounding_box"
                | "solidworks_inspect_native_geometry"
                | "solidworks_add_component"
                | "solidworks_update_dimension"
                | "solidworks_build_round_sweeps"
                | "solidworks_import_step_part"
        );
    }
    name.starts_with("solidworks_")
        && !matches!(
            name,
            "solidworks_close_documents" | "solidworks_addin_host_status"
        )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn last_tab_cannot_close() {
        let mut p = Project::new("x".into());
        let first = p.active_tab.clone();
        assert!(p.close_tab(&first).is_err());
        p.add_tab(Stage::Requirements);
        assert_eq!(p.tabs.len(), 6);
        p.close_tab(&first).unwrap();
        assert_eq!(p.tabs.len(), 5);
    }
    #[test]
    fn prototype_does_not_expose_tests() {
        for tool in [
            "solidworks_interference_check",
            "solidworks_validate_motion_study",
            "cadstudio_run_fea",
            "solidworks_review_active",
            "design_spec_validate",
        ] {
            assert!(!tool_allowed(&Stage::Prototype, tool));
        }
        assert!(tool_allowed(&Stage::Prototype, "solidworks_bounding_box"));
        assert!(!tool_allowed(
            &Stage::Requirements,
            "solidworks_create_basic_part"
        ));
    }
}
