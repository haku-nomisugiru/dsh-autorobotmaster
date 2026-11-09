"""Model API tests using injected transports and local HTTP stubs only."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from api_config import DEFAULTS
from provider import ApiProvider,HttpTransport,ProviderError,QueryCancelled,_safe_detail

SCHEMA={"type":"object","properties":{"ok":{"type":"boolean"}},
        "required":["ok"],"additionalProperties":False}


def response_payload(value=None,text=None,status="completed"):
    if text is None: text=json.dumps({"ok":True} if value is None else value)
    return {"status":status,"output":[{"type":"message","status":"completed",
        "role":"assistant","content":[{"type":"output_text","text":text}]}]}


def chat_payload(value=None,text=None,finish="stop"):
    if text is None: text=json.dumps({"ok":True} if value is None else value)
    return {"choices":[{"finish_reason":finish,"message":{"role":"assistant","content":text}}]}


def reply(payload,code=200,headers=None):
    return code,headers or {"Content-Type":"application/json"},json.dumps(payload).encode("utf-8")


class FakeTransport:
    def __init__(self,replies):
        self.replies=list(replies)
        self.calls=[]
        self.cancelled=False

    def request(self,**kwargs):
        self.calls.append(kwargs)
        if not self.replies: raise AssertionError("unexpected retry")
        value=self.replies.pop(0)
        if isinstance(value,BaseException): raise value
        return value

    def cancel(self): self.cancelled=True


class LocalServer:
    def __init__(self,reply_func):
        self.records=[]
        parent=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers.get("Content-Length","0")))
                record={"path":self.path,"body":json.loads(body),
                        "authorization":self.headers.get("Authorization")}
                parent.records.append(record)
                code,headers,raw=reply_func(record)
                self.send_response(code)
                for key,value in headers.items(): self.send_header(key,value)
                self.send_header("Content-Length",str(len(raw)))
                self.end_headers()
                try: self.wfile.write(raw)
                except OSError: pass
        self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,
            kwargs={"poll_interval":.01},daemon=True)

    @property
    def url(self): return "http://127.0.0.1:"+str(self.server.server_port)+"/v1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self,*args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


class ApiProviderTests(unittest.TestCase):
    def config(self,**overrides):
        result=dict(DEFAULTS,model="local-test-model",api_key="dummy-local-secret",key_source="test")
        result.update(overrides)
        return result

    def provider(self,replies=None,**overrides):
        transport=FakeTransport(replies or [reply(response_payload())])
        return ApiProvider(config=self.config(**overrides),transport=transport),transport

    def test_unconfigured_provider_constructs_and_fails_before_network(self):
        fake=FakeTransport([])
        provider=ApiProvider(config={},transport=fake)
        self.assertFalse(provider.status()["available"])
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
        self.assertFalse(fake.calls)

    def test_responses_request_uses_strict_schema_and_store_false_without_tools(self):
        provider,transport=self.provider()
        self.assertEqual(provider.query("设计检查",SCHEMA),{"ok":True})
        request=transport.calls[0]
        self.assertEqual(request["url"],"https://api.openai.com/v1/responses")
        body=json.loads(request["body"])
        self.assertFalse(body["store"])
        self.assertEqual(body["tools"],[])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(body["text"]["format"]["schema"],SCHEMA)
        self.assertEqual(body["max_output_tokens"],6000)

    def test_chat_completions_request_schema_and_default_token_parameter(self):
        provider,transport=self.provider([reply(chat_payload())],protocol="chat_completions")
        self.assertEqual(provider.query("test",SCHEMA),{"ok":True})
        body=json.loads(transport.calls[0]["body"])
        self.assertEqual(transport.calls[0]["url"],"https://api.openai.com/v1/chat/completions")
        self.assertEqual(body["response_format"]["type"],"json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(body["max_completion_tokens"],6000)
        self.assertNotIn("max_tokens",body)
        self.assertNotIn("store",body)
        self.assertNotIn("tools",body)

    def test_chat_legacy_max_tokens_is_explicit(self):
        provider,transport=self.provider([reply(chat_payload())],
            protocol="chat_completions",token_parameter="max_tokens")
        provider.query("test",SCHEMA)
        body=json.loads(transport.calls[0]["body"])
        self.assertEqual(body["max_tokens"],6000)
        self.assertNotIn("max_completion_tokens",body)

    def test_responses_json_object_is_an_explicit_configuration(self):
        provider,transport=self.provider(structured_output="json_object")
        provider.query("test",SCHEMA)
        body=json.loads(transport.calls[0]["body"])
        self.assertEqual(body["text"]["format"],{"type":"json_object"})
        self.assertIn("JSON Schema",body["instructions"])

    def test_chat_json_object_still_requires_local_schema_validation(self):
        provider,transport=self.provider([reply(chat_payload({"ok":"not a bool"}))],
            protocol="chat_completions",structured_output="json_object")
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
        self.assertEqual(len(transport.calls),1)

    def test_schema_rejection_does_not_silently_downgrade_format(self):
        provider,transport=self.provider([reply({"error":{"message":"unsupported json_schema"}},400)])
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
        self.assertEqual(len(transport.calls),1)

    def test_responses_refusal_is_rejected(self):
        payload=response_payload()
        payload["output"][0]["content"]=[{"type":"refusal","refusal":"cannot comply"}]
        provider,_=self.provider([reply(payload)])
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_chat_refusal_is_rejected_even_with_json_text(self):
        payload=chat_payload()
        payload["choices"][0]["message"]["refusal"]="cannot comply"
        provider,_=self.provider([reply(payload)],protocol="chat_completions")
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_incomplete_responses_is_rejected(self):
        payload=response_payload(status="incomplete")
        payload["incomplete_details"]={"reason":"max_output_tokens"}
        provider,_=self.provider([reply(payload)])
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_chat_truncation_is_rejected_even_with_valid_json(self):
        provider,_=self.provider([reply(chat_payload(finish="length"))],protocol="chat_completions")
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_response_function_call_is_never_executed(self):
        payload=response_payload()
        payload["output"].insert(0,{"type":"function_call","name":"solidworks_create_basic_part","arguments":"{}"})
        provider,_=self.provider([reply(payload)])
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_chat_tool_call_is_rejected(self):
        payload=chat_payload()
        payload["choices"][0]["message"]["tool_calls"]=[{"type":"function","function":{"name":"cad"}}]
        provider,_=self.provider([reply(payload)],protocol="chat_completions")
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_invalid_model_json_and_duplicate_keys_are_rejected(self):
        fenced=chr(96)*3+'json\n{"ok":true}\n'+chr(96)*3
        for text in ("not json",'{"ok":true,"ok":false}',"[true]",'{"ok":NaN}',fenced):
            with self.subTest(text=text):
                provider,_=self.provider([reply(response_payload(text=text))])
                with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_schema_mismatch_is_rejected(self):
        provider,_=self.provider([reply(response_payload({"unexpected":True}))])
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)

    def test_remote_schema_reference_is_rejected_before_request(self):
        provider,transport=self.provider()
        with self.assertRaises(ValueError): provider.query("test",{"$ref":"https://example.test/schema.json"})
        self.assertFalse(transport.calls)

    def test_http_401_is_not_retried_and_secret_is_redacted(self):
        provider,transport=self.provider([reply({"error":{"message":"invalid key dummy-local-secret"}},401)])
        with self.assertRaises(ProviderError) as error: provider.query("test",SCHEMA)
        self.assertIn("401",str(error.exception))
        self.assertNotIn("dummy-local-secret",str(error.exception))
        self.assertEqual(len(transport.calls),1)

    def test_network_error_is_not_automatically_retried_and_secret_is_redacted(self):
        provider,transport=self.provider([OSError("dummy-local-secret transport failed")])
        with self.assertRaises(ProviderError) as error: provider.query("test",SCHEMA)
        self.assertNotIn("dummy-local-secret",str(error.exception))
        self.assertEqual(len(transport.calls),1)

    def test_retry_only_transient_429_and_server_errors(self):
        provider,transport=self.provider([reply({"error":{"message":"busy"}},429),
            reply({"error":{"message":"server"}},503),reply(response_payload())])
        self.assertEqual(provider.query("test",SCHEMA),{"ok":True})
        self.assertEqual(len(transport.calls),3)

    def test_transient_retries_are_bounded(self):
        provider,transport=self.provider([reply({"error":{"message":"busy"}},429)]*3)
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
        self.assertEqual(len(transport.calls),3)

    def test_json_error_on_http_error_still_reports_http_status(self):
        provider,transport=self.provider([(502,{},b"<html>bad gateway</html>")])
        provider.max_retries=0
        with self.assertRaises(ProviderError) as error: provider.query("test",SCHEMA)
        self.assertIn("502",str(error.exception))

    def test_query_lock_prevents_concurrent_requests(self):
        provider,transport=self.provider()
        provider._query_lock.acquire()
        try:
            with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
        finally: provider._query_lock.release()
        self.assertFalse(transport.calls)

    def test_clone_has_independent_lock_and_default_transport(self):
        provider=ApiProvider(config=self.config())
        clone=provider.clone()
        self.assertIsNot(provider._query_lock,clone._query_lock)
        self.assertIsNot(provider.transport,clone.transport)
        self.assertEqual(clone.status(),provider.status())
        self.assertNotIn("dummy-local-secret",json.dumps(clone.status()))

    def test_precancelled_query_never_sends_request(self):
        provider,transport=self.provider()
        cancel=threading.Event();cancel.set()
        with self.assertRaises(QueryCancelled): provider.query("test",SCHEMA,cancel_event=cancel)
        self.assertFalse(transport.calls)

    def test_cancellation_interrupts_transport_and_discards_late_result(self):
        started=threading.Event()
        class Blocking(FakeTransport):
            def request(self,**kwargs):
                started.set()
                kwargs["cancel_event"].wait(5)
                return reply(response_payload())
        transport=Blocking([])
        provider=ApiProvider(config=self.config(),transport=transport)
        cancel=threading.Event()
        result=[]
        def run():
            try: result.append(provider.query("test",SCHEMA,cancel_event=cancel))
            except BaseException as error: result.append(error)
        thread=threading.Thread(target=run)
        thread.start()
        self.assertTrue(started.wait(2))
        cancel.set();thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result[0],QueryCancelled)
        self.assertTrue(transport.cancelled)

    def test_timeout_interrupts_transport(self):
        class Blocking(FakeTransport):
            def request(self,**kwargs):
                kwargs["cancel_event"].wait(5)
                return reply(response_payload())
        transport=Blocking([])
        provider=ApiProvider(config=self.config(timeout_seconds=1),transport=transport)
        started=time.monotonic()
        with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
        self.assertLess(time.monotonic()-started,2.5)
        self.assertTrue(transport.cancelled)

    def test_connection_probe_returns_only_public_result_and_respects_configured_budget(self):
        provider,transport=self.provider()
        result=provider.test_connection()
        self.assertEqual(set(result),{"ok","message","model","protocol","elapsed_ms"})
        self.assertTrue(result["ok"])
        self.assertNotIn("dummy-local-secret",json.dumps(result))
        self.assertEqual(json.loads(transport.calls[0]["body"])["max_output_tokens"],6000)

    def test_connection_probe_failure_is_redacted(self):
        provider,_=self.provider([reply({"error":{"message":"dummy-local-secret rejected"}},401)])
        result=provider.test_connection()
        self.assertFalse(result["ok"])
        self.assertNotIn("dummy-local-secret",json.dumps(result))

    def test_local_http_stubs_cover_both_real_protocols(self):
        for protocol in ("responses","chat_completions"):
            with self.subTest(protocol=protocol):
                handler=lambda record:reply(response_payload() if protocol=="responses" else chat_payload())
                with LocalServer(handler) as server:
                    provider=ApiProvider(config=self.config(protocol=protocol,base_url=server.url))
                    self.assertEqual(provider.query("本地桩测试",SCHEMA),{"ok":True})
                    self.assertEqual(server.records[0]["authorization"],"Bearer dummy-local-secret")
                    suffix="/responses" if protocol=="responses" else "/chat/completions"
                    self.assertEqual(server.records[0]["path"],"/v1"+suffix)

    def test_redirect_never_forwards_authorization_to_destination(self):
        with LocalServer(lambda record:reply(response_payload())) as target:
            with LocalServer(lambda record:(302,{"Location":target.url+"/responses"},b"")) as initial:
                provider=ApiProvider(config=self.config(base_url=initial.url))
                with self.assertRaises(ProviderError): provider.query("test",SCHEMA)
                self.assertEqual(len(initial.records),1)
                self.assertFalse(target.records)

    def test_safe_detail_keeps_legacy_signature_and_masks_common_tokens(self):
        self.assertNotIn("sk-testtoken123456789",_safe_detail("key sk-testtoken123456789"))
        self.assertEqual(_safe_detail("abc",0),"")
        self.assertEqual(_safe_detail("abcdef",3),"def")


if __name__=="__main__": unittest.main()
