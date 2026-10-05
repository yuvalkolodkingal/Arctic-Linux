#!/usr/bin/env python3
"""Exercise the actual AppsService timers across a long-running background job.

Needs Quickshell/Qt, no compositor, network or package transaction. Only the
five-minute timeout is shortened in a temporary copy, keeping the real handlers.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


QML = '''import QtQuick
import Quickshell
import "service" as Arctic

Scope {
    id: probe
    Component.onCompleted: {
        Arctic.AppsService.fedoraPackages = [{ id: 'retained-catalog' }];
        Arctic.AppsService.indexLoaded = true;
        Arctic.AppsService.watching = true;
        Arctic.AppsService.jobs = [{ id: 'long-job', phase: 'running', kind: 'install', ids: [], name: '' }];
        Arctic.AppsService.watching = false;
    }
    Timer {
        interval: 180; running: true
        onTriggered: {
            if (Arctic.AppsService.fedoraPackages.length !== 1) {
                console.warn('EVICTION_FAIL: dropped a catalog while its job was running');
                Qt.quit(); return;
            }
            Arctic.AppsService.jobs = [];
            released.start();
        }
    }
    Timer {
        id: released; interval: 180
        onTriggered: {
            if (Arctic.AppsService.fedoraPackages.length !== 0 || Arctic.AppsService.indexLoaded) {
                console.warn('EVICTION_FAIL: retained the catalog after its job finished');
            } else {
                console.warn('EVICTION_PASS');
            }
            Qt.quit();
        }
    }
    Timer { interval: 2000; running: true; onTriggered: { console.warn('EVICTION_FAIL: timed out'); Qt.quit(); } }
}
'''


@unittest.skipUnless(shutil.which('quickshell'), 'Quickshell is required for the real QML timer test')
class CatalogEviction(unittest.TestCase):
    def test_job_outlasts_initial_eviction_timeout(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='arctic-catalog-test-') as directory:
            root = Path(directory)
            shutil.copytree(source, root/'service')
            service = root/'service/AppsService.qml'
            text = service.read_text()
            self.assertEqual(text.count('interval: 5 * 60 * 1000'), 1)
            service.write_text(text.replace('interval: 5 * 60 * 1000', 'interval: 60'))
            (root/'shell.qml').write_text(QML)
            runtime = root/'runtime'
            runtime.mkdir(mode=0o700)
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_RUNTIME_DIR=str(runtime),
                       ARCTIC_FORCE_LIVE='1')
            result = subprocess.run(['quickshell', '-p', str(root)], env=env,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=20, check=False)
            self.assertIn('EVICTION_PASS', result.stdout, result.stdout)
            self.assertNotIn('EVICTION_FAIL', result.stdout, result.stdout)


if __name__ == '__main__':
    unittest.main()
