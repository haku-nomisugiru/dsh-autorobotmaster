"""Public model API settings and Windows current-user DPAPI credentials."""
from __future__ import annotations
from contextlib import suppress
import ctypes
from ctypes import wintypes
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import unquote, urlsplit, urlunsplit

DEFAULTS = {
    "protocol":"responses", "base_url":"https://api.openai.com/v1", "model":"",
    "structured_output":"json_schema", "timeout_seconds":180,
    "max_output_tokens":6000, "api_key_env":"ROBOMASTER_API_KEY",
    "token_parameter":"max_completion_tokens",
}
_PUBLIC_FIELDS = set(DEFAULTS)
_UPDATE_FIELDS = _PUBLIC_FIELDS | {"api_key","clear_api_key","has_api_key","key_source"}
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,95}$")


class ApiConfigError(ValueError):
    """Invalid, unavailable, or unreadable local API configuration."""


def normalize_base_url(value):
    if not isinstance(value,str):
        raise ApiConfigError("API 地址必须是文本。")
    value=value.strip()
    if not value or any(ord(ch)<33 for ch in value) or "\\" in value or "?" in value or "#" in value:
        raise ApiConfigError("API 地址不能包含空白、查询参数、片段或反斜杠。")
    try:
        parsed=urlsplit(value)
        host=(parsed.hostname or "").lower()
        port=parsed.port
    except ValueError as exc:
        raise ApiConfigError("API 地址格式或端口无效。") from exc
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ApiConfigError("API 地址不能包含用户名或密码。")
    if not host or "%" in host or parsed.scheme not in {"https","http"}:
        raise ApiConfigError("请使用完整的 HTTPS API 基础地址。")
    try: local=ipaddress.ip_address(host).is_loopback
    except ValueError: local=host=="localhost"
    if parsed.scheme=="http" and not local:
        raise ApiConfigError("远程 API 必须使用 HTTPS；HTTP 仅允许明确的本机回环地址。")
    if port is not None and not 1<=port<=65535:
        raise ApiConfigError("API 端口范围应为 1–65535。")
    decoded=unquote(parsed.path)
    if "\\" in decoded or any(part in {".",".."} for part in decoded.split("/")):
        raise ApiConfigError("API 基础地址不能包含路径跳转。")
    path=parsed.path.rstrip("/")
    if path.endswith("/responses") or path.endswith("/chat/completions"):
        raise ApiConfigError("请填写 API 基础目录，例如 /v1，不要填写具体响应接口。")
    authority=("["+host+"]") if ":" in host else host
    if port is not None and port!=(443 if parsed.scheme=="https" else 80):
        authority+=":"+str(port)
    return urlunsplit((parsed.scheme,authority,path,"",""))


def endpoint_origin(base_url):
    parsed=urlsplit(normalize_base_url(base_url))
    host=parsed.hostname.lower()
    authority="["+host+"]" if ":" in host else host
    return parsed.scheme+"://"+authority+":"+str(
        parsed.port or (443 if parsed.scheme=="https" else 80))


def is_official_host(base_url):
    parsed=urlsplit(normalize_base_url(base_url))
    return parsed.scheme=="https" and parsed.hostname=="api.openai.com" and parsed.port in {None,443}


def validate_config(value):
    result=dict(DEFAULTS)
    if value:
        for key in _PUBLIC_FIELDS:
            if key in value: result[key]=value[key]
    if result["protocol"] not in {"responses","chat_completions"}:
        raise ApiConfigError("API 协议只能是 responses 或 chat_completions。")
    if result["structured_output"] not in {"json_schema","json_object"}:
        raise ApiConfigError("结构化输出只能是 json_schema 或 json_object。")
    if result["token_parameter"] not in {"max_completion_tokens","max_tokens"}:
        raise ApiConfigError("Chat Completions token 参数无效。")
    result["base_url"]=normalize_base_url(result["base_url"])
    if not isinstance(result["model"],str) or len(result["model"])>200 or any(
        ord(ch)<32 for ch in result["model"]):
        raise ApiConfigError("模型名称必须是正常的短文本。")
    result["model"]=result["model"].strip()
    seconds=result["timeout_seconds"]
    if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 1<=seconds<=600:
        raise ApiConfigError("API 超时应为 1–600 秒。")
    tokens=result["max_output_tokens"]
    if type(tokens) is not int or not 32<=tokens<=128000:
        raise ApiConfigError("最大输出 token 应为 32–128000 的整数。")
    env=result["api_key_env"]
    if not isinstance(env,str) or (env and not _ENV_NAME.fullmatch(env)):
        raise ApiConfigError("密钥环境变量应使用大写字母、数字和下划线。")
    if env=="OPENAI_API_KEY" and not is_official_host(result["base_url"]):
        raise ApiConfigError("第三方服务请使用专用环境变量，不能复用 OPENAI_API_KEY。")
    return result


def _atomic_bytes(path,content):
    path=Path(path)
    if path.is_symlink():
        raise ApiConfigError("API 设置文件不能是符号链接。")
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix=".api-",dir=path.parent)
    try:
        with os.fdopen(descriptor,"wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        with suppress(FileNotFoundError): Path(name).unlink()


class DpapiCipher:
    """Protect bytes using the current Windows user's DPAPI key, without UI."""
    class Blob(ctypes.Structure):
        _fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_ubyte))]

    @staticmethod
    def _blob(data):
        buffer=ctypes.create_string_buffer(data,max(1,len(data)))
        return DpapiCipher.Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte))),buffer

    def _convert(self,data,decrypt):
        if os.name!="nt":
            raise ApiConfigError("本机密钥保存需要 Windows DPAPI；其他平台可使用专用环境变量。")
        if not isinstance(data,bytes):
            raise TypeError("DPAPI 输入必须是 bytes。")
        crypt=ctypes.WinDLL("crypt32",use_last_error=True)
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        incoming,buffer=self._blob(data)
        entropy,entropy_buffer=self._blob(b"RoboMasterWorkbench.ApiKey.v1")
        outgoing=self.Blob()
        function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        function.restype=wintypes.BOOL
        function.argtypes=[ctypes.POINTER(self.Blob),
            ctypes.POINTER(wintypes.LPWSTR) if decrypt else wintypes.LPCWSTR,
            ctypes.POINTER(self.Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,
            ctypes.POINTER(self.Blob)]
        label=None if decrypt else "RoboMaster Workbench model API"
        if not function(ctypes.byref(incoming),label,ctypes.byref(entropy),None,None,1,ctypes.byref(outgoing)):
            raise ApiConfigError("Windows DPAPI "+("解密" if decrypt else "加密")+"失败；请重新输入本机 API 密钥。")
        try: return ctypes.string_at(outgoing.pbData,outgoing.cbData)
        finally:
            kernel.LocalFree.argtypes=[ctypes.c_void_p]
            kernel.LocalFree.restype=ctypes.c_void_p
            kernel.LocalFree(ctypes.cast(outgoing.pbData,ctypes.c_void_p))

    def encrypt(self,data): return self._convert(data,False)
    def decrypt(self,data): return self._convert(data,True)


class ApiSettingsStore:
    """Store public settings separately from one encrypted, origin-bound key.

    snapshot() returns an INTERNAL dict including api_key: do not log or expose
    it. Passing a payload previews unsaved settings and never writes files.
    """
    def __init__(self,root,cipher=None,environ=None):
        self.root=Path(root).resolve()
        self.data=self.root/"data"
        if not self.data.resolve().is_relative_to(self.root):
            raise ApiConfigError("API 设置目录不能指向项目之外。")
        self.data.mkdir(parents=True,exist_ok=True)
        self.settings_path=self.data/"api-settings.json"
        self.key_path=self.data/"api-key.bin"
        self.cipher=cipher or DpapiCipher()
        self.environ=os.environ if environ is None else environ
        self._lock=threading.RLock()

    def _read(self,repair=False):
        try:
            if self.settings_path.is_symlink():
                raise ApiConfigError("API 设置文件不能是符号链接。")
            if self.settings_path.stat().st_size>65536:
                raise ApiConfigError("API 配置文件过大，请重新保存设置。")
            content=json.loads(self.settings_path.read_text(encoding="utf-8-sig"))
            if not isinstance(content,dict):
                raise ApiConfigError("API 配置文件内容必须是对象。")
            validate_config(content)
            return content
        except FileNotFoundError:
            return {}
        except (OSError,UnicodeError,ValueError,TypeError) as exc:
            if repair: return {}
            if isinstance(exc,ApiConfigError): raise
            raise ApiConfigError("API 配置文件无法读取或格式损坏；请重新保存设置以修复。") from exc

    @staticmethod
    def _new_key(payload):
        key=payload.get("api_key")
        if key is None: return ""
        if not isinstance(key,str) or len(key)>8192 or any(ord(ch)<32 for ch in key):
            raise ApiConfigError("API 密钥必须是无换行的正常文本。")
        return key.strip()

    def _prepare(self,stored,payload):
        if payload is not None and not isinstance(payload,dict):
            raise ApiConfigError("API 设置请求必须是对象。")
        payload=payload or {}
        if set(payload)-_UPDATE_FIELDS:
            raise ApiConfigError("包含不支持的 API 设置字段。")
        if "clear_api_key" in payload and type(payload["clear_api_key"]) is not bool:
            raise ApiConfigError("clear_api_key 必须是布尔值。")
        key=self._new_key(payload)
        clear=payload.get("clear_api_key",False)
        if clear and key:
            raise ApiConfigError("不能同时清除和写入 API 密钥。")
        combined=dict(stored)
        combined.update({k:v for k,v in payload.items() if k in _PUBLIC_FIELDS})
        config=validate_config(combined)
        old=validate_config(stored)
        env_host=stored.get("_env_origin") or endpoint_origin(old["base_url"])
        # A newly selected dedicated variable is an explicit host-specific choice.
        if "api_key_env" in payload and payload["api_key_env"]!=old["api_key_env"]:
            env_host=endpoint_origin(config["base_url"])
        config["_env_origin"]=env_host
        return config,key,clear

    def _saved_key(self,origin):
        try:
            if not self.key_path.exists(): return "","none"
            if self.key_path.is_symlink() or self.key_path.stat().st_size>65536:
                raise ApiConfigError("已保存的密钥文件无效，请重新输入密钥。")
            raw=self.cipher.decrypt(self.key_path.read_bytes())
            value=json.loads(raw.decode("utf-8"))
            if not isinstance(value,dict) or not isinstance(value.get("api_key"),str):
                raise ApiConfigError("已保存的密钥无法识别，请重新输入密钥。")
            if value.get("origin")!=origin: return "","host_changed"
            return value["api_key"],"dpapi"
        except FileNotFoundError:
            return "","none"
        except ApiConfigError: raise
        except Exception as exc:
            raise ApiConfigError("无法解密已保存密钥，请在此 Windows 用户下重新保存。") from exc

    def _resolve(self,config,key="",clear=False):
        origin=endpoint_origin(config["base_url"])
        source="none"
        if key: return key,"input"
        if not clear:
            key,source=self._saved_key(origin)
            if key: return key,source
        env=config["api_key_env"]
        if env and config.get("_env_origin")==origin:
            value=str(self.environ.get(env) or "").strip()
            if value:
                if any(ord(ch)<32 for ch in value): raise ApiConfigError("专用环境变量中的密钥格式无效。")
                return value,"environment:"+env
        if is_official_host(config["base_url"]):
            value=str(self.environ.get("OPENAI_API_KEY") or "").strip()
            if value:
                if any(ord(ch)<32 for ch in value): raise ApiConfigError("OPENAI_API_KEY 的格式无效。")
                return value,"environment:OPENAI_API_KEY"
        return "",source

    def snapshot(self,payload=None):
        with self._lock:
            stored=self._read(repair=payload is not None)
            config,key,clear=self._prepare(stored,payload)
            key,source=self._resolve(config,key,clear)
            return {k:config[k] for k in _PUBLIC_FIELDS} | {
                "api_key":key,"key_source":source,"has_api_key":bool(key)}

    def public_config(self):
        with self._lock:
            config,key,clear=self._prepare(self._read(),None)
            try:
                key,source=self._resolve(config,key,clear)
                result={k:config[k] for k in _PUBLIC_FIELDS}
                result.update(has_api_key=bool(key),key_source=source)
                return result
            except ApiConfigError as exc:
                return {k:config[k] for k in _PUBLIC_FIELDS} | {
                    "has_api_key":False,"key_source":"unreadable","error":str(exc)}

    def update(self,payload):
        if not isinstance(payload,dict): raise ApiConfigError("API 设置请求必须是对象。")
        with self._lock:
            stored=self._read(repair=True)
            config,key,clear=self._prepare(stored,payload)
            encoded=None
            if key:
                secret=json.dumps({"origin":endpoint_origin(config["base_url"]),
                                   "api_key":key},ensure_ascii=False).encode("utf-8")
                try: encoded=self.cipher.encrypt(secret)
                except ApiConfigError: raise
                except Exception:
                    raise ApiConfigError("本机密钥加密失败，设置尚未保存。") from None
                if not isinstance(encoded,bytes):
                    raise ApiConfigError("本机密钥加密组件返回格式无效。")
            if self.key_path.is_symlink() or self.settings_path.is_symlink():
                raise ApiConfigError("API 设置或密钥文件不能是符号链接。")
            previous_key=self.key_path.read_bytes() if self.key_path.exists() else None
            previous_settings=self.settings_path.read_bytes() if self.settings_path.exists() else None
            try:
                if encoded is not None: _atomic_bytes(self.key_path,encoded)
                if clear and self.key_path.exists():
                    if self.key_path.is_symlink(): raise ApiConfigError("密钥文件不能是符号链接。")
                    self.key_path.unlink()
                plain=json.dumps(config,ensure_ascii=False,indent=2).encode("utf-8")
                _atomic_bytes(self.settings_path,plain)
            except Exception as exc:
                # Restore only the two files owned by this store.
                with suppress(Exception):
                    if previous_key is None:
                        if self.key_path.exists() and not self.key_path.is_symlink(): self.key_path.unlink()
                    else: _atomic_bytes(self.key_path,previous_key)
                    if previous_settings is None:
                        if self.settings_path.exists() and not self.settings_path.is_symlink(): self.settings_path.unlink()
                    else: _atomic_bytes(self.settings_path,previous_settings)
                if isinstance(exc,ApiConfigError): raise
                raise ApiConfigError("API 设置保存失败；原有设置已尽量保留。") from exc
            return self.public_config()
