import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cad_library import CadLibrary
from test_workbench import server,FakeBridge

DATA=b'local cad fixture'
class Stub(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  model={'id':'fixture','name':'舵轮','entry':{'path':'module.step','sha256':hashlib.sha256(DATA).hexdigest()},'downloads':{'package_sha256':hashlib.sha256(DATA).hexdigest(),'package_name':'package.zip'},'source_url':'https://bbs.robomaster.com/article/1','verification':{'motion_verified':False},'limitations':['未验证']}
  if self.path.endswith('/package') or self.path.endswith('/file'):raw=b'changed' if self.server.corrupt else DATA
  else:raw=json.dumps({'items':[model]} if self.path.startswith('/v1/search') else model).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
class CatalogIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.http=ThreadingHTTPServer(('127.0.0.1',0),Stub);self.http.corrupt=False
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
  self.client=CadLibrary(self.root,'http://127.0.0.1:'+str(self.http.server_port))
 def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()
 def test_search_download_and_provenance(self):
  self.assertEqual(self.client.context('舵轮')['status'],'ok')
  result=self.client.download('fixture');self.assertEqual(Path(result['path']).read_bytes(),DATA)
  self.assertTrue(result['download_verified']);self.assertFalse(result['assembly_verified'])
  self.assertTrue(Path(result['path']+'.json').exists())
  self.assertNotEqual(result['path'],self.client.download('fixture')['path'])
 def test_bad_hash_no_final_file(self):
  self.http.corrupt=True
  with self.assertRaises(ValueError):self.client.download('fixture')
  self.assertEqual(list((self.root/'data/library-downloads/fixture').iterdir()),[])
 def test_boundary(self):
  for url in ['https://example.com','http://localhost@evil.com','http://127.0.0.1/private']:
   with self.assertRaises(ValueError):CadLibrary(self.root,url)
  with self.assertRaises(ValueError):self.client.download('../../escape')
  with patch.object(self.client,'search',side_effect=OSError()):self.assertEqual(self.client.context('x')['status'],'unavailable')
 def test_ai_receives_retrieval_before_plan_and_selected_download(self):
  prompts=[]
  class Provider:
   def query(self,prompt,*args,**kwargs):prompts.append(prompt);return {'message':'参考fixture来源，运动未验证','summary':'参考已有模型','steps':[]}
   def status(self):return {'available':True}
  app=server.Workbench(self.root,bridge=FakeBridge(),provider=Provider());app.cad_library=self.client
  result=app.library_download('fixture');self.assertTrue(result['attached_to_current_task'])
  app.state['messages'].append({'role':'user','content':'设计舵轮','at':app.now()});app.design()
  self.assertTrue(prompts);self.assertIn('cad_library',prompts[0]);self.assertIn('https://bbs.robomaster.com/article/1',prompts[0]);self.assertIn('selected_download',prompts[0]);self.assertEqual(app.state['steps'],[])
  app.state['busy']=True
  with self.assertRaises(ValueError):app.library_download('fixture')

class StartupRecoveryTests(unittest.TestCase):
 def test_connection_refused_retries_after_start(self):
  import io
  from urllib.error import URLError
  client=CadLibrary(Path('unused'))
  with patch.object(client.http,'open',side_effect=[URLError(ConnectionRefusedError()),io.BytesIO(b'{"items":[]}')]), patch.object(client,'_start_local_service',return_value=True) as start:
   self.assertEqual(client.search('wheel')['items'],[]);start.assert_called_once()
 def test_http_errors_do_not_launch_process(self):
  from urllib.error import HTTPError
  client=CadLibrary(Path('unused'))
  with patch.object(client.http,'open',side_effect=HTTPError('local',404,'not found',{},None)),patch.object(client,'_start_local_service') as start:
   with self.assertRaises(ValueError):client.search('wheel')
   start.assert_not_called()
 def test_custom_port_never_autostarts_default(self):
  self.assertFalse(CadLibrary(Path('unused'),'http://127.0.0.1:8766')._start_local_service())
