"""Collect dependency license texts already present in the local build inputs."""
from pathlib import Path
import json
import tomllib
import sys

root = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'release/RoboMaster-Studio-v0.1.0-win-x64/DEPENDENCY_LICENSES.txt'
blocks = []
lock = json.loads((root / 'package-lock.json').read_text(encoding='utf-8'))
for location, meta in lock.get('packages', {}).items():
    if not location or meta.get('dev'):
        continue
    folder = root / location
    for file in sorted(folder.glob('*')):
        if file.is_file() and file.name.lower().startswith(('license', 'copying')):
            blocks.append(f"{location} {meta.get('version', '')}\n{file.read_text(encoding='utf-8',errors='replace')}")
registry = root / '.local/cargo/registry/src/index.crates.io-1949cf8c6b5b557f'
for package in tomllib.loads((root / 'src-tauri/Cargo.lock').read_text(encoding='utf-8'))['package']:
    folder = registry / f"{package['name']}-{package['version']}"
    for file in sorted(folder.glob('*')):
        if file.is_file() and file.name.lower().startswith(('license', 'copying')):
            blocks.append(f"{package['name']} {package['version']}\n{file.read_text(encoding='utf-8',errors='replace')}")
hermes = root / 'docs/research/LICENSE'
blocks.append('NousResearch/hermes-agent research reference\n' + hermes.read_text(encoding='utf-8'))
output.write_text('\n\n' + ('\n\n' + '='*72 + '\n\n').join(blocks), encoding='utf-8')
print(f'Collected {len(blocks)} dependency license texts.')
