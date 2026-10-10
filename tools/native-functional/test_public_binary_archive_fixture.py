"""Preserve only the exact public binary archive fixture, with strict controls."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('public_binary_screen', HERE/'screen-evidence.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


class PublicBinaryArchiveFixture(unittest.TestCase):
    def fixture(self, root, relative, content):
        source = root/'source'
        path = source/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return source, path

    def test_exact_original_native_writer_and_paths(self):
        expected_paths = set()
        for name in ('native_smoke.py', 'guest-check-native-v6.py'):
            tree = ast.parse((HERE/name).read_bytes())
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == 'write'
                     and len(node.args) >= 2 and isinstance(node.args[0], ast.Constant)
                     and node.args[0].value == 'archive source/nested directory/hello world.txt']
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].args[1].value, S.PUBLIC_NATIVE_BINARY_BYTES)
            archives = next(node for node in ast.walk(tree)
                            if isinstance(node, ast.FunctionDef) and node.name == 'archives')
            selected = next(node.value for node in archives.body if isinstance(node, ast.Assign)
                            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                            and node.targets[0].id == 'selected')
            self.assertIsInstance(selected, ast.BoolOp)
            self.assertIsInstance(selected.op, ast.Or)
            self.assertEqual(ast.literal_eval(selected.values[1]),
                ('zip','7z','tar','tar.gz','tar.bz2','tar.xz','tar.zst','cpio',
                 'gzip','bzip2','xz','zstd','7z-encrypted'))
            target = next(node.value for node in ast.walk(archives) if isinstance(node, ast.Assign)
                          and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                          and node.targets[0].id == 'target')
            self.assertEqual(ast.dump(target), ast.dump(ast.parse("self.root/('extracted '+kind)", mode='eval').body))
            # The four single-file decoders write extensionless payload, so the
            # original .txt exporter selects only these nine directory copies.
            output = next(node.value for node in ast.walk(archives) if isinstance(node, ast.Assign)
                          and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                          and node.targets[0].id == 'output')
            self.assertEqual(ast.dump(output), ast.dump(ast.parse("target/'payload'", mode='eval').body))
            for stage in ('live', 'installed'):
                expected_paths.add('native-'+stage+'/archive source/nested directory/hello world.txt')
                for kind in ('zip','7z','tar','tar.gz','tar.bz2','tar.xz','tar.zst','cpio','7z-encrypted'):
                    expected_paths.add('native-'+stage+'/extracted '+kind+'/nested directory/hello world.txt')
        self.assertEqual(len(S.PUBLIC_NATIVE_BINARY_BYTES), 28)
        self.assertEqual(S.PUBLIC_NATIVE_BINARY_BYTES.index(b'\xff'), 26)
        self.assertEqual(hashlib.sha256(S.PUBLIC_NATIVE_BINARY_BYTES).hexdigest(), S.PUBLIC_NATIVE_BINARY_SHA256)
        self.assertEqual(len(expected_paths), 20)
        self.assertEqual(S.PUBLIC_NATIVE_BINARY_PATHS, expected_paths)

    def test_whole_binary_bytes_and_format_metadata_both_modes(self):
        for path in sorted(S.PUBLIC_NATIVE_BINARY_PATHS):
            for external in (False, True):
                with self.subTest(path=path, external=external), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source, original = self.fixture(root, path, S.PUBLIC_NATIVE_BINARY_BYTES)
                    before = original.stat()
                    S.screen(source, root/'out', external=external)
                    self.assertEqual((root/'out'/path).read_bytes(), S.PUBLIC_NATIVE_BINARY_BYTES)
                    after = original.stat()
                    self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_mode),
                                     (after.st_ino, after.st_mtime_ns, after.st_mode))
                    receipt = json.loads((root/'out/upload-screening.json').read_bytes())
                    self.assertEqual(receipt['files'][path], dict(original_sha256=S.PUBLIC_NATIVE_BINARY_SHA256,
                        uploaded_sha256=S.PUBLIC_NATIVE_BINARY_SHA256, bytes=28, redactions=0))
                    self.assertEqual(receipt['source_formats'], {path:dict(schema='arctic-native-public-binary-fixture-v1',
                        source_format='binary-archive-roundtrip', bytes=28,
                        sha256=S.PUBLIC_NATIVE_BINARY_SHA256, release_acceptance=False)})

    def test_any_changed_truncated_added_private_or_wrong_type_fixture_rejected(self):
        raw = S.PUBLIC_NATIVE_BINARY_BYTES
        mutations = [raw[:-1], raw+b'\n', b'X'+raw[1:], raw.replace(b'\xff', b'\x00'),
                     b'authorization: Bearer PRIVATE\n', bytearray(raw), None]
        for path in sorted(S.PUBLIC_NATIVE_BINARY_PATHS):
            for content in mutations:
                with self.subTest(path=path, type=type(content).__name__):
                    with self.assertRaisesRegex(RuntimeError, '^Native public binary archive fixture bytes differ$'):
                        S.public_native_binary_format(path, content)
                if type(content) is bytes:
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source, _ = self.fixture(root, path, content)
                        with self.assertRaisesRegex(RuntimeError, '^Native public binary archive fixture bytes differ$'):
                            S.screen(source, root/'out')
                        self.assertFalse((root/'out').exists())

    def test_unrelated_paths_and_txt_keep_original_strict_utf8(self):
        aliases = ['other.txt', 'archive source/nested directory/hello world.txt',
                   'native-other/archive source/nested directory/hello world.txt',
                   'native-live/archive source/nested directory/other.txt',
                   'nested/native-live/archive source/nested directory/hello world.txt',
                   'Native-live/archive source/nested directory/hello world.txt',
                   'native-live/extracted gzip/nested directory/hello world.txt',
                   'native-live/extracted unknown/nested directory/hello world.txt',
                   'native-live/extracted ZIP/nested directory/hello world.txt',
                   'native-live/extracted zip/extra/nested directory/hello world.txt',
                   'native-live/extracted zip/nested directory/hello world.txt.extra.txt']
        for path in aliases:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, _ = self.fixture(root, path, S.PUBLIC_NATIVE_BINARY_BYTES)
                self.assertIsNone(S.public_native_binary_format(path, S.PUBLIC_NATIVE_BINARY_BYTES))
                with self.assertRaises(UnicodeDecodeError):
                    S.screen(source, root/'out')
                self.assertFalse((root/'out').exists())

    def test_ordinary_text_receipt_unchanged_and_private_text_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = self.fixture(root, 'ordinary.txt', b'public original text\n')
            S.screen(source, root/'out', external=True)
            self.assertEqual(set(json.loads((root/'out/upload-screening.json').read_bytes())), {'scope', 'files'})
            self.assertEqual((root/'out/ordinary.txt').read_bytes(), b'public original text\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = self.fixture(root, 'ordinary.txt', b'authorization: Bearer PRIVATE\n')
            with self.assertRaises(RuntimeError):
                S.screen(source, root/'out', external=True)
            self.assertFalse((root/'out').exists())

    def test_original_symlink_guard_still_precedes_format_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, original = self.fixture(root, sorted(S.PUBLIC_NATIVE_BINARY_PATHS)[0], S.PUBLIC_NATIVE_BINARY_BYTES)
            backing = root/'backing'
            original.rename(backing)
            original.symlink_to(backing)
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                S.screen(source, root/'out')
            self.assertFalse((root/'out').exists())


if __name__ == '__main__':
    unittest.main()
