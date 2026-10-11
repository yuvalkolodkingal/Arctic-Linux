"""Bounded synthetic research controls; no target image, VM or profile admission."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'tools/exact-image-inspection/inspect.py'
S = types.ModuleType('static_wayland_research')
S.__file__ = str(PATH)
exec(compile(PATH.read_bytes(), str(PATH), 'exec'), S.__dict__)


class ResearchBaselineControls(unittest.TestCase):
    def test_exact_baseline_is_separate_from_unchanged_candidate_limit(self):
        spec = importlib.util.spec_from_file_location('original_performance_contract', ROOT/'tools/performance/contract.py')
        contract = importlib.util.module_from_spec(spec); spec.loader.exec_module(contract)
        self.assertEqual({k:S.BASELINE_RESEARCH[k] for k in ('name','bytes','sha256')},
                         {k:contract.BASELINE[k] for k in ('name','bytes','sha256')})
        self.assertEqual(sum(p['bytes'] for p in S.BASELINE_RESEARCH['parts']), contract.BASELINE['bytes'])
        self.assertGreater(contract.BASELINE['bytes'], 2_000_000_000)
        self.assertEqual(S.EXECUTION_FILES, {S.WORKFLOW,'tools/exact-image-inspection/inspect.py','tools/native-functional/fetch-image.py'})
        for key in ('release_acceptance','performance_acceptance','observer_profile_admitted'):
            self.assertIs(S.REPORT[key], False)
        source = PATH.read_text()
        self.assertIn("image['bytes'] < 2_000_000_000", source)
        self.assertIn("fields[:2] == [package, version]", source)
        self.assertIn("'mangowm', '0.17.3'", source)
        self.assertIn("package, '0.20.2'", source)
        self.assertNotIn('BASELINE_RESEARCH', source[source.index('def validate_manifest'):source.index('def activation_guard')])

    def toy(self, fault=None):
        data = [b'first original baseline part', b'second original baseline part']
        pin = copy.deepcopy(S.BASELINE_RESEARCH)
        for part, content in zip(pin['parts'], data):
            part['bytes'] = len(content); part['sha256'] = hashlib.sha256(content).hexdigest()
        pin['bytes'] = sum(map(len,data)); pin['sha256'] = hashlib.sha256(b''.join(data)).hexdigest()
        if fault == 'whole_hash': pin['sha256'] = '0'*64
        def download(argv, **kwargs):
            self.assertEqual(argv[:4], ['gh','release','download','v1.2.0'])
            self.assertEqual(kwargs['timeout'], 900)
            destination = Path(argv[argv.index('--dir')+1])
            patterns = [argv[i+1] for i,value in enumerate(argv) if value == '--pattern']
            self.assertEqual(patterns, [pin['name']+'.part00',pin['name']+'.part01'])
            for i, content in enumerate(data):
                path = destination / (pin['name']+'.part'+str(i).zfill(2))
                if fault == 'symlink' and i == 0:
                    outside = destination.parent/'outside'; outside.write_bytes(content); path.symlink_to(outside)
                elif fault == 'missing' and i == 0: continue
                elif fault == 'part_hash' and i == 0: path.write_bytes(bytes([content[0]^1])+content[1:])
                elif fault == 'part_size' and i == 0: path.write_bytes(content+b'x')
                else: path.write_bytes(content)
            if fault == 'extra': (destination/'unrequested').write_bytes(b'private')
            return 0,''
        return data,pin,download

    def test_original_two_parts_and_complete_hash_are_required_without_network_in_controls(self):
        for fault in (None,'part_hash','part_size','whole_hash','extra','missing','symlink'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary)/'download'; data,pin,download=self.toy(fault)
                with patch.object(S,'BASELINE_RESEARCH',pin),patch.object(S,'capture',side_effect=download):
                    if fault is None:
                        path,proof=S.download_baseline(folder)
                        self.assertEqual(path.read_bytes(), b''.join(data))
                        self.assertEqual({p.name for p in folder.iterdir()},{pin['name']})
                        self.assertFalse(proof['release_acceptance']);self.assertFalse(proof['performance_acceptance'])
                        self.assertEqual([p['original_release_asset_id'] for p in proof['original_parts']], [611480575,611480574])
                    else:
                        with self.assertRaises(ValueError): S.download_baseline(folder)


class WaylandProviderControls(unittest.TestCase):
    def rows(self):
        return ''.join('/usr/lib64/libwayland-'+kind+'.so.0.26.0\t'+'1'*64+'\t'+str(stat.S_IFREG|0o755)+'\n'
                       for kind in ('server','client'))

    def test_each_provider_must_be_unique_regular_exact_rpmdb_file(self):
        inventory='wayland-libs\t1.26.0\tx86_64\n';files=self.rows();needed={'libwayland-server.so.0','libwayland-client.so.0'}
        with patch.object(S,'rpm_query',side_effect=[inventory,files]):
            records=S.wayland_library_records(Path('/proof'),needed)
            self.assertEqual([r['kind'] for r in records],['server','client'])
        for inv,rows in ((inventory*2,files),(inventory.replace('x86_64','aarch64'),files),(inventory,files*2),
            (inventory,files.replace(str(stat.S_IFREG|0o755),str(stat.S_IFLNK|0o755))),
            (inventory,files.replace('1'*64,'x'*64)),(inventory,files.splitlines()[0]+'\n')):
            with self.subTest(inventory=inv,files=rows),patch.object(S,'rpm_query',side_effect=[inv,rows]),self.assertRaises(ValueError):
                S.wayland_library_records(Path('/proof'),needed)
        with patch.object(S,'rpm_query') as query,self.assertRaises(ValueError):
            S.wayland_library_records(Path('/proof'),{'libunknown.so.0'})
        query.assert_not_called()

    def test_filtered_reader_accepts_only_exact_provider_paths_and_never_runs_the_target(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,RUNNER_TEMP=temporary),\
                patch.object(S,'reader_capture',return_value=(0,'')) as reader:
            for path in ('/usr/lib64/libwayland-server.so.0','/usr/lib64/libwayland-client.so.0.26.0'):
                S.extract_selected(Path(temporary)/'rootfs',Path(temporary),path,'wayland-server',{},time.monotonic()+120)
                self.assertEqual(reader.call_args.args[0],'/usr/bin/fsck.erofs')
                self.assertIn('--path='+path,reader.call_args.args[1])
            reader.reset_mock()
            for path in ('/usr/lib64/libwayland-server.so.1','/usr/lib64/libwayland-server.so.0.debug',
                         '/usr/lib64/libwayland-server.so.0/../../etc/passwd','/usr/lib64/private.so'):
                with self.subTest(path=path),self.assertRaises(ValueError):
                    S.extract_selected(Path(temporary)/'rootfs',Path(temporary),path,'wayland-server',{},time.monotonic()+120)
            reader.assert_not_called()

    def test_dynamic_needed_inventory_does_not_establish_live_resolution(self):
        text=' 0x0001 (NEEDED) Shared library: [libwayland-server.so.0]\n 0x0001 (NEEDED) Shared library: [libwayland-client.so.0]\n'
        with patch.object(S,'capture',return_value=(0,text)):
            self.assertEqual(S.dynamic_dependencies(Path('data-only-elf')),['libwayland-server.so.0','libwayland-client.so.0'])
        for wrong in ('',text+text,text.replace('libwayland-client.so.0','../../private.so')):
            with self.subTest(text=wrong),patch.object(S,'capture',return_value=(0,wrong)),self.assertRaises(ValueError):
                S.dynamic_dependencies(Path('data-only-elf'))

    def test_baseline_branch_keeps_magic_gate_without_assuming_candidate_versions(self):
        # This tiny synthetic EROFS envelope exercises dispatch only. The RPMDB
        # and selected Mango are fixtures, not image or ABI qualification.
        for scope, magic in (('baseline', True), ('candidate', True), ('baseline', False)):
            with self.subTest(scope=scope, magic=magic), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);iso=root/'fixture.iso';iso.write_bytes(b'fixture')
                def capture(argv,**kwargs):
                    if '-find' in argv:return 0,'/LiveOS/squashfs.img\n'
                    data=bytearray(2048)
                    if magic:data[1024:1028]=b'\xe2\xe1\xf5\xe0'
                    Path(argv[-1]).write_bytes(data);return 0,''
                def extract(_fs,selected,path,name,_proof,_deadline):
                    if name=='rpmdb':
                        database=selected/name;database.mkdir();(database/'rpmdb.sqlite').write_bytes(b'fixture')
                    else:(selected/name).write_bytes(b'synthetic Mango')
                with patch.object(S,'capture',side_effect=capture),patch.object(S,'extract_selected',side_effect=extract),\
                        patch.object(S,'collect_wayland') as collect,patch.object(S,'library_record',side_effect=ValueError('candidate version gate')) as required:
                    if scope=='baseline' and magic:
                        S.inspect_iso(iso,{},root,scope=scope)
                        collect.assert_called_once();self.assertEqual(collect.call_args.args[-1],'baseline');required.assert_not_called()
                    else:
                        with self.assertRaisesRegex(ValueError,'candidate version gate' if magic else 'EROFS'):
                            S.inspect_iso(iso,{},root,scope=scope)
                        collect.assert_not_called()

    @unittest.skipUnless(all(shutil.which(name) for name in ('gcc','readelf','objdump')), 'Native static ELF tools needed')
    def test_real_library_bytes_symbol_rpm_digest_and_both_output_scopes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'fixture.c';binary=root/'provider.so';selected=root/'selected';selected.mkdir()
            source.write_text('struct list { struct list *prev, *next; };\nvoid wl_list_insert(struct list *a,struct list *b) { b->prev=a;b->next=a->next;a->next->prev=b;a->next=b; }\n')
            subprocess.run(['gcc','-O2','-fPIC','-shared','-o',str(binary),str(source)],check=True)
            digest=S.sha(binary);rows=''.join('/usr/lib64/libwayland-'+kind+'.so.0.26.0\t'+digest+'\t'+str(stat.S_IFREG|0o755)+'\n'for kind in ('server','client'))
            def query(_root,args):
                if args[0]=='-qa':return 'wayland-libs\t1.26.0\tx86_64\n'
                if 'FILEDIGESTALGO' in args[-1]:return 'wayland-libs\t1.26.0\t1.fc44\tx86_64\t8\n'
                return rows
            def extract(_fs,out,_source,destination,_proof,_deadline): shutil.copyfile(binary,out/destination)
            for scope in ('candidate','baseline'):
                output=root/('evidence-'+scope);output.mkdir();proof={'filesystem':{}}
                with patch.object(S,'OUTPUT',output),patch.object(S,'ALLOWED',set()),\
                        patch.object(S,'dynamic_dependencies',return_value=['libwayland-server.so.0']),\
                        patch.object(S,'rpm_query',side_effect=query),patch.object(S,'extract_selected',side_effect=extract):
                    S.collect_wayland(root/'filesystem',selected,root,binary,proof,time.monotonic()+120,scope)
                self.assertEqual(len(proof['wayland_providers']),2)
                for provider in proof['wayland_providers']:
                    self.assertTrue(provider['rpm']['file_digest_verified']);self.assertFalse(provider['profile_admitted'])
                    self.assertEqual((output/(scope+'/wayland-'+provider['kind']+'.elf')).read_bytes(),binary.read_bytes())
                    self.assertGreater(provider['wl_list_insert_symbol']['bytes'],0)
                    self.assertIn('<wl_list_insert>:',(output/(scope+'/wayland-'+provider['kind']+'-disassembly.txt')).read_text())
            with patch.object(S,'dynamic_dependencies',return_value=['libunknown.so.0']),patch.object(S,'rpm_query') as query,\
                    self.assertRaisesRegex(ValueError,'server dependency'):
                S.collect_wayland(root/'filesystem',selected,root,binary,{},time.monotonic()+120,'candidate')
            query.assert_not_called()


if __name__=='__main__':unittest.main()
