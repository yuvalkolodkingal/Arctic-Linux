"""Independent kernel-format, ELF and causal interval failure controls."""
import copy
import importlib.util
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

C = load('causal_fixture', ROOT/'tools/performance/causal.py')
R = load('causal_roles', ROOT/'tools/tests/test_performance_roles.py')


class CausalControls(unittest.TestCase):
    def test_tracefs_command_uses_one_nontruncating_nonseeking_owned_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);events=root/'uprobe_events'
            original=b'unrelated global events must not be truncated'+b'X'*100
            events.write_bytes(original)
            command='-:owned/map_create\n';data=command.encode('ascii')
            actual_open,actual_write,actual_close=os.open,os.write,os.close
            with patch.object(C.os,'open',wraps=actual_open) as opened, \
                 patch.object(C.os,'write',wraps=actual_write) as written, \
                 patch.object(C.os,'close',wraps=actual_close) as closed, \
                 patch.object(C.os,'lseek',side_effect=AssertionError('tracefs must not seek')):
                C.write_uprobe_command(root,command)
            opened.assert_called_once_with(events,os.O_WRONLY|os.O_CLOEXEC)
            self.assertEqual(opened.call_args.args[1]&(os.O_APPEND|os.O_TRUNC|os.O_CREAT),0)
            written.assert_called_once()
            fd,payload=written.call_args.args
            self.assertEqual(payload,data)
            closed.assert_called_once_with(fd)
            with self.assertRaises(OSError):os.fstat(fd)
            # A regular fixture has byte-offset semantics; the real seq-file
            # parses commands. Its untouched suffix detects destructive flags.
            self.assertEqual(events.read_bytes(),data+original[len(data):])

    def test_tracefs_short_or_failed_write_closes_fd_and_never_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'uprobe_events').touch()
            command='-:owned/map_create\n';actual_close=os.close
            for fault in (0,len(command)-1,OSError(22,'kernel rejected command')):
                with self.subTest(fault=fault), \
                     patch.object(C.os,'write',**({'side_effect':fault} if isinstance(fault,Exception) else {'return_value':fault})) as written, \
                     patch.object(C.os,'close',wraps=actual_close) as closed:
                    with self.assertRaises((OSError,RuntimeError)):
                        C.write_uprobe_command(root,command)
                    written.assert_called_once()
                    fd=written.call_args.args[0]
                    closed.assert_called_once_with(fd)
                    with self.assertRaises(OSError):os.fstat(fd)
            with patch.object(C.os,'open') as opened:
                for fault in ('', 'missing newline', 'two\ncommands\n','X'*4096+'\n'):
                    with self.subTest(fault=fault),self.assertRaises(RuntimeError):
                        C.write_uprobe_command(root,fault)
                opened.assert_not_called()

    def test_unregister_write_failure_still_closes_owned_fd_and_attempts_unmount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);probe=C.LowerBoundProbe([]);probe.root=root
            (root/'events'/probe.group/'map_create').mkdir(parents=True)
            (root/'trace_pipe').touch()
            fd=os.open(root/'trace_pipe',os.O_RDONLY);probe.fd=fd
            probe.requested_events={'map_create'};probe.mounted=True
            previous=signal.getsignal(signal.SIGTERM);probe.old_sigterm=previous
            with patch.object(C,'write_uprobe_command',side_effect=OSError(22,'unregister failed')) as written, \
                 patch.object(C.subprocess,'run') as run, \
                 patch.object(C.os.path,'ismount',return_value=True), \
                 self.assertRaisesRegex(RuntimeError,'cleanup failed.*unregister failed'):
                probe.__exit__(None,None,None)
            written.assert_called_once_with(root,'-:'+probe.group+'/map_create\n')
            run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)
            self.assertIsNone(probe.fd)
            with self.assertRaises(OSError):os.fstat(fd)
            self.assertEqual(signal.getsignal(signal.SIGTERM),previous)
            self.assertFalse(hasattr(probe,'old_sigterm'))

    def test_kernel_timestamp_identity_and_precision_are_literal(self):
        ident = '0123456789abcdef'*2
        for fraction, expected, resolution in [('123456789', 123456789, 1), ('123456', 123456000, 1000)]:
            line = f' mango-234 [001] d... 99.{fraction}: map_create: (0x7ffff123 <- 0x7ffff456) foreign_id="{ident}"'
            event = C.trace_receipt(line, 234)
            self.assertEqual(event['foreign_toplevel_id'], ident)
            self.assertEqual(event['kernel_text_monotonic_ns'], 99_000_000_000+expected)
            self.assertEqual(event['kernel_timestamp_text'],'99.'+fraction)
            self.assertEqual(event['lower_monotonic_ns'], 99_000_000_000+expected-resolution)
            self.assertEqual(event['timestamp_rounding_allowance_ns'],resolution)
            self.assertEqual(event['timestamp_resolution_ns'], resolution)
        for fault in [line.replace('mango-234', 'mango-235'), line.replace(ident,'fault'),
                      line.replace('.123456:', '.1234567890:'), line.replace('map_create:', 'other:')]:
            with self.subTest(fault=fault), self.assertRaises(RuntimeError): C.trace_receipt(fault,234)

    def test_linux_rounded_microsecond_text_is_always_a_conservative_lower(self):
        ident='a'*32
        # Linux ns2usecs() adds500 then divides1000. Exercise both sides of
        # rounding and second rollover; direct parsed text is too late for the
        # first half of each unit and cannot be used as a causal lower bound.
        for base in (99_123_456_000,99_999_999_000,100_000_000_000):
            for offset in (-500,-499,-1,0,1,499,500):
                actual=base+offset
                printed=((actual+500)//1000)*1000
                seconds,fraction=divmod(printed,1_000_000_000)
                line=f'mango-234 [001] d... {seconds}.{fraction//1000:06d}: map_create: foreign_id="{ident}"'
                event=C.trace_receipt(line,234)
                self.assertEqual(event['kernel_text_monotonic_ns'],printed)
                self.assertEqual(event['lower_monotonic_ns'],printed-1000)
                self.assertLessEqual(event['lower_monotonic_ns'],actual)

    @unittest.skipUnless(shutil.which('gcc'), 'gcc required for independent ELF fixture')
    def test_exported_real_elf_function_has_file_offset_and_absent_symbol_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'fixture.c').write_text('void *wlr_ext_foreign_toplevel_handle_v1_create(void *a, void *b) { return a; }\n')
            subprocess.run(['gcc','-shared','-fPIC',str(root/'fixture.c'),'-o',str(root/'fixture.so')],check=True)
            offset=C.elf_symbol_offset(root/'fixture.so')
            self.assertGreater(offset,0)
            self.assertLess(offset,(root/'fixture.so').stat().st_size)
            with self.assertRaisesRegex(RuntimeError,'exported causal'):C.elf_symbol_offset(root/'fixture.so','absent')
            raw=bytearray((root/'fixture.so').read_bytes());raw[4]=1
            (root/'bad.so').write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError,'ELF64'):C.elf_symbol_offset(root/'bad.so')

    @unittest.skipUnless(shutil.which('gcc') and shutil.which('nm') and shutil.which('readelf'), 'gcc and GNU ELF tools required for native fixture')
    def test_native_profile_binds_actual_owned_executable_code_and_process_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'owned.c';binary=root/'owned'
            source.write_text('#include <unistd.h>\n__attribute__((noinline)) int managed_map_fixture(int value) { return value + 19; }\n__attribute__((noinline)) const char *original_id_fixture(const char *value) { return value; }\nint main(void) { while (1) pause(); }\n')
            subprocess.run(['gcc','-fPIE','-pie','-O0',str(source),'-o',str(binary)],check=True)
            output=subprocess.check_output(['nm','-S','--defined-only',str(binary)],text=True)
            symbols=[line.split() for line in output.splitlines() if line.endswith(' managed_map_fixture')]
            self.assertEqual(len(symbols),1)
            virtual,size=int(symbols[0][0],16),int(symbols[0][1],16)
            loads=[]
            for line in subprocess.check_output(['readelf','-l','--wide',str(binary)],text=True).splitlines():
                fields=line.split()
                if fields and fields[0]=='LOAD' and 'E' in fields:
                    offset,vaddr,file_size=int(fields[1],16),int(fields[2],16),int(fields[4],16)
                    if vaddr<=virtual< vaddr+file_size:loads.append((offset,vaddr,file_size))
            self.assertEqual(len(loads),1)
            load_offset,load_virtual,_=loads[0]
            file_offset=load_offset+virtual-load_virtual
            getter=[line.split() for line in output.splitlines() if line.endswith(' original_id_fixture')]
            self.assertEqual(len(getter),1)
            getter_virtual,getter_size=int(getter[0][0],16),int(getter[0][1],16)
            getter_offset=load_offset+getter_virtual-load_virtual
            child=subprocess.Popen([str(binary)])
            try:
                maps=(Path('/proc')/str(child.pid)/'maps').read_text()
                executable=[line.split(None,5) for line in maps.splitlines() if line.endswith(str(binary)) and 'x' in line.split()[1]]
                self.assertEqual(len(executable),1)
                start,end=(int(value,16) for value in executable[0][0].split('-'))
                mapped_offset=int(executable[0][2],16)
                # Independently derive PIE bias from GNU program headers and
                # Linux's actual file mapping, rather than reusing the helper.
                mapped_virtual=load_virtual+mapped_offset-load_offset
                address=start+virtual-mapped_virtual
                self.assertTrue(start<=address<end)
                self.assertNotEqual(address,virtual)
                raw=binary.read_bytes()
                profile=dict(C.MAPPING_PROFILES[0], executable_sha256=hashlib.sha256(raw).hexdigest(),
                    function_file_offset=file_offset,function_size=size,
                    function_sha256=hashlib.sha256(raw[file_offset:file_offset+size]).hexdigest(),
                    instruction_file_offset=file_offset,client_ext_offset=1584,
                    ipc_function_file_offset=getter_offset,ipc_function_size=getter_size,
                    ipc_function_sha256=hashlib.sha256(raw[getter_offset:getter_offset+getter_size]).hexdigest())
                with patch.object(C,'MAPPING_PROFILES',(profile,)):
                    self.assertEqual(C.mapping_profile(binary),profile)
                    actual=C.instruction_mapping(binary,maps,file_offset)
                    self.assertEqual(actual['instruction_address'],address)
                    with self.assertRaises(RuntimeError):C.instruction_mapping(binary,maps+'\n'+executable[0][0]+' '+ ' '.join(executable[0][1:]),file_offset)
                    with self.assertRaises(RuntimeError):C.instruction_mapping(binary,maps.replace(str(binary),str(binary)+' (deleted)'),file_offset)
                    for changed in (file_offset,len(raw)-1):
                        mutated=bytearray(raw);mutated[changed]^=1
                        bad=root/'changed';bad.write_bytes(mutated)
                        with self.subTest(changed=changed),self.assertRaises(RuntimeError):C.mapping_profile(bad)
                    mutated=bytearray(raw);mutated[18]=183
                    bad.write_bytes(mutated)
                    with self.assertRaisesRegex(RuntimeError,'x86_64'):C.mapping_profile(bad)
                    mutated=bytearray(raw);mutated[getter_offset]^=1;bad.write_bytes(mutated)
                    # Even a coherently updated whole-ELF pin cannot substitute
                    # the separately frozen original getter function bytes.
                    changed_profile=dict(profile,executable_sha256=hashlib.sha256(mutated).hexdigest())
                    with patch.object(C,'MAPPING_PROFILES',(changed_profile,)):
                        with self.assertRaisesRegex(RuntimeError,'original app-ID getter bytes'):
                            C.mapping_profile(bad)
            finally:
                child.terminate();child.wait(timeout=5)
            self.assertIsNotNone(child.poll())

    def test_explicit_retained_and_baseline_profiles_are_bound_in_replay(self):
        # Evidence permits exactly these two additional whole executables;
        # equal code or source alone cannot admit a new packaging build.
        expected={
            '2f1107221157f47418cfda87dd091a3bb81ecd97dc2945184d0c42de7bbd254b':
                (0x43110,0x4362f,'3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc'),
            '67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35':
                (0x430d0,0x435ef,'11a56d467fe7e444f46fa6da1f91a88ecf1a26bc3c54e4965727438e078a47dd')}
        self.assertEqual(C.MAPPING_PROFILES,R.comparison.MAPPING_PROFILES)
        admitted={profile['executable_sha256']:profile for profile in C.MAPPING_PROFILES}
        self.assertEqual(set(admitted),set(expected)|{'1c66767fc0d814e9002306c983524b476edc671de544f3b2a6f755ea7a52dcb1'})
        for digest,(start,upper,function_digest) in expected.items():
            profile=admitted[digest]
            self.assertEqual((profile['function_file_offset'],profile['instruction_file_offset'],
                profile['function_sha256']),(start,upper,function_digest))
            self.assertEqual(profile['native_audit_sha256'],'c263158a0e29ee302bed2f09a24c43e9017ce7d87ceb53d22b86398b39dcd2aa')
            bound=R.causal_bound(.09975,.1)
            proof=bound['causal_lower_bound']
            proof['upper_mapping_profile']=dict(profile);proof['mango_sha256']=digest
            address=proof['upper_executable_mapping']['start']+upper-proof['upper_executable_mapping']['file_offset']
            proof['upper_executable_mapping']['instruction_address']=address
            proof['upper_instruction_address']=address
            proof['matched_upper_events'][0]['instruction_address']=address
            self.assertTrue(R.comparison.causal_precision(bound,('foot',)))
            for fault in ('whole','same_code_new_build','function','stable_function','getter','upper','audit','missing_audit'):
                changed=copy.deepcopy(bound);p=changed['causal_lower_bound']
                if fault=='whole':p['mango_sha256']='f'*64
                elif fault=='same_code_new_build':p['mango_sha256']=p['upper_mapping_profile']['executable_sha256']='f'*64
                elif fault=='function':p['upper_mapping_profile']['function_sha256']='0'*64
                elif fault=='stable_function':p['upper_mapping_profile']['function_sha256']=C.MAPPING_PROFILES[0]['function_sha256']
                elif fault=='getter':p['upper_mapping_profile']['ipc_function_sha256']='0'*64
                elif fault=='upper':p['upper_mapping_profile']['instruction_file_offset']+=1
                elif fault=='audit':p['upper_mapping_profile']['native_audit_sha256']='0'*64
                else:p['upper_mapping_profile'].pop('native_audit_sha256')
                with self.subTest(executable=digest,fault=fault):
                    self.assertFalse(R.comparison.causal_precision(changed,('foot',)))

    def test_upper_kernel_receipt_retains_ip_metadata_and_handle_ownership(self):
        ident='a'*32
        line=f'mango-234 [001] d... 99.123456: map_listed_xdg: (0xabcdef) client_type=0 original_app_id="Foot" foreign_id="{ident}" app_id="Foot" client=0x1000 handle=0x2000 owner=0x1000'
        event=C.trace_receipt(line,234)
        self.assertEqual(event['upper_monotonic_ns'],99_123_457_000)
        self.assertEqual(event['instruction_address'],0xabcdef)
        self.assertEqual(event['app_id'],'Foot')
        self.assertEqual(event['original_app_id'],'Foot')
        self.assertEqual(event['client_type'],0)
        self.assertEqual(event['client_address'],event['handle_owner_address'])
        for fault in (line.replace('(0xabcdef)',''),line.replace('owner=0x1000','owner=0x3000'),
                      line.replace('handle=0x2000','handle=0x0'),line.replace('app_id="Foot"','app_id=""'),
                      line.replace('app_id="Foot"','app_id="later changed title"'),
                      line.replace('234','235',1),line.replace('.123456:','.12345:')):
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):C.trace_receipt(fault,234)
        x11=line.replace('map_listed_xdg','map_listed_x11').replace('client_type=0','client_type=2')
        self.assertEqual(C.trace_receipt(x11,234)['client_type'],2)
        for fault in (line.replace('client_type=0','client_type=2'),
                      x11.replace('client_type=2','client_type=0'),line.replace('client_type=0','client_type=1'),
                      line.replace('client_type=0','client_type=True'),
                      line.replace('original_app_id="Foot"','original_app_id=(fault)'),
                      line.replace('original_app_id="Foot"','original_app_id=""'),
                      line.replace('original_app_id="Foot"','original_app_id="'+('F'*129)+'"'),
                      line.replace('original_app_id="Foot"','original_app_id="Foot\\200"'),
                      line.replace('original_app_id="Foot"','original_app_id="Fóot"'),
                      line.replace('original_app_id="Foot"','original_app_id="Foot\\x00extra"'),
                      line.replace('original_app_id="Foot"','original_app_id="other"'),
                      line.replace('map_listed_xdg','map_listed')):
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):C.trace_receipt(fault,234)
        # Exercise both sides of Linux nearest-microsecond rounding, including
        # rollover. The full displayed unit must enclose the actual event.
        for base in (99_123_456_000,99_999_999_000,100_000_000_000):
            for offset in (-500,-499,-1,0,1,499,500):
                actual=base+offset;printed=((actual+500)//1000)*1000
                sec,fraction=divmod(printed,1_000_000_000)
                receipt=C.trace_receipt(line.replace('99.123456',f'{sec}.{fraction//1000:06d}'),234)
                self.assertGreaterEqual(receipt['upper_monotonic_ns'],actual)

    def test_loss_accounting_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);stats=root/'per_cpu/cpu0/stats';stats.parent.mkdir(parents=True)
            good='entries: 12\noverrun: 0\ncommit overrun: 0\ndropped events: 0\n'
            stats.write_text(good)
            self.assertEqual(C.loss_counts(root)['cpu0']['dropped events'],0)
            for bad in [good.replace('overrun: 0','overrun: 1',1),good.replace('dropped events: 0\n','')]:
                stats.write_text(bad)
                with self.assertRaises(RuntimeError):C.loss_counts(root)

    def test_bound_intersects_both_native_receipts_with_original_ipc(self):
        probe=C.LowerBoundProbe([]);probe.pid=234
        probe.proof={'method':C.METHOD,'upper_instruction_address':0x435ef}
        ident='a'*32
        probe.events[ident]=C.trace_receipt(f'mango-234 [000] d... 0.040000: map_create: foreign_id="{ident}"',234)
        probe.upper_events[ident]=C.trace_receipt(f'mango-234 [000] d... 0.040500: map_listed_xdg: (0x435ef) client_type=0 original_app_id="foot" foreign_id="{ident}" app_id="foot" client=0x1000 handle=0x2000 owner=0x1000',234)
        with patch.object(C,'loss_counts',return_value={'cpu0':{'overrun':0,'commit overrun':0,'dropped events':0}}), \
                patch.object(probe,'_check_owner'):
            lower,upper,proof=probe.bound([{'id':1,'foreign_toplevel_id':ident,'appid':'foot'}],10_000_000,39_000_000,51_000_000,('foot',))
            self.assertEqual(lower,39_999_000)
            self.assertEqual(upper,40_501_000)
            self.assertEqual(proof['ipc_upper_monotonic_ns'],51_000_000)
            self.assertEqual(proof['matched_upper_events'][0]['upper_monotonic_ns'],upper)
            for fault in ('missing','duplicate','start','future','ip','delayed_appid','wrong_ipc','string_predicate'):
                windows=[{'id':1,'foreign_toplevel_id':ident,'appid':'foot'}]
                start,ipc_lower,ipc_upper,pattern=10_000_000,39_000_000,51_000_000,('foot',)
                changed=copy.deepcopy(probe.upper_events[ident])
                if fault=='missing':windows[0]['foreign_toplevel_id']='b'*32
                elif fault=='duplicate':windows+=windows
                elif fault=='start':start=ipc_lower=40_000_000
                elif fault=='future':ipc_upper=40_000_000
                elif fault=='ip':probe.upper_events[ident]['instruction_address']+=1
                elif fault=='delayed_appid':probe.upper_events[ident]['app_id']='unrelated'
                elif fault=='wrong_ipc':windows[0]['appid']='unrelated'
                else:pattern='foot'
                with self.subTest(fault=fault),self.assertRaises(RuntimeError):
                    probe.bound(windows,start,ipc_lower,ipc_upper,pattern,timeout=.001)
                probe.upper_events[ident]=changed

    def test_original_getter_copy_and_later_ipc_must_match_case_preserving(self):
        for client_type, event_name in ((0,'map_listed_xdg'),(2,'map_listed_x11')):
            event=dict(event=event_name,client_type=client_type,app_id='Foot',original_app_id='Foot')
            self.assertTrue(C.original_appid_matches(event,dict(appid='Foot'),('foot',)))
            for fault in ('missing','fault','long','nonascii','nul','malformed_alias','late_case_change','type','kind'):
                changed=dict(event);window=dict(appid='Foot')
                if fault=='missing':changed.pop('original_app_id')
                elif fault=='fault':changed['original_app_id']='(fault)'
                elif fault=='long':changed['original_app_id']='F'*129
                elif fault=='nonascii':changed['original_app_id']='Fóot'
                elif fault=='nul':changed['original_app_id']='Foot\0extra'
                elif fault=='malformed_alias':changed['original_app_id']='Foot'+'\u0080'*4091
                elif fault=='late_case_change':window['appid']='foot'
                elif fault=='type':changed['client_type']=True
                else:changed['event']='map_listed_x11' if client_type==0 else 'map_listed_xdg'
                with self.subTest(client_type=client_type,fault=fault):
                    self.assertFalse(C.original_appid_matches(changed,window,('foot',)))

    def test_original_upper_commands_capture_selected_branch_first(self):
        profile=C.MAPPING_PROFILES[0]
        commands=C.upper_probe_commands('owned',Path('/usr/bin/mango'),profile)
        self.assertEqual(set(commands),{'map_listed_xdg','map_listed_x11'})
        self.assertIn('original_app_id=+0(+192(+56(+328(%bx)))):string ',commands['map_listed_xdg'])
        self.assertIn('original_app_id=+0(+144(+328(%bx))):string ',commands['map_listed_x11'])
        for command in commands.values():
            self.assertEqual(command.count('original_app_id='),1)
            self.assertLess(command.index('original_app_id='),command.index('foreign_id='))
            self.assertLess(command.index('original_app_id='),command.index(' app_id='))
            self.assertIn('client_type=+0(%bx):u32',command)
            self.assertTrue(command.endswith('\n'))

    def test_original_first_kernel_budget_and_fault_formatter_controls(self):
        # Independent kernel-format vectors, derived from trace_probe_tmpl.h
        # d0e458a5 (get_data_size/store_trace_args) and trace_uprobe.c
        # 24fba47b (fetch_store_string). These are not idealized '(fault)'
        # fixtures: an intermediate chain fault can retain a shared data_loc.
        ident='a'*32
        def formatted(original, foreign, copied):
            return ('mango-234 [001] d... 99.123456: map_listed_xdg: (0x435ef) '
                f'client_type=0 original_app_id={original} foreign_id={foreign} '
                f'app_id={copied} client=0x1000 handle=0x2000 owner=0x1000')
        good=C.trace_receipt(formatted('"foot"','"'+ident+'"','"foot"'),234)
        self.assertTrue(C.original_appid_matches(good,dict(appid='foot'),('foot',)))
        # PAGE_SIZE=4096, fixed fields=40: normal dynamic returns 5,33,5.
        # A 4080-byte original clamps the 4119-byte request to 4056 bytes;
        # ret==maxlen NUL-terminates it at 4055 and consumes all later budget.
        near_page='foot'+'A'*4051
        # A 5000-byte (>PATH_MAX) original contributes zero during sizing.
        # The remaining 38 bytes force NUL at 37, leaving both later strings
        # with zero length. A short-looking original is still not admissible.
        over_path='foot'+'A'*33
        for label,original,foreign,copied in (
                ('near_page','"'+near_page+'"','(fault)','(fault)'),
                ('over_path','"'+over_path+'"','(fault)','(fault)'),
                # Intermediate fetch ret=-EFAULT retains the initial data_loc;
                # the following 33-byte foreign identifier overwrites it.
                ('intermediate_chain','"'+ident+'"','"'+ident+'"','"foot"'),
                ('final_string','(fault)','"'+ident+'"','"foot"')):
            with self.subTest(label=label),self.assertRaises(RuntimeError):
                C.trace_receipt(formatted(original,foreign,copied),234)
        # Even a coherent 32-hex copy/IPC value cannot make the retained fault
        # location a valid role predicate. Exclude this alias at both endpoints.
        aliased=C.trace_receipt(formatted('"'+ident+'"','"'+ident+'"','"'+ident+'"'),234)
        self.assertFalse(C.original_appid_matches(aliased,dict(appid=ident),(ident,)))
        probe=C.LowerBoundProbe([])
        with patch.object(probe,'_check_owner'),self.assertRaisesRegex(RuntimeError,'exact application-ID'):
            probe.bound([],1,1,1,(ident,),timeout=0)
        bound=R.causal_bound(.09975,.1,appids=(ident,))
        self.assertFalse(R.comparison.causal_precision(bound,(ident,)))

    def test_multiple_matching_windows_bound_the_first_eligible_managed_client(self):
        probe=C.LowerBoundProbe([]);probe.pid=234
        probe.proof={'method':C.METHOD,'upper_instruction_address':0x435ef}
        windows=[]
        for ident,created,listed in (('a'*32,'0.040000','0.045000'),('b'*32,'0.042000','0.043000')):
            windows.append(dict(id=len(windows)+1,foreign_toplevel_id=ident,appid='foot'))
            probe.events[ident]=C.trace_receipt(f'mango-234 [000] d... {created}: map_create: foreign_id="{ident}"',234)
            client=0x1000*len(windows);handle=0x4000+client
            probe.upper_events[ident]=C.trace_receipt(f'mango-234 [000] d... {listed}: map_listed_xdg: (0x435ef) client_type=0 original_app_id="foot" foreign_id="{ident}" app_id="foot" client=0x{client:x} handle=0x{handle:x} owner=0x{client:x}',234)
        with patch.object(probe,'_check_owner'),patch.object(C,'loss_counts',return_value={'cpu0':{'overrun':0,'commit overrun':0,'dropped events':0}}):
            lower,upper,proof=probe.bound(windows,10_000_000,41_000_000,60_000_000,('foot',))
            self.assertEqual(lower,41_000_000)
            self.assertEqual(upper,43_001_000)
            self.assertLessEqual(lower,43_000_000)
            self.assertGreaterEqual(upper,43_000_000)
            self.assertEqual(len(proof['matched_upper_events']),2)
            with self.assertRaisesRegex(RuntimeError,'do not intersect'):
                probe.bound(windows,10_000_000,50_000_000,60_000_000,('foot',))

    def test_native_receipt_owner_rechecks_actual_pid_uid_start_and_executable(self):
        probe=C.LowerBoundProbe([]);probe.pid=os.getpid()
        proc=Path('/proc')/str(probe.pid)
        probe.executable=(proc/'exe').resolve(strict=True)
        probe.proof=dict(desktop_uid=proc.stat().st_uid,
            mango_start_ticks=int((proc/'stat').read_text().rsplit(')',1)[1].split()[19]))
        probe._check_owner()
        for fault in ('uid','start','exe','pid'):
            saved=copy.deepcopy(probe.proof);executable=probe.executable;pid=probe.pid
            if fault=='uid':probe.proof['desktop_uid']+=1
            elif fault=='start':probe.proof['mango_start_ticks']+=1
            elif fault=='exe':probe.executable=Path('/definitely-not-the-owner')
            else:probe.pid=2**31-1
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):probe._check_owner()
            probe.proof=saved;probe.executable=executable;probe.pid=pid

    def test_causal_receipt_cannot_relax_original_precision_limit(self):
        runs=R.paired_roles()
        bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
        bound.clear();bound.update(R.causal_bound(.0389,.04,R.comparison.ROLE_APPIDS[runs['candidate'][0]['startup_role_terminal_cold_seconds']['app_id']]))
        report=R.comparison.compare(runs)
        self.assertEqual(report['status'],'measurement_precision_gate_failed')
        check=report['measurement_precision']['checks']['candidate'][0][0]
        self.assertTrue(check['causal_lower_bound_valid'])
        self.assertFalse(check['valid'])
        self.assertEqual(check['maximum_interval_seconds'],.001)

    def test_missing_forged_lossy_or_wrong_launch_receipts_fail_qualification(self):
        original=R.paired_roles()
        for fault in ['missing','method','clock','pid','library','version','layout','loss','old_event','future_event','boolean_resolution','forged_lower','missing_literal','missing_allowance','boolean_literal','boolean_allowance','zero_allowance','short_allowance','unsubtracted_display','missing_text','malformed_text','text_literal_mismatch']:
            runs=copy.deepcopy(original)
            bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
            proof=bound['causal_lower_bound']
            if fault=='missing':bound.pop('causal_lower_bound')
            elif fault=='method':proof['method']='arrival-is-exact'
            elif fault=='clock':proof['clock']='local'
            elif fault=='pid':proof['matched_events'][0]['kernel_pid']+=1
            elif fault=='library':proof['library_sha256']='unknown'
            elif fault=='version':proof['library_rpm']='wlroots-0.20.3-1.fc44.x86_64'
            elif fault=='layout':proof['identifier_offset']=64
            elif fault=='loss':proof['loss_counts']['cpu0']['overrun']=1
            elif fault=='old_event':proof['matched_events'][0]['lower_monotonic_ns']=1
            elif fault=='future_event':proof['matched_events'][0]['lower_monotonic_ns']=2_000_000_000
            elif fault=='boolean_resolution':proof['matched_events'][0]['timestamp_resolution_ns']=True
            elif fault=='missing_literal':proof['matched_events'][0].pop('kernel_text_monotonic_ns')
            elif fault=='missing_allowance':proof['matched_events'][0].pop('timestamp_rounding_allowance_ns')
            elif fault=='boolean_literal':proof['matched_events'][0]['kernel_text_monotonic_ns']=True
            elif fault=='boolean_allowance':proof['matched_events'][0]['timestamp_rounding_allowance_ns']=True
            elif fault=='zero_allowance':proof['matched_events'][0]['timestamp_rounding_allowance_ns']=0
            elif fault=='short_allowance':proof['matched_events'][0]['timestamp_rounding_allowance_ns']=500
            elif fault=='unsubtracted_display':proof['matched_events'][0]['kernel_text_monotonic_ns']=proof['matched_events'][0]['lower_monotonic_ns']
            elif fault=='missing_text':proof['matched_events'][0].pop('kernel_timestamp_text')
            elif fault=='malformed_text':proof['matched_events'][0]['kernel_timestamp_text']='10.999e-3'
            elif fault=='text_literal_mismatch':proof['matched_events'][0]['kernel_timestamp_text']='10.999000'
            else:bound['lower_seconds']+=.0001;bound['interval_seconds']-=.0001
            with self.subTest(fault=fault):
                report=R.comparison.compare(runs)
                self.assertEqual(report['status'],'measurement_precision_gate_failed')
                self.assertFalse(report['measurement_precision']['valid'])

    def test_six_digit_kernel_text_cannot_claim_nanosecond_precision(self):
        runs=R.paired_roles()
        bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
        event=bound['causal_lower_bound']['matched_events'][0]
        self.assertEqual(len(event['kernel_timestamp_text'].split('.')[1]),6)
        self.assertTrue(R.comparison.causal_precision(bound, ('foot',)))
        event['timestamp_resolution_ns']=event['timestamp_rounding_allowance_ns']=1
        event['lower_monotonic_ns']=event['kernel_text_monotonic_ns']-1
        bound['lower_seconds']=(event['lower_monotonic_ns']-bound['launch_started_monotonic_ns'])/1e9
        bound['interval_seconds']=bound['upper_seconds']-bound['lower_seconds']
        self.assertFalse(R.comparison.causal_precision(bound, ('foot',)))
        self.assertEqual(R.comparison.compare(runs)['status'],'measurement_precision_gate_failed')

    def test_missing_wrong_future_or_backdated_native_upper_cannot_qualify(self):
        for fault in ('missing','id','pid','future','pre_create','ip','profile','float_profile','elf','mapping','missing_appid',
                      'delayed_match','self_declared_predicate','ipc_mismatch','owner','lower_allowance','upper_allowance','upper_text',
                      'boolean_upper','forged_upper','missing_ipc_upper','ipc_before_create','duplicate_pair'):
            runs=R.paired_roles();run=runs['candidate'][0]
            bound=run['startup_role_terminal_cold_seconds']['observation_bounds'][0]
            proof=bound['causal_lower_bound'];event=proof['matched_upper_events'][0]
            if fault=='missing':proof.pop('matched_upper_events')
            elif fault=='id':event['foreign_toplevel_id']='d'*32
            elif fault=='pid':event['kernel_pid']+=1
            elif fault=='future':
                # Keep literal/arithmetic coherent, but place the native event
                # far after the ORIGINAL positive socket completion.
                event['kernel_text_monotonic_ns']+=1_000_000_000
                event['upper_monotonic_ns']+=1_000_000_000
                event['kernel_timestamp_text']='2.039999'
            elif fault=='pre_create':event['upper_monotonic_ns']=proof['matched_events'][0]['lower_monotonic_ns']-1
            elif fault=='ip':event['instruction_address']+=1
            elif fault=='profile':proof['upper_mapping_profile']['client_ext_offset']+=8
            elif fault=='float_profile':proof['upper_mapping_profile']['client_ext_offset']=1584.0
            elif fault=='elf':proof['mango_sha256']='f'*64
            elif fault=='mapping':proof['upper_executable_mapping']['start']+=1
            elif fault=='missing_appid':event.pop('app_id')
            elif fault=='delayed_match':event['app_id']='unrelated-at-insertion'
            elif fault=='self_declared_predicate':
                proof['application_id_predicate']=['unrelated-at-insertion'];event['app_id']='unrelated-at-insertion'
                proof['matched_ipc_clients'][0]['appid']='unrelated-at-insertion'
            elif fault=='ipc_mismatch':proof['matched_ipc_clients'][0]['appid']='unrelated'
            elif fault=='owner':event['handle_owner_address']+=1
            elif fault=='lower_allowance':event['timestamp_rounding_allowance_ns']=0
            elif fault=='upper_allowance':event['timestamp_resolution_ns']=event['timestamp_rounding_allowance_ns']=1
            elif fault=='upper_text':event['kernel_timestamp_text']='10.999e-3'
            elif fault=='boolean_upper':event['upper_monotonic_ns']=True
            elif fault=='forged_upper':
                bound['upper_seconds']-=.00001;bound['interval_seconds']-=.00001
                run['startup_role_terminal_cold_seconds']['first']=bound['upper_seconds']
            elif fault=='missing_ipc_upper':proof.pop('ipc_upper_monotonic_ns')
            elif fault=='ipc_before_create':proof['ipc_upper_monotonic_ns']=bound['launch_started_monotonic_ns']
            else:
                proof['matched_events']*=2;proof['matched_upper_events']*=2;proof['matched_ipc_clients']*=2
            with self.subTest(fault=fault):
                report=R.comparison.compare(runs)
                self.assertEqual(report['status'],'measurement_precision_gate_failed')
                self.assertFalse(report['measurement_precision']['valid'])

    def test_prior_v10_lower_only_sampler_cannot_be_reclassified(self):
        runs=R.paired_roles()
        for run in runs['candidate']:run['identity']['sampler']='cpu-30-pss-6-v10-raw-causal-role-first-use'
        with self.assertRaises(ValueError):R.comparison.compare(runs)

    def test_copied_match_cannot_alias_malformed_original_or_replay_prior_v11(self):
        for fault in ('missing','fault','long','nonascii','nul','malformed_alias','wrong_type','boolean_type',
                      'wrong_kind','getter_chain','float_chain','getter_hash','audit','old_method','old_sampler','late_case_change'):
            runs=R.paired_roles();bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
            proof=bound['causal_lower_bound'];event=proof['matched_upper_events'][0]
            if fault=='missing':event.pop('original_app_id')
            elif fault=='fault':event['original_app_id']='(fault)'
            elif fault=='long':event['original_app_id']='f'*129
            elif fault=='nonascii':event['original_app_id']='fóot'
            elif fault=='nul':event['original_app_id']='foot\0suffix'
            elif fault=='malformed_alias':event['original_app_id']='foot'+'\u0080'*4091
            elif fault=='wrong_type':event['client_type']=1
            elif fault=='boolean_type':event['client_type']=False
            elif fault=='wrong_kind':event['event']='map_listed_x11'
            elif fault=='getter_chain':proof['upper_mapping_profile']['xdg_appid_offset']+=8
            elif fault=='float_chain':proof['upper_mapping_profile']['client_type_offset']=0.0
            elif fault=='getter_hash':proof['upper_mapping_profile']['ipc_function_sha256']='0'*64
            elif fault=='audit':proof['audited_original_appid_sha256']='0'*64
            elif fault=='old_method':proof['method']='wlroots-0.20-and-mango-managed-list-native-bracket-raw-v3'
            elif fault=='old_sampler':runs['candidate'][0]['identity']['sampler']='cpu-30-pss-6-v11-native-bracket-role-first-use'
            else:
                event['original_app_id']=event['app_id']='Foot'
                # Original exact-ID predicate is case-insensitive, but metadata
                # changes between native and positive IPC are conservatively refused.
            if fault=='old_sampler':
                with self.assertRaises(ValueError):R.comparison.compare(runs)
            else:
                with self.subTest(fault=fault):
                    self.assertFalse(R.comparison.causal_precision(bound,('foot',)))
                    self.assertEqual(R.comparison.compare(runs)['status'],'measurement_precision_gate_failed')
        runs=R.paired_roles();bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
        event=bound['causal_lower_bound']['matched_upper_events'][0]
        event['event']='map_listed_x11';event['client_type']=2
        self.assertTrue(R.comparison.causal_precision(bound,('foot',)))

    def test_old_sampler_remains_unqualified_in_new_role_lane(self):
        runs=R.paired_roles()
        for run in runs['candidate']:run['identity']['sampler']='cpu-30-pss-6-v8-autonomous-role-first-use'
        with self.assertRaises(ValueError):R.comparison.compare(runs)

    def test_mixed_adjusted_and_raw_clock_evidence_cannot_pass(self):
        for fault in ('timing','bound','kernel','userspace','observer'):
            runs=R.paired_roles()
            timing=runs['candidate'][0]['startup_role_terminal_cold_seconds']
            bound=timing['observation_bounds'][0]
            if fault=='timing':timing['clock']='CLOCK_MONOTONIC'
            elif fault=='bound':bound['clock']='CLOCK_MONOTONIC'
            elif fault=='kernel':bound['causal_lower_bound']['clock']='mono'
            elif fault=='userspace':bound['causal_lower_bound']['userspace_clock']='CLOCK_MONOTONIC'
            else:timing['observer']=bound['observer']='mango-socket-worker-v2-autonomous'
            with self.subTest(fault=fault):
                self.assertEqual(R.comparison.compare(runs)['status'],'measurement_precision_gate_failed')
        runs=R.paired_roles()
        for run in runs['candidate']:run['identity']['sampler']='cpu-30-pss-6-v9-causal-role-first-use'
        with self.assertRaises(ValueError):R.comparison.compare(runs)

    def test_host_cannot_activate_root_tracing(self):
        with self.assertRaisesRegex(RuntimeError,'disposable root collector'):
            with C.LowerBoundProbe([]):pass

    def test_cleanup_failure_still_disables_unregisters_and_attempts_owned_unmount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            probe=C.LowerBoundProbe([]);probe.root=root;probe.instance=root/'owned';probe.instance.mkdir()
            (root/'uprobe_events').write_text('')
            (probe.instance/'tracing_on').write_text('1')
            event=probe.instance/'events'/probe.group/'map_create/enable';event.parent.mkdir(parents=True)
            event.write_text('1')
            stats=probe.instance/'per_cpu/cpu0/stats';stats.parent.mkdir(parents=True)
            stats.write_text('overrun: 0\ncommit overrun: 0\ndropped events: 0\n')
            (root/'events'/probe.group/'map_create').mkdir(parents=True)
            probe.instance_created=True;probe.requested_events={'map_create'};probe.mounted=True
            # Ordinary fixture directories deliberately cannot be removed while
            # nonempty, modeling failed instance cleanup without host tracing.
            with patch.object(C.subprocess,'run') as run, patch.object(C.os.path,'ismount',return_value=True), self.assertRaisesRegex(RuntimeError,'cleanup failed'):
                probe.__exit__(None,None,None)
            self.assertEqual((probe.instance/'tracing_on').read_text(),'0')
            self.assertEqual(event.read_text(),'0')
            self.assertEqual((root/'uprobe_events').read_text(),'-:'+probe.group+'/map_create\n')
            run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)

    def test_three_hook_cleanup_failure_still_removes_other_event_and_owned_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);probe=C.LowerBoundProbe([]);probe.root=root
            probe.instance=root/'owned';probe.instance.mkdir()
            (root/'uprobe_events').write_text('unrelated events remain untouched'+'X'*100)
            (probe.instance/'tracing_on').write_text('1')
            stats=probe.instance/'per_cpu/cpu0/stats';stats.parent.mkdir(parents=True)
            stats.write_text('overrun: 0\ncommit overrun: 0\ndropped events: 0\n')
            for name in ('map_create','map_listed_x11','map_listed_xdg'):
                (root/'events'/probe.group/name).mkdir(parents=True)
                event=probe.instance/'events'/probe.group/name/'enable'
                event.parent.mkdir(parents=True);event.write_text('1')
            probe.instance_created=True;probe.requested_events={'map_create','map_listed_x11','map_listed_xdg'};probe.mounted=True
            (root/'trace_pipe').touch();fd=os.open(root/'trace_pipe',os.O_RDONLY);probe.fd=fd
            actual=C.write_uprobe_command;commands=[]
            def remove(path,command):
                commands.append(command)
                if command.endswith('/map_create\n'):raise OSError(22,'first owned unregister failed')
                return actual(path,command)
            with patch.object(C,'write_uprobe_command',side_effect=remove), \
                 patch.object(C.subprocess,'run') as run,patch.object(C.os.path,'ismount',return_value=True), \
                 self.assertRaisesRegex(RuntimeError,'cleanup failed.*first owned unregister failed'):
                probe.__exit__(None,None,None)
            self.assertEqual(commands,['-:'+probe.group+'/map_create\n','-:'+probe.group+'/map_listed_x11\n','-:'+probe.group+'/map_listed_xdg\n'])
            for name in ('map_create','map_listed_x11','map_listed_xdg'):
                self.assertEqual((probe.instance/'events'/probe.group/name/'enable').read_text(),'0')
            self.assertEqual((probe.instance/'tracing_on').read_text(),'0')
            self.assertEqual(probe.requested_events,set())
            self.assertIsNone(probe.fd)
            with self.assertRaises(OSError):os.fstat(fd)
            run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)

    def test_coherent_distinct_foreign_pairs_cannot_duplicate_ipc_or_object_identity(self):
        for fault in ('ipc','client','handle'):
            runs=R.paired_roles();bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
            proof=bound['causal_lower_bound']
            lower=copy.deepcopy(proof['matched_events'][0]);upper=copy.deepcopy(proof['matched_upper_events'][0]);ipc=copy.deepcopy(proof['matched_ipc_clients'][0])
            lower['foreign_toplevel_id']=upper['foreign_toplevel_id']=ipc['foreign_toplevel_id']='d'*32
            ipc['id']=2;upper['client_address']=upper['handle_owner_address']=0x3000;upper['handle_address']=0x4000
            proof['matched_events'].append(lower);proof['matched_upper_events'].append(upper);proof['matched_ipc_clients'].append(ipc)
            self.assertTrue(R.comparison.causal_precision(bound,('foot',)))
            if fault=='ipc':ipc['id']=1
            elif fault=='client':upper['client_address']=upper['handle_owner_address']=0x1000
            else:upper['handle_address']=0x2000
            with self.subTest(fault=fault):
                self.assertFalse(R.comparison.causal_precision(bound,('foot',)))
                self.assertEqual(R.comparison.compare(runs)['status'],'measurement_precision_gate_failed')

    def test_cancellation_is_delivered_after_resource_ownership_handoff(self):
        state={}
        previous=signal.getsignal(signal.SIGTERM)
        def interrupted(signum,frame):
            self.assertTrue(state.get('owned'))
            raise InterruptedError('termination after handoff')
        signal.signal(signal.SIGTERM,interrupted)
        try:
            with self.assertRaisesRegex(InterruptedError,'after handoff'):
                with C.deferred_termination():
                    os.kill(os.getpid(),signal.SIGTERM)
                    state['owned']=True
        finally:
            signal.signal(signal.SIGTERM,previous)

    def test_collector_worker_inherits_blocked_process_cancellation(self):
        masks=[]
        def worker():masks.append(signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        with C.deferred_termination():
            thread=threading.Thread(target=worker);thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertTrue({signal.SIGTERM,signal.SIGINT}<=masks[0])

    def test_repeat_termination_during_join_cannot_skip_owned_event_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);probe=C.LowerBoundProbe([]);probe.root=root
            (root/'events'/probe.group/'map_create').mkdir(parents=True)
            (root/'uprobe_events').write_text('')
            probe.requested_events={'map_create'};probe.mount_requested=True
            class Reader:
                def join(self,timeout):os.kill(os.getpid(),signal.SIGTERM)
                def is_alive(self):return False
            probe.thread=Reader()
            previous=signal.getsignal(signal.SIGTERM)
            def interrupted(signum,frame):raise InterruptedError('repeat termination after unwind')
            signal.signal(signal.SIGTERM,interrupted);probe.old_sigterm=interrupted
            try:
                with patch.object(C.subprocess,'run') as run, patch.object(C.os.path,'ismount',return_value=True), self.assertRaisesRegex(InterruptedError,'after unwind'):
                    probe.__exit__(None,None,None)
                self.assertEqual((root/'uprobe_events').read_text(),'-:'+probe.group+'/map_create\n')
                run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)
            finally:
                signal.signal(signal.SIGTERM,previous)


if __name__=='__main__':unittest.main()
