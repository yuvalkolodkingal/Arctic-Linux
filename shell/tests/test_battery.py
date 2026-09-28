"""Tests for scripts/battery.py (the battery menu's UPower details): the parts without D-Bus.

Run: python3 -m unittest discover -s shell/tests -p 'test_battery.py'
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('battery', SCRIPTS / 'battery.py')
battery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(battery)


class Conf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_percentages_defaults_and_drop_ins(self):
        main = self.write('UPower.conf', '[UPower]\n# comment\nPercentageLow=15\nPercentageAction=3\n[Other]\nPercentageLow=99\n')
        self.write('UPower.conf.d/10-arctic.conf', '[UPower]\nPercentageLow=25.0\n')
        got = battery.percentages(battery.conf_chain(str(main)))
        self.assertEqual(got, {'percentage_low': 25, 'percentage_critical': 5, 'percentage_action': 3})
        self.assertEqual(battery.percentages([str(self.root / 'missing.conf')]),
                         {'percentage_low': 20, 'percentage_critical': 5, 'percentage_action': 2})
        bad = self.write('bad.conf', '[UPower]\nPercentageLow=lots\n')
        self.assertEqual(battery.percentages([str(bad)])['percentage_low'], 20)

    def test_critical_action(self):
        yes = lambda name: 'yes'
        self.assertEqual(battery.action_verb('PowerOff', [], yes), 'shut down')
        self.assertEqual(battery.action_verb('Hibernate', [], yes), 'hibernate')
        self.assertEqual(battery.action_verb('HybridSleep', [], yes), 'suspend')
        self.assertEqual(battery.action_verb('Ignore', [], yes), 'nothing')
        # Sleep/Auto: the default SleepOperation, where suspend-then-hibernate isn't possible (no swap).
        can = {'SuspendThenHibernate': 'no', 'Suspend': 'yes', 'Hibernate': 'no'}.get
        self.assertEqual(battery.action_verb('Sleep', [], can), 'suspend')
        conf = self.write('sleep.conf', '[Sleep]\nSleepOperation=hibernate suspend\n')
        can2 = {'Hibernate': 'yes', 'Suspend': 'yes'}.get
        self.assertEqual(battery.action_verb('Auto', battery.conf_chain(str(conf)), can2), 'hibernate')
        self.assertEqual(battery.action_verb('Sleep', [], lambda name: 'no'), 'suspend')

    def test_usage(self):
        self.assertEqual(battery.main(['limit', 'maybe']), 2)
        self.assertEqual(battery.main([]), 2)


if __name__ == '__main__':
    unittest.main()
