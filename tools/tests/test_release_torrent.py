import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('release_torrent',
    Path(__file__).resolve().parents[1] / 'qualified-release/torrent.py')
T = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)


class Response(io.BytesIO):
    def __init__(self, body, status, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class PublicDownload:
    def __init__(self, body, wrong_range=False, corrupt=False):
        self.body, self.wrong_range, self.corrupt = body, wrong_range, corrupt
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        byte_range = request.get_header('Range')
        if byte_range:
            start, end = map(int, byte_range.removeprefix('bytes=').split('-'))
            body = self.body[start:end + 1]
            if self.corrupt:
                body = b'x' + body[1:]
            return Response(body, 200 if self.wrong_range else 206,
                            {'Content-Range': f'bytes {start}-{end}/{len(self.body)}'})
        return Response(self.body, 200)


class TorrentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.iso = Path(self.temp.name) / 'Arctic-Linux-1.2.1-x86_64.iso'
        self.payload = b'arctic-local-download\0' * 100_001
        self.iso.write_bytes(self.payload)
        self.torrent = self.iso.with_suffix('.iso.torrent')

    def test_creation_exact_piece_hashes_and_stable_http_seed(self):
        proof = T.create(self.iso, self.torrent, 'v1.2.1')
        info, digest, url = T.verify_local(self.iso, self.torrent, 'v1.2.1')
        self.assertEqual(digest, hashlib.sha256(self.payload).hexdigest())
        pieces = [self.payload[n:n + T.PIECE_BYTES] for n in range(0, len(self.payload), T.PIECE_BYTES)]
        self.assertEqual(info[b'pieces'], b''.join(hashlib.sha1(piece).digest() for piece in pieces))
        self.assertEqual(proof['info_hash'], hashlib.sha1(T.bencode(info)).hexdigest())
        self.assertFalse(proof['webseed_verified'])
        self.assertEqual(url, T.PREFIX + 'v1.2.1/' + self.iso.name)

    def test_actual_download_and_first_last_ranges_required_for_claim(self):
        T.create(self.iso, self.torrent, 'v1.2.1')
        server = PublicDownload(self.payload)
        proof = T.verify_public(self.iso, self.torrent, 'v1.2.1', server)
        self.assertTrue(proof['webseed_verified'])
        self.assertEqual(proof['download_bytes'], len(self.payload))
        self.assertEqual(proof['range_pieces_verified'], [0, 2])
        self.assertEqual(len(server.requests), 3)

    def test_download_corruption_or_false_range_cannot_pass(self):
        T.create(self.iso, self.torrent, 'v1.2.1')
        for server in (PublicDownload(self.payload[:-1]), PublicDownload(self.payload, wrong_range=True),
                       PublicDownload(self.payload, corrupt=True)):
            with self.subTest(server=server), self.assertRaises(ValueError):
                T.verify_public(self.iso, self.torrent, 'v1.2.1', server)

    def test_torrent_tampering_is_rejected(self):
        T.create(self.iso, self.torrent, 'v1.2.1')
        original = self.torrent.read_bytes()
        for field in ('pieces', 'name', 'length', 'piece length'):
            metadata = T.bdecode(original)
            metadata[b'info'][field.encode()] = 1 if field in ('length', 'piece length') else b'wrong'
            self.torrent.write_bytes(T.bencode(metadata))
            with self.subTest(field=field), self.assertRaises(ValueError):
                T.verify_local(self.iso, self.torrent, 'v1.2.1')

    def test_cannot_overwrite_existing_torrent_or_read_symlink(self):
        T.create(self.iso, self.torrent, 'v1.2.1')
        with self.assertRaises(FileExistsError):
            T.create(self.iso, self.torrent, 'v1.2.1')
        link = self.iso.parent / 'link.iso'
        link.symlink_to(self.iso)
        with self.assertRaises(ValueError):
            T.create(link, link.with_suffix('.torrent'), 'v1.2.1')

    def test_wrong_identity_size_or_zero_bytes_cannot_create(self):
        with self.assertRaises(ValueError):
            T.create(self.iso, self.torrent, 'v1.2.2')
        self.iso.write_bytes(b'')
        with self.assertRaises(ValueError):
            T.create(self.iso, self.torrent, 'v1.2.1')
        with self.iso.open('wb') as stream:
            stream.truncate(T.MAX_ISO_BYTES)
        with self.assertRaises(ValueError):
            T.create(self.iso, self.torrent, 'v1.2.1')

    def test_noncanonical_metadata_and_trailing_bytes_are_rejected(self):
        for raw in (b'd1:ai1e1:ai2ee', b'd1:zi1e1:ai2ee', b'i01e', b'i-0e',
                    b'03:abc', b'3:ab', b'leextra', b'l' * 10 + b'e' * 10):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                T.bdecode(raw)

    def test_https_downgrade_redirect_is_rejected(self):
        with self.assertRaises(ValueError):
            T.HTTPSRedirects().redirect_request(None, None, 302, '', {}, 'http://example.invalid/iso')


if __name__ == '__main__':
    unittest.main()
