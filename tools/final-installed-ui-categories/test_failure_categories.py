"""Closed failure categories are observations, never UART/UI admission or authentication."""
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as C
import guest as G
import run as R


def without_categories(body):
    marker='# BEGIN SOURCE-CLOSED FAILURE CATEGORY CHANNEL\n'
    if marker not in body:return body
    start=body.index(marker);end=body.index('# END SOURCE-CLOSED FAILURE CATEGORY CHANNEL\n',start)
    end+=len('# END SOURCE-CLOSED FAILURE CATEGORY CHANNEL\n\n\n')
    body=body[:start]+body[end:]
    replacements=[
        ("'guest-preprobe-observation.json','guest-failure-categories.json',","'guest-preprobe-observation.json',"),
        ("            if name=='guest-failure-categories.json':validate_categories(C.strict_json(data))\n",''),
        ("    if 'guest-failure-categories.json' in files:\n        C.require(C.strict_json(files['host-status.json']).get('status')=='failed',\n            'Failure categories require the original failed host')\n",''),
        ("""                try:
                    diagnostic=guest_failure_categories(private,context)
                    data=(json.dumps(diagnostic,sort_keys=True,indent=2)+'\\n').encode()
                    C.require(scanner.external_text(data)==data,'Failure category privacy rejected')
                    C.exclusive(public/'guest-failure-categories.json',data)
                except BaseException:pass  # Categories never change the original failure or UART admission.
""",'')]
    for new,old in replacements:
        assert body.count(new)==1,new
        body=body.replace(new,old,1)
    return body


def context():
    value=C.strict_json((HERE/'execution-manifest.json').read_bytes())
    return dict(schema='arctic-final-installed-ui-context-v1',nonce='a'*32,
        execution_sha=C.git('rev-parse','HEAD'),source_sha=value['image']['source_sha'],
        iso_sha256=value['image']['sha256'],
        native_sha256=value['source_files']['tools/native-functional/native_smoke.py'],
        ui_sha256=value['execution_files'][C.PREFIX+'guest.py'])


def record(ctx,stage='live',status='observed',phase='context-validated',guard='unknown',error_class='none'):
    return dict(schema='arctic-final-ui-guest-preprobe-v1',context=ctx,stage=stage,
        status=status,phase=phase,guard=guard,error_class=error_class,
        ui_acceptance=False,release_acceptance=False,raw_error_exported=False)


def wire(*records):
    return ''.join(G.GUEST_OBSERVATION_PREFIX+json.dumps(r,sort_keys=True)+'\n' for r in records).encode()


class FailureCategories(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.ctx=context()
        self.scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','category_actual_scanner')
        self.first=record(self.ctx)
        self.failed=record(self.ctx,status='failed',phase='native-authorization',
            guard='native-enforcing',error_class='RuntimeError')

    def original(self,data):
        path=self.root/'owned.log';path.write_bytes(data);path.chmod(0o600)
        return path

    def report(self,data):
        slot=R.category_slot(data,'live',self.ctx,G)
        return R.validate_categories(dict(schema='arctic-final-ui-failure-categories-v1',
            stages=dict(live=slot,installed=dict(status='unavailable',reason='absent',records=[])),
            source_text_observation_only=True,authenticated_guest_execution=False,
            original_UART_admission_used=False,raw_private_exported=False,
            ui_acceptance=False,release_acceptance=False))

    def test_rejected_original_retains_only_fixed_observations_and_remains_rejected(self):
        data=b'transcript: private sentinel\n'+wire(self.first,self.failed)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(Exception):
            self.scanner.external_text(data)
        value=self.report(data);projected=json.dumps(value).encode()
        self.assertEqual(value['stages']['live']['status'],'observed')
        self.assertEqual(value['stages']['live']['records'][-1]['guard'],'native-enforcing')
        self.assertEqual(self.scanner.external_text(projected),projected)
        for private in ('private sentinel',self.ctx['nonce'],self.ctx['execution_sha'],self.ctx['native_sha256']):
            self.assertNotIn(private,projected.decode())
        private=self.root/'private';(private/'vm').mkdir(parents=True)
        (private/'vm/serial-install.log').write_bytes(data)
        old=R.guest_uart_projection(private,self.ctx,self.scanner)
        self.assertEqual(old['stages']['live']['privacy'],'rejected')
        self.assertEqual(old['stages']['live']['records'],[])
        self.assertFalse(value['ui_acceptance']);self.assertFalse(value['authenticated_guest_execution'])

    def test_actual_guest_emitter_matches_closed_projection(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            G.emit_guest_observation(self.ctx,'live','observed','context-validated')
            G.emit_guest_observation(self.ctx,'live','failed','native-authorization','native-enforcing','RuntimeError')
        self.assertEqual(self.report(output.getvalue().encode()),self.report(wire(self.first,self.failed)))

    def test_declared_execution_and_image_source_context_are_bound(self):
        self.assertIsNotNone(R.category_context(self.ctx))
        for name in ('execution_sha','native_sha256','ui_sha256','source_sha','iso_sha256'):
            bad=dict(self.ctx);bad[name]='f'*len(bad[name])
            with self.assertRaises(RuntimeError):R.category_context(bad)

    def test_duplicate_foreign_private_suffix_and_record_bound_deny(self):
        changed=copy.deepcopy(self.first);changed['context']['nonce']='f'*32
        foreign=record(self.ctx,stage='installed')
        unknown=dict(self.first,private='private sentinel')
        cases=[(wire(self.first,self.first),'duplicate-record'),(wire(changed),'foreign-context'),
            (wire(foreign),'foreign-context'),(wire(unknown),'invalid-record'),
            (wire(self.first).rstrip()+b' private sentinel\n','invalid-record'),
            (b'prefix '+wire(self.first),'ambiguous-prefix'),
            (wire(self.first)+b'ARCTIC-UI-GUEST-OBSERVATION-PRIVATE operand\n','ambiguous-prefix'),
            (wire(self.first,record(self.ctx,phase='native-authorized'),self.failed,
                  record(self.ctx,status='failed',phase='probe-acquisition',error_class='OSError')),'record-bound')]
        for data,reason in cases:
            with self.subTest(reason=reason):
                slot=self.report(data)['stages']['live']
                self.assertEqual((slot['status'],slot['reason'],slot['records']),('denied',reason,[]))

    def test_utf8_json_nonfinite_duplicate_fields_and_line_bounds_deny(self):
        prefix=G.GUEST_OBSERVATION_PREFIX.encode()
        data=wire(self.first)
        cases=[(b'\xff'+data,'invalid-utf8'),(prefix+b'{"schema":NaN}\n','invalid-record'),
            (prefix+b'{"schema":"x","schema":"y"}\n','invalid-record'),
            (prefix+b' '+b'x'*8192,'line-bound')]
        for original,reason in cases:self.assertEqual(self.report(original)['stages']['live']['reason'],reason)

    def test_original_roles_and_sequence_are_required_in_public_validation(self):
        valid=self.report(wire(self.first,self.failed))
        for edit in ('phase','guard','status','error_class','stage','extra','sequence','duplicate','acceptance'):
            value=copy.deepcopy(valid);records=value['stages']['live']['records']
            if edit=='phase':records[-1]['phase']='desktop-discovery'
            elif edit=='guard':records[-1]['guard']='private-guard'
            elif edit=='status':records[-1]['status']='observed'
            elif edit=='error_class':records[-1]['error_class']='none'
            elif edit=='stage':records[-1]['stage']='unknown'
            elif edit=='extra':records[-1]['operand']='private'
            elif edit=='sequence':records.reverse()
            elif edit=='duplicate':records[:]=[records[0],records[0]]
            else:value['ui_acceptance']=True
            with self.subTest(edit=edit),self.assertRaises(RuntimeError):R.validate_categories(value)
        self.assertEqual(self.report(wire(self.failed))['stages']['live']['reason'],'sequence-denied')

    def test_failure_only_screening_never_admits_rejected_raw_uart(self):
        value=self.report(wire(self.first,self.failed))
        for passed,raw in ((False,False),(True,False),(False,True)):
            source=self.root/f'source-{passed}-{raw}';source.mkdir()
            (source/'host-status.json').write_text(json.dumps(dict(status='passed' if passed else 'failed')))
            (source/'guest-failure-categories.json').write_text(json.dumps(value))
            if raw:
                import gzip
                (source/'serial-install.log.gz').write_bytes(gzip.compress(b'transcript: private sentinel\n'))
            target=self.root/f'screen-{passed}-{raw}'
            if passed or raw:
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(Exception):R.screen(source,target)
                self.assertFalse(target.exists())
            else:
                R.screen(source,target)
                self.assertEqual((target/'guest-failure-categories.json').read_bytes(),(source/'guest-failure-categories.json').read_bytes())

    def test_owned_regular_read_rejects_owner_mode_size_symlink_and_fifo(self):
        path=self.original(wire(self.first));uid=os.getuid()
        self.assertEqual(R.category_original(path,8192,uid),path.read_bytes())
        with self.assertRaises(RuntimeError):R.category_original(path,8192,uid+1)
        with self.assertRaises(RuntimeError):R.category_original(path,1,uid)
        path.chmod(0o622)
        with self.assertRaises(RuntimeError):R.category_original(path,8192,uid)
        path.chmod(0o600);link=self.root/'link';link.symlink_to(path)
        with self.assertRaises(OSError):R.category_original(link,8192,uid)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(RuntimeError):R.category_original(fifo,8192,uid)

    def test_path_replacement_preserves_foreign_path_and_closes_original_fd(self):
        path=self.original(wire(self.first));original_read=os.read;seen=[]
        def replace(fd,count):
            seen.append(fd);path.rename(self.root/'retained-original');path.write_bytes(b'foreign original');path.chmod(0o600)
            return original_read(fd,count)
        with patch.object(R.os,'read',side_effect=replace),self.assertRaises(RuntimeError):
            R.category_original(path,8192,os.getuid())
        self.assertEqual(path.read_bytes(),b'foreign original')
        with self.assertRaises(OSError):os.fstat(seen[0])

    def test_foreign_reused_descriptor_remains_open_on_read_failure(self):
        path=self.original(wire(self.first));foreign=self.root/'foreign';foreign.write_bytes(b'foreign');foreign.chmod(0o600)
        held=os.open(foreign,os.O_RDONLY);reused=[];error=PermissionError('private operand')
        def replace(fd,count):
            os.dup2(held,fd);reused.append(fd);raise error
        try:
            with patch.object(R.os,'read',side_effect=replace),self.assertRaises(PermissionError) as caught:
                R.category_original(path,8192,os.getuid())
            self.assertIs(caught.exception,error)
            self.assertEqual(os.fstat(reused[0]).st_ino,os.fstat(held).st_ino)
        finally:
            for fd in set(reused+[held]):os.close(fd)

    def test_partial_read_mutation_is_denied_and_original_descriptor_reaped(self):
        path=self.original(wire(self.first));read=os.read;seen=[];changed=False
        def mutate(fd,count):
            nonlocal changed
            seen.append(fd)
            data=read(fd,min(count,10))
            if not changed:
                changed=True
                with path.open('ab') as output:output.write(b' private appended operand')
            return data
        with patch.object(R.os,'read',side_effect=mutate),self.assertRaises(RuntimeError):
            R.category_original(path,8192,os.getuid())
        self.assertTrue(path.read_bytes().endswith(b' private appended operand'))
        with self.assertRaises(OSError):os.fstat(seen[0])

    def test_complete_reader_missing_and_owned_stage_projection(self):
        private=self.root/'private';(private/'vm').mkdir(parents=True)
        expected=R.guest_failure_categories(private,self.ctx)
        self.assertEqual(expected['stages']['live']['reason'],'absent')
        path=private/'vm/serial-install.log';path.write_bytes(wire(self.first,self.failed));path.chmod(0o600)
        acquired=R.category_original;calls=[]
        def same_reader(path,limit,expected_uid=0):
            if path.name.startswith('serial-'):calls.append((path.name,limit))
            # Local actual UID fixture only; production deliberately requires Docker UID0.
            return acquired(path,limit,os.getuid() if expected_uid==0 else expected_uid)
        with patch.object(R,'category_original',side_effect=same_reader):
            actual=R.guest_failure_categories(private,self.ctx)
        self.assertEqual(actual['stages']['live'],self.report(wire(self.first,self.failed))['stages']['live'])
        self.assertEqual(calls,[('serial-install.log',16*1024*1024),('serial-boot.log',128*1024*1024)])
        self.assertEqual(actual['stages']['installed']['status'],'unavailable')

    def test_cancellation_and_reporting_failure_keep_the_original_exception(self):
        path=self.original(wire(self.first));error=KeyboardInterrupt('private operand');seen=[]
        def cancel(fd,count):seen.append(fd);raise error
        with patch.object(R.os,'read',side_effect=cancel),self.assertRaises(KeyboardInterrupt) as caught:
            R.category_original(path,8192,os.getuid())
        self.assertIs(caught.exception,error)
        with self.assertRaises(OSError):os.fstat(seen[0])
        primary=RuntimeError('original private operand')
        node=next(n for n in ast.walk(ast.parse(Path(R.__file__).read_text()))
            if isinstance(n,ast.If) and ast.unparse(n.test)=='primary is not None'
            and any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name)
                and x.func.id=='guest_failure_categories' for x in ast.walk(n)))
        namespace=dict(R.__dict__,primary=primary,primary_phase='harness',context=self.ctx,
            observations=[],private=self.root,public=self.root,scanner=self.scanner,
            failure_observation=lambda *a:{},guest_failure_categories=lambda *a:(_ for _ in ()).throw(error),
            guest_uart_projection=lambda *a:{})
        with patch.object(C,'exclusive',side_effect=OSError('private output failure')):
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-source-reporting-block>','exec'),namespace)
        self.assertIs(namespace['primary'],primary)

    def test_additive_channel_rolls_back_to_the_entire_actual_failed_source(self):
        original=without_categories(Path(R.__file__).read_text()).encode()
        self.assertEqual(hashlib.sha256(original).hexdigest(),'c9cfa9c27467b2a48a0a92c2b7ec5d77fd395ee2fa368d29330baed9dc2154eb')
        actual=subprocess.check_output(['git','show','9b3dd0d7c48d43eb2e478f4b8fab7a09e666f5b6:tools/final-installed-ui-guest-diagnostic/'+'run.py'],cwd=C.ROOT)
        self.assertEqual(original,actual)
        for name in ('guest.py','compose.py','common.py'):
            current=(HERE/name).read_bytes()
            if name=='common.py':
                current=current.decode().replace('final-installed-ui-categories','final-installed-ui-guest-diagnostic').replace(
                    "BASE = '9b3dd0d7c48d43eb2e478f4b8fab7a09e666f5b6'","BASE = '7a39d4dadce8e26ed9a899bd5a58af73f1ff8cb8'").replace(
                    "WORKFLOW = 'Final installed UI closed failure categories'",
                    "WORKFLOW = 'Final installed UI guest failure observation'").replace(
                    "'test_guest_diagnostic.py', 'test_failure_categories.py')}","'test_guest_diagnostic.py')}").encode()
            self.assertEqual(current,subprocess.check_output(['git','show',
                '9b3dd0d7c48d43eb2e478f4b8fab7a09e666f5b6:tools/final-installed-ui-guest-diagnostic/'+name],cwd=C.ROOT))

    def test_real_load_swap_restoration_counterfactual_and_closed_current_screen(self):
        original=(HERE/'guest.py').read_bytes();foreign_phase='foreign-phase-value-7b8c'
        foreign=original+('\nGUEST_OBSERVATION_PHASES += ('+repr(foreign_phase)+',)\n'
            'GUEST_FAILED_PHASES += ('+repr(foreign_phase)+',)\n').encode()
        path=self.root/'guest.py';path.write_bytes(original)
        old=types.ModuleType('owned_exact_e3f_category_source');old.__file__=str(self.root/'run.py')
        source=subprocess.check_output(['git','show',
            'e3f030170aa5dae4030f9b024e879f72ae43566b:tools/final-installed-ui-guest-diagnostic/'+'run.py'],cwd=C.ROOT)
        exec(compile(source,old.__file__,'exec'),old.__dict__)
        load=C.load;loaded=[]
        def swap(candidate,name):
            if Path(candidate)!=path:return load(candidate,name)
            path.write_bytes(foreign)
            try:result=load(candidate,name);loaded.append(name)
            finally:path.write_bytes(original)
            return result
        failed=dict(self.failed,phase=foreign_phase,guard='unknown')
        data=wire(self.first,failed)
        with patch.object(C,'load',side_effect=swap):
            guest=old.category_context(self.ctx)
            bad=dict(self.report(wire(self.first)),stages=dict(
                live=old.category_slot(data,'live',self.ctx,guest),
                installed=dict(status='unavailable',reason='absent',records=[])))
            old.validate_categories(bad)
            public=self.root/'public';public.mkdir()
            (public/'host-status.json').write_text(json.dumps(dict(status='failed')))
            (public/'guest-failure-categories.json').write_text(json.dumps(bad))
            old.screen(public,self.root/'old-admitted')
            self.assertEqual(bad['stages']['live']['records'][-1]['phase'],foreign_phase)
            self.assertGreaterEqual(len(loaded),3)
            with patch.object(R,'__file__',str(self.root/'run.py')):
                verified=R.category_context(self.ctx)
                self.assertNotIn(foreign_phase,verified.GUEST_OBSERVATION_PHASES)
                self.assertEqual(R.category_slot(data,'live',self.ctx,verified)['reason'],'invalid-record')
                with self.assertRaises(RuntimeError):R.validate_categories(bad)
                with self.assertRaises(RuntimeError):R.screen(public,self.root/'new-denied')
        self.assertFalse((self.root/'new-denied').exists())
        self.assertEqual(path.read_bytes(),original)

    def test_foreign_buffer_is_denied_after_path_restoration_before_compile(self):
        original=(HERE/'guest.py').read_bytes();path=self.root/'guest.py';path.write_bytes(original)
        foreign=original+b'\nSOURCE_FOREIGN_EXECUTION_SENTINEL=True\n'
        acquire=R.category_original;compiled=[]
        def changed(candidate,limit,expected_uid=0):
            if Path(candidate)!=path:return acquire(candidate,limit,expected_uid)
            path.write_bytes(foreign)
            try:return acquire(candidate,limit,expected_uid)
            finally:path.write_bytes(original)
        def forbidden(*args,**kwargs):compiled.append(args);raise AssertionError('Unpinned compile')
        with patch.object(R,'__file__',str(self.root/'run.py')), \
             patch.object(R,'category_original',side_effect=changed), \
             patch('builtins.compile',side_effect=forbidden),self.assertRaises(RuntimeError):
            R.category_guest()
        self.assertEqual(compiled,[]);self.assertEqual(path.read_bytes(),original)

    def test_verified_buffer_execution_ignores_later_foreign_path_substitution(self):
        original=(HERE/'guest.py').read_bytes();path=self.root/'guest.py';path.write_bytes(original)
        foreign=original+b'\nSOURCE_FOREIGN_EXECUTION_SENTINEL=True\n'
        acquire=R.category_original;compiled=[];actual_compile=compile
        def changed(candidate,limit,expected_uid=0):
            data=acquire(candidate,limit,expected_uid)
            if Path(candidate)==path:path.write_bytes(foreign)
            return data
        def same_buffer(source,filename,mode,*args,**kwargs):
            compiled.append((source,filename));return actual_compile(source,filename,mode,*args,**kwargs)
        try:
            with patch.object(R,'__file__',str(self.root/'run.py')), \
                 patch.object(R,'category_original',side_effect=changed),patch('builtins.compile',side_effect=same_buffer):
                guest=R.category_context(self.ctx)
                self.assertFalse(hasattr(guest,'SOURCE_FOREIGN_EXECUTION_SENTINEL'))
                self.assertEqual(compiled,[(original,str(path))])
                self.assertEqual(R.category_slot(wire(self.first,self.failed),'live',self.ctx,guest)['status'],'observed')
        finally:path.write_bytes(original)


if __name__=='__main__':unittest.main()
