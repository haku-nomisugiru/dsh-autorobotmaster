"""Publish an audited local build via GitHub Actions; never rebuild the binaries."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def gh(*args):
    return subprocess.run(['gh', *args], check=True, capture_output=True).stdout


def api(endpoint):
    return json.loads(gh('api', endpoint))


def find_release(repo, tag):
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases'))
    return next((r for page in pages for r in page if r['tag_name'] == tag), None)


def verify_assets(release, assets):
    actual = {a['name']: a for a in release['assets']}
    if set(actual) != {a['name'] for a in assets}:
        raise ValueError('Release assets do not match the reviewed manifest')
    for item in assets:
        uploaded = actual[item['name']]
        if uploaded['size'] != item['size'] or uploaded.get('digest') != 'sha256:' + item['sha256']:
            raise ValueError('Uploaded asset mismatch: ' + item['name'])


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    commit = os.environ['GITHUB_SHA']
    if os.environ.get('GITHUB_ACTIONS') != 'true' or repo != 'haku-nomisugiru/autorobomaster':
        raise ValueError('Run only in the authorized repository GitHub Actions environment')
    if os.environ.get('GITHUB_REF') != 'refs/heads/main' or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Publication requires a specific main commit')
    manifest = json.loads(Path('release-manifest.json').read_text(encoding='utf-8'))
    tag = manifest['tag']
    if tag != 'studio-v0.2.0':
        raise ValueError('This publication workflow is scoped to Studio 0.2.0')
    assets = manifest['assets']
    names = {'RoboMaster-Studio-Codex-v0.2.0-win-x64.zip', 'RoboMaster-Studio-DSH-v0.2.0.zip'}
    if len(assets) != 2 or {a['name'] for a in assets} != names:
        raise ValueError('Unexpected installation package list')
    for item in assets:
        if not re.fullmatch('[0-9a-f]{40}', item['blob_sha']) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('Invalid artifact digest')
        if not isinstance(item['size'], int) or not 0 < item['size'] < 100_000_000:
            raise ValueError('Invalid artifact size')
    sums = ''.join(f"{a['sha256']}  {a['name']}\n" for a in assets).encode('ascii')
    checksums = {'name': 'SHA256SUMS.txt', 'size': len(sums), 'sha256': hashlib.sha256(sums).hexdigest()}
    expected = [*assets, checksums]
    existing = find_release(repo, tag)
    if existing and not existing['draft']:
        verify_assets(existing, expected)
        print('Already published with matching assets: ' + existing['html_url'])
        return
    if existing and existing['target_commitish'] != commit:
        previous = existing['target_commitish']
        if not re.fullmatch('[0-9a-f]{40}', previous):
            raise ValueError('Existing draft does not target an exact source commit')
        original = api(f'repos/{repo}/contents/studio/distribution/{tag}.json?ref={previous}')
        original_manifest = json.loads(base64.b64decode(original['content']))
        if original_manifest != manifest or (existing.get('body') or '').strip() != Path('release-notes.md').read_text(encoding='utf-8').strip():
            raise ValueError('Existing draft differs from this reviewed release')
    refs = api(f'repos/{repo}/git/matching-refs/tags/{tag}')
    for ref in refs:
        if ref['ref'] == f'refs/tags/{tag}' and ref['object']['sha'] != commit:
            raise ValueError('Existing tag targets a different commit; refusing to move it')

    for item in assets:
        blob = api(f"repos/{repo}/git/blobs/{item['blob_sha']}")
        if blob.get('encoding') != 'base64' or blob.get('sha') != item['blob_sha']:
            raise ValueError('Unexpected Git blob response')
        raw = base64.b64decode(blob['content'])
        if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Artifact integrity failed: ' + item['name'])
        Path(item['name']).write_bytes(raw)
        with zipfile.ZipFile(item['name']) as package:
            if package.testzip():
                raise ValueError('Corrupted ZIP')
            for name in package.namelist():
                parts = Path(name.replace('\\', '/')).parts
                if '..' in parts or any(p in {'data', '.local', 'node_modules', '.git'} for p in parts):
                    raise ValueError('Unexpected packaged data')
        print('Verified ' + item['name'] + ': ' + item['sha256'])
    Path('SHA256SUMS.txt').write_bytes(sums)
    if not existing:
        gh('release', 'create', tag, '--repo', repo, '--target', commit,
           '--title', manifest['title'], '--notes-file', 'release-notes.md', '--draft')
        # The tag endpoint excludes unpublished releases. Read drafts from the list.
        existing = find_release(repo, tag)
        if existing is None:
            raise ValueError('Created draft is not visible in the release list')
    uploaded = {a['name']: a for a in existing['assets']}
    if set(uploaded) - {a['name'] for a in expected}:
        raise ValueError('Draft contains unrecognized assets; refusing to replace them')
    for item in expected:
        if item['name'] in uploaded:
            current = uploaded[item['name']]
            if current['size'] != item['size'] or current.get('digest') != 'sha256:' + item['sha256']:
                raise ValueError('Existing draft asset differs; refusing to overwrite')
        else:
            gh('release', 'upload', tag, item['name'], '--repo', repo)
    verify_assets(api(f'repos/{repo}/releases/{existing["id"]}'), expected)
    # The draft is made public only after every attachment is verified.
    gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--latest',
       '--target', commit, '--title', manifest['title'], '--notes-file', 'release-notes.md')
    release = api(f'repos/{repo}/releases/{existing["id"]}')
    if release['draft']:
        raise ValueError('Release remained a draft')
    verify_assets(release, expected)
    print('Published: ' + release['html_url'])


if __name__ == '__main__':
    main()
