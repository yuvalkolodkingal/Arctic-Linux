"""Exact Fedora package-wrapper representation; no VM or package substitution."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import test_contract as F
import runner as R
C = F.C
ORIGINAL = (b'#!/bin/sh\n'
    b'# Arctic Linux installer (Quickshell wizard in /usr/share/arctic/installer-ui). It talks to\n'
    b'# arcticd through `arctic-install bridge`.\n'
    b'exec quickshell -p /usr/share/arctic/installer-ui "$@"\n')
CANONICAL = b'#!/usr/bin/sh\n' + ORIGINAL.split(b'\n', 1)[1]
START = b"[ -f dotfiles/.local/bin/arctic-installer ] || cat > %{buildroot}%{_bindir}/arctic-installer << 'EOF'\n"
WRAPPER = '/usr/bin/arctic-installer'


class CanonicalWrapperControls(unittest.TestCase):
    def tree(self, root, wrapper=ORIGINAL):
        for installed, source in C.PACKAGED_SOURCES.items():
            path = root / source; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(START + wrapper + b'EOF\n' if installed == WRAPPER else b'Exact synthetic QML\n')

    def test_exact_original_source_derives_one_canonical_hash_and_retains_every_body_byte(self):
        self.assertEqual(len(ORIGINAL), 200); self.assertEqual(len(CANONICAL), 204)
        self.assertEqual(C.digest(ORIGINAL), '23f868674b161d937ba57a7f13dc45ceef0312bd968eb2b0d5c6652da90bd841')
        self.assertEqual(C.digest(CANONICAL), 'a2aa635388ca946732d6ff7a2149a49ee2345c35f435370507fc404b09e1ac20')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.tree(root)
            expected = C.packaged_source_hashes(root)
            self.assertEqual(expected[WRAPPER], {'bytes': 204, 'sha256': C.digest(CANONICAL)})
            self.assertEqual((root / 'packaging/arctic-linux.spec').read_bytes(), START + ORIGINAL + b'EOF\n')
            for installed in set(C.PACKAGED_SOURCES) - {WRAPPER}:
                self.assertEqual(expected[installed], {'bytes': 20, 'sha256': C.digest(b'Exact synthetic QML\n')})
            changed = ORIGINAL.replace(b'It talks to', b'It connects to')
            self.tree(root, changed)
            actual = C.packaged_source_hashes(root)[WRAPPER]
            self.assertEqual(actual, {'bytes': len(changed) + 4,
                'sha256': C.digest(b'#!/usr/bin/sh\n' + changed.split(b'\n', 1)[1])})
            self.assertNotEqual(actual, expected[WRAPPER])

    def test_source_header_body_tail_and_alternate_wrapper_guards_stay_closed(self):
        for wrapper in (ORIGINAL.replace(b'#!/bin/sh', b'#!/usr/bin/sh'),
                        ORIGINAL.replace(b'#!/bin/sh', b'#!/bin/bash'),
                        ORIGINAL.replace(b'#!/bin/sh\n', b'#!/bin/sh -e\n'),
                        ORIGINAL.replace(b'exec quickshell', b'exec foreign-wrapper'),
                        ORIGINAL + b'extra private body\n'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.tree(root, wrapper)
                with self.assertRaises(RuntimeError) as caught: C.packaged_source_hashes(root)
                self.assertEqual(caught.exception.args, ('installer wrapper source differs',))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.tree(root); path = root / 'dotfiles/.local/bin/arctic-installer'
            path.parent.mkdir(parents=True); path.write_bytes(CANONICAL)
            with self.assertRaises(RuntimeError) as caught: C.packaged_source_hashes(root)
            self.assertEqual(caught.exception.args, ('alternate installer wrapper needs review',))

    def test_actual_host_gate_accepts_only_full_canonical_wrapper_and_rejects_counterfactuals(self):
        for wrapper, valid in ((CANONICAL, True), (ORIGINAL, False),
                               (CANONICAL.replace(b'It talks to', b'It connects to'), False),
                               (CANONICAL.replace(b'#!/usr/bin/sh', b'#!/usr/bin/bash'), False),
                               (CANONICAL + b'\n', False)):
            report, state, files, media, _ = F.fixture()
            expected = copy.deepcopy(report['baseline']['packaged_sources'])
            expected[WRAPPER] = {'bytes': len(CANONICAL), 'sha256': C.digest(CANONICAL)}
            report['baseline']['packaged_sources'][WRAPPER] = {'bytes': len(wrapper), 'sha256': C.digest(wrapper)}
            original = copy.deepcopy(report)
            with contextlib.redirect_stdout(io.StringIO()):
                if valid:
                    result = C.validate_report(report, state['context'], files, lambda name: media['installer/' + name], expected)
                    self.assertEqual(result['cases'], 6); self.assertIs(result['release_acceptance'], False)
                else:
                    with self.assertRaises(RuntimeError) as caught:
                        C.validate_report(report, state['context'], files, lambda name: media['installer/' + name], expected)
                    self.assertEqual(caught.exception.args, ('packaged GUI bytes differ from exact image source',))
                    self.assertEqual(R.contract_assertion_code(caught.exception, C), 'installer-report-validation-assertion-idle-031')
                    self.assertIs(caught.exception._arctic_installer_assertion[0], C._ASSERTION_TOKEN)
            self.assertEqual(report, original)


if __name__ == '__main__': unittest.main()
