"""The recorded cache toolchain must be the one actually used for the build."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BuildImageIdentityTest(unittest.TestCase):
    def run_build(self, identity):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'source'
            (source / 'packaging').mkdir(parents=True)
            for name, version in [('arctic-linux', '1.2.0'), ('mangowm', '0.13.2')]:
                (source / 'packaging' / (name + '.spec')).write_text('Version: ' + version + '\n')
            # No network/build mutation: the fake engine records the actual final
            # docker invocation. Its tag changes after inspection, so using the
            # original tag would execute a different toolchain than the cache key.
            engine = base / 'mock-engine'
            engine.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] == ['image', 'inspect']:
    if '--format' in args:
        print(os.environ['TEST_IMAGE_ID'])
        open(os.environ['TEST_TAG_STATE'], 'w').write('sha256:' + 'b' * 64)
elif args and args[0] == 'run':
    json.dump(args, open(os.environ['TEST_ENGINE_LOG'], 'w'))
    # Simulate the now-repointed tag resolving differently at run time.
    image = args[args.index('bash') - 1]
    actual = open(os.environ['TEST_TAG_STATE']).read() if image == 'fedora:44' else image
    open(os.environ['TEST_ACTUAL_IMAGE'], 'w').write(actual)
else:
    raise SystemExit('Unexpected engine invocation: ' + repr(args))
''')
            engine.chmod(0o755)
            env = dict(os.environ, CONTAINER_ENGINE=str(engine), ARCTIC_FEDORA_IMAGE='fedora:44',
                       ARCTIC_CA_BUNDLE='', ARCTIC_REQUIRE_GPG_KEY='0',
                       TEST_IMAGE_ID=identity, TEST_TAG_STATE=str(base / 'tag'),
                       TEST_ENGINE_LOG=str(base / 'invocation.json'),
                       TEST_ACTUAL_IMAGE=str(base / 'actual-image'))
            env.pop('ARCTIC_GPG_PUBLIC_KEY', None)
            result = subprocess.run([str(ROOT / 'tools/build-rpms.sh'), '--only', 'arctic',
                                     '--src', str(source), '--out', str(base / 'output'),
                                     '--no-cache', '--release-suffix', 'none'],
                                    env=env, text=True, capture_output=True)
            args = json.loads((base / 'invocation.json').read_text()) if (base / 'invocation.json').exists() else None
            actual = (base / 'actual-image').read_text() if (base / 'actual-image').exists() else None
            return result, args, actual

    def test_repointed_tag_cannot_change_resolved_build_toolchain(self):
        identity = 'sha256:' + 'a' * 64
        result, args, actual = self.run_build(identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(actual, identity)
        self.assertIn('BUILD_IMAGE_ID=' + identity, args)
        self.assertIn('BUILD_CACHE_ENABLED=0', args)

    def test_podman_bare_immutable_identity_is_supported(self):
        identity = 'a' * 64
        result, args, actual = self.run_build(identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(actual, identity)
        self.assertIn('BUILD_IMAGE_ID=' + identity, args)

    def test_unresolved_identity_fails_before_build(self):
        result, args, actual = self.run_build('fedora:44')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(args)
        self.assertIsNone(actual)
