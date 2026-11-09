"""Private loopback connection manifest shared by all native launchers."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

PRODUCT_VERSION='1.0.0'

def reusable_connection(path):
    try:
        path=Path(path)
        if path.stat().st_size>65536:return None
        previous=json.loads(path.read_text(encoding='utf-8-sig'))
        address=urlsplit(previous.get('url',''))
        token=previous.get('token','')
        if (address.scheme!='http' or address.hostname!='127.0.0.1' or not address.port or
            address.username is not None or address.password is not None or
            address.path not in ('','/') or address.query or address.fragment or
            not isinstance(token,str) or re.fullmatch(r'[a-f0-9]{64}',token) is None): return None
        return {'url':'http://127.0.0.1:'+str(address.port),'token':token,'pid':previous.get('pid',0)}
    except (OSError,ValueError,TypeError,AttributeError): return None

def write_manifest(path,connection):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(connection),encoding='utf-8')
    os.replace(temporary,path)

def mark_stopped(path,pid):
    # Keep the validated address/token so already-open UI clients can reconnect.
    # The singleton remains locked until after this update.
    previous=reusable_connection(path)
    if previous is not None and previous.get('pid')==pid:
        previous.update(pid=0,version=PRODUCT_VERSION,model_backend='direct_api',status='stopped')
        write_manifest(path,previous)
