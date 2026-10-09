"""Couple outer cancellation grace to real inner bounds; no VM/runtime claim."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
INNER = (ROOT / 'tools/performance/run-paired.py').read_text()
OUTER = (ROOT / 'tools/performance/qualification.py').read_text()
WORKFLOW = (ROOT / '.github/workflows/iso.yml').read_text()


def function(tree, name):
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise AssertionError('Ambiguous cleanup function: ' + name)
    return matches[0]


def timeouts(node, method, constants=None):
    values = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr != method:
            continue
        timeout = [item.value for item in call.keywords if item.arg == 'timeout']
        if len(timeout) != 1:
            raise AssertionError('Cleanup operation lacks one explicit bound')
        value = timeout[0]
        if isinstance(value, ast.Constant):
            values.append(value.value)
        elif isinstance(value, ast.Name) and constants is not None:
            values.append(constants[value.id])
        else:
            raise AssertionError('Unreviewed cleanup bound expression')
    if any(type(value) is not int or value <= 0 for value in values):
        raise AssertionError('Invalid cleanup bound')
    return values


def coupled_budget(inner, outer, workflow):
    tree = ast.parse(inner)
    execute = function(function(tree, 'main'), 'execute')
    stop = timeouts(function(execute, 'stop_owned'), 'wait')
    containers = timeouts(function(execute, 'remove_owned'), 'run')
    prepared = function(tree, 'cleanup_prepared_image')
    per_api = timeouts(function(prepared, 'command'), 'run')
    calls = sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'command'
                for node in ast.walk(prepared))
    if not stop or not containers or len(per_api) != 1 or not calls:
        raise AssertionError('Incomplete inner cleanup budget inventory')
    budget = sum(stop) + sum(containers) + per_api[0] * calls
    outer_tree = ast.parse(outer)
    constants = {node.targets[0].id: node.value.value for node in outer_tree.body
                 if isinstance(node, ast.Assign) and len(node.targets) == 1
                 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)}
    waits = timeouts(function(outer_tree, 'stop_owned'), 'wait', constants)
    grace = max(waits)
    # A full longest cleanup RPC of headroom must remain, while grace itself
    # stays finite and at most twice the independently derived inner budget.
    if not budget + max(stop + containers + per_api) <= grace <= budget * 2:
        raise AssertionError('Outer TERM grace does not safely cover bounded inner cleanup')
    launches = [node for node in ast.walk(outer_tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen']
    if len(launches) != 1 or not isinstance(launches[0].args[0], ast.List):
        raise AssertionError('Ambiguous outer timeout launch')
    arguments = launches[0].args[0].elts
    if sum(isinstance(node, ast.Constant) and node.value == '120m' for node in arguments) != 1:
        raise AssertionError('Original measurement budget changed')
    kill = [node for node in arguments if (isinstance(node, ast.Constant) and
            isinstance(node.value, str) and node.value.startswith('--kill-after=')) or
            (isinstance(node, ast.JoinedStr) and isinstance(node.values[0], ast.Constant)
             and node.values[0].value.startswith('--kill-after='))]
    if len(kill) != 1:
        raise AssertionError('Ambiguous outer kill grace')
    # Only constants or a simple interpolation of reviewed integer constants.
    if any(not isinstance(node, (ast.Constant, ast.JoinedStr, ast.FormattedValue, ast.Name, ast.Load))
           for node in ast.walk(kill[0])):
        raise AssertionError('Unreviewed GNU timeout grace expression')
    actual = eval(compile(ast.Expression(kill[0]), '<kill-grace>', 'eval'), {'__builtins__': {}}, constants)
    if actual != '--kill-after=' + str(grace) + 's':
        raise AssertionError('GNU timeout can preempt the qualifier cleanup grace')
    paired = re.findall(r'timeout --signal=TERM --kill-after=(\d+)s (\d+)m python3 tools/performance/run-paired.py', workflow)
    if paired != [(str(grace), '120')]:
        raise AssertionError('Legacy paired timeout differs from the frozen lane')
    return budget, grace


class CoupledCleanupBudget(unittest.TestCase):
    def test_actual_source_bounds_are_covered_by_both_outer_timeouts(self):
        budget, grace = coupled_budget(INNER, OUTER, WORKFLOW)
        self.assertGreater(grace, budget)

    def test_old_grace_or_growing_inner_work_cannot_silently_pass(self):
        for outer, inner, workflow in (
            (OUTER.replace('CLEANUP_GRACE_SECONDS = 300', 'CLEANUP_GRACE_SECONDS = 60'), INNER, WORKFLOW),
            (OUTER, INNER.replace('text=True, timeout=30, check=True', 'text=True, timeout=150, check=True'), WORKFLOW),
            (OUTER, INNER, WORKFLOW.replace('--kill-after=300s 120m', '--kill-after=60s 120m')),
            (OUTER.replace("'120m'", "'121m'"), INNER, WORKFLOW)):
            with self.assertRaises(AssertionError): coupled_budget(inner, outer, workflow)

    def test_nonpaired_workflow_timeouts_keep_their_original_grace(self):
        nix = re.findall(r'timeout --signal=TERM --kill-after=(\d+)s (100|45)m tools/test-install.sh', WORKFLOW)
        self.assertEqual(nix, [('60', '100'), ('60', '45')])


if __name__ == '__main__':
    unittest.main()
