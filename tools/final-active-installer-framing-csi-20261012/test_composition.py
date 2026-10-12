"""Finite Source-only controls; no VM, API or historical original evidence."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import types
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = load('composition_source_controls', HERE / 'composition.py')
P = load('composition_privacy_source_controls', HERE / 'privacy-entry.py')


class CompositionControls(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((HERE / 'execution-manifest.json').read_bytes())

    def test_disabled_exact_source_and_component_closure(self):
        self.assertIs(C.checked(self.manifest), self.manifest)
        self.assertFalse(self.manifest['ready'])
        self.assertFalse(self.manifest['release_acceptance'])
        self.assertEqual(len(self.manifest['execution_files']), 90)

    def test_ready_type_image_inventory_and_private_fields_fail_closed(self):
        for key, value in (('ready', 0), ('ready', True), ('release_acceptance', 0),
                ('base', '0' * 40), ('image', None)):
            candidate = copy.deepcopy(self.manifest)
            candidate[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                C.checked(candidate)
        for change in ('extra', 'missing', 'retarget', 'type-alias'):
            candidate = copy.deepcopy(self.manifest)
            if change == 'extra':
                candidate['password'] = 'source-control-placeholder'
            elif change == 'missing':
                candidate['execution_files'].pop(next(iter(candidate['execution_files'])))
            elif change == 'retarget':
                candidate['execution_files']['tools/installer-qualification/driver.py'] = '0' * 64
            else:
                candidate['limits']['active_profile'] = 1
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                C.checked(candidate)

    def test_shell_whole_inverse_and_retained_runner_function_code(self):
        old = C.raw_file(C.ROOT, 'tools/installer-qualification/run-live.sh')
        new = C.raw_file(C.ROOT, C.PREFIX + 'run-live-observed.sh')
        self.assertEqual(new.replace(b'final-active-installer-framing-csi-20261012/driver-entry.py',
            b'installer-qualification/driver.py'), old)
        runner = C.runner(self.manifest)
        raw = C.raw_file(C.ROOT, 'tools/installer-qualification/runner.py')
        code = compile(raw, str(C.ROOT / 'tools/installer-qualification/runner.py'), 'exec', optimize=0)
        functions = {c.co_name: c for c in code.co_consts if type(c) is types.CodeType}
        for name, expected in functions.items():
            if name not in ('verify', 'execute'):
                actual = getattr(runner, name)
                self.assertEqual(actual.__code__, expected, name)
        self.assertEqual(runner.E.active_contract().EXECUTION_FILES,
            tuple(sorted(self.manifest['execution_files'])))
        self.assertEqual(runner._driver.DIAGNOSTIC_CODES, C.driver().DIAGNOSTIC_CODES)

    def test_original_acceptance_function_codes_and_secret_guards_unchanged(self):
        runner = C.runner(self.manifest)
        active = runner.E.active_contract()
        path = C.ROOT / 'tools/installer-qualification/active-contract.py'
        source = compile(path.read_bytes(), str(path), 'exec', optimize=0)
        functions = {c.co_name: c for c in source.co_consts if type(c) is types.CodeType}
        for name, expected in functions.items():
            self.assertEqual(getattr(active, name).__code__, expected, name)
        self.assertEqual(active.REQUIRED_IMAGES,
            ('host/installed-getty-password.png', 'host/installed-sudo-password.png',
             'host/installer-vt-away-0.png', 'installer/baseline.png',
             'installer/output-0-relocated.png', 'installer/output-0.png', 'installer/vt-0.png'))
        driver = C.driver()
        old = ast.parse(C.raw_file(C.ROOT, 'tools/installer-qualification/driver.py'))
        new = ast.parse(C.raw_file(C.ROOT, C.PREFIX + 'driver-observed.py'))
        old_nodes = {n.name: ast.dump(n, include_attributes=False) for n in old.body if isinstance(n, ast.FunctionDef)}
        new_nodes = {n.name: ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, ast.FunctionDef)}
        for name in ('console_prompt', 'installed_shell_ready', 'boot_installed'):
            self.assertEqual(old_nodes[name], new_nodes[name], name)
        self.assertEqual(driver.console_user_identity.__code__.co_filename,
            str(C.ROOT / 'tools/installer-qualification/driver.py'))

    def test_source_execute_adapter_preserves_deadline_and_other_commands(self):
        runner = C.runner(self.manifest)
        # Bind the actual original execute wrapper's dependency through its
        # closure, without launching or replacing the reviewed Source loader.
        names = dict(zip(runner.execute.__code__.co_freevars, runner.execute.__closure__))
        calls = []
        names['original_execute'].cell_contents = lambda *args: calls.append(args)
        old = str(C.ROOT / 'tools/installer-qualification/run-live.sh')
        argv = ['bash', old, 'source', 'execution', 'iso', 'payload', 'context', 'uefi', 'out']
        runner.execute(argv, 'log', 4800, C.ROOT, {})
        self.assertEqual(calls[0][0], ['bash', str(HERE / 'run-live-observed.sh'), *argv[2:]])
        self.assertEqual(calls[0][2], 4800)
        with self.assertRaises(RuntimeError):
            runner.execute(argv, 'log', 4801, C.ROOT, {})
        other = ['bash', 'unrelated-source-control']
        runner.execute(other, 'log', 3, C.ROOT, {})
        self.assertIs(calls[-1][0], other)

    def test_selected_qmp_driver_and_csi_code_use_exact_buffers_and_canonical_names(self):
        driver = C.driver()
        selected = C.raw_file(C.ROOT, C.PREFIX + 'driver-observed.py')
        self.assertEqual(C.sha(selected), C.COMPONENT_BINDINGS['identity_driver_sha256'])
        canonical = str(C.ROOT / 'tools/installer-qualification/driver.py')
        code = compile(selected, canonical, 'exec', optimize=0)
        functions = {c.co_name: c for c in code.co_consts if type(c) is types.CodeType}
        for name in ('owned_qmp_path', 'owned_vm_type', 'prepare_vm', 'main'):
            self.assertEqual(getattr(driver, name).__code__, functions[name])
            self.assertEqual(getattr(driver, name).__code__.co_filename, canonical)
        _, scanner, _, _ = P.build(self.manifest)
        module = scanner()
        raw = C.raw_file(C.ROOT, C.PREFIX + 'scanner.py')
        code = compile(raw, str(C.ROOT / 'tools/native-functional/screen-evidence.py'), 'exec', optimize=0)
        functions = {c.co_name: c for c in code.co_consts if type(c) is types.CodeType}
        self.assertEqual(module.classification_view.__code__, functions['classification_view'])
        self.assertEqual(C.sha(raw), C.COMPONENT_BINDINGS['privacy_scanner_sha256'])
        self.assertNotEqual(raw, C.raw_file(C.ROOT, 'tools/native-functional/screen-evidence.py'))

    def test_complete_csi_preserves_bytes_and_unknown_sensitive_rejection(self):
        _, scanner, screened, _ = P.build(self.manifest)
        module = scanner()
        allowed = b'\x1b[0;32mordinary original Source control\x1b[0m\n'
        self.assertIs(module.external_text(allowed), allowed)
        self.assertEqual(screened(module, allowed), (True, None, []))
        sensitive = b'private\x1b[0;32m-person@example.net\x1b[0m\n'
        passed, reason, rows = screened(module, sensitive)
        self.assertFalse(passed)
        self.assertEqual(reason, 'sensitive-text')
        self.assertTrue(rows)
        self.assertNotIn('private-person', json.dumps(rows))
        self.assertNotIn('example.net', json.dumps(rows))
        for row in rows:
            self.assertFalse(row['privacy_admitted'])
            self.assertFalse(row['runtime_cause_proven'])

    def test_privacy_actual_owned_rejection_adds_only_fixed_shape_and_restores_callback(self):
        _, scanner, screened, helper = P.build(self.manifest)
        module = scanner()
        prior = module.diagnose_sensitive_match
        passed, reason, rows = screened(module, b'getty@tty1.service\n')
        self.assertFalse(passed)
        self.assertEqual(reason, 'sensitive-text')
        self.assertEqual(len(rows), 1)
        shape = rows[0]['same_owned_rejected_match_public_shape']
        self.assertEqual(shape['canonical_unit_id'], 'unit-009')
        self.assertTrue(all(type(shape[k]) is bool for k in helper.DIAGNOSTIC_SHAPE_FLAGS))
        self.assertFalse(shape['privacy_admitted'])
        self.assertFalse(shape['runtime_cause_proven'])
        self.assertFalse(shape['operand_value_or_digest_exported'])
        self.assertIs(module.diagnose_sensitive_match, prior)

    def test_privacy_unknown_allowed_and_encoding_controls_preserve_original_results(self):
        _, scanner, screened, _ = P.build(self.manifest)
        module = scanner()
        passed, reason, rows = screened(module, b'private-person@example.net\n')
        self.assertFalse(passed)
        self.assertEqual(reason, 'sensitive-text')
        self.assertEqual(rows[0]['same_owned_rejected_match_public_shape']['canonical_unit_id'], 'unknown')
        self.assertNotIn('private-person', json.dumps(rows))
        allowed = b'ordinary original source control\n'
        self.assertIs(module.external_text(allowed), allowed)
        self.assertEqual(screened(module, allowed), (True, None, []))
        self.assertEqual(screened(module, b'\xff'), (False, 'invalid-utf8', []))
        self.assertEqual(screened(module, b'\x1b]partial'), (False, 'incomplete-terminal', []))

    def test_optional_shape_failure_or_private_schema_omits_shape_without_admitting_text(self):
        for replacement in ('throws', 'private', 'type-alias'):
            _, scanner, screened, helper = P.build(self.manifest)
            module = scanner()
            original = helper.diagnostic_public_source_shape
            if replacement == 'throws':
                def changed(*args):
                    raise RuntimeError('source control optional error')
            else:
                def changed(*args):
                    value = original(*args)
                    value['secret'] = 'source control' if replacement == 'private' else 1
                    return value
            helper.diagnostic_public_source_shape = changed
            passed, reason, rows = screened(module, b'getty@tty2.service\n')
            self.assertFalse(passed)
            self.assertEqual(reason, 'sensitive-text')
            self.assertNotIn('same_owned_rejected_match_public_shape', rows[0])

    def test_changed_scanner_global_rejects_before_content(self):
        _, scanner, screened, _ = P.build(self.manifest)
        module = scanner()
        module.EXTERNAL_SENSITIVE = re.compile('source control changed regex')
        with mock.patch.object(module, 'external_text', side_effect=AssertionError('must not inspect content')):
            with self.assertRaises(RuntimeError):
                screened(module, b'private-person@example.net\n')

    def test_foreign_direct_annotation_receives_no_owned_shape(self):
        prepared, scanner, _, _ = P.build(self.manifest)
        screened = prepared.original.__globals__['screened_text']
        names = dict(zip(screened.__code__.co_freevars, screened.__closure__))
        cloned = names['cloned_screened'].cell_contents
        annotated = cloned.__globals__['annotated_match']
        module = scanner()
        value = 'getty@tty2.service\n'
        match = module.EXTERNAL_SENSITIVE.search(value)
        view, boundaries, removed = module.classification_view(value)
        row = annotated(module, match, 'source-view', value, boundaries, removed)
        self.assertNotIn('same_owned_rejected_match_public_shape', row)

    def test_cloned_callback_replacement_cannot_export_raw_rejected_operand(self):
        prepared, scanner, screened, _ = P.build(self.manifest)
        module = scanner()
        prepared.original.__globals__['annotated_match'] = lambda m, match, *args: {'unprojected_placeholder': match.group(0)}
        with self.assertRaises(RuntimeError):
            screened(module, b'private-person@example.net\n')

    def test_same_source_helper_map_mutation_omits_shape_and_keeps_rejection(self):
        _, scanner, screened, helper = P.build(self.manifest)
        module = scanner()
        changed = []
        def trace(frame, event, arg):
            if frame.f_code is helper.diagnostic_public_source_shape.__code__ and event == 'return':
                frame.f_locals['boundaries'].append(0)
                frame.f_locals['removed'].append(0)
                changed.append(True)
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            passed, reason, rows = screened(module, b'getty@tty1.service\n')
        finally:
            sys.settrace(previous)
        self.assertEqual(changed, [True])
        self.assertFalse(passed)
        self.assertEqual(reason, 'sensitive-text')
        self.assertNotIn('same_owned_rejected_match_public_shape', rows[0])


    def test_identity_selected_buffer_and_original_fixed_outer_relay(self):
        runner = C.runner(self.manifest)
        token = 'b' * 32
        codes = tuple(sorted(runner._driver._IDENTITY_LABEL_CODES | runner._driver._IDENTITY_SOURCE_CODES))
        self.assertEqual(len(codes), 39)
        wire = b''.join(('ARCTIC-INSTALLER-INNER ' + token + ' ' + code + '\n').encode() for code in codes)
        self.assertEqual(runner.inner_codes(wire, token), codes)
        self.assertEqual(runner.inner_codes(wire, 'c' * 32), ())
        self.assertEqual(runner.inner_codes(('ARCTIC-INSTALLER-INNER ' + token + ' private-operand\n').encode(), token), ())
        self.assertEqual(C.LIMITS['console_identity_seconds'], 45)
        self.assertEqual(C.BRANCH, 'refs/heads/codex/active-installer-framing-csi-20261012')

    def test_source_owned_new_diagnostics_keep_full_parent_inverse_binding(self):
        driver = C.driver()
        self.assertEqual(C.COMPONENT_BINDINGS['identity_source_sha'], '8cdd1324649ab2323a1da6a476c2812d858274ce')
        self.assertEqual(C.COMPONENT_BINDINGS['retained_identity_driver_sha256'],
            C.sha(C.raw_file(C.ROOT, 'tools/final-active-installer-identity-csi-20261011/driver-observed.py')))
        self.assertEqual(driver._IDENTITY_SYNTAX_FIELDS,
            ('four-fields', 'marker', 'nonce-syntax', 'uid-prefix', 'uid-syntax', 'user-prefix', 'user-syntax'))
        self.assertEqual(len(driver._IDENTITY_SOURCE_CODES), 27)
        owner = {'codes': set()}
        driver._AUTH_ACTIVE = owner
        try:
            driver.observe_installed_identity_comparisons(['ARCTIC-USER ' + 'a' * 32 + ' uid=1000 user=arcticqual'], 'source-only-foreign-call')
            labels = driver.identity_comparison_codes(owner)
            self.assertIn('installer-inner-driver-installed-auth-identity-callsite-unowned', labels)
            self.assertIn('installer-inner-driver-installed-auth-identity-namespace-unknown', labels)
            self.assertTrue(all(label.endswith('-unknown') for label in labels if '-syntax-' in label))
        finally:
            driver._AUTH_ACTIVE = None

if __name__ == '__main__':
    unittest.main()
