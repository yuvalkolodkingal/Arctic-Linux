#!/usr/bin/env python3
"""Small Source-only controls; never invoke hosted main, a VM or producer API."""
import contextlib,gzip,hashlib,importlib.util,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
H=module(HERE/'composition.py','format_test_composition')
C=module(HERE/'common.py','format_test_common')
class Controls(unittest.TestCase):
    def value(self):return C.strict_json((HERE/'execution-manifest.json').read_bytes())
    def build(self,value=None):
        value=self.value() if value is None else value
        def loader(path,expected):
            raw=path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),expected);return raw
        return H.build(ROOT,value,loader,lambda *a:None)
    def test_pure_composition_exact_codes_and_disabled(self):
        value=self.value();C.manifest(value)
        with self.assertRaises(RuntimeError):C.manifest(value,True)
        wrapped,observed,original,state=self.build(value)
        self.assertIs(wrapped.__code__,original.__code__)
        self.assertIs(observed.__code__,original.__code__)
        self.assertFalse(state['runtime_cause_proven'])
        self.assertFalse(state['original_operand_observed'])
        self.assertEqual(state['mapping'],C.SCANNER_BINDING)
        for boundary in state['Source_boundaries']:self.assertIs(boundary.function.__code__,boundary.code)
    def test_foreign_scanner_requests_fail_closed(self):
        wrapped,observed,original,state=self.build()
        admission=wrapped.__globals__['C']
        for name,expected in [('bios_host_screen',H.ORIGINAL_SHA),('bios_source_screen',H.ORIGINAL_SHA),('foreign',H.SELECTED_SHA)]:
            with self.subTest(name=name),self.assertRaises(RuntimeError):
                admission.load(ROOT/H.ORIGINAL_PATH,name,expected)
        staged=H.cell(observed.__globals__['original_evidence'],'staged')
        with self.assertRaises(RuntimeError):staged.__globals__['C'].load(ROOT/H.ORIGINAL_PATH,'bios_source_screen',H.ORIGINAL_SHA)
    def test_actual_original_records_select_new_scanner_preserve_rejection(self):
        wrapped,observed,original,state=self.build()
        with tempfile.TemporaryDirectory() as folder:
            vm=Path(folder);(vm/'serial-install.log').write_bytes(b'private@example.invalid\n')
            (vm/'serial-boot.log').write_bytes(b'public\n')
            caught=[]
            def trace(frame,event,arg):
                if event=='exception' and frame.f_code.co_name=='reject_sensitive_match':caught.append(arg[1])
                return trace
            prior=sys.gettrace()
            try:
                sys.settrace(trace)
                with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError) as raised:observed.__globals__['original_evidence'](vm,{},'0'*64)
            finally:sys.settrace(prior)
            self.assertEqual(len(caught),1);self.assertIs(raised.exception,caught[0])
        # The unchanged strict observer must recognize the actual selected
        # scanner Code before its same primary rejection is propagated.
        self.assertTrue(state['strict']['finite']['actual_raising_Source_Code_globals_owned'])
        self.assertEqual(state['strict']['finite']['original_source_site']['source_sha256'],H.SELECTED_SHA)
    def test_complete_public_frame_samebuffer_and_negative_neighbors(self):
        wrapped,observed,original,state=self.build()
        scanner=H.cell(original.__globals__['execute'],'scanner')
        frame=(b'\x1b]3008;start='+b'0'*32+b';user=root;hostname=arctic-ci;machineid='+b'1'*32+b';bootid='+b'2'*32+b';pid=123;pidfdid=456;comm=(agetty);servicename=serial-getty@ttyS0.service;invocationid='+b'3'*32+b';type=service\x1b\\')
        self.assertEqual(scanner.external_text(frame),frame)
        for raw in (b'serial-getty@ttyS0.service\n',frame.replace(b'ttyS0',b'ttyS99'),frame.replace(b'arctic-ci',b'foreign-host'),frame.replace(b';type=service',b';password=synthetic;type=service'),frame[:-2],frame.replace(b'pid=123;',b'pid=2147483648;'),frame+b'\npassword=synthetic\n'):
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError):scanner.external_text(raw)
    def test_failure_snapshot_selects_same_wholebuffer_scanner(self):
        wrapped,observed,original,state=self.build();execute=original.__globals__['execute']
        scanner=H.cell(execute,'scanner');old=H.cell(execute,'old')
        adapter=H.cell(execute,'observer_adapter');manifest=H.cell(execute,'source_manifest')
        frame=(b'\x1b]3008;start='+b'0'*32+b';user=root;hostname=arctic-ci;machineid='+b'1'*32+b';bootid='+b'2'*32+b';pid=123;pidfdid=456;comm=(agetty);servicename=serial-getty@ttyS0.service;invocationid='+b'3'*32+b';type=service\x1b\\')
        with tempfile.TemporaryDirectory() as folder:
            private=Path(folder)/'private';private.mkdir(mode=0o700);vm=private/'vm';vm.mkdir(mode=0o700)
            (vm/'serial-install.log').write_bytes(frame);(vm/'serial-install.log').chmod(0o600)
            (vm/'serial-boot.log').write_bytes(frame+b'\npassword=synthetic\n');(vm/'serial-boot.log').chmod(0o600)
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                files,finite=execute.__globals__['snapshot'](vm,{},old,scanner,manifest['allowed_sites'],adapter)
            self.assertEqual(gzip.decompress(files['serial-install.log.gz']),frame)
            self.assertNotIn('serial-boot.log.gz',files)
            self.assertEqual(finite['member_status']['serial-install.log'],'screened')
            self.assertEqual(finite['member_status']['serial-boot.log'],'privacy-rejected')
            self.assertFalse(finite['qualification_supplied']);self.assertFalse(finite['release_acceptance'])
    def test_selected_buffer_drift_rejected_before_composition(self):
        value=self.value();value['execution_files']=dict(value['execution_files'])
        value['execution_files'][C.SCANNER_BINDING['selected_path']]='0'*64
        with self.assertRaises(AssertionError):self.build(value)
    def test_original_manifest_projection_cannot_change(self):
        wrapped,observed,original,state=self.build();admission=wrapped.__globals__['C']
        value=admission.manifest(admission.strict_json((ROOT/'tools/final-bios-install/execution-manifest.json').read_bytes()),True)
        self.assertIsNone(admission.guard(value,Path('/synthetic-source-only'),None))
        for key,changed in [('install_timeout',2401),('harness_seconds',6601),('firmware','uefi'),('boot_network','online')]:
            bad=dict(value,**{key:changed})
            with self.subTest(key=key),self.assertRaises(RuntimeError):admission.guard(bad,Path('/synthetic-source-only'),None)
    def test_mapping_descriptor_typed_and_complete(self):
        for key,changed in [('runtime_cause_proven',0),('selected_path','tools/native-functional/screen-evidence.py'),('selected_sha256','0'*64),('release_acceptance',True)]:
            value=self.value();value['scanner_binding']=dict(value['scanner_binding'],**{key:changed})
            with self.subTest(key=key),self.assertRaises(RuntimeError):C.manifest(value)
            with self.subTest(key=key),self.assertRaises(RuntimeError):self.build(value)
        value=self.value();value['scanner_binding']['extra']='unknown'
        with self.assertRaises(RuntimeError):C.manifest(value)
        with self.assertRaises(RuntimeError):self.build(value)
    def test_boundary_exact_code_and_absence(self):
        raw=b'def f():\n return RuntimeError\n'
        ns={'__builtins__':__builtins__};exec(compile(raw,'public-fixture','exec'),ns)
        f=ns['f'];boundary=H.Boundary(f,raw)
        capture=[]
        def tracer(frame,event,arg):
            if frame.f_code is f.__code__ and event=='call':capture.append(boundary.owns(frame))
            return tracer
        old=sys.gettrace()
        try:sys.settrace(tracer);f()
        finally:sys.settrace(old)
        self.assertEqual(capture,[True]);capture.clear();ns['RuntimeError']=ValueError
        try:sys.settrace(tracer);f()
        finally:sys.settrace(old)
        self.assertEqual(capture,[False]);del ns['RuntimeError']
        prior=f.__code__;f.__code__=prior.replace();self.assertEqual(f.__code__,prior);self.assertIsNot(f.__code__,prior)
        capture.clear()
        try:sys.settrace(tracer);f()
        finally:sys.settrace(old)
        self.assertEqual(capture,[False])
if __name__=='__main__':unittest.main()
