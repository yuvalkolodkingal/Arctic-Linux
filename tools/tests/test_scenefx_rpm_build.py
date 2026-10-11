"""Exercise the real builder's source-integrity and dependency-order admission.

The fake engine records shell/argv only. A disclosed small synthetic source
replaces the fixture spec digest; no RPM build, Fedora download or VM occurs.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SceneFxBuildAdmission(unittest.TestCase):
    def build(self, mode, cached=b'fixture source', downloaded=b'fixture source'):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'source'
            (source / 'packaging/scenefx').mkdir(parents=True)
            for name in ('arctic-linux', 'mangowm', 'scenefx'):
                shutil.copyfile(ROOT / f'packaging/{name}.spec', source / f'packaging/{name}.spec')
            spec = source / 'packaging/scenefx.spec'
            spec.write_text(spec.read_text().replace(
                '0fa8ecca0e310f813efd052624c5ed7d9153d6a0fdead5cc957d34c07f9a86c6',
                hashlib.sha256(b'fixture source').hexdigest()))
            shutil.copyfile(ROOT / 'packaging/scenefx/test_safe_completion.py',
                            source / 'packaging/scenefx/test_safe_completion.py')
            # Avoid unrelated Mango/font network calls in the focused fixture.
            output = base / 'out'
            (output / 'sources').mkdir(parents=True)
            if cached is not None:
                (output / 'sources/scenefx-0.5.tar.gz').write_bytes(cached)
            (output / 'sources/mango-0.17.3.tar.gz').write_bytes(b'mango fixture')
            (output / 'sources/NerdFontsSymbolsOnly-3.4.0.tar.xz').write_bytes(b'font fixture')
            arctic = source / 'packaging/arctic-linux.spec'
            # Font fetching is separate; disable that fixture declaration only.
            arctic.write_text('\n'.join(line for line in arctic.read_text().splitlines()
                                        if not line.startswith(('%global nerd_version ', '%global nerd_sha256 '))) + '\n')
            engine = base / 'engine'
            engine.write_text('''#!/usr/bin/env python3
import json,os,sys
args=sys.argv[1:]
if args[:2]==['image','inspect']:
    if '--format' in args: print('sha256:'+'a'*64)
elif args and args[0]=='run':
    json.dump(args,open(os.environ['SCENE_ENGINE_LOG'],'w'))
else: raise SystemExit(2)
''')
            engine.chmod(0o755)
            curl = base / 'curl'
            curl.write_text('''#!/usr/bin/env python3
import json,os,sys,pathlib
args=sys.argv[1:]
json.dump(args,open(os.environ['SCENE_CURL_LOG'],'w'))
pathlib.Path(args[args.index('-o')+1]).write_bytes(bytes.fromhex(os.environ['SCENE_DOWNLOAD_HEX']))
''')
            curl.chmod(0o755)
            env = dict(os.environ, CONTAINER_ENGINE=str(engine), ARCTIC_REQUIRE_GPG_KEY='0',
                       PATH=str(base) + ':' + os.environ['PATH'],
                       SCENE_ENGINE_LOG=str(base / 'engine.json'), SCENE_CURL_LOG=str(base / 'curl.json'),
                       SCENE_DOWNLOAD_HEX=downloaded.hex())
            env.pop('ARCTIC_GPG_PUBLIC_KEY', None)
            argv = [str(ROOT / 'tools/build-rpms.sh'), '--src', str(source), '--out', str(output),
                    '--no-cache', '--release-suffix', 'none']
            if mode:
                argv += ['--only', mode]
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            engine_args = json.loads((base / 'engine.json').read_text()) if (base / 'engine.json').exists() else None
            curl_args = json.loads((base / 'curl.json').read_text()) if (base / 'curl.json').exists() else None
            return result, engine_args, curl_args, (output / 'sources/scenefx-0.5.tar.gz.part').exists()

    def test_default_and_mango_build_order_include_the_patched_dependency(self):
        for mode, expected in ((None, 'SPECS=scenefx mangowm arctic-linux'),
                               ('mangowm', 'SPECS=scenefx mangowm'), ('scenefx', 'SPECS=scenefx')):
            with self.subTest(mode=mode):
                result, args, _, _ = self.build(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, args)
                inner = args[-1]
                self.assertLess(inner.index('install_scenefx()'), inner.index('for spec in $SPECS; do'))
                self.assertIn('[[ "$spec" != scenefx ]] || install_scenefx /root/rpmbuild/RPMS/x86_64', inner)
                self.assertIn('rpm --root "$transaction_root" --install --test --nodeps /out/repo/*.rpm', inner)

    def test_corrupt_cached_source_rejects_before_the_engine(self):
        result, args, curl, _ = self.build('scenefx', cached=b'tampered fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(args)
        self.assertIsNone(curl)

    def test_corrupt_download_is_rejected_and_partial_source_removed(self):
        result, args, curl, partial = self.build('scenefx', cached=None, downloaded=b'tampered download')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(args)
        self.assertIsNotNone(curl)
        self.assertFalse(partial)

    def test_valid_download_admits_only_the_exact_pinned_scene_source(self):
        result, args, curl, partial = self.build('scenefx', cached=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SPECS=scenefx', args)
        self.assertEqual(curl[-1], 'https://github.com/wlrfx/scenefx/archive/refs/tags/0.5/scenefx-0.5.tar.gz')
        self.assertFalse(partial)


class InstalledDependencyControls(unittest.TestCase):
    """Run exact shell functions/caller with finite command responses, no RPMs.

    These controls prove failures propagate to the real builder caller. Actual
    RPM ownership, capability, loader resolution and signatures remain CI gates.
    """
    def run_install(self, mode='required', fault=None, scene=False):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            directory = base / 'rpms'
            directory.mkdir()
            for name in ('mangowm-0.17.3-1.x86_64.rpm', 'scenefx-0.5-2.x86_64.rpm',
                         'scenefx-devel-0.5-2.x86_64.rpm'):
                (directory / name).write_bytes(b'explicit command fixture, not a real RPM')
            (base / 'logs').mkdir()
            script = (ROOT / 'tools/build-rpms.sh').read_text()
            begin = script.index('install_mango() {')
            end = script.index('\nif [[ " $SPECS "', begin)
            functions = script[begin:end].replace('/out/logs/', str(base / 'logs') + '/')
            prefix = '''set -euo pipefail
dnf_args=()
dnf() { printf 'dnf\\n' >> "$CONTROL_LOG"; [[ "$FAULT" != install ]]; }
rpm() {
  printf 'rpm:%s\\n' "$1" >> "$CONTROL_LOG"
  local name file version release arch=x86_64
  case "$1" in
    -qp) file="${!#}"
         case "$file" in *scenefx-devel-*) name=scenefx-devel ;; *scenefx-*) name=scenefx ;; *) name=mangowm ;; esac ;;
    -qf) [[ "$FAULT" != owner-error ]] || return 1
         if [[ "$2" == /usr/bin/mango ]]; then name=mangowm; else name=scenefx; fi ;;
    -q) if [[ "$2" == --whatprovides ]]; then
          [[ "$FAULT" != provider-error ]] || return 1; name=scenefx
        else [[ "$FAULT" != installed-error ]] || return 1; name="$2"; fi ;;
    -V) [[ "$FAULT" != verify && !( "$FAULT" == mango-verify && "$2" == mangowm ) ]]; return ;;
    *) return 1 ;;
  esac
  if [[ "$name" == mangowm ]]; then version=0.17.3; release=1.fc44; else version=0.5; release=2.fc44; fi
  if [[ "$*" == *FILEDIGESTALGO* ]]; then
    [[ !( "$1" == -qp && "$FAULT" == local-files-error ) && !( "$1" == -q && "$FAULT" == installed-files-error ) ]] || return 1
    local digest=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa algo=8
    [[ "$FAULT" != algo ]] || algo=7
    if [[ "$1" == -q && "$FAULT" == "payload-$name" ]]; then digest=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb; fi
    printf '%s\\n/usr/lib/fixture-%s\\t%s\\t\\t33188\\n' "$algo" "$name" "$digest"
    return
  fi
  if [[ "$1" == -q && "$2" != --whatprovides && "$FAULT" == "$name-noop" ]]; then release=3.fc44; fi
  if [[ "$1" == -qf ]]; then
    case "$FAULT" in owner) name=foreign ;; owner-release) release=3.fc44 ;; owner-arch) arch=i686 ;; esac
  fi
  if [[ "$1" == -q && "$2" == --whatprovides ]]; then
    case "$FAULT" in provider) name=foreign ;; provider-release) release=3.fc44 ;; provider-arch) arch=i686 ;; esac
  fi
  [[ "$FAULT" != local-and-installed-arch ]] || arch=i686
  if [[ "$*" == *'%{NAME}-%{VERSION}'* ]]; then
    printf '%s-%s\\n' "$name" "$version"
    return
  fi
  printf '%s-0:%s-%s.%s\\n' "$name" "$version" "$release" "$arch"
  if [[ "$1" == -q && "$2" == --whatprovides && "$FAULT" == provider-duplicate ]]; then
    printf '%s-0:%s-%s.%s\\n' "$name" "$version" "$release" "$arch"
  fi
}
readelf() { [[ "$FAULT" != needed ]] || return 1; if [[ "$FAULT" == needed-absent ]]; then printf ' (NEEDED) Shared library: [libforeign.so]\\n'; else printf ' (NEEDED) Shared library: [libscenefx-0.5.so]\\n'; fi; }
ldd() { if [[ "$FAULT" == link ]]; then printf 'libscenefx-0.5.so => not found\\n'; else printf 'libscenefx-0.5.so => /usr/lib64/libscenefx-0.5.so (0x1)\\n'; fi; }
readlink() { [[ "$2" == /usr/lib64/libscenefx-0.5.so ]] || return 1; printf '/usr/lib64/libscenefx-0.5.so\\n'; }
'''
            # Use the actual required production OR-list caller, so an erased
            # failure cannot hide behind Bash's conditional errexit semantics.
            call = ('install_scenefx "$CONTROL_RPMS"' if scene else
                    'spec=mangowm; [[ "$spec" != mangowm ]] || install_mango "$CONTROL_RPMS" required'
                    if mode == 'required' else 'install_mango "$CONTROL_RPMS"')
            env = dict(os.environ, CONTROL_LOG=str(base / 'commands'), CONTROL_RPMS=str(directory),
                       FAULT=fault or '')
            result = subprocess.run(['bash'], input=prefix + functions + '\n' + call + '\nprintf "ADMITTED\\n"\n',
                                    env=env, text=True, capture_output=True, timeout=5)
            commands = (base / 'commands').read_text() if (base / 'commands').exists() else ''
            return result, commands

    def test_required_actual_caller_rejects_install_failure_while_optional_keeps_old_behavior(self):
        required, commands = self.run_install(fault='install')
        self.assertNotEqual(required.returncode, 0)
        self.assertNotIn('ADMITTED', required.stdout)
        self.assertNotIn('rpm:', commands)
        optional, _ = self.run_install(mode='optional', fault='install')
        self.assertEqual(optional.returncode, 0)
        self.assertIn('note: could not install', optional.stdout)

    def test_required_install_rejects_missing_wrong_or_unverified_scene_capability_and_link(self):
        for fault in ('owner-error', 'provider-error', 'owner', 'provider', 'verify', 'mango-verify',
                      'needed', 'needed-absent', 'link'):
            with self.subTest(fault=fault):
                result, _ = self.run_install(fault=fault)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('ADMITTED', result.stdout)

    def test_scene_runtime_devel_install_itself_rejects_bad_ownership_or_capability(self):
        for fault in ('install', 'owner-error', 'provider-error', 'owner', 'provider', 'verify'):
            with self.subTest(fault=fault):
                result, _ = self.run_install(fault=fault, scene=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('ADMITTED', result.stdout)

    def test_full_native_identity_rejects_provider_aliases_and_install_noops(self):
        for fault, scene in (('provider-release', False), ('provider-arch', False),
                             ('provider-duplicate', False), ('owner-release', False),
                             ('owner-arch', False), ('local-and-installed-arch', False),
                             ('installed-error', False), ('mangowm-noop', False),
                             ('scenefx-noop', True), ('scenefx-devel-noop', True)):
            with self.subTest(fault=fault, scene=scene):
                result, _ = self.run_install(fault=fault, scene=scene)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('ADMITTED', result.stdout)

    def test_same_identity_different_local_payload_or_digest_algorithm_rejects(self):
        for fault, scene in (('payload-mangowm', False), ('payload-scenefx', True),
                             ('payload-scenefx-devel', True), ('algo', False),
                             ('local-files-error', False), ('installed-files-error', False)):
            with self.subTest(fault=fault, scene=scene):
                result, _ = self.run_install(fault=fault, scene=scene)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('ADMITTED', result.stdout)

    def test_required_scene_and_mango_commands_admit_complete_exact_fixture_responses(self):
        for scene in (False, True):
            with self.subTest(scene=scene):
                result, commands = self.run_install(scene=scene)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('ADMITTED', result.stdout)
                self.assertIn('rpm:-qf', commands)
                self.assertIn('rpm:-q', commands)
                self.assertIn('rpm:-V', commands)


if __name__ == '__main__':
    unittest.main()
