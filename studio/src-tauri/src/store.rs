use crate::domain::*;
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
type Result<T> = std::result::Result<T, String>;
pub struct Store {
    pub conn: Connection,
    pub root: PathBuf,
}
impl Store {
    pub fn open(root: &Path) -> Result<Self> {
        std::fs::create_dir_all(root.join("skills")).map_err(|e| e.to_string())?;
        let conn = Connection::open(root.join("workspace.sqlite3")).map_err(|e| e.to_string())?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,data TEXT NOT NULL,updated TEXT NOT NULL); CREATE TABLE IF NOT EXISTS skills(id TEXT PRIMARY KEY,data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,text TEXT NOT NULL,kind TEXT NOT NULL,updated TEXT NOT NULL); CREATE VIRTUAL TABLE IF NOT EXISTS recall USING fts5(project_id UNINDEXED,kind UNINDEXED,text,tokenize='trigram'); CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);").map_err(|e|e.to_string())?;
        Ok(Self {
            conn,
            root: root.into(),
        })
    }
    pub fn settings(&self) -> Settings {
        self.conn
            .query_row("SELECT data FROM settings WHERE id=1", [], |r| {
                r.get::<_, String>(0)
            })
            .ok()
            .and_then(|x| serde_json::from_str(&x).ok())
            .unwrap_or_default()
    }
    pub fn save_settings(&self, s: &Settings) -> Result<()> {
        let mut s = s.clone();
        s.has_api_key = false;
        self.conn
            .execute(
                "INSERT OR REPLACE INTO settings VALUES(1,?1)",
                [serde_json::to_string(&s).unwrap()],
            )
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    pub fn project(&self, id: &str) -> Result<Project> {
        let text = self
            .conn
            .query_row("SELECT data FROM projects WHERE id=?1", [id], |r| {
                r.get::<_, String>(0)
            })
            .map_err(|e| e.to_string())?;
        serde_json::from_str(&text).map_err(|e| e.to_string())
    }
    pub fn active(&self) -> Result<Project> {
        if let Ok(id) = self
            .conn
            .query_row("SELECT value FROM meta WHERE key='active'", [], |r| {
                r.get::<_, String>(0)
            })
        {
            return self.project(&id);
        }
        let p = Project::new("我的机械设计项目".into());
        self.save_project(&p)?;
        self.set_active(&p.id)?;
        Ok(p)
    }
    pub fn set_active(&self, id: &str) -> Result<()> {
        self.project(id)?;
        self.conn
            .execute("INSERT OR REPLACE INTO meta VALUES('active',?1)", [id])
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    pub fn save_project(&self, p: &Project) -> Result<()> {
        let tx = self
            .conn
            .unchecked_transaction()
            .map_err(|e| e.to_string())?;
        tx.execute(
            "INSERT OR REPLACE INTO projects VALUES(?1,?2,?3,?4)",
            params![p.id, p.name, serde_json::to_string(p).unwrap(), now()],
        )
        .map_err(|e| e.to_string())?;
        tx.execute(
            "DELETE FROM recall WHERE project_id=?1 AND kind='conversation'",
            [&p.id],
        )
        .map_err(|e| e.to_string())?;
        for m in &p.messages {
            if m.role != "tool" {
                tx.execute(
                    "INSERT INTO recall VALUES(?1,'conversation',?2)",
                    params![p.id, m.content],
                )
                .map_err(|e| e.to_string())?;
            }
        }
        tx.commit().map_err(|e| e.to_string())
    }
    pub fn projects(&self) -> Result<Vec<Value>> {
        let mut stmt = self
            .conn
            .prepare("SELECT id,name,updated FROM projects ORDER BY updated DESC")
            .map_err(|e| e.to_string())?;
        let rows=stmt.query_map([],|r|Ok(json!({"id":r.get::<_,String>(0)?,"name":r.get::<_,String>(1)?,"updatedAt":r.get::<_,String>(2)?}))).map_err(|e|e.to_string())?;
        rows.map(|r| r.map_err(|e| e.to_string())).collect()
    }
    pub fn skills(&self) -> Result<Vec<Skill>> {
        let mut stmt = self
            .conn
            .prepare("SELECT data FROM skills ORDER BY rowid DESC")
            .map_err(|e| e.to_string())?;
        let rows = stmt
            .query_map([], |r| r.get::<_, String>(0))
            .map_err(|e| e.to_string())?;
        rows.map(|r| {
            serde_json::from_str(&r.map_err(|e| e.to_string())?).map_err(|e| e.to_string())
        })
        .collect()
    }
    pub fn save_skill(&self, s: &Skill) -> Result<()> {
        if uuid::Uuid::parse_str(&s.id).is_err() {
            return Err("无效 skill ID".into());
        }
        if s.body.len() > 100_000 || s.name.trim().is_empty() {
            return Err("skill 为空或超过 100 KB".into());
        }
        let dir = self.root.join("skills").join(&s.id);
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let content = format!(
            "---\nname: {}\ndescription: {}\nstatus: {}\n---\n\n{}\n",
            serde_json::to_string(&s.name).unwrap(),
            serde_json::to_string(&s.description).unwrap(),
            s.status,
            s.body
        );
        let target = dir.join("SKILL.md");
        let temp = dir.join("SKILL.md.tmp");
        std::fs::write(&temp, content).map_err(|e| e.to_string())?;
        std::fs::rename(&temp, &target).map_err(|e| e.to_string())?;
        self.conn
            .execute(
                "INSERT OR REPLACE INTO skills VALUES(?1,?2)",
                params![s.id, serde_json::to_string(s).unwrap()],
            )
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    pub fn remember(&self, project: &str, text: &str, kind: &str) -> Result<()> {
        if text.trim().is_empty() || text.len() > 8000 {
            return Err("记忆需为 1–8000 字节".into());
        }
        let tx = self
            .conn
            .unchecked_transaction()
            .map_err(|e| e.to_string())?;
        let exists: bool = tx
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM memories WHERE project_id=?1 AND text=?2)",
                params![project, text],
                |r| r.get(0),
            )
            .map_err(|e| e.to_string())?;
        if !exists {
            tx.execute(
                "INSERT INTO memories VALUES(?1,?2,?3,?4,?5)",
                params![id(), project, text, kind, now()],
            )
            .map_err(|e| e.to_string())?;
            tx.execute(
                "INSERT INTO recall VALUES(?1,?2,?3)",
                params![project, kind, text],
            )
            .map_err(|e| e.to_string())?;
        }
        tx.commit().map_err(|e| e.to_string())
    }
    pub fn memories(&self, project: &str) -> Result<Vec<Memory>> {
        let mut q=self.conn.prepare("SELECT id,text,kind,project_id,updated FROM memories WHERE project_id=?1 OR project_id='global' ORDER BY updated DESC LIMIT 100").map_err(|e|e.to_string())?;
        let rows = q
            .query_map([project], |r| {
                Ok(Memory {
                    id: r.get(0)?,
                    text: r.get(1)?,
                    kind: r.get(2)?,
                    project_id: r.get(3)?,
                    updated_at: r.get(4)?,
                })
            })
            .map_err(|e| e.to_string())?;
        rows.map(|r| r.map_err(|e| e.to_string())).collect()
    }
    pub fn recall(&self, query: &str, project: &str) -> Result<Vec<Value>> {
        let q = query.trim();
        if q.is_empty() {
            return Ok(vec![]);
        }
        let mut stmt=self.conn.prepare("SELECT project_id,kind,text FROM recall WHERE (project_id=?1 OR project_id='global') AND text LIKE ?2 ESCAPE '\\' ORDER BY rowid DESC LIMIT 12").map_err(|e|e.to_string())?;
        let pattern = format!(
            "%{}%",
            q.replace('\\', "\\\\")
                .replace('%', "\\%")
                .replace('_', "\\_")
        );
        let rows=stmt.query_map(params![project,pattern],|r|Ok(json!({"projectId":r.get::<_,String>(0)?,"kind":r.get::<_,String>(1)?,"text":r.get::<_,String>(2)?}))).map_err(|e|e.to_string())?;
        rows.map(|r| r.map_err(|e| e.to_string())).collect()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn durable_state_and_unicode_recall() {
        let dir = tempfile::tempdir().unwrap();
        let s = Store::open(dir.path()).unwrap();
        let mut p = s.active().unwrap();
        p.spec.assumptions.push(SpecItem {
            id: id(),
            text: "板厚 6 mm".into(),
            source: "待确认".into(),
        });
        s.save_project(&p).unwrap();
        s.remember(&p.id, "舵轮接口需要重新测量", "fact").unwrap();
        s.remember(&p.id, "舵轮接口需要重新测量", "fact").unwrap();
        assert_eq!(s.memories(&p.id).unwrap().len(), 1);
        assert_eq!(s.recall("舵轮", &p.id).unwrap().len(), 1);
        drop(s);
        assert_eq!(
            Store::open(dir.path())
                .unwrap()
                .active()
                .unwrap()
                .spec
                .assumptions
                .len(),
            1
        );
    }
    #[test]
    fn skill_path_cannot_escape() {
        let dir = tempfile::tempdir().unwrap();
        let s = Store::open(dir.path()).unwrap();
        assert!(s
            .save_skill(&Skill {
                id: "../outside".into(),
                name: "x".into(),
                description: String::new(),
                body: "x".into(),
                source: "import".into(),
                status: "draft".into(),
                enabled: false,
                updated_at: now()
            })
            .is_err());
    }
}
