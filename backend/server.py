"""Local service bootstrap. UI, model transport and CAD workflows are separate modules."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from domain import *
from application import Workbench
from http_api import Handler
from runtime import reusable_connection, write_manifest, mark_stopped, PRODUCT_VERSION

def acquire_service_lock(data_dir):
    """One writer and one MCP execution session per project root, across all launchers."""
    import msvcrt
    directory=Path(data_dir)
    directory.mkdir(parents=True,exist_ok=True)
    handle=(directory/'service.lock').open('a+b')
    if handle.seek(0,2)==0:
        handle.write(b'0');handle.flush()
    handle.seek(0)
    try: msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        handle.close()
        return None
    return handle


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=0); args=parser.parse_args()
    singleton=acquire_service_lock(ROOT/'data')
    if singleton is None:
        print('The local workbench service is already running.',flush=True)
        return
    token=secrets.token_hex(32)
    preferred_port=args.port
    runtime_path=ROOT/'data'/'runtime.json'
    # Keep existing native clients connected when this local service is updated.
    if args.port==0:
        previous=reusable_connection(runtime_path)
        if previous is not None:
            preferred_port=urlsplit(previous['url']).port
            token=previous['token']
    app=Workbench()
    try: server=ThreadingHTTPServer(('127.0.0.1',preferred_port),Handler)
    except OSError:
        if preferred_port==args.port: raise
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    server.app=app; server.token=token
    runtime={'url':'http://127.0.0.1:'+str(server.server_port),'token':token,'pid':os.getpid(),'version':PRODUCT_VERSION,'model_backend':'direct_api','status':'running'}
    runtime_path=app.data/'runtime.json'
    write_manifest(runtime_path,runtime)
    threading.Thread(target=app.initialize,daemon=True).start()
    try: server.serve_forever(poll_interval=.3)
    finally:
        app.cancel.set(); app.cancel_learning(); app.bridge.close(); server.server_close()
        try:
            mark_stopped(runtime_path,os.getpid())
        except (OSError,ValueError): pass
        singleton.close()

if __name__=='__main__': main()
