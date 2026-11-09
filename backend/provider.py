"""Direct JSON-only model API provider. CAD is executed by the application."""
from __future__ import annotations
import contextlib
import copy
import http.client
import json
from pathlib import Path
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

try:
    from .api_config import ApiSettingsStore, ApiConfigError, validate_config
except ImportError:
    from api_config import ApiSettingsStore, ApiConfigError, validate_config

MAX_RESPONSE_BYTES=4*1024*1024


class ProviderError(RuntimeError):
    """The configured model API did not produce a usable structured response."""


class QueryCancelled(ProviderError):
    """The caller cancelled the request; no model result may be committed."""


def _safe_detail(value,limit=1000):
    text=str(value)
    text=re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{12,})","[REDACTED]",text)
    text=re.sub(r"(?i)(bearer\s+)\S+",r"\1[REDACTED]",text)
    text=re.sub(
        r"""(?i)((?:api[_-]?key|access[_-]?token|token|password|secret)\s*[:=]\s*)["']?[^"'\s,;}]+""",
        r"\1[REDACTED]",text)
    bound=max(0,int(limit))
    return text[-bound:] if bound else ""


class HttpTransport:
    """Standard-library transport; never follows HTTP redirects or uses proxies."""
    def __init__(self):
        self._lock=threading.Lock()
        self._connection=None

    def clone(self):
        return type(self)()

    def cancel(self):
        with self._lock:
            connection=self._connection
        if connection is not None:
            with contextlib.suppress(OSError,AttributeError):
                connection.sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                connection.close()

    def request(self,url,headers,body,timeout,cancel_event):
        parts=urlsplit(url)
        connection=(http.client.HTTPSConnection(parts.hostname,parts.port,
            timeout=timeout,context=ssl.create_default_context()) if parts.scheme=="https" else
            http.client.HTTPConnection(parts.hostname,parts.port,timeout=timeout))
        with self._lock:
            self._connection=connection
        try:
            if cancel_event.is_set(): raise QueryCancelled("API 请求已取消。")
            # Explicit connect lets a cancellation during DNS/TLS prevent a late
            # Authorization header from being sent after the caller has left.
            connection.connect()
            if cancel_event.is_set(): raise QueryCancelled("API 请求已取消。")
            connection.request("POST",parts.path or "/",body=body,headers=headers)
            response=connection.getresponse()
            length=response.getheader("Content-Length")
            if length is not None:
                try:
                    if int(length)>MAX_RESPONSE_BYTES:
                        raise ProviderError("API 响应过大，请缩小任务范围。")
                except ValueError:
                    raise ProviderError("API 返回了无效的响应长度。")
            chunks,size=[],0
            while True:
                if cancel_event.is_set(): raise QueryCancelled("API 请求已取消。")
                chunk=response.read(65536)
                if not chunk: break
                size+=len(chunk)
                if size>MAX_RESPONSE_BYTES:
                    raise ProviderError("API 响应过大，请缩小任务范围。")
                chunks.append(chunk)
            return response.status,dict(response.getheaders()),b"".join(chunks)
        finally:
            connection.close()
            with self._lock:
                if self._connection is connection: self._connection=None


def _load_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError("JSON 存在重复字段。")
            result[key]=value
        return result
    def constant(value):
        raise ValueError("JSON 不允许非有限数值。")
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)


def _validate_schema(schema):
    if not isinstance(schema,dict):
        raise ValueError("响应 schema 必须是 JSON 对象。")
    def scan(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key in {"$ref","$dynamicRef"} and isinstance(value,str) and not value.startswith("#"):
                    raise ValueError("响应 schema 只能使用本地引用。")
                scan(value)
        elif isinstance(node,list):
            for value in node: scan(value)
    scan(schema)
    try:
        import jsonschema
        validator=jsonschema.validators.validator_for(schema)
        validator.check_schema(schema)
        return validator(schema)
    except ImportError as exc:
        raise ProviderError("后端缺少 jsonschema，无法验证模型结果。") from exc
    except Exception as exc:
        raise ValueError("响应 schema 无效。") from exc


class ApiProvider:
    """Call Responses or Chat Completions without tools, SDKs, or subprocesses.

    config is an INTERNAL snapshot, including api_key. status()/availability()
    return only public readiness information. A clone has an independent query
    lock and transport so background learning can be cancelled separately.
    """
    def __init__(self,project_root=None,config=None,transport=None,max_retries=2):
        self.project_root=Path(project_root or Path(__file__).resolve().parents[1]).resolve()
        if config is None:
            config=ApiSettingsStore(self.project_root).snapshot()
        self._config=validate_config(config)
        key=config.get("api_key") or ""
        if not isinstance(key,str) or any(ord(ch)<32 for ch in key):
            raise ApiConfigError("API 密钥格式无效。")
        self._config["api_key"]=key.strip()
        self._config["key_source"]=str(config.get("key_source") or "none")
        self.model=self._config["model"]
        self.timeout=float(self._config["timeout_seconds"])
        self.transport=transport if transport is not None else HttpTransport()
        self.max_retries=min(2,max(0,int(max_retries)))
        self._query_lock=threading.Lock()

    def _detail(self,value,limit=1000):
        text=str(value)
        secret=self._config.get("api_key") or ""
        if secret: text=text.replace(secret,"[REDACTED]")
        return _safe_detail(text,limit)

    def availability(self):
        missing=[]
        if not self.model: missing.append("模型名称")
        if not self._config["api_key"]: missing.append("API 密钥")
        available=not missing
        return {"available":available,"model":self.model,"protocol":self._config["protocol"],
                "base_url":self._config["base_url"],
                "reason":"API 已配置，可开始设计。" if available else "请先配置"+"与".join(missing)+"。"}

    def status(self):
        return self.availability()

    def clone(self):
        transport=self.transport.clone() if hasattr(self.transport,"clone") else self.transport
        return type(self)(project_root=self.project_root,config=copy.deepcopy(self._config),
                          transport=transport,max_retries=self.max_retries)

    def _request_body(self,prompt,schema):
        instructions=(
            "你是机械设计工作台的结构化规划组件。只返回一个符合指定JSON Schema的JSON对象。"
            "不执行CAD，不调用工具，不读取文件。所有可用事实和工具说明均由请求提供；"
            "实际CAD执行和验收由应用负责。")
        if self._config["structured_output"]=="json_object":
            instructions+="目标JSON Schema："+json.dumps(schema,ensure_ascii=False,separators=(",",":"))
        if self._config["protocol"]=="responses":
            format_spec=({"type":"json_schema","name":"robomaster_result","strict":True,"schema":schema}
                         if self._config["structured_output"]=="json_schema" else {"type":"json_object"})
            return {"model":self.model,"instructions":instructions,"input":prompt,
                    "store":False,"tools":[],"max_output_tokens":self._config["max_output_tokens"],
                    "text":{"format":format_spec}}
        format_spec=({"type":"json_schema","json_schema":{
            "name":"robomaster_result","strict":True,"schema":schema}}
            if self._config["structured_output"]=="json_schema" else {"type":"json_object"})
        return {"model":self.model,"messages":[{"role":"system","content":instructions},
                {"role":"user","content":prompt}],
                self._config["token_parameter"]:self._config["max_output_tokens"],
                "response_format":format_spec}

    def _send(self,url,body,deadline,cancel_event):
        done=threading.Event()
        network_cancel=threading.Event()
        response={}
        headers={"Authorization":"Bearer "+self._config["api_key"],
                 "Content-Type":"application/json; charset=utf-8","Accept":"application/json",
                 "User-Agent":"RoboMasterWorkbench/DirectAPI"}
        def worker():
            try:
                response["value"]=self.transport.request(
                    url=url,headers=headers,body=body,
                    timeout=max(.1,deadline-time.monotonic()),cancel_event=network_cancel)
            except BaseException as exc:
                response["error"]=exc
            finally:
                done.set()
        threading.Thread(target=worker,name="workbench-model-http",daemon=True).start()
        while not done.wait(.05):
            if cancel_event is not None and cancel_event.is_set():
                network_cancel.set()
                if hasattr(self.transport,"cancel"):
                    with contextlib.suppress(Exception): self.transport.cancel()
                raise QueryCancelled("API 请求已取消。")
            if time.monotonic()>=deadline:
                network_cancel.set()
                if hasattr(self.transport,"cancel"):
                    with contextlib.suppress(Exception): self.transport.cancel()
                raise ProviderError("API 请求超时，请稍后重试或缩小任务。")
        if cancel_event is not None and cancel_event.is_set():
            network_cancel.set()
            raise QueryCancelled("API 请求已取消。")
        if time.monotonic()>=deadline:
            raise ProviderError("API 请求超时，结果未采用。")
        if "error" in response:
            error=response["error"]
            if isinstance(error,QueryCancelled): raise QueryCancelled("API 请求已取消。")
            if isinstance(error,ProviderError): raise ProviderError(self._detail(error))
            raise ProviderError("API 网络请求失败："+self._detail(error)) from error
        return response["value"]

    def _extract_text(self,payload):
        if not isinstance(payload,dict): raise ProviderError("API 响应必须是 JSON 对象。")
        if payload.get("error"):
            error=payload["error"]
            detail=error.get("message") if isinstance(error,dict) else str(error)
            raise ProviderError("API 返回错误："+self._detail(detail))
        if self._config["protocol"]=="responses":
            if payload.get("status")!="completed" or payload.get("incomplete_details"):
                raise ProviderError("模型响应未完整完成，可能被截断；请检查输出 token 上限。")
            output=payload.get("output")
            if not isinstance(output,list): raise ProviderError("Responses 返回缺少输出内容。")
            texts=[]
            for item in output:
                if not isinstance(item,dict): raise ProviderError("Responses 输出格式无效。")
                kind=item.get("type")
                if kind=="reasoning": continue
                if kind!="message" or item.get("tool_calls") or item.get("function_call"):
                    raise ProviderError("模型返回了工具调用或不支持的输出，已拒绝执行。")
                if item.get("status") not in {None,"completed"}:
                    raise ProviderError("模型消息未完整完成。")
                if item.get("refusal"):
                    raise ProviderError("模型拒绝了此次请求，请调整设计需求。")
                content=item.get("content")
                if not isinstance(content,list): raise ProviderError("Responses 消息正文无效。")
                for part in content:
                    if not isinstance(part,dict): raise ProviderError("Responses 内容格式无效。")
                    if part.get("type")=="refusal" or part.get("refusal"):
                        raise ProviderError("模型拒绝了此次请求，请调整设计需求。")
                    if part.get("type")!="output_text" or not isinstance(part.get("text"),str):
                        raise ProviderError("模型返回了不支持的非文本内容。")
                    texts.append(part["text"])
            text="".join(texts)
        else:
            choices=payload.get("choices")
            if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
                raise ProviderError("Chat Completions 返回的候选结果无效。")
            choice=choices[0]
            message=choice.get("message")
            if not isinstance(message,dict): raise ProviderError("模型消息格式无效。")
            if message.get("refusal"):
                raise ProviderError("模型拒绝了此次请求，请调整设计需求。")
            if message.get("tool_calls") or message.get("function_call"):
                raise ProviderError("模型返回了工具调用，已拒绝执行。")
            if choice.get("finish_reason")!="stop":
                raise ProviderError("模型响应未完整结束，可能被截断或过滤；请检查输出上限。")
            text=message.get("content")
            if isinstance(text,list):
                if any(not isinstance(p,dict) or p.get("type")!="text" or not isinstance(p.get("text"),str) for p in text):
                    raise ProviderError("模型返回了不支持的非文本内容。")
                text="".join(p["text"] for p in text)
        if not isinstance(text,str) or not text.strip():
            raise ProviderError("API 未返回可用的 JSON 文本。")
        return text.strip()

    def query(self,prompt,schema,cancel_event=None,on_status=None):
        if not isinstance(prompt,str) or not prompt.strip():
            raise ValueError("AI 请求不能为空。")
        validator=_validate_schema(schema)
        status=self.availability()
        if not status["available"]: raise ProviderError(status["reason"])
        if cancel_event is not None and cancel_event.is_set(): raise QueryCancelled("API 请求已取消。")
        if not self._query_lock.acquire(blocking=False):
            raise ProviderError("AI 正在处理上一项请求，请稍后再试。")
        def notify(message):
            if on_status:
                with contextlib.suppress(Exception): on_status(message)
        try:
            deadline=time.monotonic()+self.timeout
            suffix="/responses" if self._config["protocol"]=="responses" else "/chat/completions"
            url=self._config["base_url"]+suffix
            body=json.dumps(self._request_body(prompt,schema),ensure_ascii=False,allow_nan=False).encode("utf-8")
            notify("正在连接模型 API……")
            for attempt in range(self.max_retries+1):
                if cancel_event is not None and cancel_event.is_set(): raise QueryCancelled("API 请求已取消。")
                code,headers,raw=self._send(url,body,deadline,cancel_event)
                if not isinstance(code,int): raise ProviderError("API 返回了无效的 HTTP 状态。")
                if 300<=code<=399:
                    raise ProviderError("API 返回重定向，已停止以避免向其他地址发送密钥；请核对基础地址。")
                if (code==429 or 500<=code<=599) and attempt<self.max_retries:
                    delay=.3*(2**attempt)
                    for key,value in (headers or {}).items():
                        if key.lower()=="retry-after":
                            with contextlib.suppress(ValueError,TypeError):
                                delay=min(3.0,max(delay,float(value)))
                    end=min(deadline,time.monotonic()+delay)
                    notify("API 暂时繁忙，正在有限重试……")
                    while time.monotonic()<end:
                        if cancel_event is not None and cancel_event.wait(min(.05,end-time.monotonic())):
                            raise QueryCancelled("API 请求已取消。")
                        if cancel_event is None: time.sleep(max(0,min(.05,end-time.monotonic())))
                    if time.monotonic()>=deadline: raise ProviderError("API 请求超时，请稍后重试。")
                    continue
                break
            if isinstance(raw,str): raw=raw.encode("utf-8")
            if not isinstance(raw,bytes) or len(raw)>MAX_RESPONSE_BYTES:
                raise ProviderError("API 响应格式无效或超过容量限制。")
            try: payload=_load_json(raw.decode("utf-8-sig"))
            except (ValueError,UnicodeError) as exc:
                if not 200<=code<=299:
                    raise ProviderError("API HTTP "+str(code)+" 请求失败，正文不是有效 JSON。") from exc
                raise ProviderError("API 返回的正文不是有效 JSON。") from exc
            if not 200<=code<=299:
                error=payload.get("error") if isinstance(payload,dict) else None
                detail=error.get("message") if isinstance(error,dict) else error
                raise ProviderError("API HTTP "+str(code)+" 请求失败。"+
                    (" "+self._detail(detail) if detail else "请检查地址、模型、权限及服务状态。"))
            text=self._extract_text(payload)
            try: result=_load_json(text)
            except ValueError as exc:
                raise ProviderError("模型返回的结果不是有效 JSON，未用于建模。") from exc
            if not isinstance(result,dict): raise ProviderError("模型结果必须是 JSON 对象。")
            try: validator.validate(result)
            except Exception as exc:
                # Validation errors can quote model values; redact the known key.
                detail=getattr(exc,"message","字段类型或必需内容不符合约定")
                raise ProviderError("模型结果不符合约定格式："+self._detail(detail,400)) from exc
            if cancel_event is not None and cancel_event.is_set(): raise QueryCancelled("API 请求已取消。")
            notify("结构化 API 结果已生成并通过格式验证。")
            return result
        except QueryCancelled: raise
        except ProviderError as exc:
            raise ProviderError(self._detail(exc)) from None
        except Exception as exc:
            raise ProviderError("API 请求失败："+self._detail(exc)) from None
        finally:
            self._query_lock.release()

    def test_connection(self,cancel_event=None,on_status=None):
        started=time.monotonic()
        probe=self.clone()
        probe.timeout=min(self.timeout,30)
        schema={"type":"object","properties":{"ok":{"type":"boolean"}},
                "required":["ok"],"additionalProperties":False}
        try:
            result=probe.query('连接测试：只返回JSON对象 {"ok":true}。',schema,
                               cancel_event=cancel_event,on_status=on_status)
            ok=result.get("ok") is True
            message="连接成功，结构化输出验证通过。" if ok else "连接已响应，但测试结果未通过。"
        except QueryCancelled:
            raise
        except Exception as exc:
            ok=False
            message=self._detail(exc)
        return {"ok":ok,"message":message,"model":self.model,
                "protocol":self._config["protocol"],
                "elapsed_ms":round((time.monotonic()-started)*1000)}
