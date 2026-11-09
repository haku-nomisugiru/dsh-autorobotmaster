"""Isolated API configuration/credential tests; no model requests."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from api_config import ApiConfigError,ApiSettingsStore,DEFAULTS,DpapiCipher,normalize_base_url


class FakeCipher:
    def encrypt(self,data): return b"test-encrypted:"+base64.b64encode(data)
    def decrypt(self,data):
        if not data.startswith(b"test-encrypted:"): raise ValueError("invalid test ciphertext")
        return base64.b64decode(data.split(b":",1)[1])


class ApiConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.env={}
        self.store=ApiSettingsStore(self.root,cipher=FakeCipher(),environ=self.env)

    def tearDown(self): self.temp.cleanup()

    def test_unconfigured_store_is_available_for_ui_without_writing_defaults(self):
        config=self.store.public_config()
        self.assertEqual(config["protocol"],"responses")
        self.assertEqual(config["base_url"],"https://api.openai.com/v1")
        self.assertEqual(config["max_output_tokens"],6000)
        self.assertEqual(config["timeout_seconds"],180)
        self.assertFalse(config["has_api_key"])
        self.assertFalse(self.store.settings_path.exists())
        self.assertNotIn("api_key",config)

    def test_saved_key_is_encrypted_and_never_in_public_or_settings_json(self):
        public=self.store.update({"model":"test-model","api_key":"plain-test-secret"})
        self.assertTrue(public["has_api_key"])
        self.assertEqual(public["key_source"],"dpapi")
        self.assertNotIn("plain-test-secret",json.dumps(public))
        self.assertNotIn("plain-test-secret",self.store.settings_path.read_text(encoding="utf-8"))
        self.assertNotIn(b"plain-test-secret",self.store.key_path.read_bytes())
        self.assertEqual(self.store.snapshot()["api_key"],"plain-test-secret")

    def test_key_and_settings_survive_reopening_store(self):
        self.store.update({"model":"demo","api_key":"saved-test-key"})
        other=ApiSettingsStore(self.root,cipher=FakeCipher(),environ={})
        self.assertEqual(other.snapshot()["api_key"],"saved-test-key")

    def test_empty_or_missing_api_key_preserves_saved_key(self):
        self.store.update({"api_key":"saved-test-key"})
        self.store.update({"model":"another","api_key":""})
        self.store.update({"structured_output":"json_object"})
        self.assertEqual(self.store.snapshot()["api_key"],"saved-test-key")

    def test_explicit_clear_only_removes_managed_saved_key(self):
        self.store.update({"api_key":"saved-test-key"})
        self.store.update({"clear_api_key":True})
        self.assertFalse(self.store.key_path.exists())
        self.assertFalse(self.store.public_config()["has_api_key"])

    def test_clear_and_new_key_cannot_be_ambiguous(self):
        with self.assertRaises(ApiConfigError):
            self.store.update({"clear_api_key":True,"api_key":"new-key"})

    def test_snapshot_draft_never_persists_key_settings_or_host_binding(self):
        self.store.update({"model":"old","api_key":"old-key"})
        before_settings=self.store.settings_path.read_bytes()
        before_key=self.store.key_path.read_bytes()
        draft=self.store.snapshot({"base_url":"https://example.test/v1","model":"new","api_key":"new-key"})
        self.assertEqual(draft["api_key"],"new-key")
        self.assertEqual(draft["model"],"new")
        self.assertEqual(before_settings,self.store.settings_path.read_bytes())
        self.assertEqual(before_key,self.store.key_path.read_bytes())
        self.assertEqual(self.store.snapshot()["api_key"],"old-key")

    def test_switching_host_does_not_send_saved_secret_to_new_host(self):
        self.store.update({"api_key":"official-key"})
        public=self.store.update({"base_url":"https://example.test/v1"})
        self.assertFalse(public["has_api_key"])
        self.assertEqual(public["key_source"],"host_changed")
        self.assertEqual(self.store.snapshot()["api_key"],"")
        self.store.update({"base_url":"https://api.openai.com/v1"})
        self.assertEqual(self.store.snapshot()["api_key"],"official-key")

    def test_new_key_is_bound_to_new_host(self):
        self.store.update({"api_key":"old-key"})
        self.store.update({"base_url":"https://example.test/v1","api_key":"new-key"})
        self.assertEqual(self.store.snapshot()["api_key"],"new-key")
        self.store.update({"base_url":"https://api.openai.com/v1"})
        self.assertEqual(self.store.snapshot()["api_key"],"")

    def test_same_host_different_path_keeps_key_and_different_port_does_not(self):
        self.store.update({"api_key":"key"})
        self.store.update({"base_url":"https://api.openai.com:443/custom/v1"})
        self.assertEqual(self.store.snapshot()["api_key"],"key")
        self.store.update({"base_url":"https://api.openai.com:444/v1"})
        self.assertEqual(self.store.snapshot()["api_key"],"")

    def test_dedicated_environment_and_official_fallback_priority(self):
        self.env.update(ROBOMASTER_API_KEY="dedicated",OPENAI_API_KEY="official")
        self.assertEqual(self.store.snapshot()["api_key"],"dedicated")
        self.env.pop("ROBOMASTER_API_KEY")
        self.assertEqual(self.store.snapshot()["api_key"],"official")
        self.store.update({"api_key":"stored"})
        self.assertEqual(self.store.snapshot()["api_key"],"stored")

    def test_host_change_does_not_implicitly_rebind_same_environment_name(self):
        self.env["ROBOMASTER_API_KEY"]="official-dedicated"
        self.store.update({"model":"demo"})
        self.store.update({"base_url":"https://third.test/v1","api_key_env":"ROBOMASTER_API_KEY"})
        self.assertEqual(self.store.snapshot()["api_key"],"")
        self.env["THIRD_API_KEY"]="third-dedicated"
        self.store.update({"api_key_env":"THIRD_API_KEY"})
        self.assertEqual(self.store.snapshot()["api_key"],"third-dedicated")

    def test_openai_fallback_only_uses_exact_official_https_host(self):
        self.env["OPENAI_API_KEY"]="official-private"
        self.store.update({"base_url":"https://api.openai.com.example.test/v1"})
        self.assertFalse(self.store.public_config()["has_api_key"])
        with self.assertRaises(ApiConfigError):
            self.store.update({"api_key_env":"OPENAI_API_KEY"})

    def test_url_policy_rejects_credentials_query_fragment_and_remote_http(self):
        urls=["http://example.test/v1","https://user:pass@example.test/v1",
              "https://example.test/v1?token=private","https://example.test/v1#fragment",
              "file:///tmp/api","https://example.test/a/../v1",
              "https://example.test/v1?","https://example.test/v1#"]
        for url in urls:
            with self.subTest(url=url),self.assertRaises(ApiConfigError):
                normalize_base_url(url)

    def test_loopback_http_and_trailing_slash_normalization(self):
        for value in ("http://127.0.0.1:1234/v1","http://localhost:1234/v1","http://[::1]:1234/v1"):
            self.assertEqual(normalize_base_url(value+"/"),value)

    def test_invalid_enums_and_budget_types_rejected(self):
        for payload in ({"protocol":"unknown"},{"structured_output":"auto"},
                        {"token_parameter":"output_tokens"},{"timeout_seconds":0},
                        {"timeout_seconds":True},{"timeout_seconds":float("nan")},
                        {"max_output_tokens":31},{"max_output_tokens":6000.1},
                        {"api_key_env":"bad name"},{"api_key":"line\nbreak"}):
            with self.subTest(payload=payload),self.assertRaises(ApiConfigError):
                self.store.update(payload)

    def test_invalid_saved_json_is_not_erased_and_valid_draft_can_repair(self):
        self.store.settings_path.write_text("{corrupt-json",encoding="utf-8")
        with self.assertRaises(ApiConfigError): self.store.public_config()
        draft=self.store.snapshot({"model":"repaired","api_key":"new-key"})
        self.assertEqual(draft["model"],"repaired")
        self.assertEqual(self.store.settings_path.read_text(encoding="utf-8"),"{corrupt-json")
        self.assertFalse(self.store.key_path.exists())
        self.store.update({"model":"repaired","api_key":"new-key"})
        self.assertEqual(self.store.snapshot()["api_key"],"new-key")

    def test_invalid_repair_draft_does_not_touch_bad_file(self):
        self.store.settings_path.write_text("{bad",encoding="utf-8")
        with self.assertRaises(ApiConfigError): self.store.snapshot({"base_url":"http://remote.test"})
        self.assertEqual(self.store.settings_path.read_text(encoding="utf-8"),"{bad")

    def test_other_settings_file_is_never_overwritten(self):
        old=self.root/"settings.json"
        old.write_text('{"existing":"preserve"}',encoding="utf-8")
        self.store.update({"model":"demo"})
        self.assertEqual(old.read_text(encoding="utf-8"),'{"existing":"preserve"}')

    def test_cipher_error_never_echoes_plain_secret(self):
        class BrokenCipher:
            def encrypt(self,data): raise RuntimeError("plain-test-secret")
        store=ApiSettingsStore(self.root,cipher=BrokenCipher(),environ={})
        with self.assertRaises(ApiConfigError) as error:
            store.update({"api_key":"plain-test-secret"})
        self.assertNotIn("plain-test-secret",str(error.exception))
        self.assertFalse(store.key_path.exists())

    @unittest.skipUnless(os.name=="nt","Windows DPAPI round-trip only")
    def test_real_windows_dpapi_round_trip(self):
        cipher=DpapiCipher()
        secret=b"local-dpapi-unit-test-no-network"
        encrypted=cipher.encrypt(secret)
        self.assertNotEqual(secret,encrypted)
        self.assertNotIn(secret,encrypted)
        self.assertEqual(cipher.decrypt(encrypted),secret)


if __name__=="__main__": unittest.main()
