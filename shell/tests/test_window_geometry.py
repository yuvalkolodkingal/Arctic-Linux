import importlib.util
from pathlib import Path
import unittest
import json
import os
import subprocess
import sys
import tempfile

spec = importlib.util.spec_from_file_location('window_geometry', Path(__file__).parents[1]/'scripts/window_geometry.py')
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


class WindowGeometryTests(unittest.TestCase):
    def setUp(self):
        self.monitor = dict(name='eDP-1', x=1920, y=-200, width=1280, height=720,
                            scale=1.5, active_tags=[2], hide_clients=0)
        self.client = dict(id=7, monitor='eDP-1', tags=[2], is_visible=True,
                           x=2000, y=-100, width=500, height=400)

    def result(self, **changes):
        return geometry.normalize([self.monitor], [dict(self.client, **changes)])['windows']

    def test_global_logical_rectangles_not_scaled_twice(self):
        data = geometry.normalize([self.monitor], [self.client])
        self.assertEqual(data['windows'], [dict(x=2000, y=-100, width=500, height=400)])
        self.assertEqual(data['monitors'][0]['width'], 1280)

    def test_hidden_minimized_swallowed_and_inactive_workspace_excluded(self):
        for changes in [dict(is_visible=False), dict(is_minimized=True),
                        dict(is_swallowedby=True), dict(tags=[1]), dict(monitor='removed')]:
            with self.subTest(changes=changes):
                self.assertEqual(self.result(**changes), [])

    def test_sticky_and_overlay_still_require_visibility(self):
        for key in ('is_global', 'is_unglobal', 'is_overlay'):
            self.assertEqual(len(self.result(tags=[1], **{key: True})), 1)
            self.assertEqual(self.result(tags=[1], is_visible=False, **{key: True}), [])

    def test_hidden_scratchpad_excluded_but_visible_scratchpad_included(self):
        self.assertEqual(self.result(is_scratchpad=True, is_visible=False), [])
        self.assertEqual(len(self.result(is_scratchpad=True)), 1)

    def test_fullscreen_uses_entire_output_even_during_geometry_transition(self):
        self.assertEqual(self.result(is_fullscreen=True), [dict(x=1920, y=-200, width=1280, height=720)])

    def test_no_clients_and_show_desktop_are_clear(self):
        self.assertEqual(geometry.normalize([self.monitor], [])['windows'], [])
        self.monitor['hide_clients'] = 1
        self.assertEqual(self.result(), [])

    def test_no_app_id_filter_real_apps_named_quickshell_count(self):
        self.assertEqual(len(self.result(appid='quickshell')), 1)

    def test_client_rectangles_crossing_outputs_are_not_clipped(self):
        self.assertEqual(self.result(x=1800)[0]['x'], 1800)

    def test_invalid_rectangle_fails_visible_instead_of_guessing(self):
        for value in [float('nan'), float('inf'), True, '500']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.result(width=value)
        with self.assertRaises(ValueError):
            self.result(height=0)

    def test_order_and_titles_do_not_emit_geometry_changes(self):
        other = dict(self.client, x=2600)
        first = geometry.normalize([self.monitor], [self.client, other])
        second = geometry.normalize([self.monitor], [dict(other,title='changed',is_focused=True), self.client])
        self.assertEqual(first, second)

    def test_event_stream_coalesces_without_starving_and_disconnect_reveals(self):
        with tempfile.TemporaryDirectory() as directory:
            fake=Path(directory)/'mmsg'
            fake.write_text('''#!/usr/bin/env python3
import json,sys,time
if sys.argv[1]=='get':
 print(json.dumps({'client_geometry_events':True}))
elif sys.argv[-1]=='all-monitors':
 print(json.dumps({'monitors':[{'name':'test','x':0,'y':0,'width':800,'height':600,'active_tags':[1]}]}),flush=True)
 time.sleep(2)
else:
 for x in range(60):
  print(json.dumps({'clients':[{'monitor':'test','tags':[1],'is_visible':True,'x':x,'y':0,'width':100,'height':100}]}),flush=True)
  time.sleep(.01)
''')
            fake.chmod(0o755)
            env=dict(os.environ,PATH=directory+os.pathsep+os.environ.get('PATH',''),MANGO_INSTANCE_SIGNATURE='fixture')
            run=subprocess.run([sys.executable,str(Path(geometry.__file__))],env=env,capture_output=True,text=True,timeout=5)
            rows=[json.loads(line) for line in run.stdout.splitlines()]
            ready=[row for row in rows if row['ready']]
            self.assertGreater(len(ready),3)  # updates arrive during continuous movement
            self.assertLess(len(ready),30)   # bursts are coalesced instead of one output per event
            self.assertFalse(rows[-1]['ready'])
            self.assertEqual(rows[-1]['windows'],[])
            self.assertEqual(run.returncode,1)

    def test_unsupported_compositor_fails_visible(self):
        env=dict(os.environ)
        env.pop('MANGO_INSTANCE_SIGNATURE',None)
        run=subprocess.run([sys.executable,str(Path(geometry.__file__))],env=env,capture_output=True,text=True,timeout=3)
        self.assertEqual(run.returncode,2)
        self.assertFalse(json.loads(run.stdout)['ready'])

    def test_old_mango_fails_visible_without_starting_geometry_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            fake=Path(directory)/'mmsg'
            fake.write_text('#!/bin/sh\necho \'{"error":"unknown command"}\'\n')
            fake.chmod(0o755)
            env=dict(os.environ,PATH=directory+os.pathsep+os.environ.get('PATH',''),MANGO_INSTANCE_SIGNATURE='old')
            run=subprocess.run([sys.executable,str(Path(geometry.__file__))],env=env,capture_output=True,text=True,timeout=3)
            self.assertEqual(run.returncode,2)
            self.assertFalse(json.loads(run.stdout)['ready'])


if __name__ == '__main__':
    unittest.main()
