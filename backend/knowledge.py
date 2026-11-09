"""Local, evidence-grounded project memory and learned skills.

Lightweight adaptation of patterns studied in NousResearch/hermes-agent:
bounded explicit notes, immutable summary inputs, progressive skill loading,
and locked atomic writes. No Hermes runtime or user Hermes data is loaded.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import sqlite3
import tempfile
import threading
import unicodedata

MAX_NOTE_CHARS = 1200
MAX_PROJECT_NOTE_CHARS = 8000
MAX_GLOBAL_NOTE_CHARS = 6000
MAX_ALL_NOTE_CHARS = 48000
MAX_BUNDLE_CHARS = 100000
MAX_EVIDENCE_BYTES = 512000
MAX_SKILL_CHARS = 100000
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SENSITIVE_KEYS = re.compile(
    r"(?i)^(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|"
    r"authorization|cookie|client[_-]?secret)$"
)
_BAD = {"error", "fail", "failed", "blocked", "invalid", "timeout"}
_WARN = {"warn", "warning", "review_required", "needs_review", "partial", "unknown"}
_FLAGS = {"success", "saved", "save_ok", "save_success", "exported", "rebuild_ok",
          "rebuild_success", "rebuild_succeeded", "feature_created"}
_TEXT_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_text(text):
    text = str(text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{12,})",
                  "[REDACTED]", text)
    text = re.sub(r"(?i)\b(Bearer\s+)[^\s\"',;]+", r"\1[REDACTED]", text)
    text = re.sub(
        r"""(?i)(["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|client[_-]?secret|password|secret|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}\]]+)""",
        r"\1[REDACTED]", text)
    return text


def _clean(value):
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _SENSITIVE_KEYS.match(str(k)) else _clean(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _norm(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def _slug(text, prefix="project"):
    raw = str(text)
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw.casefold()).strip("-_")
    if not slug or not slug[0].isalnum():
        slug = prefix + "-" + _hash(raw)[:12]
    if len(slug) > 64:
        slug = slug[:49].rstrip("-_") + "-" + _hash(raw)[:12]
    return slug


def _tokens(text):
    text = _norm(text)
    terms = set(re.findall(r"[a-z0-9_]+", text))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        terms.update(run[i:i+2] for i in range(len(run)-1))
        if len(run) == 1:
            terms.add(run)
    return terms


def _status(result):
    """Use actual JSON evidence, never a record's/model's claimed success."""
    failures, warnings, positives = [], [], []
    def walk(node, optional=False):
        if isinstance(node, dict):
            optional = optional or node.get("required") is False
            failed = warnings if optional else failures
            status = str(node.get("status", "")).casefold()
            if status in _BAD: failed.append(status)
            if status in _WARN: warnings.append(status)
            if status in {"ok", "success", "pass", "passed", "completed"}: positives.append(status)
            if node.get("isError") is True: failed.append("protocol error")
            if node.get("manual_review_required") is True: warnings.append("manual review")
            if node.get("errors"): failed.append("errors")
            for key, value in node.items():
                if key in _FLAGS or (key in {"passed", "ok", "success"} and node.get("required") is True):
                    if value is False: failed.append(key)
                    elif value is True: positives.append(key)
                    elif not (key == "saved" and value is None and not node.get("output_path")):
                        warnings.append(key)
                if key in {"document", "previews", "artifact_refs", "arguments"}:
                    continue
                if isinstance(value, (dict, list)): walk(value, optional)
        elif isinstance(node, list):
            for value in node: walk(value, optional)
    walk(result)
    return "failed" if failures else "review_required" if warnings else "passed" if positives else "unverified"


def _atomic_text(path, text):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("拒绝覆盖符号链接：" + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".knowledge-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try: Path(temporary).unlink()
        except FileNotFoundError: pass


class KnowledgeStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = self.root / "data"
        if not self.data.resolve().is_relative_to(self.root):
            raise ValueError("知识库目录不能指向项目之外。")
        self.data.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data / "knowledge.sqlite3"
        self.skills_root = self.root / "skills" / "learned"
        self._lock = threading.RLock()
        with self._lock, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects(
                    project_id TEXT PRIMARY KEY,title TEXT NOT NULL,phase TEXT NOT NULL,
                    updated_at TEXT NOT NULL,state_json TEXT NOT NULL,source_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS bundles(
                    project_id TEXT NOT NULL,source_hash TEXT NOT NULL,bundle_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,PRIMARY KEY(project_id,source_hash));
                CREATE TABLE IF NOT EXISTS summaries(
                    project_id TEXT PRIMARY KEY,source_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes(
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL,scope TEXT NOT NULL,
                    text TEXT NOT NULL,content_hash TEXT NOT NULL,created_at TEXT NOT NULL,
                    UNIQUE(project_id,scope,content_hash));
                CREATE TABLE IF NOT EXISTS skills(
                    id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,title TEXT NOT NULL,
                    description TEXT NOT NULL,version INTEGER NOT NULL,enabled INTEGER NOT NULL,
                    path TEXT NOT NULL,source_project_id TEXT,content_hash TEXT NOT NULL,
                    files_json TEXT NOT NULL,manual_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            """)

    @contextmanager
    def _db(self):
        # A corrupt database raises; never silently reset or replace it.
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def project_id(state):
        output = str(state.get("output_dir") or "")
        if output:
            name = PureWindowsPath(output).name if "\\" in output else Path(output).name
        else:
            project = state.get("project") or {}
            name = project.get("id") or project.get("name") or "unassigned"
        return _slug(name)

    def _state(self, state):
        messages = []
        for message in state.get("messages", []):
            if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
                continue
            if message.get("hidden") is True or message.get("display_kind") == "hidden":
                continue
            messages.append({k: _clean(message[k]) for k in ("role", "content", "at") if k in message})
        return _clean({
            "project": state.get("project") or {}, "output_dir": state.get("output_dir") or "",
            "phase": state.get("phase") or "unknown", "messages": messages,
            "steps": state.get("steps") or [], "history": state.get("history") or [],
            "plan_summary": state.get("plan_summary") or "",
            "owned_document": state.get("owned_document"),
            "active_document": state.get("active_document"),
            "accepted_at": state.get("accepted_at"), "error": state.get("error") or "",
        })

    @staticmethod
    def _brief_steps(steps):
        return [{k: item.get(k) for k in ("id", "title", "status", "attempt", "detail")}
                for item in steps if isinstance(item, dict)]

    def _evidence(self, state):
        output = Path(state.get("output_dir") or "")
        if not output.is_absolute():
            return []
        output = output.resolve()
        result, seen = [], set()
        steps = list(state.get("steps") or [])
        for history in state.get("history") or []:
            if isinstance(history, dict):
                steps.extend(history.get("steps") or [])
        for step in steps:
            if not isinstance(step, dict): continue
            for record in step.get("records") or []:
                if not isinstance(record, dict): continue
                try:
                    path = Path(record.get("path") or "").resolve()
                    if not path.is_relative_to(output) or path.suffix.lower() != ".json" or not path.is_file():
                        continue
                    if path.stat().st_size > MAX_EVIDENCE_BYTES:
                        continue
                    raw = path.read_bytes()
                    if len(raw) > MAX_EVIDENCE_BYTES: continue
                    document = json.loads(raw.decode("utf-8-sig"))
                    if not isinstance(document, dict) or "result" not in document:
                        continue
                    actual = _clean(document["result"])
                    relative = path.relative_to(output).as_posix()
                    digest = hashlib.sha256(raw).hexdigest()
                    evidence_id = "ev-" + _hash(relative + "\0" + digest)[:24]
                    if evidence_id in seen: continue
                    seen.add(evidence_id)
                    serialized = _json(actual)
                    result.append({
                        "id": evidence_id, "tool": str(document.get("tool") or record.get("tool") or "")[:160],
                        "status": _status(actual), "result_summary": serialized[:1800],
                        "source_file": str(path), "source_sha256": digest,
                        "step_id": str(step.get("id") or ""), "step_title": str(step.get("title") or "")[:200],
                    })
                    if len(result) >= 80: return result
                except (OSError, ValueError, TypeError, UnicodeError):
                    continue
        return result

    def _bundle(self, state, project_id):
        messages = state["messages"]
        rows = []
        clipped = False
        for index, message in enumerate(messages):
            row = dict(message)
            content = str(row.get("content") or "")
            clipped = clipped or len(content) > 12000
            row.update(id="message-"+str(index+1), content=content[:12000])
            rows.append(row)
        history = []
        for item in state["history"][-8:]:
            if isinstance(item, dict):
                history.append({"at":item.get("at"),"summary":str(item.get("summary") or "")[:1500],
                                "steps":self._brief_steps(item.get("steps") or [])})
        bundle = {
            "project_id":project_id,"title":str(state["project"].get("name") or project_id)[:200],
            "phase":state["phase"],"messages":rows,"total_messages":len(messages),
            "history":history,"steps":self._brief_steps(state["steps"]),
            "evidence":self._evidence(state),"owned_document":state.get("owned_document"),
            "plan_summary":str(state.get("plan_summary") or "")[:2500],
            "accepted_at":state.get("accepted_at"),"truncated":clipped,
            "source_kind":"frozen_project_snapshot",
        }
        # Keep every visible turn while it fits. Old assistant prose yields first;
        # user constraints and recent turns take priority when compaction is needed.
        while len(_json(bundle)) > MAX_BUNDLE_CHARS:
            bundle["truncated"] = True
            if bundle["history"]:
                bundle["history"].pop(0)
                continue
            long_evidence = next((item for item in bundle["evidence"]
                                  if len(item["result_summary"]) > 500),None)
            if long_evidence is not None:
                long_evidence["result_summary"] = long_evidence["result_summary"][:500]
                continue
            rows = bundle["messages"]
            middle = range(4,max(4,len(rows)-16))
            assistant = next((i for i in middle if rows[i].get("role") != "user"),None)
            if assistant is not None:
                rows.pop(assistant)
                continue
            long_user = next((rows[i] for i in middle if len(rows[i]["content"]) > 1000),None)
            if long_user is not None:
                long_user["content"] = long_user["content"][:1000]
                continue
            if len(rows) > 20:
                rows.pop(4)
                continue
            if len(bundle["evidence"]) > 8:
                bundle["evidence"].pop(0)
                continue
            long_row = next((row for row in rows if len(row["content"]) > 500),None)
            if long_row is not None:
                long_row["content"] = long_row["content"][:500]
                continue
            bundle["steps"] = bundle["steps"][:24]
            for step in bundle["steps"]:
                step["detail"] = str(step.get("detail") or "")[:300]
            if len(_json(bundle)) > MAX_BUNDLE_CHARS:
                raise ValueError("项目元数据超出总结容量，请缩小项目上下文。")
        bundle["source_hash"] = _hash(_json(bundle))
        return bundle

    def capture(self, state):
        clean = self._state(state)
        project_id = self.project_id(state)
        bundle = self._bundle(clean, project_id)
        now = _now()
        with self._lock, self._db() as db:
            db.execute("""INSERT INTO projects VALUES(?,?,?,?,?,?)
                       ON CONFLICT(project_id) DO UPDATE SET title=excluded.title,phase=excluded.phase,
                       updated_at=excluded.updated_at,state_json=excluded.state_json,source_hash=excluded.source_hash""",
                       (project_id, bundle["title"], clean["phase"], now, _json(clean), bundle["source_hash"]))
            db.execute("INSERT OR IGNORE INTO bundles VALUES(?,?,?,?)",
                       (project_id, bundle["source_hash"], _json(bundle), now))
        return {"project_id": project_id, "source_hash": bundle["source_hash"],
                "message_count": len(clean["messages"]), "evidence_count": len(bundle["evidence"])}

    def session(self, project_id):
        with self._lock, self._db() as db:
            row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None: raise ValueError("项目记录不存在。")
        state = json.loads(row["state_json"])
        state.update(project_id=project_id, title=row["title"], updated_at=row["updated_at"],
                     source_hash=row["source_hash"])
        state["summary"] = self.summary(project_id)
        return state

    def source_bundle(self, state):
        captured = self.capture(state)
        with self._lock, self._db() as db:
            row = db.execute("SELECT bundle_json FROM bundles WHERE project_id=? AND source_hash=?",
                             (captured["project_id"], captured["source_hash"])).fetchone()
        return json.loads(row[0])

    def summary(self, project_id):
        with self._lock, self._db() as db:
            row = db.execute("SELECT * FROM summaries WHERE project_id=?", (project_id,)).fetchone()
            if row is None: return None
            bundle = db.execute("SELECT bundle_json FROM bundles WHERE project_id=? AND source_hash=?",
                                (project_id,row["source_hash"])).fetchone()
            covered = json.loads(bundle[0]).get("total_messages",0) if bundle else 0
        payload = json.loads(row["payload_json"])
        payload.update(source_hash=row["source_hash"],generated_at=row["created_at"],
                       covered_message_count=covered)
        return payload

    @staticmethod
    def _skill_row(row):
        result = {key: row[key] for key in (
            "id", "name", "title", "description", "version", "enabled", "path", "source_project_id")}
        result["enabled"] = bool(result["enabled"])
        return result

    def snapshot(self, project_id):
        with self._lock, self._db() as db:
            notes = [dict(row) for row in db.execute(
                "SELECT id,text,scope,created_at FROM notes WHERE project_id=? OR scope='global' ORDER BY created_at,id",
                (project_id,))]
            sessions = [dict(row) for row in db.execute(
                "SELECT project_id,title,phase,updated_at FROM projects ORDER BY updated_at DESC,project_id LIMIT 50")]
            skills = [self._skill_row(row) for row in db.execute("SELECT * FROM skills ORDER BY updated_at DESC,id")]
            count = db.execute("SELECT count(*) FROM projects").fetchone()[0]
        return {"project_id": project_id, "summary": self.summary(project_id), "notes": notes,
                "sessions": sessions, "skills": skills,
                "stats": {"sessions": count, "notes": len(notes), "skills": len(skills)}}

    def add_note(self, project_id, text, scope="project"):
        if scope not in {"project", "global"}: raise ValueError("记忆范围只能是 project 或 global。")
        if not isinstance(text, str): raise TypeError("记忆必须是文本。")
        text = _redact_text(text).strip()
        if not text or len(text) > MAX_NOTE_CHARS: raise ValueError("单条记忆应为 1–1200 字符。")
        owner = "" if scope == "global" else project_id
        digest = _hash(_norm(text))
        with self._lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,text,scope,created_at FROM notes WHERE project_id=? AND scope=? AND content_hash=?",
                             (owner, scope, digest)).fetchone()
            if row: return dict(row)
            budget = MAX_GLOBAL_NOTE_CHARS if scope == "global" else MAX_PROJECT_NOTE_CHARS
            current = db.execute("SELECT coalesce(sum(length(text)),0) FROM notes WHERE project_id=? AND scope=?",
                                 (owner, scope)).fetchone()[0]
            total = db.execute("SELECT coalesce(sum(length(text)),0),count(*) FROM notes").fetchone()
            if current+len(text) > budget or total[0]+len(text) > MAX_ALL_NOTE_CHARS or total[1] >= 200:
                raise ValueError("记忆容量已满，请先整理或忘记不再适用的条目。")
            note = {"id": "note-"+_hash(owner+"\0"+scope+"\0"+digest)[:24],
                    "text": text, "scope": scope, "created_at": _now()}
            db.execute("INSERT INTO notes VALUES(?,?,?,?,?,?)",
                       (note["id"], owner, scope, text, digest, note["created_at"]))
            return note

    def forget_note(self, note_id, project_id):
        with self._lock, self._db() as db:
            row = db.execute("SELECT scope,project_id FROM notes WHERE id=?", (note_id,)).fetchone()
            if row and row["scope"] != "global" and row["project_id"] != project_id:
                raise ValueError("不能删除其他项目的记忆。")
            db.execute("DELETE FROM notes WHERE id=?", (note_id,))

    @staticmethod
    def _validate_payload(payload, known):
        required = {"summary", "decisions", "open_items", "lessons"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError("总结字段应为 summary、decisions、open_items、lessons。")
        if not isinstance(payload["summary"], str) or len(payload["summary"]) > 12000:
            raise ValueError("总结必须是有界文本。")
        for key in ("decisions", "open_items"):
            if not isinstance(payload[key], list) or len(payload[key]) > 30 or any(
                not isinstance(v, str) or len(v) > 1500 for v in payload[key]):
                raise ValueError("总结列表格式或容量不正确：" + key)
        if not isinstance(payload["lessons"], list) or len(payload["lessons"]) > 20:
            raise ValueError("经验列表最多包含 20 条。")
        fields = {"title", "when_to_use", "procedure", "verification", "pitfalls", "evidence_ids"}
        for lesson in payload["lessons"]:
            if not isinstance(lesson, dict) or set(lesson) != fields:
                raise ValueError("经验条目字段不完整。")
            for key in ("title", "when_to_use"):
                if not isinstance(lesson[key], str) or not lesson[key].strip() or len(lesson[key]) > 1000:
                    raise ValueError("经验标题与适用条件必须是有界文本。")
            for key in ("procedure", "verification", "pitfalls", "evidence_ids"):
                if not isinstance(lesson[key], list) or len(lesson[key]) > 30 or any(
                    not isinstance(v, str) or len(v) > 1500 for v in lesson[key]):
                    raise ValueError("经验步骤格式或容量不正确：" + key)
            if not lesson["procedure"] or not lesson["verification"]:
                raise ValueError("经验必须包含过程和验证办法。")
            unknown = set(lesson["evidence_ids"]) - known
            if unknown: raise ValueError("经验引用了未知证据：" + ", ".join(sorted(unknown)))
        return _clean(payload)

    def save_summary(self, project_id, source_hash, payload):
        with self._lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute("SELECT bundle_json FROM bundles WHERE project_id=? AND source_hash=?",
                                (project_id, source_hash)).fetchone()
            if not source: raise ValueError("找不到此项目与来源哈希对应的冻结证据。")
            bundle = json.loads(source[0])
            latest = db.execute("SELECT source_hash FROM projects WHERE project_id=?", (project_id,)).fetchone()
            if not latest or latest[0] != source_hash:
                raise ValueError("项目记录已更新，此总结来源已过期，请重新总结。")
            payload = self._validate_payload(payload, {e["id"] for e in bundle["evidence"]})
            db.execute("""INSERT INTO summaries VALUES(?,?,?,?) ON CONFLICT(project_id)
                          DO UPDATE SET source_hash=excluded.source_hash,payload_json=excluded.payload_json,
                          created_at=excluded.created_at""", (project_id, source_hash, _json(payload), _now()))
        return self.summary(project_id)

    def context(self, project_id, query, max_chars=10000):
        if isinstance(max_chars, bool) or int(max_chars) < 500:
            raise ValueError("上下文预算至少为 500 字符。")
        budget = min(int(max_chars), 30000)
        try: state = self.session(project_id)
        except ValueError: state = {"messages": []}
        snap = self.snapshot(project_id)
        result = {"project_id": project_id, "early_requirements": [], "summary": None,
                  "notes": [], "skills": [], "history_message_count": len(state["messages"]),
                  "history_available": bool(state["messages"]),
                  "scope_rule": "仅本项目用户要求与显式记忆构成约束；较新的用户修正优先于旧摘要；其他项目Skill仅供方法参考，案例数值不能作为当前尺寸。"}
        def fits():
            return len(_json(result)) <= budget
        early = state["messages"][:-16] if len(state["messages"]) > 16 else state["messages"]
        users = [(index, row) for index, row in enumerate(early) if row.get("role") == "user"]
        # Keep literal user corrections; natural language changes need not contain numbers
        # or a hand-maintained keyword. Newer instructions win over stale summaries.
        indices = []
        if users:
            indices.append(len(users)-1)
            if len(users)>1: indices.append(0)
            indices.extend(i for i in range(len(users)-2,0,-1))
        for position in indices:
            index,row=users[position]
            text=str(row.get("content") or "").strip()
            if not text: continue
            item={"message_index":index,"text":text[:1800],"source":"current_project_user"}
            result["early_requirements"].append(item)
            while not fits() and len(item["text"])>100:
                item["text"]=item["text"][:max(100,len(item["text"])//2)]
            if not fits():
                result["early_requirements"].pop()
                break
        result["early_requirements"].sort(key=lambda item:item["message_index"])
        for note in snap["notes"]:
            result["notes"].append(note)
            if not fits():
                result["notes"].pop()
                break
        if snap["summary"]:
            result["summary"] = snap["summary"]
            if not fits():
                result["summary"] = {"summary": snap["summary"]["summary"][:1800],
                                     "source_hash": snap["summary"]["source_hash"],
                                     "open_items": snap["summary"]["open_items"][:4]}
                if not fits(): result["summary"] = None
        query_terms = _tokens(query)
        ranked = []
        for skill in snap["skills"]:
            if not skill["enabled"]: continue
            path = Path(skill["path"])
            try:
                if not path.resolve().is_relative_to(self.skills_root.resolve()) or path.is_symlink():
                    continue
                text = path.read_text(encoding="utf-8-sig")
                if len(text) > MAX_SKILL_CHARS: continue
            except (OSError, ValueError): continue
            overlap = query_terms & _tokens(skill["title"]+" "+skill["description"]+" "+text)
            score = len(overlap) + (2 if skill["source_project_id"] == project_id else 0)
            if not overlap and query_terms: continue
            ranked.append((score, skill["id"], skill, text))
        for _, _, skill, text in sorted(ranked, key=lambda v: (-v[0], v[1]))[:3]:
            item = dict(skill, content=_redact_text(text)[:5000], not_project_constraints=True)
            result["skills"].append(item)
            if not fits():
                result["skills"].pop()
                break
        return result

    def _safe_target(self, name, relative):
        if not SAFE_NAME.fullmatch(name): raise ValueError("Skill 名称不合法。")
        relative = str(relative).replace("\\", "/")
        parts = PurePosixPath(relative)
        if parts.is_absolute() or ".." in parts.parts or ":" in relative:
            raise ValueError("Skill 文件路径不合法。")
        base = self.skills_root.resolve()
        if not base.is_relative_to(self.root):
            raise ValueError("Skill 根目录不能指向项目之外。")
        folder = self.skills_root / name
        if folder.is_symlink() or not folder.resolve().is_relative_to(base):
            raise ValueError("Skill 目录越界或为符号链接。")
        target = folder / Path(*parts.parts)
        if not target.resolve().is_relative_to(folder.resolve()) or target.is_symlink():
            raise ValueError("Skill 文件路径越界或为符号链接。")
        return target

    def _persist_skill(self, *, skill_id, name, title, description, project_id, files, enabled, manual=False):
        content_hash = _hash(_json(files))
        now = _now()
        with self._lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if old and old["content_hash"] == content_hash:
                return self._skill_row(old)
            version = old["version"]+1 if old else 1
            if old and old["manual_enabled"]:
                enabled, manual = bool(old["enabled"]), True
            paths = {relative: self._safe_target(name, relative) for relative in files}
            prior = {}
            old_files = json.loads(old["files_json"]) if old else []
            for relative in set(old_files) | set(files):
                target = self._safe_target(name, relative)
                if target.exists(): prior[relative] = target.read_text(encoding="utf-8")
            if old:
                backup = self.data / "knowledge_backups" / skill_id / ("v"+str(old["version"]))
                if backup.is_symlink() or not backup.resolve().is_relative_to(self.data.resolve()):
                    raise ValueError("Skill 备份路径越界。")
                for relative, text in prior.items():
                    backup_file = backup/relative
                    if not backup_file.resolve().is_relative_to(self.data.resolve()):
                        raise ValueError("Skill 备份文件路径越界。")
                    _atomic_text(backup_file, text)
            try:
                for relative, text in files.items():
                    if len(text) > MAX_SKILL_CHARS: raise ValueError("Skill 文本超出容量限制。")
                    _atomic_text(paths[relative], text)
                for relative in set(old_files)-set(files):
                    target = self._safe_target(name, relative)
                    if target.exists(): target.unlink()
                path = str(self._safe_target(name, "SKILL.md"))
                db.execute("""INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,title=excluded.title,
                    description=excluded.description,version=excluded.version,enabled=excluded.enabled,
                    path=excluded.path,source_project_id=excluded.source_project_id,
                    content_hash=excluded.content_hash,files_json=excluded.files_json,
                    manual_enabled=excluded.manual_enabled,updated_at=excluded.updated_at""",
                    (skill_id,name,title,description,version,int(enabled),path,project_id,
                     content_hash,_json(sorted(files)),int(manual),old["created_at"] if old else now,now))
                row = db.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            except BaseException:
                for relative in set(old_files) | set(files):
                    target = self._safe_target(name, relative)
                    if relative in prior: _atomic_text(target, prior[relative])
                    elif target.exists(): target.unlink()
                raise
            return self._skill_row(row)

    def generate_skill(self, project_id):
        summary = self.summary(project_id)
        if not summary or not summary["lessons"]:
            raise ValueError("请先生成包含可复用经验与真实证据的总结。")
        with self._lock, self._db() as db:
            source = db.execute("SELECT bundle_json FROM bundles WHERE project_id=? AND source_hash=?",
                                (project_id, summary["source_hash"])).fetchone()
        if not source: raise ValueError("总结来源证据不存在。")
        bundle = json.loads(source[0])
        evidence = {item["id"]: item for item in bundle["evidence"]}
        lessons = summary["lessons"]
        if any(not lesson["evidence_ids"] for lesson in lessons):
            raise ValueError("每条可复用经验必须引用真实证据。")
        known_ids = {key for lesson in lessons for key in lesson["evidence_ids"]}
        if known_ids - evidence.keys(): raise ValueError("总结引用了未知证据。")
        verified = bundle["phase"] == "completed" and all(
            evidence[key]["status"] == "passed" for key in known_ids)
        name = _slug("rm-modeling-"+project_id, "rm-modeling").replace("_", "-")
        title = "RoboMaster 建模经验 · "+bundle["title"]
        description = "按适用条件复用有来源的建模步骤与验收方法。"
        lines = ["---", "name: "+name,
                 "description: "+json.dumps(description, ensure_ascii=False), "---", "",
                 "# "+title, "", "状态："+("已验收来源" if verified else "待复核草稿"), "",
                 "使用前确认机构、接口、软件版本与工艺条件。以下为可复用方法，来源项目尺寸不自动成为当前设计约束。",
                 "项目来源："+project_id, "证据来源哈希："+summary["source_hash"], ""]
        for index, lesson in enumerate(lessons, 1):
            lines.extend(["## "+str(index)+". "+lesson["title"], "",
                          "适用条件："+lesson["when_to_use"], "", "步骤："])
            lines.extend(f"{i}. {text}" for i,text in enumerate(lesson["procedure"],1))
            lines.extend(["", "验证："]+["- "+text for text in lesson["verification"]])
            if lesson["pitfalls"]: lines.extend(["", "注意："]+["- "+text for text in lesson["pitfalls"]])
            lines.extend(["", "证据："+", ".join(lesson["evidence_ids"]), ""])
        lines.append("详细证据：[references/evidence.json](references/evidence.json)")
        manifest = {"project_id":project_id, "source_hash":summary["source_hash"],
                    "phase":bundle["phase"], "verified":verified,
                    "evidence":[evidence[key] for key in sorted(known_ids)]}
        return self._persist_skill(
            skill_id="skill-"+_hash(project_id)[:24], name=name, title=title, description=description,
            project_id=project_id, files={"SKILL.md":"\n".join(lines)+"\n",
            "references/evidence.json":json.dumps(manifest,ensure_ascii=False,indent=2)+"\n"}, enabled=verified)

    def set_skill_enabled(self, skill_id, enabled):
        if type(enabled) is not bool: raise ValueError("enabled 必须是布尔值。")
        with self._lock, self._db() as db:
            db.execute("UPDATE skills SET enabled=?,manual_enabled=1,updated_at=? WHERE id=?",
                       (int(enabled),_now(),skill_id))
            row = db.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if not row: raise ValueError("Skill 不存在。")
            return self._skill_row(row)

    def import_skill(self, directory):
        source = Path(directory).resolve()
        skill_md = source/"SKILL.md"
        if not skill_md.is_file() or skill_md.is_symlink():
            raise ValueError("导入目录缺少正常的 SKILL.md。")
        if skill_md.stat().st_size > MAX_SKILL_CHARS*3:
            raise ValueError("导入的 Skill 过大。")
        text = skill_md.read_text(encoding="utf-8-sig")
        match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)",text,re.S)
        if not match: raise ValueError("Skill 缺少 frontmatter。")
        fields = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                key,value=line.split(":",1)
                fields[key.strip()]=value.strip().strip("\"'")
        name = fields.get("name","")
        if not SAFE_NAME.fullmatch(name): raise ValueError("导入的 Skill 名称不合法。")
        description = fields.get("description","")[:1000]
        if not description: raise ValueError("导入的 Skill 缺少说明。")
        files = {"SKILL.md":_redact_text(text)}
        size = len(text)
        reference_root = source/"references"
        if reference_root.is_dir() and not reference_root.is_symlink():
            for path in sorted(reference_root.rglob("*")):
                if not path.is_file() or path.is_symlink() or path.suffix.lower() not in _TEXT_EXTENSIONS:
                    continue
                if not path.resolve().is_relative_to(source) or any(p.startswith(".") for p in path.relative_to(source).parts):
                    continue
                if path.stat().st_size > MAX_SKILL_CHARS*3: raise ValueError("导入参考文件过大。")
                value = path.read_text(encoding="utf-8-sig")
                size += len(value)
                if len(files)>=64 or size>400000: raise ValueError("导入文本总量超出限制。")
                files[path.relative_to(source).as_posix()] = _redact_text(value)
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")),name)[:200]
        return self._persist_skill(skill_id="imported-"+_hash(name)[:24], name=name, title=title,
                                   description=description, project_id=None, files=files,enabled=True,manual=True)
