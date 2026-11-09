"""Runtime restart invariants without starting CAD or contacting model APIs."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from runtime import reusable_connection,write_manifest,mark_stopped

class RuntimeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'runtime.json'
    def tearDown(self):self.temp.cleanup()
    def connection(self,**extra):
        result={'url':'http://127.0.0.1:53421','token':'a'*64,'pid':1234};result.update(extra);return result
    def test_clean_stop_preserves_reusable_address_and_token(self):
        write_manifest(self.path,self.connection());mark_stopped(self.path,1234)
        restored=reusable_connection(self.path)
        self.assertEqual(restored['url'],'http://127.0.0.1:53421');self.assertEqual(restored['token'],'a'*64);self.assertEqual(restored['pid'],0)
        write_manifest(self.path,dict(restored,pid=5678));self.assertEqual(reusable_connection(self.path)['pid'],5678)
    def test_old_process_cannot_mark_new_process_stopped(self):
        write_manifest(self.path,self.connection(pid=5678));mark_stopped(self.path,1234)
        self.assertEqual(reusable_connection(self.path)['pid'],5678)
    def test_invalid_or_nonlocal_manifest_is_not_reused(self):
        for url in ['https://127.0.0.1:53','http://example.invalid:53','http://user@127.0.0.1:53','http://127.0.0.1:53/path','http://127.0.0.1:53?query=1','http://127.0.0.1:53#fragment','http://127.0.0.1:0']:
            with self.subTest(url=url):
                write_manifest(self.path,self.connection(url=url));self.assertIsNone(reusable_connection(self.path))
    def test_invalid_token_and_corrupt_manifest_are_not_reused(self):
        write_manifest(self.path,self.connection(token='short'));self.assertIsNone(reusable_connection(self.path))
        self.path.write_text('{broken');self.assertIsNone(reusable_connection(self.path))
if __name__=='__main__':unittest.main()
