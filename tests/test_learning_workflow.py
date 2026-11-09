"""Integration of remembered context and cancellable learning; no CAD or paid AI."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_workbench import server, FakeBridge


def payload(summary='记住接口约束',lessons=None):
    return {'summary':summary,'decisions':['以本项目已确定接口为准'], 'open_items':['未验证项保留'], 'lessons':lessons or []}


class LearningProvider:
    def __init__(self):
        self.prompts=[];self.started=threading.Event();self.release=None;self.fail=False;self.lesson=False
    def query(self,prompt,schema,cancel_event=None,**kwargs):
        self.prompts.append(prompt)
        if 'message' in schema.get('properties',{}): return {'message':'已保留设计约束','summary':'继续讨论','steps':[]}
        self.started.set()
        if self.release is not None: self.release.wait(3)
        if self.fail: raise RuntimeError('Injected summary failure')
        start=prompt.find('\n{')+1
        bundle=json.JSONDecoder().raw_decode(prompt[start:])[0]
        lessons=[]
        if self.lesson:
            evidence=bundle['evidence']
            lessons=[{'title':'回读安装板外形','when_to_use':'生成带确定外形要求的安装板后',
                      'procedure':['创建本任务原生零件','读取实际几何尺寸'],
                      'verification':['三个方向均与目标尺寸一致'],
                      'pitfalls':['配置名称不能替代实际几何'],
                      'evidence_ids':[evidence[0]['id']]}]
        return payload('项目目标与已验证范围已总结',lessons)


class LearningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='workbench-learning-')
        self.root=Path(self.temp.name);self.provider=LearningProvider()
        self.app=server.Workbench(self.root,bridge=FakeBridge(),provider=self.provider)
    def tearDown(self):
        self.app.cancel_learning()
        self.provider.release.set() if self.provider.release else None
        if self.app.learning_thread:self.app.learning_thread.join(4)
        if self.app.worker:self.app.worker.join(4)
        self.temp.cleanup()
    def wait_learning(self):
        self.app.learning_thread.join(4)
        self.assertFalse(self.app.learning_thread.is_alive())
    def evidence(self,phase='completed'):
        out=Path(self.app.state['output_dir'])
        path=out/'evidence'/'measured.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'tool':'solidworks_bounding_box','result':{'status':'ok','size_mm':[80,50,6]}}),encoding='utf-8')
        self.app.state.update(phase=phase,steps=[{'id':'1','title':'检查外形','status':'passed','attempt':1,'detail':'实测80、50、6',
            'records':[{'tool':'solidworks_bounding_box','path':str(path),'status':'passed'}]}])
        self.app.save()

    def test_design_receives_constraint_older_than_recent_message_window(self):
        self.app.state['messages']=[{'role':'user','content':'安装孔距必须44 mm，保留电机接口'}]+[
            {'role':'assistant','content':'布局讨论'+str(i)} for i in range(30)]
        self.app.save();self.app.start_chat('继续优化安装板')
        self.app.worker.join(4)
        self.assertEqual(self.app.state['phase'],'idle')
        prompt=self.provider.prompts[-1]
        start=prompt.find('\n{')+1;data=json.JSONDecoder().raw_decode(prompt[start:])[0]
        self.assertNotIn('44',json.dumps(data['conversation'],ensure_ascii=False))
        self.assertIn('44',json.dumps(data['project_memory_and_relevant_skills'],ensure_ascii=False))

    def test_remember_command_persists_without_model_call_and_is_project_scoped(self):
        self.app.start_chat('/remember 安装孔距44 mm')
        self.assertEqual(self.provider.prompts,[])
        old_project=self.app.knowledge.project_id(self.app.state)
        restarted=server.Workbench(self.root,bridge=FakeBridge(),provider=self.provider)
        self.assertIn('44',str(restarted.knowledge_view()['notes']))
        restarted.new()
        self.assertNotEqual(restarted.knowledge.project_id(restarted.state),old_project)
        self.assertNotIn('44',str(restarted.knowledge_view()['notes']))

    def test_summary_without_lessons_updates_memory_without_fabricating_skill(self):
        self.app.start_learning(generate_skill=True);self.wait_learning()
        info=self.app.knowledge_view()
        self.assertIn('项目目标',info['summary']['summary'])
        self.assertEqual(info['skills'],[])
        self.assertEqual(self.app.knowledge.session(info['project_id'])['summary']['summary'],info['summary']['summary'])
        self.assertEqual(info['learning']['error'],'')

    def test_completed_source_and_real_evidence_generate_enabled_skill(self):
        self.evidence();self.provider.lesson=True
        self.app.start_learning(generate_skill=True);self.wait_learning()
        info=self.app.knowledge_view()
        self.assertEqual(info['learning']['error'],'')
        self.assertEqual(len(info['skills']),1)
        self.assertTrue(info['skills'][0]['enabled'])
        self.assertTrue(Path(info['skills'][0]['path']).is_file())
        self.assertIn('回读安装板',self.app.knowledge_skill(info['skills'][0]['id'])['content'])

    def test_unaccepted_source_generates_draft_instead_of_verified_skill(self):
        self.evidence(phase='review_required');self.provider.lesson=True
        self.app.start_learning(generate_skill=True);self.wait_learning()
        info=self.app.knowledge_view();self.assertFalse(info['skills'][0]['enabled'])
        self.assertIn('草稿',info['learning']['status'])

    def test_late_review_cannot_overwrite_new_foreground_requirements(self):
        self.provider.release=threading.Event();self.app.start_learning()
        self.assertTrue(self.provider.started.wait(2))
        self.app.start_chat('/remember 新安装孔距改为48 mm')
        self.provider.release.set();self.wait_learning()
        info=self.app.knowledge_view()
        self.assertIsNone(info['summary'])
        self.assertIn('48',str(info['notes']))

    def test_restart_and_new_project_show_the_correct_summary_state(self):
        self.app.start_learning();self.wait_learning()
        restarted=server.Workbench(self.root,bridge=FakeBridge(),provider=self.provider)
        self.assertIn('恢复',restarted.learning['status'])
        self.assertIsNotNone(restarted.knowledge_view()['summary'])
        restarted.new()
        self.assertEqual(restarted.learning['status'],'尚未总结')
        self.assertIsNone(restarted.knowledge_view()['summary'])

    def test_failed_summary_keeps_previous_summary_and_original_messages(self):
        self.app.start_learning();self.wait_learning()
        previous=copy.deepcopy(self.app.knowledge_view()['summary'])
        messages=copy.deepcopy(self.app.state['messages']);self.provider.fail=True
        self.app.start_learning();self.wait_learning()
        self.assertEqual(self.app.knowledge_view()['summary'],previous)
        self.assertEqual(self.app.state['messages'],messages)
        self.assertIn('Injected',self.app.learning['error'])

    def test_new_project_preempts_review_without_mixing_its_summary(self):
        self.provider.release=threading.Event();self.app.start_learning()
        self.assertTrue(self.provider.started.wait(2));old=self.app.knowledge.project_id(self.app.state)
        self.app.new();self.provider.release.set();self.wait_learning()
        self.assertNotEqual(old,self.app.knowledge.project_id(self.app.state))
        self.assertIsNone(self.app.knowledge_view()['summary'])

    def test_long_conversation_rolls_summary_before_the_next_design(self):
        self.app.settings['auto_compact_history']=True
        self.app.state['messages']=[{'role':'user','content':'孔距44 mm'}]+[
            {'role':'assistant','content':'中间讨论'+str(i)} for i in range(25)]
        self.app.save();self.app.start_chat('继续设计')
        self.app.worker.join(4)
        self.assertFalse(self.app.worker.is_alive())
        self.assertEqual(len(self.provider.prompts),2)
        info=self.app.knowledge_view()
        self.assertGreaterEqual(info['summary']['covered_message_count'],26)
        self.assertEqual(self.app.state['phase'],'idle')

    def test_cancelled_review_cannot_capture_old_snapshot_before_query(self):
        class DeferredThread:
            def __init__(self,target,args=(),**kwargs):self.target=target;self.args=args
            def start(self):pass
            def join(self,*args):pass
            def is_alive(self):return False
            def run(self):self.target(*self.args)
        with mock.patch.object(server.threading,'Thread',DeferredThread):
            self.app.start_learning()
            pending=self.app.learning_thread
            self.app.start_chat('/remember 最新材料改成尼龙')
        current=self.app.knowledge.project_id(self.app.state)
        pending.run()
        recorded=self.app.knowledge.session(current)['messages']
        self.assertIn('尼龙',json.dumps(recorded,ensure_ascii=False))
        self.assertFalse(self.provider.started.is_set())

    def test_natural_language_correction_survives_failed_or_disabled_compaction(self):
        self.app.state['messages']=[{'role':'user','content':'安装板采用铝合金'}]
        self.app.save()
        bundle=self.app.knowledge.source_bundle(self.app.knowledge_state())
        self.app.knowledge.save_summary(bundle['project_id'],bundle['source_hash'],payload('安装板采用铝合金'))
        self.app.state['messages'].append({'role':'user','content':'换成尼龙'})
        self.app.state['messages'].extend({'role':'assistant','content':'后续讨论'+str(i)} for i in range(30))
        self.app.save();self.app.start_chat('继续按之前的要求设计')
        self.app.worker.join(4)
        prompt=self.provider.prompts[-1];start=prompt.find('\n{')+1
        data=json.JSONDecoder().raw_decode(prompt[start:])[0]
        self.assertNotIn('尼龙',json.dumps(data['conversation'],ensure_ascii=False))
        memory=data['project_memory_and_relevant_skills']
        self.assertIn('尼龙',json.dumps(memory['early_requirements'],ensure_ascii=False))
        self.assertIn('铝合金',json.dumps(memory['summary'],ensure_ascii=False))
        self.assertIn('较新的用户修正',memory['scope_rule'])

    def test_failed_or_needs_review_checks_never_auto_enable_a_learned_skill(self):
        from knowledge import _status
        for check in [{'required':True,'ok':False},{'required':True,'status':'needs_review'}]:
            with self.subTest(check=check):
                self.evidence()
                path=Path(self.app.state['output_dir'])/'evidence'/'measured.json'
                result={'status':'ok','checks':[check]}
                path.write_text(json.dumps({'tool':'solidworks_bounding_box','result':result}),encoding='utf-8')
                self.assertNotEqual(server.verdict(result)[0],'passed')
                self.assertEqual(_status(result),server.verdict(result)[0])
                self.app.save();self.provider.lesson=True
                self.app.start_learning(generate_skill=True);self.wait_learning()
                info=self.app.knowledge_view()
                self.assertEqual(info['learning']['error'],'')
                self.assertFalse(info['skills'][0]['enabled'])

if __name__=='__main__':unittest.main()
