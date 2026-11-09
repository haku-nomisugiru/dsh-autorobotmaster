"""API configuration lifecycle. No CAD state or conversation is stored here."""
from __future__ import annotations
from pathlib import Path
import threading
from api_config import ApiSettingsStore
from provider import ApiProvider, _safe_detail


class ModelService:
    def __init__(self,root,provider=None,store=None):
        self.root=Path(root)
        self.store=store or ApiSettingsStore(self.root)
        self.lock=threading.RLock()
        self.test_lock=threading.Lock()
        self.injected=provider is not None
        self.config_error=''
        if provider is not None: self.provider=provider
        else: self.reload()

    def reload(self):
        with self.lock:
            try:
                config=self.store.snapshot()
                self.config_error=''
            except Exception as exc:
                config={}
                self.config_error=_safe_detail(str(exc),700)
            self.provider=ApiProvider(project_root=self.root,config=config)

    def public_config(self):
        try: return self.store.public_config()
        except Exception as exc:
            return {'protocol':'responses','base_url':'https://api.openai.com/v1','model':'',
                    'structured_output':'json_schema','timeout_seconds':180,'max_output_tokens':6000,
                    'api_key_env':'ROBOMASTER_API_KEY','token_parameter':'max_completion_tokens',
                    'has_api_key':False,'key_source':'none','error':_safe_detail(str(exc),700)}

    def validate(self,payload):
        if not isinstance(payload,dict): raise ValueError('API 设置必须是 JSON 对象')
        self.store.snapshot(payload)

    def update(self,payload):
        with self.lock:
            public=self.store.update(payload)
            self.injected=False
            self.reload()
            return public

    def status(self):
        if self.config_error: return {'available':False,'message':'API 配置未就绪：'+self.config_error}
        try:
            status=self.provider.status()
            return {'message':status} if isinstance(status,str) else status
        except Exception as exc: return {'available':False,'message':'模型 API 未就绪：'+self.safe_detail(exc,700)}

    def ensure_ready(self):
        if self.config_error: raise ValueError('请打开 API 设置修复配置：'+self.config_error)
        availability=getattr(self.provider,'availability',None)
        if callable(availability):
            status=availability()
            if not status.get('available'):
                raise ValueError(status.get('message') or status.get('reason') or '请先配置模型 API')

    def safe_detail(self,error,limit=1200):
        text=str(error)
        try:
            key=self.store.snapshot().get('api_key')
            if key: text=text.replace(key,'[已隐藏密钥]')
        except Exception: pass
        return _safe_detail(text,limit)

    def test(self,payload,cancel_event=None):
        if not self.test_lock.acquire(blocking=False): raise ValueError('连接测试正在进行，请稍候')
        try:
            config=self.store.snapshot(payload)
            # A settings check is a tiny bounded request, separate from design/review.
            config=dict(config,timeout_seconds=min(float(config.get('timeout_seconds',180)),30))
            provider=ApiProvider(project_root=self.root,config=config)
            return provider.test_connection(cancel_event=cancel_event)
        finally: self.test_lock.release()
