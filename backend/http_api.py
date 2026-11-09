"""Authenticated loopback HTTP boundary for the native SolidWorks task pane."""
from __future__ import annotations
import hmac
import json
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
from provider import _safe_detail


class Handler(BaseHTTPRequestHandler):
    server_version='RoboMasterWorkbench/1.0.0'
    timeout=15
    def log_message(self,*args): pass

    def reply(self,status,body):
        raw=json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        try: self.wfile.write(raw)
        except (ConnectionError,OSError): pass

    def authorized(self):
        expected={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
        if self.headers.get('Host','') not in expected or self.headers.get('Origin'): return False
        return hmac.compare_digest(self.headers.get('X-Workbench-Token',''),self.server.token)

    def safe_error(self,exc):
        text=self.server.app.models.safe_detail(exc,1200)
        for key in getattr(self,'request_secrets',[]):
            if key: text=text.replace(key,'[已隐藏密钥]')
        return _safe_detail(text,1200)

    def do_GET(self):
        if not self.authorized(): return self.reply(403,{'error':'请求未授权'})
        try:
            route=urlsplit(self.path);query=parse_qs(route.query);app=self.server.app
            if route.path=='/api/library/inspection': return self.reply(200,app.library_inspection_view())
            if route.path=='/api/library/search': return self.reply(200,app.cad_library.search(query.get('q',[''])[0],query.get('section',[None])[0]))
            if route.path=='/api/library/model': return self.reply(200,app.cad_library.detail(query.get('id',[''])[0]))
            if route.path=='/api/state': return self.reply(200,app.snapshot())
            if route.path=='/api/settings': return self.reply(200,app.api_settings())
            if route.path=='/api/knowledge': return self.reply(200,app.knowledge_view())
            if route.path=='/api/knowledge/skill': return self.reply(200,app.knowledge_skill(query.get('id',[''])[0]))
            if route.path=='/api/knowledge/session': return self.reply(200,app.require_knowledge().session(query.get('id',[''])[0]))
            return self.reply(404,{'error':'接口不存在'})
        except (ValueError,KeyError,TypeError) as exc: return self.reply(400,{'error':self.safe_error(exc)})
        except Exception as exc: return self.reply(500,{'error':self.safe_error(exc)})

    def connection_test(self,body):
        cancelled=threading.Event();done=threading.Event()
        def watch_disconnect():
            while not done.wait(.15):
                try:
                    readable,_,_=select.select([self.connection],[],[],0)
                    if readable and self.connection.recv(1,socket.MSG_PEEK)==b'':
                        cancelled.set();return
                except (OSError,ValueError): cancelled.set();return
        watcher=threading.Thread(target=watch_disconnect,daemon=True,name='api-test-client')
        watcher.start()
        try: return self.server.app.test_api_settings(body,cancelled)
        finally: done.set()

    def do_POST(self):
        if not self.authorized(): return self.reply(403,{'error':'请求未授权'})
        self.request_secrets=[]
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>65536: raise ValueError('请求内容过长')
            raw=self.rfile.read(size)
            if len(raw)!=size: raise ValueError('请求内容不完整')
            body=json.loads(raw.decode('utf-8')) if size else {}
            if not isinstance(body,dict): raise ValueError('请求内容必须是 JSON 对象')
            if isinstance(body.get('api_key'),str): self.request_secrets.append(body['api_key'])
            app=self.server.app;route=urlsplit(self.path).path
            if route=='/api/library/assess': return self.reply(200,app.start_library_assessment(body.get('target_requirements','')))
            if route=='/api/library/open': return self.reply(200,app.start_library_inspection(body.get('id','')))
            if route=='/api/library/download': return self.reply(200,app.library_download(body.get('id',''),body.get('kind','package')))
            if route=='/api/settings': return self.reply(200,app.update_api_settings(body))
            if route=='/api/settings/test': return self.reply(200,self.connection_test(body))
            if route=='/api/chat': app.start_chat(body.get('message',''))
            elif route=='/api/run': app.start_run()
            elif route=='/api/control': app.control(body.get('action',''))
            elif route=='/api/new': app.new()
            elif route=='/api/knowledge/note': return self.reply(200,app.knowledge_note(body.get('text',''),body.get('scope','project')))
            elif route=='/api/knowledge/forget': return self.reply(200,app.knowledge_forget(body.get('id','')))
            elif route=='/api/knowledge/summarize': app.start_learning()
            elif route=='/api/knowledge/skill': app.start_learning(generate_skill=True)
            elif route=='/api/knowledge/toggle': return self.reply(200,app.knowledge_toggle(body.get('id',''),body.get('enabled')))
            elif route=='/api/context':
                with app.lock:
                    title=str(body.get('title') or '等待 SolidWorks 文档')[:200]
                    if app.state['active_document']!=title:
                        app.state['active_document']=title;app.save()
            else: return self.reply(404,{'error':'接口不存在'})
            self.reply(200,app.snapshot())
        except (ValueError,KeyError,TypeError) as exc: self.reply(400,{'error':self.safe_error(exc)})
        except Exception as exc: self.reply(500,{'error':self.safe_error(exc)})
