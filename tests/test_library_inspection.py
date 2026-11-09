import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from library_inspection import prepare,classify_reference,ai_evidence

class InspectionPreparationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.download=self.root/'data/library-downloads/model';self.download.mkdir(parents=True)
 def tearDown(self):self.temp.cleanup()
 def selection(self,path,data=b'cad',ext='.sldasm'):
  return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'model':{'id':'model','entry':{'path':'assets/model'+ext,'extension':ext,'sha256':hashlib.sha256(data).hexdigest()}}}
 def test_original_and_nested_layout_preserved(self):
  archive=self.download/'model.zip'
  with zipfile.ZipFile(archive,'w') as z:z.writestr('package/main.sldasm',b'cad');z.writestr('package/sub/part.sldprt',b'part')
  before=archive.read_bytes();job=prepare(self.root,self.selection(archive))
  self.assertEqual(Path(job['entry_path']).name,'main.sldasm');self.assertEqual(Path(job['entry_path']).read_bytes(),b'cad');self.assertTrue((Path(job['workspace'])/'package/sub/part.sldprt').is_file());self.assertEqual(archive.read_bytes(),before)
 def test_reject_traversal_duplicate_and_hash_changes(self):
  for entries in [[('../escape.sldasm',b'cad')],[('A.sldasm',b'cad'),('a.sldasm',b'cad')]]:
   archive=self.download/'model.zip'
   with zipfile.ZipFile(archive,'w') as z:
    for name,data in entries:z.writestr(name,data)
   with self.assertRaises(ValueError):prepare(self.root,self.selection(archive))
  f=self.download/'single.step';f.write_bytes(b'cad');selection=self.selection(f,ext='.step');f.write_bytes(b'changed')
  with self.assertRaises(ValueError):prepare(self.root,selection)
 def test_cannot_open_unregistered_outside_download(self):
  f=self.root/'other.sldasm';f.write_bytes(b'cad')
  with self.assertRaises(ValueError):prepare(self.root,self.selection(f))
 def test_missing_ambiguous_and_potential_not_resolved(self):
  a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir();p=a/'part.sldprt';p.write_bytes(b'part');other=b/'part.sldprt';other.write_bytes(b'other')
  owner=a/'main.sldasm'
  self.assertEqual(classify_reference('part.sldprt',owner,[p,other],self.root)['status'],'local_path_found')
  self.assertEqual(classify_reference(r'C:\old\part.sldprt',owner,[p,other],self.root)['status'],'ambiguous')
  self.assertEqual(classify_reference(r'C:\old\part.sldprt',owner,[p],self.root)['status'],'potential_local_match')
  self.assertEqual(classify_reference(r'C:\old\missing.sldprt',owner,[p],self.root)['status'],'missing_from_package')
 def test_ai_summary_retains_issues_and_marks_truncation(self):
  report={'status':'inspected','components':[{'name':str(i)} for i in range(200)],'dependencies':[{'status':'missing_from_package','saved_path':str(i)} for i in range(200)],'motion_verified':False}
  evidence=ai_evidence(report);self.assertEqual(len(evidence['components']),150);self.assertTrue(evidence['components_in_prompt_truncated']);self.assertTrue(evidence['dependency_issues_in_prompt_truncated']);self.assertFalse(evidence['motion_verified'])

class DependencyScopeTests(unittest.TestCase):
 def test_package_only_missing_does_not_block_selected_model(self):
  from library_inspection import scope_dependencies
  report={'entry_path':'main.sldasm','components':[{'path':'part.sldprt'}],'dependencies':[{'owner':'main.sldasm','saved_path':'part.sldprt','status':'potential_local_match'},{'owner':'other.sldasm','saved_path':'missing.sldprt','status':'missing_from_package'}]}
  scope_dependencies(report)
  self.assertEqual(report['dependency_counts'],{'potential_local_match':1})
  self.assertEqual(report['package_dependency_counts']['missing_from_package'],1)
  self.assertEqual(ai_evidence(report)['dependency_issues'],[])

class ReuseAssessmentTests(unittest.TestCase):
 def test_payload_excludes_paths_and_other_task_context(self):
  from library_inspection import reuse_payload
  selection={'sha256':'hash','model':{'id':'sample','name':'公开机构','source_url':'https://bbs.robomaster.com/article/1','entry':{'path':'D:/private/design.sldasm'},'verification':{'motion_verified':False}}}
  report={'status':'inspected','model_id':'sample','download_sha256':'hash','entry_path':'D:/private/main.sldasm','components':[{'name':'component','path':'D:/private/part.sldprt','loaded':True}], 'dependencies':[]}
  payload=reuse_payload(selection,report)
  self.assertNotIn('D:/private',json.dumps(payload));self.assertEqual(payload['components'][0]['name'],'component')
  report['model_id']='other'
  with self.assertRaises(ValueError):reuse_payload(selection,report)
 def test_assessment_local_provider_result_is_saved(self):
  from test_workbench import server,FakeBridge
  class Provider:
   def query(self,prompt,*args,**kwargs):
    self.prompt=prompt;return {'decision':'needs_target_requirements','summary':'需要目标接口','evidence':['实际组件已加载'],'missing_checks':['安装孔位','目标载荷']}
   def status(self):return {'available':True}
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);provider=Provider();app=server.Workbench(root,bridge=FakeBridge(),provider=provider)
   folder=root/'data/library-inspections/test';folder.mkdir(parents=True)
   app.state['library_selection']={'sha256':'hash','model':{'id':'sample','name':'机构','source_url':'https://bbs.robomaster.com/article/1','verification':{'motion_verified':False}}}
   app.state['library_inspection']={'status':'inspected','report':{'status':'inspected','model_id':'sample','download_sha256':'hash','report_path':str(folder/'inspection.json'),'components':[{'name':'motor','loaded':True}]}}
   app.start_library_assessment();app.worker.join(5)
   self.assertFalse(app.state['busy']);self.assertEqual(app.state['library_inspection']['assessment']['status'],'completed');self.assertIn('motor',provider.prompt);self.assertTrue((folder/'reuse-ai-result.json').is_file())

class LegacyChineseArchiveTests(unittest.TestCase):
 def test_gbk_archive_filenames_preserved(self):
  class ChineseInfo(zipfile.ZipInfo):
   def _encodeFilenameFlags(self):return self.filename.encode('gbk'),0
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);folder=root/'data/library-downloads/model';folder.mkdir(parents=True);archive=folder/'legacy.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr(ChineseInfo('机构/总装.SLDASM'),b'cad')
   selection={'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'model':{'id':'model','entry':{'path':'总装.SLDASM','extension':'.sldasm','sha256':hashlib.sha256(b'cad').hexdigest()}}}
   job=prepare(root,selection);self.assertEqual(Path(job['entry_path']).name,'总装.SLDASM');self.assertEqual(Path(job['entry_path']).parent.name,'机构')
