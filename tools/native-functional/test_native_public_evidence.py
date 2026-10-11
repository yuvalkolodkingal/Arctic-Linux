"""Execute the actual guest exporter and unchanged encoder/host privacy gates."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ORIGINAL_GUEST_SHA = 'aab4323815e239b5debeccf93c4b73f727cd9ed54715f519b8bb1e99915a1d78'
PROFILE_RECORD = 'ARCTIC-NATIVE-PRIVATE-PROFILES '


def load(name, path, raw=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if raw is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


G = load('native_public_guest', HERE / 'guest-check-native-v6.py')
E = load('native_public_host', HERE / 'evidence.py')
S = load('native_public_screen', HERE / 'screen-evidence.py')
N = load('native_public_runtime', HERE / 'native_smoke.py')


def original_guest():
    # A whole-byte reversal, usable in an RPM Source0 archive without Git.
    from test_controls_state_trials import restore_controls_guest
    source = restore_controls_guest((HERE / 'guest-check-native-v6.py').read_text())
    start = source.index('# BEGIN NATIVE_PUBLIC_EVIDENCE_INVENTORY\n')
    stop = source.index('# END NATIVE_PUBLIC_EVIDENCE_INVENTORY\n', start)
    source = source[:start] + source[stop + len('# END NATIVE_PUBLIC_EVIDENCE_INVENTORY\n\n\n'):]
    replacements = (
        ("        # Export the audit's owned public artifacts, even after failed gates.\n",
         '        # Export only owned guest JSON/screens/logs/text, even after failed gates.\n'),
        ('                    if not native_public_evidence_member(relative):\n                        continue\n', ''),
        ("            print('ARCTIC-NATIVE-PRIVATE-PROFILES '+json.dumps(dict(\n"
         "                  schema='arctic-native-private-profile-disclosure-v1', stage=stage,\n"
         "                  category='private-isolated-profiles-retained-not-published',\n"
         "                  retention='owned-guest-tmp-until-poweroff', durable_host_copy=False,\n"
         "                  release_acceptance=False),sort_keys=True),flush=True)\n", ''),
    )
    for new, old in replacements:
        if source.count(new) != 1:
            raise AssertionError('Exporter inverse occurrence differs')
        source = source.replace(new, old)
    raw = source.encode()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_GUEST_SHA:
        raise AssertionError('Original whole guest bytes differ')
    return load('native_public_original_guest', HERE / 'guest-check-native-v6.py', raw), raw


def exact_finally(module, raw):
    main = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    body = next(n for n in main.body if isinstance(n, ast.Try) and n.finalbody).finalbody
    fields = ('report', 'expected_uid', 'original_roots', 'provenance', 'begin',
              'stage', 'error', 'export_complete', 'roots')
    args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in fields], vararg=None,
                         kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
    function = ast.FunctionDef(name='exact_export_finally', args=args,
        body=body + [ast.Return(value=ast.Tuple(elts=[ast.Name(id=n, ctx=ast.Load())
            for n in ('error', 'export_complete', 'passed')], ctx=ast.Load()))], decorator_list=[])
    ast.fix_missing_locations(function)
    module.__dict__.update(zlib=__import__('zlib'), traceback=__import__('traceback'))
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'actual-main-finally', 'exec'), module.__dict__)
    return module.exact_export_finally


class Port:
    def __init__(self): self.raw = []; self.closed = False
    def write(self, text):
        if self.closed: raise AssertionError('Write after owned port closed')
        self.raw.append(text.encode('ascii'))
    def close(self): self.closed = True


class PublicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='arctic-native-smoke-', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = tempfile.TemporaryDirectory(prefix='native-public-host-', dir='/tmp')
        self.addCleanup(self.host.cleanup)
        self.host_root = Path(self.host.name)

    def write(self, name, raw=b'synthetic public evidence\n'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def export(self, original=False, primary='RuntimeError: original native gate failed', report=None):
        module, raw = original_guest() if original else (G, (HERE / 'guest-check-native-v6.py').read_bytes())
        run = exact_finally(module, raw)
        begin = dict(stage='live', native_source_sha256=E.NATIVE_SOURCE_SHA,
                     checker_sha256=hashlib.sha256(raw).hexdigest(), release_acceptance=False)
        proof = dict(boot_id='00000000-0000-0000-0000-000000000001')
        if report is None: report = dict(evidence_root=str(self.root), status='failed')
        port = Port(); stdout = io.StringIO(); stderr = io.StringIO()
        with mock.patch.object(module, 'open_native_bulk_port', return_value=(port, {})), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = run(report, os.getuid(), set(), proof, begin, 'live', primary, False, [])
        lines = b''.join(port.raw).decode('ascii').splitlines()
        manifests = E.records(lines, 'ARCTIC-NATIVE-EVIDENCE-MANIFEST ')
        disclosure = E.records(stdout.getvalue().splitlines(), PROFILE_RECORD)
        end = E.records(stdout.getvalue().splitlines(), 'ARCTIC-NATIVE-RUNNER-END ')[0]
        return dict(result=result, port=port, lines=lines, manifests=manifests,
                    disclosure=disclosure, end=end, begin=begin)

    def extract(self, exported, name):
        target = self.host_root / name / 'native-live'
        copied = E.extract_evidence(exported['lines'], 'live', target)
        return target, copied

    def screen(self, source, name):
        target = self.host_root / name
        # Match the real runner's stage directory beneath the screening root.
        with contextlib.redirect_stdout(io.StringIO()): S.screen(source.parent, target, external=True)
        return target

    def test_actual_old_profile_database_defect_and_fixed_private_retention(self):
        public = {'report.json': b'{"status":"failed"}\n', 'gui-trace.log': b'{"event":"synthetic"}\n',
                  'visual-reference-frame.rgb': b'\xda\x00\xff'}
        for name, raw in public.items(): self.write(name, raw)
        profiles = {}
        for directory in ('home', 'config', 'data', 'cache'):
            path = self.root / directory / 'synthetic-profile' / 'database.log'
            path.parent.mkdir(parents=True)
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE evidence(value BLOB)')
                db.execute('INSERT INTO evidence VALUES(?)', (b'\xda\x00',))
                self.assertEqual(db.execute('SELECT value FROM evidence').fetchone(), (b'\xda\x00',))
            profiles[path] = (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
        old = self.export(original=True); old_host, old_copied = self.extract(old, 'old')
        self.assertTrue(all(p.relative_to(self.root).as_posix() in old_copied for p in profiles))
        with self.assertRaises(UnicodeDecodeError): self.screen(old_host, 'old-screen')
        fixed = self.export(); target, copied = self.extract(fixed, 'fixed')
        self.assertEqual(set(copied), set(public)); self.screen(target, 'fixed-screen')
        for path, (raw, inode, mtime) in profiles.items():
            self.assertEqual((path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns), (raw, inode, mtime))
        for name, raw in public.items():
            self.assertEqual((old_host / name).read_bytes(), raw)
            self.assertEqual((target / name).read_bytes(), raw)
        self.assertEqual(old['result'], fixed['result'])
        self.assertEqual(fixed['result'], ('RuntimeError: original native gate failed', True, False))
        self.assertEqual(fixed['disclosure'], [dict(schema='arctic-native-private-profile-disclosure-v1', stage='live',
            category='private-isolated-profiles-retained-not-published', retention='owned-guest-tmp-until-poweroff',
            durable_host_copy=False, release_acceptance=False)])

    def test_every_finite_public_member_transports_exact_original_bytes(self):
        names = sorted(G.NATIVE_PUBLIC_EVIDENCE_FILES)
        # Separate roots keep the unchanged original 128-file bound in force.
        for offset in range(0, len(names), 64):
            batch = names[offset:offset + 64]
            for name in batch: self.write(name)
            value = self.export(); target, copied = self.extract(value, 'batch-' + str(offset))
            self.assertEqual(set(copied), set(batch))
            for name in batch:
                self.assertEqual((target / name).read_bytes(), (self.root / name).read_bytes())
                (self.root / name).unlink()
            self.assertFalse(value['end']['status'] == 'passed')

    def test_public_only_original_chunk_manifest_and_failure_receipts_are_identical(self):
        for name, raw in (('report.json', b'{"status":"failed"}\n'),
                          ('gui-trace.log', b'{"event":"synthetic"}\n'),
                          ('visual-owned-window.rgb', b'\xda\x00\xff')):
            self.write(name, raw)
        old = self.export(original=True); fixed = self.export()
        prefixes = ('ARCTIC-NATIVE-EVIDENCE-CHUNK ', 'ARCTIC-NATIVE-EVIDENCE-MANIFEST ')
        self.assertEqual([x for x in old['lines'] if x.startswith(prefixes)],
                         [x for x in fixed['lines'] if x.startswith(prefixes)])
        self.assertEqual(old['end'], fixed['end'])
        self.assertTrue(old['port'].closed and fixed['port'].closed)
        self.assertEqual(old['disclosure'], [])
        self.assertEqual(len(fixed['disclosure']), 1)

    def test_source_bound_finite_diagnostic_names_archive_formats_and_launch_bounds(self):
        tree = ast.parse((HERE / 'native_smoke.py').read_bytes())
        gates = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'gate'}
        direct = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == 'diagnostic'
                  and isinstance(n.args[0], ast.Constant)}
        navigation = {n.args[2].value for n in ast.walk(tree) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute) and n.func.attr == 'navigate'}
        labels = {'failure-' + n for n in gates} | direct | {n + suffix for n in navigation
                  for suffix in ('-before-location', '-navigation-confirmed')}
        self.assertEqual(len(labels), 13)
        expected = {'gui-%02d-' % index + label + '.png' for index in range(len(labels)) for label in labels}
        self.assertEqual({n for n in G.NATIVE_PUBLIC_EVIDENCE_FILES if n.startswith('gui-') and n.endswith('.png')}, expected)
        self.assertEqual({n for n in G.NATIVE_PUBLIC_EVIDENCE_FILES if n.startswith('gui-launch-')},
                         {'gui-launch-' + str(i) + '.log' for i in range(130)})
        for directory in ('archive source', *('extracted ' + kind for kind in
                ('zip', '7z', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'tar.zst', 'cpio', '7z-encrypted'))):
            self.assertIn(directory + '/nested directory/hello world.txt', G.NATIVE_PUBLIC_EVIDENCE_FILES)
            self.assertIn(directory + '/Unicode-\u05e9.txt', G.NATIVE_PUBLIC_EVIDENCE_FILES)
        self.assertEqual(hashlib.sha256((HERE / 'native_smoke.py').read_bytes()).hexdigest(), E.NATIVE_SOURCE_SHA)

    def test_unknown_public_names_aliases_and_private_symlinks_fail_before_bulk(self):
        names = ('unexpected.log', 'home-private/database.log', 'Home/database.log', 'config.json',
                 'renderer-trial-private/reference.png', 'gui-launch-130.log', 'gui-launch-01.log',
                 'gui-13-editor-save-confirmed.png', 'gui-00-private-label.png',
                 'wrong-password-control/Unicode-\u05e9.txt')
        for name in names:
            with self.subTest(name=name):
                path = self.write(name); value = self.export(); path.unlink()
                self.assertFalse(value['manifests']); self.assertFalse(value['port'].raw)
                self.assertFalse(value['end']['evidence_export_complete'])
                self.assertTrue(value['result'][0].startswith('RuntimeError: original native gate failed;'))
        for name in ('home/foreign.log', 'config/foreign', 'data/link.txt', 'cache/link.json'):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to('/dev/null'); value = self.export(); path.unlink()
            self.assertFalse(value['manifests']); self.assertFalse(value['port'].raw)
            self.assertIn('native evidence tree contains a symlink', value['result'][0])

    def test_expected_public_malformed_utf8_and_sensitive_text_still_reject_atomically(self):
        for raw, error in ((b'\xda\x00', UnicodeDecodeError), (b'ghp_SyntheticPrivateCounterfactual123\n', RuntimeError)):
            with self.subTest(error=error.__name__):
                self.write('gui-trace.log', raw)
                value = self.export(); target, copied = self.extract(value, error.__name__)
                self.assertEqual((target / 'gui-trace.log').read_bytes(), raw)
                with self.assertRaises(error): self.screen(target, 'screen-' + error.__name__)
                self.assertFalse((self.host_root / ('screen-' + error.__name__)).exists())
                self.assertEqual(copied['gui-trace.log']['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertFalse(value['result'][2])

    def test_original_exact_binary_fixture_is_not_a_general_format_exception(self):
        raw = b'Arctic archive roundtrip\n\x00\xff\n'
        name = 'archive source/nested directory/hello world.txt'
        self.write(name, raw); value = self.export(); target, _ = self.extract(value, 'fixture')
        self.screen(target, 'fixture-screen')
        self.assertEqual((target / name).read_bytes(), raw)
        self.write(name, raw + b'private'); value = self.export(); target, _ = self.extract(value, 'changed')
        with self.assertRaises(RuntimeError): self.screen(target, 'changed-screen')
        self.assertFalse((self.host_root / 'changed-screen').exists())

    def test_original_file_count_file_size_and_total_size_failures_remain(self):
        for i in range(129): self.write('gui-launch-' + str(i) + '.log')
        value = self.export(); self.assertIn('file count/size exceeded bound', value['result'][0])
        self.assertFalse(value['port'].raw)
        for i in range(129): (self.root / ('gui-launch-' + str(i) + '.log')).unlink()
        self.write('visual-owned-window.rgb', b'x' * (4 * 1024 * 1024 + 1))
        value = self.export(); self.assertIn('file count/size exceeded bound', value['result'][0])
        (self.root / 'visual-owned-window.rgb').unlink()
        for name in ('editor-saved.png', 'files-opened-zip.png', 'celluloid-playing.png',
                     'celluloid-reference.png', 'visual-owned-window.rgb'):
            self.write(name, b'x' * (4 * 1024 * 1024))
        value = self.export(); self.assertIn('total exceeded bound', value['result'][0])
        self.assertFalse(value['port'].raw)

    def native_consumer_fixture(self):
        begin = dict(stage='live', native_source_sha256=E.NATIVE_SOURCE_SHA,
                     checker_sha256=E.CHECKERS['native-functional'][1], release_acceptance=False)
        process = dict(pid=10, start_ticks=11, uid=1000, executable_sha256='a' * 64)
        launcher = dict(schema='arctic-native-launcher-v1', stage='live',
            boot_id='00000000-0000-0000-0000-000000000001', launcher_sha256=E.LAUNCHER_SHA,
            owned_launcher_gone=True, shell=dict(process, executable='/usr/bin/bash'),
            foot=dict(process, executable='/usr/bin/foot'), probe=dict(process, uid=0, executable='/usr/bin/python3'))
        proof = dict(begin, desktop_uid=1000, boot_id=launcher['boot_id'], launcher=launcher,
                     active_desktop_session='synthetic', cmdline='rd.live.image', virtual_audio_cards=' 0 [Synthetic]')
        shots = [dict(path=str(self.root / n), sha256=hashlib.sha256(b'\x89PNG\r\n\x1a\n').hexdigest())
                 for n in ('editor-saved.png', 'files-opened-zip.png', 'celluloid-playing.png', 'celluloid-reference.png')]
        rgb = N.visual_reference_frame()
        visual = dict(screenshot=shots[3], client_pixel_crop=dict(width=160, height=120),
                      oracle=N.evaluate_reference_rgb(rgb, 160, 120, rgb))
        for role, name in (('expected_rgb', 'visual-reference-frame.rgb'), ('actual_rgb', 'visual-owned-window.rgb')):
            visual[role + '_path'] = str(self.root / name); visual[role + '_sha256'] = hashlib.sha256(rgb).hexdigest()
        report = dict(schema='arctic-native-functional-smoke-v4', stage='live', release_acceptance=False,
                      status='limited-smoke-passed', evidence_root=str(self.root), gates=[dict(check=n, status='passed', value={}) for n in E.GATES])
        byname = {g['check']: g for g in report['gates']}
        byname['actual-role-file-manager-terminal-editor']['value'] = dict(screenshots=shots[:2])
        byname['open-codec-content-and-player-state']['value'] = dict(screenshot=shots[2], visual_reference=visual)
        public = {'report.json': json.dumps(report).encode(), 'visual-oracle.json': json.dumps(visual).encode(),
                  'visual-reference-frame.rgb': rgb, 'visual-owned-window.rgb': rgb}
        public.update({Path(s['path']).name: b'\x89PNG\r\n\x1a\n' for s in shots})
        public.update({n: b'{}' for n in ('gui-trace.log', 'gui-trace-summary.json', 'final-clients.json', 'moving-player-proof.json')})
        return begin, proof, report, public

    def test_unchanged_actual_consumer_keeps_missing_required_evidence_failed(self):
        begin, proof, report, public = self.native_consumer_fixture()
        omissions = ('report.json', 'editor-saved.png', 'files-opened-zip.png',
                     'celluloid-playing.png', 'celluloid-reference.png',
                     'visual-reference-frame.rgb', 'visual-owned-window.rgb',
                     'gui-trace.log', 'gui-trace-summary.json', 'final-clients.json',
                     'visual-oracle.json', 'moving-player-proof.json')
        for missing in omissions:
            with self.subTest(missing=missing):
                for name, raw in public.items():
                    if name != missing: self.write(name, raw)
                value = self.export(primary=None, report=report)
                self.assertTrue(value['result'][2])  # Host acceptance must still reject absent evidence.
                serial = '\n'.join(['ARCTIC-NATIVE-RUNNER-BEGIN ' + json.dumps(begin),
                    'ARCTIC-NATIVE-PROVENANCE ' + json.dumps(proof),
                    'ARCTIC-NATIVE-FUNCTIONAL ' + json.dumps(report), *value['lines'],
                    'ARCTIC-NATIVE-RUNNER-END ' + json.dumps(value['end'])])
                with self.assertRaises(RuntimeError): E.check_native(serial, 'live', self.host_root / ('missing-' + missing))
                for name in public:
                    path = self.root / name
                    if path.exists(): path.unlink()

    def test_original_unicode_editor_and_fullscreen_file_oracles_still_require_evidence(self):
        # Project only the final actual Unicode-byte oracle, without altering
        # its AST. Earlier physical/session proofs are not fabricated here.
        function = next(n for n in ast.parse((HERE / 'evidence.py').read_bytes()).body
                        if isinstance(n, ast.FunctionDef) and n.name == 'check_editor_save')
        first = next(i for i, n in enumerate(function.body) if isinstance(n, ast.Assign)
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'fixture')
        module = ast.Module(body=function.body[first:first + 3], type_ignores=[])
        namespace = dict(Path=Path, R=E.R, target=self.root, report=dict(evidence_root=str(self.root)))
        oracle = compile(module, 'actual-final-unicode-editor-byte-oracle', 'exec')
        with self.assertRaises(RuntimeError): exec(oracle, namespace)
        wanted = ('Arctic GUI saved fixture ' + self.root.name + '\nUnicode: שלום λ 日本語\n').encode()
        fixture = self.write('files with spaces/editor fixture.txt', wanted)
        exec(oracle, namespace)
        fixture.write_bytes(wanted + b'changed')
        with self.assertRaises(RuntimeError): exec(oracle, namespace)
        report = dict(diagnostic_controls=dict(gui_v6=True, editor_physical_save=True,
                      owned_player_fullscreen=True, accessibility_proof=False))
        for missing in ('fullscreen-player-receipts.json', 'fullscreen-player-captures.json'):
            with self.subTest(missing=missing):
                other = 'fullscreen-player-captures.json' if missing.endswith('receipts.json') else 'fullscreen-player-receipts.json'
                self.write(other, b'[]')
                with self.assertRaises(FileNotFoundError): E.check_fullscreen(self.root, report, 1000)
                (self.root / other).unlink()


if __name__ == '__main__':
    unittest.main()
