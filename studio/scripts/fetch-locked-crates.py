"""Populate the project-local Cargo cache from official crates.io with SHA-256 checks.

Useful on Windows hosts where Cargo's HTTP backend is slow; never changes Cargo.lock.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / '.local/cargo/registry'
INDEX = REGISTRY / 'index/index.crates.io-1949cf8c6b5b557f'
CACHE = REGISTRY / 'cache/index.crates.io-1949cf8c6b5b557f'
PACKAGES = [p for p in tomllib.loads((ROOT / 'src-tauri/Cargo.lock').read_text())['package'] if p.get('source', '').startswith('registry+')]

def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'RoboMaster-Studio-build/0.1'}), timeout=40) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)

def index_path(name):
    if len(name) == 1: return '1/' + name
    if len(name) == 2: return '2/' + name
    if len(name) == 3: return '3/' + name[0] + '/' + name
    return name[:2] + '/' + name[2:4] + '/' + name

def fetch_index(name):
    path = index_path(name)
    raw = get('https://index.crates.io/' + path)
    rows = [json.loads(row) for row in raw.splitlines()]
    blob = b'\x03\x02\x00\x00\x00etag: "local-verified"\x00'
    blob += b''.join(row['vers'].encode() + b'\x00' + json.dumps(row, separators=(',', ':')).encode() + b'\x00' for row in rows)
    target = INDEX / '.cache' / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)

def fetch_crate(p):
    target = CACHE / f"{p['name']}-{p['version']}.crate"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == p['checksum']:
        return
    content = get(f"https://static.crates.io/crates/{p['name']}/{p['name']}-{p['version']}.crate")
    if hashlib.sha256(content).hexdigest() != p['checksum']:
        raise ValueError(f"Checksum mismatch: {target.name}")
    target.write_bytes(content)

if __name__ == '__main__':
    INDEX.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    (INDEX / 'config.json').write_text(json.dumps({'dl': 'https://static.crates.io/crates', 'api': 'https://crates.io'}))
    jobs = [(fetch_index, name) for name in sorted({p['name'] for p in PACKAGES})] + [(fetch_crate, p) for p in PACKAGES]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(fn, arg) for fn, arg in jobs]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if i % 50 == 0 or i == len(futures):
                print(f'Verified cache {i}/{len(futures)}', flush=True)
