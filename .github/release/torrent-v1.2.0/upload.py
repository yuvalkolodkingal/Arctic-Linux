#!/usr/bin/env python3
"""Upload only new torrent assets with explicit raw-body length; never replace."""
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT
API = 'https://api.github.com/repos/yuvalkolodkingal/Arctic-Linux/releases/tags/v1.2.0'
HEADERS = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
           'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
with urlopen(Request(API, headers=HEADERS), timeout=30) as response:
    release = json.load(response)
original = json.loads((ROOT / 'release-original.json').read_text())
for key in ['id', 'tag_name', 'target_commitish', 'body', 'draft', 'prerelease']:
    assert release[key] == original[key], key
existing = {item['name']: item for item in release['assets']}
for item in original['assets']:
    assert all(existing[item['name']][key] == item[key] for key in ['id', 'name', 'size', 'digest'])
assets = [
    ('Arctic-Linux-1.2-x86_64.iso.parts.torrent', 'application/x-bittorrent', 'Torrent: both ISO parts; verified GitHub web seed; assemble after download'),
    ('Arctic-Linux-1.2-x86_64.iso.parts.torrent.sha256', 'text/plain', 'Torrent file SHA256'),
    ('Arctic-Linux-1.2-TORRENT.md', 'text/markdown', 'BitTorrent download and ISO assembly guide'),
    ('Arctic-Linux-1.2-TORRENT-verification.json', 'application/json', 'Torrent pieces and complete web-seed download verification'),
]
url = release['upload_url'].split('{')[0]
uploaded = []
for name, content_type, label in assets:
    data = (OUTPUT / name).read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    if name in existing:
        asset = existing[name]
        assert asset['size'] == len(data) and asset['digest'] == 'sha256:' + sha256
        print('Already present and byte digest matches: ' + name, flush=True)
    else:
        headers = HEADERS | {'Content-Type': content_type, 'Content-Length': str(len(data))}
        request = Request(url + '?' + urlencode({'name': name, 'label': label}),
                          data=data, headers=headers, method='POST')
        try:
            response = urlopen(request, timeout=60)
        except HTTPError as error:
            print(json.dumps({'failed_action': 'upload_release_asset', 'target': url,
                              'name': name, 'http_status': error.code,
                              'response': error.read(1200).decode(errors='replace')}), flush=True)
            raise SystemExit(1)
        assert response.status == 201
        asset = json.load(response)
        assert asset['state'] == 'uploaded' and asset['size'] == len(data)
        assert asset['digest'] == 'sha256:' + sha256
        print(json.dumps({key: asset[key] for key in ['id', 'name', 'state', 'size', 'digest', 'browser_download_url']}), flush=True)
    uploaded.append(asset)
(OUTPUT / 'uploaded-assets.json').write_text(json.dumps(uploaded, indent=2) + '\n')

# Verify anonymous public download bytes without an Authorization header.
for item in uploaded:
    with urlopen(Request(item['browser_download_url']), timeout=30) as response:
        public_bytes = response.read()
    assert public_bytes == (OUTPUT / item['name']).read_bytes(), item['name']
    print('Verified anonymous download: ' + item['name'], flush=True)
with urlopen(Request(API, headers=HEADERS), timeout=30) as response:
    final_release = json.load(response)
for key in ['id', 'tag_name', 'target_commitish', 'body', 'draft', 'prerelease']:
    assert final_release[key] == original[key], key
for original_asset in original['assets']:
    final_asset = next(item for item in final_release['assets'] if item['id'] == original_asset['id'])
    assert all(final_asset[key] == original_asset[key] for key in ['id','name','size','digest'])
print('Release identity, notes, and original assets preserved.', flush=True)
