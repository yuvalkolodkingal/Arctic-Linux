"""Execute source-bound pre-Probe and whole-UART boundaries; no VM/PAM claim."""
import ast
import base64
import contextlib
import copy
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
import zlib
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as C
import guest as G
import run as R


def context():
    return dict(schema='arctic-final-installed-ui-context-v1',nonce='a'*32,
        execution_sha='b'*40,source_sha='326690f173d4dc4f049f43e046c8380e66825a07',
        iso_sha256='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',
        native_sha256='c'*64,ui_sha256='d'*64)


def records(text):
    return [json.loads(line[len(G.GUEST_OBSERVATION_PREFIX):]) for line in text.splitlines()
            if line.startswith(G.GUEST_OBSERVATION_PREFIX)]


def without_guest_observation(body):
    start=body.index('# BEGIN SOURCE-CLOSED GUEST PREPROBE OBSERVATION\n')
    end=body.index('# END SOURCE-CLOSED GUEST PREPROBE OBSERVATION\n',start)+len('# END SOURCE-CLOSED GUEST PREPROBE OBSERVATION\n\n\n')
    body=body[:start]+body[end:]
    suffix='\n# Exact Source call spans, bound to the loaded code objects above.\n'
    body=body[:body.index(suffix)]
    new='''    validate_context(context)
    probe = _preprobe(native, context)
    if probe is None:
        return 0
'''
    old='''    validate_context(context)
    require(len(sys.argv) == 2 and sys.argv[1] in ('live', 'installed'), 'stage')
    require(Path(__file__).parent == Path('/run/t')
            and os.geteuid() == 0, 'owned-data-cd')
    native['guest_guard'](sys.argv[1], True)
    if sys.argv[1] == 'live':
        print('ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS', flush=True)
        return 0
    prefix = native['discover_desktop']()
    require(prefix[:5] == ['runuser', '-u', 'ci', '--', 'env'] and not any(
            value.startswith(('ARCTIC_UPDATE_STATUS=', 'ARCTIC_WALLPAPER_TEST_BUS=')) for value in prefix),
            'fixture-user-and-production-backends')
    probe = Probe(native, prefix, context)
'''
    assert body.count(new)==1
    return body.replace(new,old,1)


def without_host_projection(body):
    start=body.index('# BEGIN SOURCE-CLOSED GUEST UART PROJECTION\n')
    end=body.index('# END SOURCE-CLOSED GUEST UART PROJECTION\n',start)+len('# END SOURCE-CLOSED GUEST UART PROJECTION\n\n\n')
    body=body[:start]+body[end:]
    new="'host-failure.json','guest-preprobe-observation.json',"
    assert body.count(new)==1;body=body.replace(new,"'host-failure.json',",1)
    new="            if name=='guest-preprobe-observation.json':validate_guest_projection(C.strict_json(data))\n"
    assert body.count(new)==1;body=body.replace(new,'',1)
    new="    if 'guest-preprobe-observation.json' in files:\n        host=C.strict_json(files['host-status.json']);projection=C.strict_json(files['guest-preprobe-observation.json'])\n        C.require(host.get('status')=='failed' and host.get('context')==projection['context'],\n            'Guest projection differs from failed original host')\n"
    assert body.count(new)==1;body=body.replace(new,'',1)
    new='''                try:
                    diagnostic=guest_uart_projection(private,context,scanner)
                    data=(json.dumps(diagnostic,sort_keys=True,indent=2)+'\n').encode()
                    C.require(scanner.external_text(data)==data,'Guest observation privacy rejected')
                    C.exclusive(public/'guest-preprobe-observation.json',data)
                except BaseException:pass  # Guest observation never masks the original failure.
'''
    # Source uses a literal backslash-n in its serializer.
    new=new.replace("+'\n').encode()", "+'\\n').encode()")
    assert body.count(new)==1
    return body.replace(new,'',1)


class GuestDiagnosis(unittest.TestCase):
    def setUp(self):
        self.scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_guest_actual_scanner')
        self.output=io.StringIO()

    def invoke(self,native,stage='live',directory='/run/t',ctx=None):
        with patch.object(G,'__file__',directory+'/guest-check.py'), \
             patch.object(sys,'argv',[directory+'/guest-check.py',stage]), \
             patch.object(G.os,'geteuid',return_value=0), contextlib.redirect_stdout(self.output):
            return G.main(native,context() if ctx is None else ctx)

    def native(self):
        body=(C.ROOT/'tools/native-functional/native_smoke.py').read_text()
        namespace={'__name__':'owned_final_ui_native','__file__':'/run/t/guest-check.py'}
        exec(compile(body,'/run/t/guest-check.py','exec'),namespace)
        return namespace

    def test_context_marker_precedes_native_guard_and_original_live_marker(self):
        calls=[]
        self.assertEqual(self.invoke({'guest_guard':lambda *a:calls.append(a)}),0)
        self.assertEqual(calls,[('live',True)])
        self.assertEqual(records(self.output.getvalue())[0]['phase'],'context-validated')
        self.assertTrue(self.output.getvalue().endswith('ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS\n'))
        self.assertEqual(self.scanner.external_text(self.output.getvalue().encode()),self.output.getvalue().encode())

    def test_actual_transport_decoder_and_guest_observer_do_not_collide(self):
        ctx=context()
        report=dict(schema='arctic-final-installed-ui-report-v1',context=ctx,
            status='failed',phase='appearance',error_class='RuntimeError',checks=[],
            selinux='Enforcing',visual_review_required=True,release_acceptance=False)
        data=(json.dumps(report,sort_keys=True)+'\n').encode();compressed=zlib.compress(data)
        inventory=[dict(name='report.json',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
            compressed_bytes=len(compressed),chunks=1)]
        wire=('ARCTIC-FINAL-UI-BEGIN '+json.dumps(ctx)+'\n'
            +'ARCTIC-FINAL-UI-CHUNK '+json.dumps(dict(name='report.json',index=0,
                data=base64.b64encode(compressed).decode()))+'\n'
            +'ARCTIC-FINAL-UI-MANIFEST '+json.dumps(inventory)+'\n'
            +'ARCTIC-FINAL-UI-END '+json.dumps(ctx)+'\n').encode()
        with contextlib.redirect_stdout(self.output):
            G.emit_guest_observation(ctx,'installed','observed','context-validated')
        observation=self.output.getvalue().encode()
        self.assertTrue(observation.startswith(b'ARCTIC-UI-GUEST-OBSERVATION '))
        self.assertFalse(observation.startswith(b'ARCTIC-FINAL-UI-'))
        combined=observation+wire
        self.assertEqual(self.scanner.external_text(combined),combined)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline=C.decode(wire,ctx,self.scanner,root/'baseline')
            observed=C.decode(combined,ctx,self.scanner,root/'observed')
            self.assertEqual(baseline,(report,inventory));self.assertEqual(observed,baseline)
            # Exact historical observation namespace reproduces the collision.
            historical=observation.replace(b'ARCTIC-UI-GUEST-OBSERVATION ',
                b'ARCTIC-FINAL-UI-GUEST-OBSERVATION ',1)+wire
            self.assertEqual(self.scanner.external_text(historical),historical)
            with self.assertRaises(RuntimeError):C.decode(historical,ctx,self.scanner,root/'historical')
            self.assertFalse((root/'historical').exists())
            # The separately parsed fixed observer record survives on the same UART.
            private=root/'private';(private/'vm').mkdir(parents=True)
            (private/'vm/serial-boot.log').write_bytes(combined)
            projected=R.guest_uart_projection(private,ctx,self.scanner)
            self.assertEqual(len(projected['stages']['installed']['records']),1)
            (private/'vm/serial-boot.log').write_bytes(b'transcript: private sentinel\n'+combined)
            rejected=R.guest_uart_projection(private,ctx,self.scanner)
            self.assertEqual(rejected['stages']['installed']['privacy'],'rejected')
            self.assertEqual(rejected['stages']['installed']['records'],[])

    def test_actual_source_stage_and_owned_mount_guards_keep_primary(self):
        for stage,directory,label in [('foreign','/run/t','guest-stage'),('live','/data','guest-owned-data-cd')]:
            self.output=io.StringIO();calls=[]
            with self.assertRaises(RuntimeError):self.invoke({'guest_guard':lambda *a:calls.append(a)},stage,directory)
            values=records(self.output.getvalue())
            self.assertEqual(values[-1]['guard'],label);self.assertEqual(values[-1]['status'],'failed')
            self.assertEqual(calls,[])

    def test_loaded_native_authorization_and_command_exit_are_source_bound(self):
        for which,label in [('virtualization','native-root-virtualized'),('enforcing','native-enforcing'),('command','native-command-exit')]:
            self.output=io.StringIO();native=self.native()
            if which=='command':
                result=types.SimpleNamespace(stdout=b'',stderr=b'private-command-operand',returncode=7)
                with patch.object(native['subprocess'],'run',return_value=result),self.assertRaises(RuntimeError):
                    self.invoke(native)
            else:
                def execute(argv,**kwargs):
                    return 0, ('container' if which=='virtualization' else 'kvm') if argv==['systemd-detect-virt'] else 'Permissive', ''
                native['execute']=execute
                with self.assertRaises(RuntimeError):self.invoke(native)
            value=records(self.output.getvalue())[-1]
            self.assertEqual(value['guard'],label);self.assertEqual(value['phase'],'native-authorization')
            self.assertNotIn('private-command-operand',self.output.getvalue())

    def test_foreign_lookalike_fake_repr_and_reporting_failure_preserve_original(self):
        class Foreign(RuntimeError):
            def __str__(self):raise AssertionError('exception text read')
            def __repr__(self):raise AssertionError('exception repr read')
        error=Foreign('private-operand')
        def failure(*args):raise error
        with self.assertRaises(Foreign) as caught:self.invoke({'guest_guard':failure})
        self.assertIs(caught.exception,error)
        value=records(self.output.getvalue())[-1]
        self.assertEqual((value['guard'],value['error_class']),('unknown','OtherError'))
        self.output=io.StringIO()
        with patch('builtins.print',side_effect=OSError('synthetic closed stdout')),self.assertRaises(Foreign) as caught:
            self.invoke({'guest_guard':failure})
        self.assertIs(caught.exception,error);self.assertNotIn('private-operand',self.output.getvalue())

    def test_invalid_context_never_serializes_and_closed_values_reject(self):
        bad=context();bad['private-field']='private-operand'
        with self.assertRaises(RuntimeError):self.invoke({'guest_guard':lambda *a:None},ctx=bad)
        self.assertEqual(self.output.getvalue(),'')
        self.invoke({'guest_guard':lambda *a:None});value=records(self.output.getvalue())[0]
        for field,changed in [('guard','foreign'),('error_class','PrivateError'),('ui_acceptance',True),('raw_error_exported',True),('stage','private-stage')]:
            other=copy.deepcopy(value);other[field]=changed
            with self.assertRaises(RuntimeError):G.validate_guest_observation(other)

    def test_whole_original_privacy_precedes_guest_projection(self):
        self.invoke({'guest_guard':lambda *a:None});wire=self.output.getvalue().encode()
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);(private/'vm').mkdir();p=private/'vm/serial-install.log'
            p.write_bytes(wire)
            value=R.guest_uart_projection(private,context(),self.scanner)
            self.assertEqual(value['stages']['live']['privacy'],'passed')
            self.assertEqual(len(value['stages']['live']['records']),2)
            p.write_bytes(b'transcript: private sentinel\n'+wire)
            value=R.guest_uart_projection(private,context(),self.scanner)
            self.assertEqual(value['stages']['live']['privacy'],'rejected')
            self.assertEqual(value['stages']['live']['records'],[])

    def test_duplicate_foreign_context_and_stage_are_rejected(self):
        self.invoke({'guest_guard':lambda *a:None});wire=self.output.getvalue().encode()
        first=records(self.output.getvalue())[0]
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);(private/'vm').mkdir();p=private/'vm/serial-install.log'
            for bad in [wire+wire, G.GUEST_OBSERVATION_PREFIX.encode()+json.dumps(dict(first,stage='installed')).encode()+b'\n']:
                p.write_bytes(bad)
                with self.assertRaises(RuntimeError):R.guest_uart_projection(private,context(),self.scanner)
            changed=copy.deepcopy(first);changed['context']['nonce']='e'*32
            p.write_text(G.GUEST_OBSERVATION_PREFIX+json.dumps(changed)+'\n')
            with self.assertRaises(RuntimeError):R.guest_uart_projection(private,context(),self.scanner)

    def test_failure_only_host_projection_and_guard_roles_are_closed(self):
        self.invoke({'guest_guard':lambda *a:None})
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp)/'private';(private/'vm').mkdir(parents=True)
            (private/'vm/serial-install.log').write_text(self.output.getvalue())
            projection=R.guest_uart_projection(private,context(),self.scanner)
            for accepted in (False,True):
                public=Path(tmp)/('failed' if not accepted else 'passed');public.mkdir()
                (public/'host-status.json').write_text(json.dumps(dict(context=context(),status='passed' if accepted else 'failed')))
                (public/'guest-preprobe-observation.json').write_text(json.dumps(projection))
                output=Path(tmp)/('screen-failed' if not accepted else 'screen-passed')
                if accepted:
                    with self.assertRaises(RuntimeError):R.screen(public,output)
                else:
                    R.screen(public,output)
                    self.assertEqual((output/'guest-preprobe-observation.json').read_bytes(),(public/'guest-preprobe-observation.json').read_bytes())
        value=dict(records(self.output.getvalue())[0],status='failed',phase='owned-data-cd',
            error_class='RuntimeError',guard='guest-stage')
        with self.assertRaises(RuntimeError):G.validate_guest_observation(value)

    def test_original_guest_and_host_whole_bytes_restore_exactly(self):
        for name,rollback in [('guest.py',without_guest_observation),('run.py',without_host_projection)]:
            old=subprocess.check_output(['git','show','4bf65d3b09ca98558fe2f213910fb1925133453c:tools/final-installed-ui-live-mount/'+name],cwd=C.ROOT).decode()
            current=(HERE/name).read_text().replace('final-installed-ui-guest-diagnostic','final-installed-ui-live-mount')
            self.assertEqual(rollback(current),old)
        native=(C.ROOT/'tools/native-functional/native_smoke.py').read_text()
        for name,spans in G.NATIVE_PREPROBE_SPANS.items():
            function=next(x for x in ast.parse(native).body if isinstance(x,ast.FunctionDef) and x.name==name)
            calls=sorted([x for x in ast.walk(function) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='require'],key=lambda x:x.lineno)
            self.assertEqual([(x.lineno,x.end_lineno) for x in calls],[(a,b) for a,b,_ in spans])


if __name__=='__main__':unittest.main()
