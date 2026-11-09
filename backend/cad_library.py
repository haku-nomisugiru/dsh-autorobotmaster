"""Local catalog client; downloaded assets are evidence, never CAD commands."""
import hashlib
import json
from pathlib import Path
import re
import uuid
import subprocess
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

class CadLibrary:
    _startup_lock = threading.Lock()
    def __init__(self, root, base_url="http://127.0.0.1:8765"):
        self.root=Path(root)
        parsed=urlsplit(base_url)
        if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost"} or parsed.username or parsed.password or parsed.path not in {"","/"} or parsed.query or parsed.fragment:
            raise ValueError("模型库地址必须是本机HTTP服务地址")
        self.base_url=base_url.rstrip("/")
        self.http=build_opener(ProxyHandler({}),NoRedirect())

    def _start_local_service(self):
        # Only auto-start the known sibling deployment on its default loopback port.
        if self.base_url != "http://127.0.0.1:8765": return False
        directory = self.root.resolve().parent / "RoboMasterCADLibrary"
        script = directory / "scripts" / "start-service.ps1"
        if not script.is_file() or not (directory / "tools" / "http_service.py").is_file(): return False
        with self._startup_lock:
            try:
                with self.http.open(self.base_url + "/health", timeout=2): return True
            except URLError: pass
            try:
                subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                    cwd=directory, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
                for _ in range(10):
                    try:
                        with self.http.open(self.base_url + "/health", timeout=1): return True
                    except URLError: time.sleep(.2)
            except (OSError, subprocess.TimeoutExpired): return False
        return False

    def get(self,path):
        for attempt in range(2):
            try:
                with self.http.open(self.base_url+path,timeout=8) as response:
                    raw=response.read(4*1024*1024+1)
                    if len(raw)>4*1024*1024: raise ValueError("模型库响应过大")
                    return json.loads(raw)
            except HTTPError as error:
                raise ValueError("模型库请求失败，HTTP "+str(error.code)) from error
            except URLError as error:
                if attempt == 0 and isinstance(error.reason, ConnectionRefusedError) and self._start_local_service(): continue
                raise ValueError("无法连接模型库服务："+self.base_url+"。请检查模型库服务是否已启动。") from error

    def search(self,query,section=None,limit=5):
        if not isinstance(query,str) or not query.strip() or len(query)>256: raise ValueError("检索词应为1–256字符")
        if section not in {None,"gimbal","chassis","wheel_or_leg"}: raise ValueError("模型库分类无效")
        params={"q":query,"limit":limit}
        if section: params["section"]=section
        return self.get("/v1/search?"+urlencode(params))

    def detail(self,model_id):
        if not isinstance(model_id,str) or not re.fullmatch(r"[a-zA-Z0-9_-]+",model_id): raise ValueError("模型ID无效")
        return self.get("/v1/models/"+model_id)

    @staticmethod
    def evidence(model):
        return {k:model.get(k) for k in ["id","name","section","source","source_url","entry","selection_scope","definition_id","features","verification","dependency_scope","limitations","engineering_parameters","usage"]}

    def context(self,query):
        try:
            result=self.search(query[:256],limit=5)
            return {"status":"ok","retrieval":"lexical","candidates":[self.evidence(m) for m in result["items"]]}
        except Exception as error:
            return {"status":"unavailable","message":"模型库检索失败，不能推断没有可复用模型。"+type(error).__name__,"candidates":[]}

    def download(self,model_id,kind="package"):
        if kind not in {"file","package"}: raise ValueError("下载类型无效")
        model=self.detail(model_id)
        record=model["entry"]
        expected=record["sha256"] if kind=="file" else model["downloads"].get("package_sha256")
        name=Path(record["path"]).name if kind=="file" else model["downloads"].get("package_name")
        if not expected or not re.fullmatch("[a-fA-F0-9]{64}",expected): raise ValueError("来源包缺少校验信息")
        # Never use server-provided directories or arbitrary download URLs.
        suffix=Path(name or "").suffix.lower()
        if suffix not in {".zip",".step",".stp",".sldasm",".sldprt"}: raise ValueError("不支持该模型格式")
        directory=self.root/"data"/"library-downloads"/model_id
        directory.mkdir(parents=True,exist_ok=True)
        destination=directory/(kind+"-"+uuid.uuid4().hex+suffix)
        temporary=destination.with_suffix(destination.suffix+".part")
        digest=hashlib.sha256();size=0
        try:
            with self.http.open(self.base_url+"/v1/models/"+model_id+"/"+kind,timeout=120) as response, temporary.open("xb") as output:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk)
                    if size>8*1024**3: raise ValueError("模型包超过8GiB下载上限")
                    digest.update(chunk);output.write(chunk)
            if digest.hexdigest().lower()!=expected.lower(): raise ValueError("模型下载SHA-256不符，未保留文件")
            temporary.rename(destination)
        finally:
            temporary.unlink(missing_ok=True)
        result={"model":self.evidence(model),"kind":kind,"path":str(destination.resolve()),"sha256":expected,"bytes":size,"download_verified":True,"assembly_verified":False}
        destination.with_suffix(destination.suffix+".json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        return result
