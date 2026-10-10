#!/usr/bin/env python3
"""Create a single-file torrent and verify its immutable public HTTP seed."""
import argparse
import hashlib
import re
import time
from pathlib import Path
import urllib.request

PREFIX = 'https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/'
PIECE_BYTES = 1024 * 1024
MAX_ISO_BYTES = 2_000_000_000


def bencode(value):
    if isinstance(value, bytes):
        return str(len(value)).encode() + b':' + value
    if isinstance(value, str):
        return bencode(value.encode())
    if type(value) is int:
        return b'i' + str(value).encode() + b'e'
    if isinstance(value, list):
        return b'l' + b''.join(map(bencode, value)) + b'e'
    if isinstance(value, dict):
        entries = sorted((key.encode() if isinstance(key, str) else key, item)
                         for key, item in value.items())
        return b'd' + b''.join(bencode(key) + bencode(item) for key, item in entries) + b'e'
    raise ValueError('Unsupported torrent value')


def bdecode(raw):
    if len(raw) > 100_000:
        raise ValueError('Oversized torrent metadata')

    def read(offset, depth=0):
        if depth > 8 or offset >= len(raw):
            raise ValueError('Invalid torrent nesting')
        kind = raw[offset:offset + 1]
        if kind == b'i':
            end = raw.index(b'e', offset + 1)
            number = raw[offset + 1:end]
            if not re.fullmatch(rb'0|-?[1-9][0-9]*', number):
                raise ValueError('Noncanonical torrent integer')
            return int(number), end + 1
        if kind in (b'l', b'd'):
            items, offset = [], offset + 1
            while offset < len(raw) and raw[offset:offset + 1] != b'e':
                value, offset = read(offset, depth + 1)
                items.append(value)
            if offset >= len(raw):
                raise ValueError('Truncated torrent collection')
            if kind == b'l':
                return items, offset + 1
            keys = items[::2]
            if len(items) % 2 or any(not isinstance(key, bytes) for key in keys):
                raise ValueError('Invalid torrent dictionary')
            if keys != sorted(set(keys)):
                raise ValueError('Noncanonical torrent keys')
            return dict(zip(keys, items[1::2])), offset + 1
        end = raw.index(b':', offset)
        digits = raw[offset:end]
        if not re.fullmatch(rb'0|[1-9][0-9]*', digits):
            raise ValueError('Invalid torrent byte length')
        length = int(digits)
        start = end + 1
        if start + length > len(raw):
            raise ValueError('Truncated torrent bytes')
        return raw[start:start + length], start + length

    value, end = read(0)
    if end != len(raw):
        raise ValueError('Trailing torrent data')
    return value


def identity(iso, tag):
    if iso.is_symlink() or not iso.is_file() or not 0 < iso.stat().st_size < MAX_ISO_BYTES:
        raise ValueError('ISO must be a regular file below 2,000,000,000 bytes')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise ValueError('Invalid stable release tag')
    name = 'Arctic-Linux-' + tag[1:] + '-x86_64.iso'
    if iso.name != name:
        raise ValueError('ISO filename differs from release tag')
    return PREFIX + tag + '/' + name


def file_info(iso):
    pieces, digest = [], hashlib.sha256()
    with iso.open('rb') as stream:
        for piece in iter(lambda: stream.read(PIECE_BYTES), b''):
            digest.update(piece)
            pieces.append(hashlib.sha1(piece).digest())
    return {b'length': iso.stat().st_size, b'name': iso.name.encode(),
            b'piece length': PIECE_BYTES, b'pieces': b''.join(pieces)}, digest.hexdigest()


def create(iso, target, tag):
    url = identity(iso, tag)
    info, digest = file_info(iso)
    payload = bencode({b'created by': b'Arctic Linux', b'info': info,
                       b'url-list': [url.encode()]})
    with target.open('xb') as output:
        output.write(payload)
    return {'iso_sha256': digest, 'info_hash': hashlib.sha1(bencode(info)).hexdigest(),
            'torrent_sha256': hashlib.sha256(payload).hexdigest(),
            'webseed_url': url, 'webseed_verified': False}


def verify_local(iso, torrent, tag):
    url = identity(iso, tag)
    if torrent.is_symlink() or not torrent.is_file():
        raise ValueError('Torrent must be a regular file')
    metadata = bdecode(torrent.read_bytes())
    info, digest = file_info(iso)
    if metadata != {b'created by': b'Arctic Linux', b'info': info, b'url-list': [url.encode()]}:
        raise ValueError('Torrent does not describe the exact ISO and release URL')
    return info, digest, url


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Release download redirects must remain HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_public(iso, torrent, tag, opener=None, max_seconds=1200):
    """Hash the full public download and test first/last torrent piece ranges."""
    info, expected, url = verify_local(iso, torrent, tag)
    opener = opener or urllib.request.build_opener(HTTPSRedirects())
    deadline = time.monotonic() + max_seconds
    digest, count = hashlib.sha256(), 0
    with opener.open(urllib.request.Request(url, headers={'Accept-Encoding': 'identity'}), timeout=60) as response:
        if response.status != 200:
            raise ValueError('Public ISO download did not return HTTP 200')
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError('Public release verification exceeded its time bound')
            data = response.read(PIECE_BYTES)
            if not data:
                break
            count += len(data)
            if count > info[b'length']:
                raise ValueError('Public ISO exceeds the qualified size')
            digest.update(data)
    if count != info[b'length'] or digest.hexdigest() != expected:
        raise ValueError('Public ISO download differs from the qualified image')
    indices = sorted({0, (count - 1) // PIECE_BYTES})
    for index in indices:
        if time.monotonic() >= deadline:
            raise TimeoutError('Public release verification exceeded its time bound')
        start, end = index * PIECE_BYTES, min(count, (index + 1) * PIECE_BYTES) - 1
        request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}',
                                                     'Accept-Encoding': 'identity'})
        with opener.open(request, timeout=60) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{count}':
                raise ValueError('Public HTTP seed does not serve the requested torrent range')
            data = response.read(end - start + 2)
        expected_piece = info[b'pieces'][index * 20:(index + 1) * 20]
        if len(data) != end - start + 1 or hashlib.sha1(data).digest() != expected_piece:
            raise ValueError('Public HTTP seed returned incorrect torrent piece bytes')
    return {'download_bytes': count, 'download_sha256': expected, 'webseed_url': url,
            'webseed_verified': True, 'range_pieces_verified': indices,
            'verification_scope': 'full HTTP download and first/last torrent piece ranges; no peer seed claim'}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create', 'verify-public'])
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--torrent', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    result = (create(args.iso, args.torrent, args.tag) if args.command == 'create'
              else verify_public(args.iso, args.torrent, args.tag))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
