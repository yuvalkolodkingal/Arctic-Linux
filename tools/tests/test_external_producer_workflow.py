"""Producer workflow mode isolation controls; no build, VM or publication occurs."""
import ast
from itertools import product
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / '.github/workflows/iso.yml').read_text()
EXTERNAL = 'frozen-external-paired-v1'
LEGACY = 'in-producer-paired-v1'


def step(name):
    marker = '      - name: ' + name + '\n'
    if SOURCE.count(marker) != 1:
        raise AssertionError('Missing or duplicate producer step: ' + name)
    return SOURCE.split(marker, 1)[1].split('\n      - ', 1)[0].split('\n  publish:', 1)[0]


def condition(block):
    matches = re.findall(r'^\s+if: \$\{\{ (.+) \}\}$', block, re.M)
    if len(matches) != 1:
        raise AssertionError('Expected exactly one producer condition')
    return matches[0]


def evaluate(expression, event, mode, release, performance):
    values = {'github.event_name': event, 'inputs.performance_mode': mode,
              'inputs.release': release, 'inputs.performance_acceptance': performance}
    expression = expression.replace('always()', 'True').replace('&&', ' and ').replace('||', ' or ')
    for name, value in values.items():
        expression = expression.replace(name, repr(value))
    parsed = ast.parse(expression, mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
               ast.Compare, ast.Eq, ast.NotEq, ast.Constant)
    if any(not isinstance(node, allowed) for node in ast.walk(parsed)):
        raise AssertionError('Unexpected workflow expression syntax')
    return eval(compile(parsed, '<producer-condition>', 'eval'), {'__builtins__': {}})


class ProducerWorkflowControls(unittest.TestCase):
    def test_legacy_and_external_uploads_are_exclusive_for_all_dispatch_flags(self):
        legacy = condition(step('Upload the ISO (workflow artifact)'))
        external = condition(step('Upload external-mode ISO and producer receipt (workflow artifact)'))
        for event, mode, release, performance in product(('workflow_dispatch', 'push'),
                                                        (LEGACY, EXTERNAL, ''), (False, True), (False, True)):
            values = (event, mode, release, performance)
            with self.subTest(values=values):
                self.assertEqual(evaluate(legacy, *values), mode != EXTERNAL)
                self.assertEqual(evaluate(external, *values), mode == EXTERNAL)

    def test_external_mode_cannot_enter_paired_or_publish_even_with_conflicting_flags(self):
        publish = condition(SOURCE.split('\n  publish:\n', 1)[1].split('\n    runs-on:', 1)[0])
        paired = [condition(step(name)) for name in ('Paired KVM performance acceptance',
                   'Screen paired performance diagnostics', 'Upload paired performance evidence')]
        for event, mode, release, performance in product(('workflow_dispatch', 'push'),
                                                        (LEGACY, EXTERNAL, ''), (False, True), (False, True)):
            values = (event, mode, release, performance)
            with self.subTest(values=values):
                self.assertEqual(evaluate(publish, *values), mode != EXTERNAL and (event == 'push' or release))
                self.assertEqual(evaluate(paired[0], *values), mode != EXTERNAL and event == 'workflow_dispatch' and performance)
                for expression in paired[1:]:
                    self.assertEqual(evaluate(expression, *values), mode != EXTERNAL and performance)

    def test_external_receipt_follows_unchanged_three_startup_lanes_and_strict_size(self):
        names = ['Verify explicit external performance producer request', 'Build RPMs', 'Build ISO',
                 'Boot test in QEMU (UEFI, Try mode)', 'Required optimized ISO size',
                 'Write external performance producer receipt',
                 'Upload external-mode ISO and producer receipt (workflow artifact)']
        positions = [SOURCE.index('      - name: ' + name + '\n') for name in names]
        self.assertEqual(positions, sorted(positions))
        boot = step('Boot test in QEMU (UEFI, Try mode)')
        commands = [line.strip() for line in boot.splitlines() if 'tools/test-iso.sh' in line]
        self.assertEqual(len(commands), 3)
        for line, firmware, mode in zip(commands, ('uefi', 'bios', 'uefi'), ('try', 'install', 'safe')):
            self.assertIn('--firmware ' + firmware + ' --mode ' + mode + ' --require-startup', line)
        self.assertIn('test "$bytes" -lt 2000000000', step('Required optimized ISO size'))
        self.assertIn('PRODUCER_INPUTS_JSON: ${{ toJSON(inputs) }}', step(names[0]))
        self.assertIn('tools/performance/producer-receipt.py --request-only', step(names[0]))
        upload = step(names[-1])
        self.assertIn('out/PERFORMANCE-PLAN.json', upload)
        self.assertIn('if-no-files-found: error', upload)


if __name__ == '__main__':
    unittest.main()
