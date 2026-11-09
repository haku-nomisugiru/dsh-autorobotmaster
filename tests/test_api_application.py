"""Direct-HTTP integration of API settings, planning, CAD guards and remembered learning.
No external model service, real API key or live SolidWorks is used.
"""
from __future__ import annotations
import copy
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_workbench import server,FakeBridge,raw_step,action,assertion
from provider import ApiProvider


def schema_sample(schema):
    if 'enum' in schema:return schema['enum'][0]
    kind=schema.get('type')
    if kind=='object':return {k:schema_sample(v) for k,v in schema.get('properties',{}).items()}
    if kind=='array':return []
    if kind=='boolean':return True
    if kind in ('integer','number'):return 1
    return '连接正常'


def all_strings(node):
    if isinstance(node,str):yield node
    elif isinstance(node,dict):
        for value in node.values():yield from all_strings(value)
    elif isinstance(node,list):
        for value in node:yield from all_strings(value)


class ModelStub(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path,data,self.headers.get('Authorization')))
        if getattr(self.server,'release',None) is not None:self.server.release.wait(4)
        fmt=(data.get('text') or {}).get('format') or data.get('response_format') or {}
        schema=fmt.get('schema') or (fmt.get('json_schema') or {}).get('schema')
        prompt=next((s for s in all_strings(data) if '\n{' in s and ('output_dir' in s or 'source_hash' in s)),None)
        if prompt:
            bundle=json.JSONDecoder().raw_decode(prompt[prompt.index('\n{')+1:])[0]
            if 'output_dir' in bundle:
                output=str(Path(bundle['output_dir'])/'api_plate.SLDPRT')
                checks=[{'label':'三个方向外形','tool':'solidworks_bounding_box','arguments_json':json.dumps({'params':{'response_format':'json'}}),
                         'assertions':[assertion('size_mm.0',expected=80),assertion('size_mm.1',expected=60),assertion('size_mm.2',expected=8)]}]
                answer={'message':'已生成安装板计划，待你开始建模。','summary':'80×60×8 mm安装板',
                        'steps':[raw_step('solidworks_create_basic_part',shape='box',width_mm=80,height_mm=60,depth_mm=8,output_path=output,checks=checks)]}
            else:
                evidence=bundle.get('evidence') or []
                ids=[e['id'] for e in evidence if e.get('tool')=='solidworks_bounding_box']
                if not ids:ids=[e['id'] for e in evidence[:1]]
                lesson={'title':'用实测核对安装板','when_to_use':'安装板主体创建后','procedure':['创建原生零件','回读几何外形'],
                        'verification':['三个方向尺寸与要求一致'],'pitfalls':['接口成功不能代替尺寸实测'],'evidence_ids':ids}
                answer={'summary':'当前安装板已完成建模，验收状态按项目证据保留。','decisions':['项目尺寸80×60×8 mm'],'open_items':[],
                        'lessons':[lesson] if ids else []}
        else:answer=schema_sample(schema or {'type':'object','properties':{'ok':{'type':'boolean'}}})
        if self.server.invalid:answer={'unexpected':'invalid output'}
        if self.path.endswith('/responses'):
            result={'id':'resp_local','object':'response','status':'completed','model':'local-model','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(answer,ensure_ascii=False)}]}],
                    'usage':{'input_tokens':12,'output_tokens':12,'total_tokens':24}}
        else:result={'id':'chat_local','model':'local-model','choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(answer,ensure_ascii=False)}}],
                     'usage':{'prompt_tokens':12,'completion_tokens':12,'total_tokens':24}}
        raw=json.dumps(result,ensure_ascii=False).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except ConnectionError:pass


class ApiApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rm-api-integration-');self.root=Path(self.temp.name)
        self.stub=ThreadingHTTPServer(('127.0.0.1',0),ModelStub);self.stub.requests=[];self.stub.invalid=False;self.stub.daemon_threads=True
        self.stub_thread=threading.Thread(target=self.stub.serve_forever,daemon=True);self.stub_thread.start()
        self.bridge=FakeBridge();self.app=server.Workbench(self.root,bridge=self.bridge)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.http.app=self.app;self.http.token='local-test-token';self.http.daemon_threads=True
        self.http_thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.http_thread.start()
    def tearDown(self):
        self.app.cancel.set();self.app.cancel_learning()
        if getattr(self.stub,'release',None) is not None:self.stub.release.set()
        if self.app.worker:self.app.worker.join(4)
        if self.app.learning_thread:self.app.learning_thread.join(4)
        self.http.shutdown();self.http.server_close();self.stub.shutdown();self.stub.server_close();self.temp.cleanup()
    def config(self,protocol='responses',**extra):
        cfg={'protocol':protocol,'base_url':f'http://127.0.0.1:{self.stub.server_port}/v1','model':'local-model',
             'structured_output':'json_schema','timeout_seconds':10,'max_output_tokens':6000,'api_key_env':'RM_TEST_UNUSED',
             'token_parameter':'max_completion_tokens','api_key':'local-fixture-secret'}
        cfg.update(extra);return cfg
    def request(self,method,path,payload=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=10)
        request_headers={'X-Workbench-Token':self.http.token,'Content-Type':'application/json'}
        if headers is not None:request_headers.update(headers)
        raw=None if payload is None else json.dumps(payload)
        connection.request(method,path,body=raw,headers=request_headers)
        response=connection.getresponse();result=json.loads(response.read());status=response.status;connection.close();return status,result
    def wait_worker(self):
        self.app.worker.join(5);self.assertFalse(self.app.worker.is_alive())
    def plan(self,protocol='responses',**extra):
        self.assertEqual(self.request('POST','/api/settings',self.config(protocol,**extra))[0],200)
        self.assertEqual(self.request('POST','/api/chat',{'message':'制作80×60×8 mm安装板，核验三向尺寸。'})[0],200)
        self.wait_worker();self.assertEqual(self.app.state['phase'],'ready',self.app.state['error'])

    def test_missing_configuration_preserves_notes_and_history(self):
        status,_=self.request('POST','/api/chat',{'message':'制作安装板'})
        self.assertEqual(status,400);self.assertFalse(self.stub.requests);self.assertEqual(self.bridge.calls,[])
        self.assertEqual(len(self.app.state['messages']),1)
        self.assertEqual(self.request('POST','/api/chat',{'message':'/remember 使用M4接口'})[0],200)
        self.assertEqual(len(self.app.knowledge_view()['notes']),1)

    def test_settings_never_return_plain_key_and_do_not_send_model_request(self):
        before=copy.deepcopy(self.app.knowledge_state())
        status,saved=self.request('POST','/api/settings',self.config())
        self.assertEqual(status,200);self.assertTrue(saved['has_api_key']);self.assertNotIn('local-fixture-secret',json.dumps(saved))
        self.assertEqual(self.request('GET','/api/settings')[0],200)
        self.assertNotIn('local-fixture-secret',json.dumps(self.request('GET','/api/state')[1]))
        self.assertEqual(self.app.knowledge_state(),before);self.assertFalse(self.stub.requests)
        self.assertNotIn('local-fixture-secret',(self.root/'data/api-settings.json').read_text())
        self.assertNotIn(b'local-fixture-secret',(self.root/'data/api-key.bin').read_bytes())

    def test_responses_plan_to_manual_acceptance_and_restarted_memory(self):
        self.app.settings['auto_summary_after_accept']=True
        self.plan();self.app.start_run();self.wait_worker()
        self.assertEqual(self.app.state['phase'],'review_required');self.assertNotIn('accepted_at',self.app.state)
        self.app.control('accept')
        if self.app.learning_thread:self.app.learning_thread.join(5)
        self.assertEqual(self.app.state['phase'],'completed')
        summary=self.app.knowledge.summary(self.app.knowledge.project_id(self.app.state))
        self.assertIsNotNone(summary,self.app.learning)
        self.assertGreaterEqual(len(self.stub.requests),2)
        restarted=server.Workbench(self.root,bridge=FakeBridge())
        self.assertEqual(restarted.state['phase'],'completed');self.assertIsNotNone(restarted.knowledge_view()['summary'])
        self.assertTrue(any(path.endswith('/responses') for path,_,_ in self.stub.requests))

    def test_chat_completion_json_object_mode_still_validates_and_runs(self):
        self.plan('chat_completions',structured_output='json_object',token_parameter='max_tokens')
        self.app.start_run();self.wait_worker();self.assertEqual(self.app.state['phase'],'review_required')
        path,data,_=self.stub.requests[0];self.assertTrue(path.endswith('/chat/completions'))
        self.assertEqual(data['response_format']['type'],'json_object')

    def test_invalid_model_output_never_creates_or_mutates_cad(self):
        self.request('POST','/api/settings',self.config());self.stub.invalid=True
        self.app.start_chat('制作安装板');self.wait_worker()
        self.assertEqual(self.app.state['phase'],'failed');self.assertEqual(self.bridge.calls,[])
        self.assertEqual(self.app.state['steps'],[])

    def test_draft_connection_test_does_not_save_key_or_configuration(self):
        before=copy.deepcopy(self.app.knowledge_state())
        status,result=self.request('POST','/api/settings/test',self.config())
        self.assertEqual(status,200,result);self.assertTrue(result['ok'],result)
        self.assertFalse((self.root/'data/api-settings.json').exists());self.assertFalse((self.root/'data/api-key.bin').exists())
        self.assertEqual(self.app.knowledge_state(),before)

    def test_active_design_blocks_configuration_change(self):
        self.app.state.update(busy=True,phase='designing')
        self.assertEqual(self.request('POST','/api/settings',self.config())[0],400)
        self.assertFalse((self.root/'data/api-settings.json').exists());self.assertEqual(self.app.state['phase'],'designing')
        self.app.state['busy']=False

    def test_settings_route_requires_token_and_rejects_browser_origin(self):
        for headers in [{'X-Workbench-Token':'invalid'},{'Origin':'https://example.invalid'},{'Host':'example.invalid'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET','/api/settings',headers=headers)[0],403)
                self.assertEqual(self.request('POST','/api/settings',self.config(),headers=headers)[0],403)
        self.assertFalse((self.root/'data/api-settings.json').exists())

    def test_non_object_payload_is_rejected(self):
        self.assertEqual(self.request('POST','/api/settings',['invalid'])[0],400)

    def test_settings_update_preserves_existing_document_and_memory(self):
        self.app.owned_document={'title':'owned.SLDPRT','path':str(Path(self.app.state['output_dir'])/'owned.SLDPRT')}
        self.app.knowledge_note('当前接口采用M4')
        before=copy.deepcopy(self.app.knowledge_state())
        self.assertEqual(self.request('POST','/api/settings',self.config())[0],200)
        self.assertEqual(self.app.knowledge_state(),before)
        self.assertEqual(len(self.app.knowledge_view()['notes']),1)

    def test_accept_without_api_key_keeps_completed_state(self):
        out=Path(self.app.state['output_dir'])/'owned.SLDPRT'
        self.bridge.call('solidworks_create_basic_part',{'params':{'output_path':str(out)}})
        self.app.owned_document=copy.deepcopy(self.bridge.active)
        self.app.state.update(phase='review_required',steps=[{'id':'1','title':'检查','status':'review_required','attempt':1,'detail':'等待用户确认'}])
        self.app.settings['auto_summary_after_accept']=True
        self.app.control('accept')
        self.assertEqual(self.app.state['phase'],'completed');self.assertFalse(self.app.learning['busy'])
        self.assertIn('API',self.app.learning['status']);self.assertFalse(self.stub.requests)

    def test_corrupt_api_configuration_can_be_repaired_via_settings_route(self):
        path=self.root/'data/api-settings.json';path.write_text('{broken',encoding='utf-8')
        public=self.request('GET','/api/settings')[1]
        self.assertIn('error',public);self.assertEqual(path.read_text(),'{broken')
        status,saved=self.request('POST','/api/settings',self.config())
        self.assertEqual(status,200,saved);self.assertTrue(saved['has_api_key'])
        self.assertEqual(json.loads(path.read_text())['model'],'local-model')
        self.assertFalse(self.stub.requests)

    def test_settings_change_preempts_old_review_without_late_summary_commit(self):
        from test_learning_workflow import LearningProvider
        old=LearningProvider();old.release=threading.Event()
        self.app.provider=old;self.app.models.provider=old
        self.app.start_learning();self.assertTrue(old.started.wait(2))
        status,_=self.request('POST','/api/settings',self.config())
        self.assertEqual(status,200)
        old.release.set();self.app.learning_thread.join(4)
        self.assertFalse(self.app.learning['busy']);self.assertIsNone(self.app.knowledge_view()['summary'])
        self.assertIsInstance(self.app.provider,ApiProvider)
        self.assertIsNot(self.app.learning_provider(),self.app.provider)

    def test_closing_connection_test_cancels_wait_and_keeps_draft_unsaved(self):
        self.stub.release=threading.Event()
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        connection.request('POST','/api/settings/test',body=json.dumps(self.config()),headers={
            'X-Workbench-Token':self.http.token,'Content-Type':'application/json'})
        deadline=time.monotonic()+2
        while not self.stub.requests and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(self.stub.requests)
        connection.close()
        deadline=time.monotonic()+2;released=False
        while time.monotonic()<deadline:
            if self.app.models.test_lock.acquire(blocking=False):
                self.app.models.test_lock.release();released=True;break
            time.sleep(.02)
        self.assertTrue(released,'API test was not cancelled after the UI connection closed')
        self.assertFalse((self.root/'data/api-settings.json').exists())
        self.stub.release.set()

if __name__=='__main__':unittest.main()
