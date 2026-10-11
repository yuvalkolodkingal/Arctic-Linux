#!/usr/bin/env python3
"""Retain unchanged strict rejection, adding fixed same-Match shape proofs."""
import importlib.util
import ast
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('active_privacy_composition', HERE / 'composition.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


def build(manifest, root=C.ROOT, ready=False):
    C.checked(manifest, root, ready)
    old_path = root / 'tools/installer-qualification/screen-diagnostic.py'
    raw = C.raw_file(root, C.PREFIX + 'match-diagnostic.py')
    helper = C.load(raw, old_path, 'active_owned_partial_helper')
    ownership_path = root / (C.PREFIX + 'source-ownership.py')
    ownership = C.load(C.raw_file(root, C.PREFIX + 'source-ownership.py'),
        ownership_path, 'active_shape_source_ownership')
    helper_owner = ownership.OwnedSource(helper.__dict__, raw, str(old_path), 'shape-helper')
    original_screened = helper.screened_text
    original_prepare = helper.prepare
    original_annotated = helper.annotated_match
    original_scanner = helper.scanner
    vocabulary = frozenset({n.value for n in ast.walk(ast.parse(raw))
        if isinstance(n, ast.Constant) and type(n.value) is str}
        | {'external-rule-' + format(n, '03d') for n in range(1, 11)})
    nested = [c for c in original_screened.__code__.co_consts
        if type(c) is types.CodeType and c.co_name == 'observe']
    C.require(len(nested) == 1)
    scanner_states = {}
    copied = helper.__dict__.copy()
    closed = {}

    def copied_unchanged():
        return (closed and set(copied) == set(closed['namespace'])
            and all(copied.get(k) is v for k, v in closed['namespace'].items())
            and closed['owner'].unchanged()
            and all(function.__code__ is code and function.__globals__ is namespace
                and function.__defaults__ is defaults and function.__closure__ is closure
                and all(cell.cell_contents is value for cell, value in cells)
                for function, code, namespace, defaults, closure, cells in closed['wrappers']))

    def finite_row(row):
        fields = {'source_match_diagnostic', 'source_text_observation_only', 'actual_code_ownership',
            'privacy_admitted', 'runtime_cause_proven', 'operand_value_or_digest_exported'}
        C.require(type(row) is dict and all(type(k) is str for k in row)
            and set(row) in (fields, fields | {'same_owned_rejected_match_public_shape'})
            and row['source_text_observation_only'] is True
            and all(row[k] is False for k in fields - {'source_match_diagnostic', 'source_text_observation_only'}))
        keys = ('regex', 'offsets', 'mapping', 'source_rule', 'candidate_reason', 'family_reason')
        diagnostic = row['source_match_diagnostic']
        C.require(type(diagnostic) is dict and all(type(k) is str for k in diagnostic)
            and set(diagnostic) == set(keys)
            and all(type(diagnostic[k]) is str and diagnostic[k] in vocabulary for k in keys))
        if 'same_owned_rejected_match_public_shape' in row:
            finite_shape(row['same_owned_rejected_match_public_shape'])

    def finite_shape(shape):
        C.require(type(shape) is dict and all(type(k) is str for k in shape)
            and set(shape) == set(helper.DIAGNOSTIC_SHAPE_FLAGS) | {
            'schema', 'canonical_unit_id', 'privacy_admitted', 'runtime_cause_proven',
            'operand_value_or_digest_exported'}
            and type(shape['schema']) is str
            and shape['schema'] == 'arctic-bios-same-match-public-source-shape-v1'
            and type(shape['canonical_unit_id']) is str
            and shape['canonical_unit_id'] in ('unknown', *(i for _, i in helper.DIAGNOSTIC_PUBLIC_UNITS))
            and all(type(shape[k]) is bool for k in helper.DIAGNOSTIC_SHAPE_FLAGS)
            and all(shape[k] is False for k in ('privacy_admitted', 'runtime_cause_proven',
                'operand_value_or_digest_exported')))

    def owned_during_callback(owner, callback, prior):
        for name, function, code, refs, namespace, builtin_refs, _ in owner.bound.values():
            binding = callback if name == 'diagnose_sensitive_match' else function
            if (owner.namespace.get(name, ownership.ABSENT) is not binding
                    or function.__code__ is not code or function.__globals__ is not owner.namespace
                    or any(owner.namespace.get(n, ownership.ABSENT) is not (
                        callback if n == 'diagnose_sensitive_match' and v is prior else v)
                        for n, v in refs.items())
                    or any(namespace.get(n, ownership.ABSENT) is not v for n, v in builtin_refs.items())):
                return False
        return True

    def scanner():
        scanner_raw = C.raw_file(root, C.PREFIX + 'scanner.py')
        C.require(C.sha(scanner_raw) == C.COMPONENT_BINDINGS['privacy_scanner_sha256'])
        # Compile the selected corrected buffer under the retained canonical
        # filename for exact caller ownership; the old physical file is a
        # retained dependency, not the selected scanner buffer.
        module = C.load(scanner_raw, root / 'tools/native-functional/screen-evidence.py',
            'active_selected_csi_scanner')
        owner = ownership.OwnedSource(module.__dict__, scanner_raw, module.__file__, 'original-scanner')
        C.require(owner.unchanged())
        scanner_states[id(module)] = (module, owner, scanner_raw, module.diagnose_sensitive_match)
        return module

    def annotated(module, match, phase, original=None, boundaries=None, removed=None):
        # Preserve the old Source-text projection even if optional shape proof
        # cannot be established. This never admits the rejected text.
        original_row = original_annotated(module, match, phase, original, boundaries, removed)
        diagnostic = original_row.get('source_match_diagnostic')
        keys = ('regex', 'offsets', 'mapping', 'source_rule', 'candidate_reason', 'family_reason')
        C.require(type(diagnostic) is dict and all(type(diagnostic.get(k)) is str
            and diagnostic[k] in vocabulary for k in keys))
        # Keep only the accepted finite vocabulary. The inherited annotation's
        # operand lengths and digest field remain private intermediate values.
        row = {'source_match_diagnostic': {k: diagnostic[k] for k in keys},
            'source_text_observation_only': True, 'actual_code_ownership': False,
            'privacy_admitted': False, 'runtime_cause_proven': False,
            'operand_value_or_digest_exported': False}
        try:
            entry = scanner_states.get(id(module))
            C.require(entry is not None and entry[0] is module and helper_owner.unchanged()
                and copied_unchanged())
            observe = sys._getframe(1)
            reject = observe.f_back
            prior = entry[3]
            # The original screened_text temporarily installs this closure.
            # Authenticate that one replacement rather than dropping the
            # diagnose_sensitive_match global from Source ownership checks.
            actual_callback = module.diagnose_sensitive_match
            C.require(type(actual_callback) is types.FunctionType
                and actual_callback.__code__ is nested[0]
                and actual_callback.__globals__ is copied
                and observe.f_code is nested[0] and observe.f_globals is copied
                and observe.f_locals.get('m') is module
                and observe.f_locals.get('prior') is prior
                and type(observe.f_locals.get('observations')) is list
                and observe.f_locals.get('match') is match
                and observe.f_locals.get('phase') is phase
                and observe.f_locals.get('original') is original
                and observe.f_locals.get('boundaries') is boundaries
                and observe.f_locals.get('removed') is removed)
            C.require(owned_during_callback(entry[1], actual_callback, prior)
                and copied.get('annotated_match') is annotated)
            C.require(reject is not None
                and reject.f_code is module.reject_sensitive_match.__code__
                and reject.f_globals is module.__dict__
                and type(reject.f_locals.get('error')) is RuntimeError
                and all(reject.f_locals.get(k) is v for k, v in (
                    ('match', match), ('phase', phase), ('original', original),
                    ('boundaries', boundaries), ('removed', removed))))
            # Bind exact Source Code/globals including the admitted callback
            # for this synchronous original rejection frame only.
            active_owner = ownership.OwnedSource(module.__dict__, entry[2], module.__file__, 'original-scanner')
            C.require(active_owner.owns(reject) and active_owner.unchanged())
            rejection_error = reject.f_locals['error']
            operands = {k: reject.f_locals[k] for k in ('match', 'phase', 'original', 'boundaries', 'removed')}
            C.require(type(boundaries) is module.array and type(removed) is module.array)
            boundary_snapshot, removed_snapshot = boundaries.tobytes(), removed.tobytes()
            shape = helper.diagnostic_public_source_shape(module, match, phase, original, boundaries, removed)
            C.require(active_owner.unchanged() and helper_owner.unchanged()
                and copied_unchanged() and module.diagnose_sensitive_match is actual_callback
                and reject.f_locals.get('error') is rejection_error
                and all(reject.f_locals.get(k) is v for k, v in operands.items())
                and boundaries.tobytes() == boundary_snapshot and removed.tobytes() == removed_snapshot)
            finite_shape(shape)
            row = dict(row, same_owned_rejected_match_public_shape=shape)
        except BaseException:
            pass
        finite_row(row)
        return row

    def screened(module, content):
        entry = scanner_states.get(id(module))
        C.require(entry is not None and entry[0] is module and entry[1].unchanged()
            and copied_unchanged())
        result = cloned_screened(module, content)
        # Original finally restores the exact prior callback. A changed owner
        # must fail, never publish an incomplete optional attestation.
        C.require(entry[1].unchanged() and copied_unchanged()
            and module.diagnose_sensitive_match is entry[3]
            and type(result) is tuple and len(result) == 3 and type(result[2]) is list)
        for row in result[2]:
            finite_row(row)
        return result

    copied['annotated_match'] = annotated
    cloned_screened = types.FunctionType(original_screened.__code__, copied,
        original_screened.__name__, original_screened.__defaults__, original_screened.__closure__)
    copied.update(scanner=scanner, screened_text=screened)
    prepared = types.FunctionType(original_prepare.__code__, copied,
        original_prepare.__name__, original_prepare.__defaults__, original_prepare.__closure__)
    copied['prepare'] = prepared
    copied['_source_screened_text'] = cloned_screened
    closed.update(namespace=dict(copied),
        owner=ownership.OwnedSource(copied, raw, str(old_path), 'adapted-partial-helper'),
        wrappers=[(f, f.__code__, f.__globals__, f.__defaults__, f.__closure__,
            tuple((cell, cell.cell_contents) for cell in (f.__closure__ or ())))
            for f in (scanner, screened, annotated)])

    def guarded_prepare(source, out, profile):
        C.require(copied_unchanged() and helper_owner.unchanged())
        result = prepared(source, out, profile)
        C.require(copied_unchanged() and helper_owner.unchanged())
        return result

    # Keep the original Code clone separately available for Source inverse and
    # negative controls; callers receive the checked admission wrapper.
    guarded_prepare.original = prepared
    return guarded_prepare, scanner, screened, helper


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', choices=('active',), required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / 'execution-manifest.json').read_bytes())
    prepared, _, _, _ = build(manifest, ready=True)
    prepared(args.source, args.out, args.profile)
    print('ARCTIC-INSTALLER-PARTIAL-DIAGNOSTIC=created-unqualified', flush=True)


if __name__ == '__main__':
    main()
