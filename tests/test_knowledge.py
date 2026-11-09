"""Behavioral tests for local memory, source grounding, and learned skill files."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]/"backend"
sys.path.insert(0,str(BACKEND))
from knowledge import KnowledgeStore, MAX_BUNDLE_CHARS, MAX_NOTE_CHARS


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = KnowledgeStore(self.root)
        self.state = self.make_state("project-a")

    def tearDown(self):
        self.temporary.cleanup()

    def make_state(self, name, phase="completed"):
        output = self.root/"data"/"projects"/name
        output.mkdir(parents=True,exist_ok=True)
        path = output/"evidence"/"step.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"tool":"solidworks_bounding_box",
            "result":{"status":"ok","size_mm":[80,50,6]}},ensure_ascii=False),encoding="utf-8")
        return {"project":{"name":"云台轴承支架"},"output_dir":str(output),"phase":phase,
                "messages":[{"role":"assistant","content":"请描述需求"},
                            {"role":"user","content":"安装板必须为80×50×6mm，保留M4安装孔"},
                            {"role":"assistant","content":"已形成设计"}],
                "history":[],"steps":[{"id":"1","title":"检查安装板尺寸","status":"passed",
                    "attempt":1,"detail":"尺寸符合要求","records":[{"tool":"solidworks_bounding_box",
                    "path":str(path),"status":"passed"}]}]}

    def payload(self, evidence_id):
        return {"summary":"安装板已完成尺寸验收","decisions":["先保留安装接口"],"open_items":[],
                "lessons":[{"title":"云台轴承接口建模","when_to_use":"云台轴承支架及安装接口",
                    "procedure":["先定义安装基准，再创建实体与安装孔"],
                    "verification":["回读真实孔位和尺寸"],"pitfalls":["截图不能证明接口尺寸"],
                    "evidence_ids":[evidence_id]}]}

    def summarized(self, state=None):
        state=state or self.state
        bundle=self.store.source_bundle(state)
        payload=self.payload(bundle["evidence"][0]["id"])
        saved=self.store.save_summary(bundle["project_id"],bundle["source_hash"],payload)
        return bundle,saved

    def test_capture_and_notes_survive_restarting_store(self):
        captured=self.store.capture(self.state)
        self.store.add_note(captured["project_id"],"优先采用可加工的板件")
        reopened=KnowledgeStore(self.root)
        self.assertEqual(reopened.session(captured["project_id"])["messages"],self.state["messages"])
        self.assertEqual(reopened.snapshot(captured["project_id"])["notes"][0]["text"],"优先采用可加工的板件")

    def test_capture_preserves_existing_summary(self):
        bundle,saved=self.summarized()
        self.state["messages"].append({"role":"user","content":"再增加圆角"})
        self.store.capture(self.state)
        self.assertEqual(self.store.summary(bundle["project_id"])["source_hash"],bundle["source_hash"])
        self.assertEqual(self.store.summary(bundle["project_id"])["summary"],saved["summary"])

    def test_same_source_is_stable_despite_ui_revision_and_service_fields(self):
        first=self.store.source_bundle(self.state)
        state=copy.deepcopy(self.state)
        state.update(revision=999,knowledge={"stats":{}},learning={"status":"running"},
                     service={"ai":"waiting"},progress={"passed":1})
        second=self.store.source_bundle(state)
        self.assertEqual(first["source_hash"],second["source_hash"])
        self.assertEqual(first["evidence"][0]["id"],second["evidence"][0]["id"])

    def test_visible_full_chat_is_preserved_beyond_model_window(self):
        self.state["messages"].extend({"role":"assistant","content":"解释"+str(i)} for i in range(40))
        pid=self.store.capture(self.state)["project_id"]
        context=self.store.context(pid,"安装板")
        self.assertIn("80×50×6",json.dumps(context,ensure_ascii=False))
        self.assertEqual(len(self.store.session(pid)["messages"]),43)

    def test_hidden_messages_are_not_imported_into_visible_history(self):
        self.state["messages"].append({"role":"assistant","content":"private reasoning","hidden":True})
        pid=self.store.capture(self.state)["project_id"]
        self.assertNotIn("private reasoning",json.dumps(self.store.session(pid)))

    def test_other_project_dimensions_do_not_become_current_constraints(self):
        self.store.capture(self.state)
        other=self.make_state("project-b")
        other["messages"]=[{"role":"user","content":"我的轮组宽度是9999毫米"}]
        self.store.capture(other)
        self.store.add_note("project-b","轮组宽度9999毫米")
        context=self.store.context("project-a","安装板宽度")
        self.assertNotIn("9999",json.dumps(context,ensure_ascii=False))
        self.assertEqual(len(self.store.snapshot("project-a")["sessions"]),2)

    def test_note_deduplication_normalizes_spacing(self):
        a=self.store.add_note("project-a","  使用 铝板  ")
        b=self.store.add_note("project-a","使用   铝板")
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(len(self.store.snapshot("project-a")["notes"]),1)

    def test_note_budgets_reject_instead_of_silently_truncating(self):
        with self.assertRaises(ValueError): self.store.add_note("project-a","x"*(MAX_NOTE_CHARS+1))
        for i in range(7): self.store.add_note("project-a",str(i)+"测"*1100)
        with self.assertRaises(ValueError): self.store.add_note("project-a","新增"+"测"*1198)
        self.assertEqual(len(self.store.snapshot("project-a")["notes"]),7)

    def test_global_note_visible_in_both_projects_and_can_be_forgotten(self):
        note=self.store.add_note("project-a","尺寸默认使用毫米",scope="global")
        self.assertEqual(self.store.snapshot("project-b")["notes"][0]["id"],note["id"])
        self.store.forget_note(note["id"],"project-b")
        self.assertFalse(self.store.snapshot("project-a")["notes"])

    def test_other_project_note_cannot_be_forgotten(self):
        note=self.store.add_note("project-b","仅项目B")
        with self.assertRaises(ValueError): self.store.forget_note(note["id"],"project-a")
        self.assertTrue(self.store.snapshot("project-b")["notes"])

    def test_source_bundle_ignores_missing_and_outside_evidence(self):
        outside=self.root/"outside.json"
        outside.write_text('{"result":{"status":"ok"}}',encoding="utf-8")
        self.state["steps"][0]["records"].extend([{"path":str(outside)},{"path":str(outside.parent/"absent.json")}])
        bundle=self.store.source_bundle(self.state)
        self.assertEqual(len(bundle["evidence"]),1)
        self.assertTrue(Path(bundle["evidence"][0]["source_file"]).resolve().is_relative_to(Path(self.state["output_dir"]).resolve()))

    def test_unknown_or_cross_project_evidence_ids_are_rejected(self):
        bundle=self.store.source_bundle(self.state)
        bad=self.payload("ev-forged")
        with self.assertRaises(ValueError):
            self.store.save_summary(bundle["project_id"],bundle["source_hash"],bad)
        other=self.store.source_bundle(self.make_state("project-b"))
        # Same JSON content/path can legitimately share an evidence ID across projects;
        # reject a known ID that is absent from this frozen bundle.
        other["evidence"][0]["id"]="ev-not-in-bundle"
        with self.assertRaises(ValueError):
            self.store.save_summary(bundle["project_id"],bundle["source_hash"],self.payload(other["evidence"][0]["id"]))

    def test_source_hash_must_exist_and_match_project(self):
        bundle=self.store.source_bundle(self.state)
        with self.assertRaises(ValueError):
            self.store.save_summary(bundle["project_id"],"f"*64,self.payload(bundle["evidence"][0]["id"]))
        with self.assertRaises(ValueError):
            self.store.save_summary("unrelated",bundle["source_hash"],self.payload(bundle["evidence"][0]["id"]))

    def test_stale_summary_does_not_overwrite_new_project_facts(self):
        bundle=self.store.source_bundle(self.state)
        self.state["messages"].append({"role":"user","content":"尺寸改为90毫米"})
        self.store.capture(self.state)
        with self.assertRaises(ValueError):
            self.store.save_summary(bundle["project_id"],bundle["source_hash"],self.payload(bundle["evidence"][0]["id"]))

    def test_failed_json_cannot_be_promoted_by_record_or_model(self):
        evidence=Path(self.state["steps"][0]["records"][0]["path"])
        evidence.write_text('{"tool":"solidworks_update_dimension","result":{"status":"ok","rebuild_ok":false}}',encoding="utf-8")
        bundle,_=self.summarized()
        self.assertEqual(bundle["evidence"][0]["status"],"failed")
        skill=self.store.generate_skill(bundle["project_id"])
        self.assertFalse(skill["enabled"])
        self.assertIn("待复核草稿",Path(skill["path"]).read_text(encoding="utf-8"))

    def test_required_nested_failure_cannot_become_successful_evidence(self):
        evidence=Path(self.state["steps"][0]["records"][0]["path"])
        evidence.write_text('{"result":{"status":"ok","checks":[{"required":true,"passed":false}]}}',encoding="utf-8")
        bundle=self.store.source_bundle(self.state)
        self.assertEqual(bundle["evidence"][0]["status"],"failed")

    def test_incomplete_project_only_generates_disabled_draft(self):
        self.state["phase"]="review_required"
        bundle,_=self.summarized()
        self.assertFalse(self.store.generate_skill(bundle["project_id"])["enabled"])

    def test_completed_passed_source_generates_enabled_skill(self):
        bundle,_=self.summarized()
        skill=self.store.generate_skill(bundle["project_id"])
        self.assertTrue(skill["enabled"])
        self.assertRegex(skill["name"],r"^[a-z0-9][a-z0-9-]{0,63}$")
        path=Path(skill["path"])
        self.assertTrue(path.resolve().is_relative_to((self.root/"skills"/"learned").resolve()))
        content=path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\nname: "))
        manifest=json.loads((path.parent/"references"/"evidence.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["verified"])
        self.assertEqual(manifest["source_hash"],bundle["source_hash"])

    def test_identical_summary_generation_is_idempotent(self):
        bundle,_=self.summarized()
        a=self.store.generate_skill(bundle["project_id"])
        b=self.store.generate_skill(bundle["project_id"])
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(a["version"],b["version"])
        self.assertEqual(len(self.store.snapshot(bundle["project_id"])["skills"]),1)

    def test_changed_summary_versions_skill_and_keeps_previous_files(self):
        bundle,_=self.summarized()
        first=self.store.generate_skill(bundle["project_id"])
        old=Path(first["path"]).read_text(encoding="utf-8")
        payload=self.payload(bundle["evidence"][0]["id"])
        payload["lessons"][0]["procedure"].append("核对固定侧与旋转侧")
        self.store.save_summary(bundle["project_id"],bundle["source_hash"],payload)
        second=self.store.generate_skill(bundle["project_id"])
        self.assertEqual(second["version"],2)
        backup=self.root/"data"/"knowledge_backups"/first["id"]/"v1"/"SKILL.md"
        self.assertEqual(backup.read_text(encoding="utf-8"),old)

    def test_manual_disable_remains_disabled_after_regeneration(self):
        bundle,_=self.summarized()
        skill=self.store.generate_skill(bundle["project_id"])
        self.store.set_skill_enabled(skill["id"],False)
        payload=self.payload(bundle["evidence"][0]["id"])
        payload["lessons"][0]["pitfalls"].append("重新回读配置几何")
        self.store.save_summary(bundle["project_id"],bundle["source_hash"],payload)
        self.assertFalse(self.store.generate_skill(bundle["project_id"])["enabled"])

    def test_chinese_query_retrieves_relevant_enabled_skill(self):
        bundle,_=self.summarized()
        skill=self.store.generate_skill(bundle["project_id"])
        self.store.capture(self.make_state("project-b"))
        context=self.store.context("project-b","云台轴承如何选择安装基准")
        self.assertEqual(context["skills"][0]["id"],skill["id"])
        self.assertTrue(context["skills"][0]["not_project_constraints"])

    def test_disabled_skill_is_not_loaded(self):
        bundle,_=self.summarized()
        skill=self.store.generate_skill(bundle["project_id"])
        self.store.set_skill_enabled(skill["id"],False)
        self.assertFalse(self.store.context(bundle["project_id"],"云台轴承")["skills"])

    def test_context_and_bundle_are_bounded(self):
        self.state["messages"].extend(
            {"role":"user","content":str(i)+"尺寸必须保留\n"+"说明"*4000} for i in range(60))
        bundle=self.store.source_bundle(self.state)
        self.assertLessEqual(len(json.dumps(bundle,ensure_ascii=False,separators=(",",":"))),MAX_BUNDLE_CHARS+100)
        context=self.store.context(bundle["project_id"],"尺寸",max_chars=4000)
        self.assertLessEqual(len(json.dumps(context,ensure_ascii=False,separators=(",",":"))),4000)
        self.assertIn("80×50×6",json.dumps(context,ensure_ascii=False))
        self.assertEqual(len(self.store.session(bundle["project_id"])["messages"]),63)

    def test_sensitive_text_is_scrubbed_in_notes_capture_and_summary(self):
        self.state["messages"].append({"role":"user","content":"api_key=abcdef123456 Bearer private-token"})
        bundle=self.store.source_bundle(self.state)
        serialized=json.dumps(self.store.session(bundle["project_id"]),ensure_ascii=False)
        self.assertNotIn("abcdef123456",serialized)
        self.assertNotIn("private-token",serialized)
        note=self.store.add_note(bundle["project_id"],"password=hidden123 token=hidden-token-value")
        self.assertNotIn("hidden123",note["text"])
        self.assertNotIn("hidden-token-value",note["text"])
        payload=self.payload(bundle["evidence"][0]["id"])
        payload["summary"]="secret=hidden456"
        saved=self.store.save_summary(bundle["project_id"],bundle["source_hash"],payload)
        self.assertNotIn("hidden456",saved["summary"])

    def test_no_evidence_lesson_cannot_generate_skill(self):
        bundle=self.store.source_bundle(self.state)
        payload=self.payload(bundle["evidence"][0]["id"])
        payload["lessons"][0]["evidence_ids"]=[]
        self.store.save_summary(bundle["project_id"],bundle["source_hash"],payload)
        with self.assertRaises(ValueError): self.store.generate_skill(bundle["project_id"])

    def test_project_id_is_stable_and_safe_for_unicode_and_traversal_names(self):
        for value in ("测试项目","../../escape","A"*200,".."):
            state={"output_dir":str(self.root/value)}
            a=self.store.project_id(state)
            self.assertRegex(a,r"^[a-z0-9][a-z0-9_-]{0,63}$")
            self.assertEqual(a,self.store.project_id(state))

    def test_atomic_file_failure_keeps_previous_skill_and_db_version(self):
        bundle,_=self.summarized()
        first=self.store.generate_skill(bundle["project_id"])
        original=Path(first["path"]).read_text(encoding="utf-8")
        payload=self.payload(bundle["evidence"][0]["id"])
        payload["lessons"][0]["procedure"].append("不同的新步骤")
        self.store.save_summary(bundle["project_id"],bundle["source_hash"],payload)
        import knowledge
        actual=knowledge._atomic_text
        failed=[False]
        def fail_once(path,text):
            if Path(path)==Path(first["path"]) and not failed[0]:
                failed[0]=True
                raise OSError("simulated atomic write failure")
            return actual(path,text)
        with patch("knowledge._atomic_text",side_effect=fail_once):
            with self.assertRaises(OSError): self.store.generate_skill(bundle["project_id"])
        self.assertEqual(Path(first["path"]).read_text(encoding="utf-8"),original)
        self.assertEqual(self.store.snapshot(bundle["project_id"])["skills"][0]["version"],1)

    def test_import_only_copies_bounded_reference_text_not_scripts(self):
        source=self.root/"personal-skill"
        (source/"references").mkdir(parents=True)
        (source/"scripts").mkdir()
        (source/"SKILL.md").write_text(
            '---\nname: robomaster-import-test\ndescription: "安装接口建模。"\n---\n# 安装接口\n核对孔位。\n',encoding="utf-8")
        (source/"references"/"workflow.md").write_text("原生孔位检查",encoding="utf-8")
        (source/"scripts"/"danger.py").write_text("raise RuntimeError()",encoding="utf-8")
        before=(source/"SKILL.md").read_bytes()
        imported=self.store.import_skill(source)
        self.assertTrue(imported["enabled"])
        folder=Path(imported["path"]).parent
        self.assertTrue((folder/"references"/"workflow.md").is_file())
        self.assertFalse((folder/"scripts").exists())
        self.assertEqual((source/"SKILL.md").read_bytes(),before)
        self.assertEqual(self.store.import_skill(source)["version"],1)

    def test_path_redirect_in_learned_skill_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store._safe_target("../escape","SKILL.md")
        with self.assertRaises(ValueError):
            self.store._safe_target("valid-name","references/../../outside.txt")

    def test_corrupt_database_is_not_erased(self):
        self.store.db_path.write_bytes(b"not a sqlite database")
        with self.assertRaises(sqlite3.DatabaseError): KnowledgeStore(self.root)
        self.assertEqual(self.store.db_path.read_bytes(),b"not a sqlite database")

    def test_real_timestamp_project_id_yields_codex_compatible_skill_name(self):
        state=self.make_state("20261025_154758_11c31c")
        bundle,_=self.summarized(state)
        skill=self.store.generate_skill(bundle["project_id"])
        self.assertIn("_",bundle["project_id"])
        self.assertNotIn("_",skill["name"])
        self.assertRegex(skill["name"],r"^[a-z0-9][a-z0-9-]{0,63}$")

    def test_import_rejects_non_codex_skill_name(self):
        source=self.root/"bad-import"
        source.mkdir()
        (source/"SKILL.md").write_text(
            "---\nname: bad_name\ndescription: Example.\n---\n# Example\n",encoding="utf-8")
        with self.assertRaises(ValueError): self.store.import_skill(source)

    def test_symlinked_skill_root_cannot_escape_project(self):
        outside=self.root.parent/("knowledge-outside-"+self.root.name)
        outside.mkdir(exist_ok=True)
        skills=self.root/"skills"
        try:
            try:
                skills.symlink_to(outside,target_is_directory=True)
            except OSError as exc:
                self.skipTest("Windows symlink creation unavailable: "+str(exc))
            with self.assertRaises(ValueError): self.store._safe_target("test-skill","SKILL.md")
        finally:
            if skills.is_symlink(): skills.unlink()
            outside.rmdir()

    def test_bundle_keeps_middle_user_corrections_when_under_budget(self):
        self.state["messages"].extend({"role":"user","content":"修正要求"+str(i)+"保留接口"} for i in range(40))
        bundle=self.store.source_bundle(self.state)
        self.assertEqual(len(bundle["messages"]),len(self.state["messages"]))
        self.assertIn("修正要求20",json.dumps(bundle,ensure_ascii=False))
        self.assertFalse(bundle["truncated"])

    def test_summary_reports_frozen_coverage_not_current_history_length(self):
        bundle,saved=self.summarized()
        self.assertEqual(saved["covered_message_count"],3)
        self.state["messages"].append({"role":"user","content":"新增要求"})
        self.store.capture(self.state)
        self.assertEqual(self.store.summary(bundle["project_id"])["covered_message_count"],3)

    def test_recent_early_user_correction_is_prioritized_over_old_chatter(self):
        self.state["messages"].extend({"role":"assistant","content":"背景说明"+str(i)} for i in range(40))
        self.state["messages"].append({"role":"user","content":"修改：接口孔距必须为47毫米"})
        self.state["messages"].extend({"role":"assistant","content":"近期讨论"+str(i)} for i in range(20))
        pid=self.store.capture(self.state)["project_id"]
        context=self.store.context(pid,"孔距",max_chars=4000)
        self.assertIn("47毫米",json.dumps(context,ensure_ascii=False))


if __name__=="__main__":
    unittest.main()
