#!/usr/bin/env python3
"""Exact retained public ELF plus owned files; runtime providers explicitly virtual."""
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
CACHE=Path('/tmp/arctic-epiphany-static-symbols-20261011')
RAW=(CACHE/'epiphany-runtime-libephymain.elf').read_bytes()
LAUNCHER=CACHE/'epiphany-runtime-member-0000'
PROFILE=types.ModuleType('main_library_source');PROFILE.__file__=str(HERE/'profile.py')
exec(compile((HERE/'profile.py').read_bytes(),PROFILE.__file__,'exec'),PROFILE.__dict__)
INVERSE=json.loads((HERE/'source-inverse.json').read_bytes())
ORIGINAL=subprocess.check_output(['git','show',INVERSE['original_head']+':'+INVERSE['original_path']],cwd=HERE)
OLD=types.ModuleType('old');exec(compile(ORIGINAL,'old.py','exec'),OLD.__dict__)
CONTEXT=json.loads((HERE/'execution-context.json').read_bytes())

@contextmanager
def defer():
    yield

class VirtualPath:
    """Fixed virtual RPM and procfs names are backed by our owned real files."""
    root=None;other=None
    def __init__(self,value):self.value=str(value)
    def __str__(self):return self.value
    def __eq__(self,other):return self.value==str(other)
    def __truediv__(self,other):return VirtualPath(self.value+'/'+str(other))
    @property
    def parent(self):return VirtualPath(str(Path(self.value).parent))
    @property
    def name(self):return Path(self.value).name
    def resolve(self,strict=False):return self
    def is_file(self):return True
    def is_symlink(self):return False
    def actual(self):
        if self.value==PROFILE.EPHY_MAIN['path']:return CACHE/'epiphany-runtime-libephymain.elf'
        if self.value=='/usr/bin/epiphany':return LAUNCHER
        if self.value.endswith('/maps'):return self.root/'maps'
        return self.other
    def stat(self):return self.actual().stat()
    def read_bytes(self):return self.actual().read_bytes()
    def open(self,*args,**kw):return self.actual().open(*args,**kw)

class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='arctic-main-library-source-')
        cls.root=Path(cls.tmp.name);VirtualPath.root=cls.root
        source=cls.root/'provider.c';names={s for lib,s,_ in PROFILE.PHASES.values() if lib not in ('browser','ephymain')}
        source.write_text('\n'.join('void '+n+'(void) {}' for n in sorted(names)))
        VirtualPath.other=cls.root/'provider.so'
        subprocess.run(['cc','-shared','-fPIC',str(source),'-o',str(VirtualPath.other)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_complete_inverse_all_unchanged_functions_constants_actions(self):
        raw=(HERE/'profile.py').read_text()
        for entry in reversed(INVERSE['replacements']):
            self.assertEqual(raw.count(entry['new']),1)
            raw=raw.replace(entry['new'],entry['old'])
        self.assertEqual(raw.encode(),ORIGINAL)
        self.assertEqual(hashlib.sha256(ORIGINAL).hexdigest(),INVERSE['original_sha256'])
        changed={'inventory','launch','finite_failure_record'}
        old={n.name:ast.dump(n) for n in ast.parse(ORIGINAL).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        new={n.name:ast.dump(n) for n in ast.parse((HERE/'profile.py').read_bytes()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        for name in old:
            if name not in changed:self.assertEqual(old[name],new[name],name)
        self.assertEqual((PROFILE.MAX_EVENTS,PROFILE.MAX_LINE,PROFILE.MAX_ELF,PROFILE.GATE),
                         (OLD.MAX_EVENTS,OLD.MAX_LINE,OLD.MAX_ELF,OLD.GATE))

    def test_disabled_context_and_whole_module_source_pins(self):
        self.assertIs(CONTEXT['ready'],False);self.assertIsNone(CONTEXT['image'])
        with self.assertRaisesRegex(RuntimeError,'^context_disabled_or_source$'):PROFILE.validate_context(CONTEXT)
        for filename,sha in CONTEXT['modules'].items():
            raw=subprocess.check_output(['git','show',INVERSE['original_head']+':tools/performance/'+filename],cwd=HERE)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),sha)

    def test_actual_signed_library_dynamic_and_exact_static_entries(self):
        proof=json.loads((CACHE/'exact-public-ELF-debug-source-joins.json').read_bytes())
        self.assertEqual(PROFILE.elf_build_id(RAW),proof['implementation_library_join']['BuildID'])
        symbols=PROFILE.implementation_symbols(RAW)
        self.assertEqual(len(symbols),11)
        for symbol,offset in symbols.items():
            self.assertEqual(offset,proof['resolved_functions'][symbol]['file_offset'])
            self.assertTrue(all(r is None for l,s,r in PROFILE.PHASES.values() if s==symbol))
        self.assertTrue(all(PROFILE.exported_offset(LAUNCHER.read_bytes(),s) is None
                            for s in symbols if s not in PROFILE.EPHY_STATIC))

    def test_modified_whole_elf_and_wrong_buildid_deny_before_resolver(self):
        altered=bytearray(RAW);altered[-1]^=1
        with patch.object(PROFILE,'exported_offset') as resolver:
            for raw in (bytes(altered),RAW[:-1]):
                with self.assertRaisesRegex(RuntimeError,'^implementation_whole_elf$'):PROFILE.implementation_symbols(raw)
            with patch.object(PROFILE,'elf_build_id',return_value='0'*40):
                with self.assertRaisesRegex(RuntimeError,'^implementation_whole_elf$'):PROFILE.implementation_symbols(RAW)
            self.assertEqual(resolver.call_count,0)

    def test_malformed_and_ambiguous_buildid_notes_deny(self):
        import struct
        for raw in (b'',b'\x7fELF\x02\x01'+bytes(58)):
            with self.assertRaises(RuntimeError):PROFILE.elf_build_id(raw)
        header=struct.unpack_from('<16sHHIQQQIHHHHHH',RAW)
        notes=[]
        for index in range(header[12]):
            at=header[6]+index*64;section=struct.unpack_from('<IIQQQQIIQQ',RAW,at)
            if section[1]==7:notes.append((at,section))
        build=next((at,s) for at,s in notes if b'GNU\0' in RAW[s[4]:s[4]+s[5]])
        alternate=next(at for at,s in notes if at!=build[0])
        altered=bytearray(RAW);altered[alternate:alternate+64]=RAW[build[0]:build[0]+64]
        with self.assertRaisesRegex(RuntimeError,'^implementation_build_id$'):PROFILE.elf_build_id(bytes(altered))
        altered=bytearray(RAW);struct.pack_into('<I',altered,build[1][4],0xffffffff)
        with self.assertRaisesRegex(RuntimeError,'^implementation_elf_notes$'):PROFILE.elf_build_id(bytes(altered))

    def test_missing_export_and_nontext_static_entry_fail_closed(self):
        with patch.object(PROFILE,'exported_offset',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'^implementation_export_absent$'):PROFILE.implementation_symbols(RAW)
        with patch.dict(PROFILE.EPHY_STATIC,{'session_start_element':len(RAW)+1}):
            with self.assertRaisesRegex(RuntimeError,'^implementation_static_entry$'):PROFILE.implementation_symbols(RAW)

    def inventory(self,foreign=False,wrong_owner=False):
        paths=[];owners={'/usr/bin/epiphany':CONTEXT['packages']['epiphany-runtime']}
        for ident,(prefix,package) in PROFILE.LIBRARIES.items():
            path=PROFILE.EPHY_MAIN['path'] if ident=='ephymain' else '/usr/lib64/'+prefix+'.owned'
            if ident=='ephymain' and foreign:path='/usr/lib64/foreign/libephymain.so'
            paths.append(path);owners[path]=CONTEXT['packages'][package]
        if wrong_owner:owners[PROFILE.EPHY_MAIN['path']]='foreign-0:1-1.x86_64'
        def output(argv,**kwargs):
            if argv[0]=='ldd':return '\n'.join('library => '+p+' (0x1234)' for p in paths)
            if argv[:2]==['rpm','-q']:return CONTEXT['packages'][argv[-1]]
            if argv[:2]==['rpm','-qf']:return owners[argv[-1]]
            raise AssertionError('unexpected provider command')
        with patch.object(PROFILE,'Path',VirtualPath),patch.object(PROFILE.subprocess,'check_output',side_effect=output),\
             patch.object(PROFILE.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=b'',stderr=b'')):
            return PROFILE.inventory(CONTEXT)

    def test_inventory_exact_nested_library_path_owner_whole_symbols(self):
        result=self.inventory()
        self.assertEqual(result['ephymain']['path'],PROFILE.EPHY_MAIN['path'])
        self.assertEqual(result['ephymain']['sha256'],PROFILE.EPHY_MAIN['sha256'])
        self.assertEqual(result['ephymain']['build_id'],PROFILE.EPHY_MAIN['build_id'])
        self.assertEqual(result['browser']['sha256'],hashlib.sha256(LAUNCHER.read_bytes()).hexdigest())
        self.assertEqual(result['browser']['symbols'],{})
        self.assertEqual(set(result['ephymain']['symbols']),{s for l,s,r in PROFILE.PHASES.values() if l=='ephymain'})

    def test_unknown_nested_path_and_wrong_rpm_owner_deny(self):
        for kwargs,reason in (({'foreign':True},'runtime_library_ambiguity'),({'wrong_owner':True},'runtime_library_owner')):
            with self.assertRaisesRegex(RuntimeError,'^'+reason+'$'):self.inventory(**kwargs)

    def mapped(self,rows=None,error=None,ticks=None):
        actual=CACHE/'epiphany-runtime-libephymain.elf';info=actual.stat()
        record=dict(PROFILE.EPHY_MAIN,file_identity=list(PROFILE.file_identity(actual)))
        row='1000-2000 r-xp 00000000 00:ff '+str(info.st_ino)+' '+PROFILE.EPHY_MAIN['path']
        (self.root/'maps').write_text((row if rows is None else rows)+'\n')
        calls=[]
        def identity(v):return(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
        def forward(proc,rows,path,raw,expected):
            calls.append((str(proc),rows,str(path),hashlib.sha256(raw).hexdigest(),expected))
            self.assertEqual(expected,identity(info));self.assertEqual(raw,RAW)
            if error:raise error
        real_open=os.open
        def opened(path,*args,**kw):return real_open(actual if str(path)==PROFILE.EPHY_MAIN['path'] else path,*args,**kw)
        causal=types.SimpleNamespace(deferred_termination=defer,forward_file_identity=identity,forward_map_files=forward)
        with patch.object(PROFILE,'Path',VirtualPath),patch.object(PROFILE.os,'open',side_effect=opened),\
             patch.object(PROFILE,'proc_identity',side_effect=ticks or [(77,'S'),(77,'S')]):
            value=PROFILE.mapped_implementation(41,os.getuid(),77,{'ephymain':record},causal)
        return value,calls

    def test_map_forwarding_exact_owned_whole_fd_and_process_generation(self):
        before=set(os.listdir('/proc/self/fd'));value,calls=self.mapped()
        self.assertEqual(set(os.listdir('/proc/self/fd')),before)
        self.assertEqual(value,dict(verified=True,library_sha256=PROFILE.EPHY_MAIN['sha256'],
                                  build_id=PROFILE.EPHY_MAIN['build_id'],mapped_segments=1,same_generation=True))
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'/proc/41')

    def test_map_absence_oversize_and_generation_reuse_deny(self):
        for kwargs,reason in (({'rows':'unknown'},'implementation_maps_absent'),
                             ({'rows':'x'* (1024*1024+1)},'implementation_maps_limit'),
                             ({'ticks':[(78,'S')]},'implementation_process_generation'),
                             ({'ticks':[(77,'S'),(78,'S')]},'implementation_process_generation')):
            with self.assertRaisesRegex(RuntimeError,'^'+reason+'$'):self.mapped(**kwargs)

    def test_map_denial_and_original_cancel_object_preserved_no_fd_leak(self):
        for error in (PermissionError('private sentinel'),KeyboardInterrupt('private sentinel')):
            before=set(os.listdir('/proc/self/fd'))
            with self.assertRaises(type(error)) as caught:self.mapped(error=error)
            self.assertIs(caught.exception,error);self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    def test_actual_sigint_inventory_callback_preserves_handler_and_descriptors(self):
        before=set(os.listdir('/proc/self/fd'));handler=signal.getsignal(signal.SIGINT)
        try:
            signal.signal(signal.SIGINT,signal.default_int_handler)
            def interrupted(raw):os.kill(os.getpid(),signal.SIGINT)
            with patch.object(PROFILE,'implementation_symbols',side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):self.inventory()
        finally:signal.signal(signal.SIGINT,handler)
        self.assertIs(signal.getsignal(signal.SIGINT),handler);self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    def test_all_11_ephy_events_closed_numeric_only_and_nested_callbacks(self):
        events=[]
        for index,(phase,(lib,symbol,args)) in enumerate(PROFILE.PHASES.items()):
            if lib!='ephymain':continue
            self.assertIsNone(args)
            for point,ns in (('enter',index*10+1),('return',index*10+2)):
                event=PROFILE.parse_event(f'epiphany-41 [001] .... 100.{ns:09d}: {phase}_{point}: private_url=https://fixture.invalid/private title=PRIVATE_SENTINEL')
                self.assertEqual(set(event),{'tid','timestamp_ns','timestamp_resolution_ns','phase','point'})
                self.assertNotIn('PRIVATE',json.dumps(event));self.assertNotIn('fixture.invalid',json.dumps(event));events.append(event)
        spans=PROFILE.spans(events,100000000000,101000000000)
        self.assertEqual(len(spans),11);self.assertTrue(all(row['completed'] for row in spans))

if __name__=='__main__':unittest.main(verbosity=2)
