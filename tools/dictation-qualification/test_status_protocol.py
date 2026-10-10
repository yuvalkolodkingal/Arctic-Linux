"""Synthetic status protocol controls; no GPU, microphone, model or VM claims."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
from test_command_output_diagnostics import restore_command_output_diagnostics

sys.path.insert(0,str(Path(__file__).parent))
import contract as c
SPEC=importlib.util.spec_from_file_location('status_protocol_guest',Path(__file__).with_name('guest_check.py'))
guest=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(guest)
PRIVATE='synthetic-private-transcript-audio-password-stderr'
ORIGINAL_GUEST_SHA256='cfa23327fe71aa43d2b6ca00d40920bd5006f858c884bf25c037d9efaeb6138c'
ORIGINAL_STATUS="    def status(self, verb='status', *args, check=True):\n        result = self.cmd(['/usr/bin/arctic-dictation', verb, *args], check=check)\n        require(len(result.stdout) <= 16384, 'status-byte-bound')\n        value = json.loads(result.stdout)\n        require(isinstance(value, dict) and {key: value.get(key) for key in PROFILES[self.profile_id]} == PROFILES[self.profile_id]\n                and all(type(value.get(key)) is type(item) for key, item in PROFILES[self.profile_id].items())\n                and value.get('version') == '1.1.0' and value.get('profile_selection') == 'recommended'\n                and value.get('recommended_profile') == PROFILES[self.profile_id]\n                and value.get('compatibility_profile') == PROFILES['small-v2'], 'status-profile-descriptor-pin')\n        for key, descriptor in (('recommended_profile', PROFILES[self.profile_id]), ('compatibility_profile', PROFILES['small-v2'])):\n            require(all(type(value[key].get(field)) is type(item) for field, item in descriptor.items()),\n                    'status-profile-byte-types')\n        require(value.get('compatibility_required') is False, 'optimized-cpu-incompatible')\n        require(value.get('active_backend') in ('', 'cpu', 'vulkan'), 'status-backend-unknown')\n        if value.get('active_backend') == 'vulkan':\n            require(self.profile_id == 'turbo-q5-v3' and value.get('active_cpu_variant') == '', 'status-backend-profile')\n        elif value.get('active_backend') == 'cpu':\n            require(value.get('active_cpu_variant') == PROFILES[self.profile_id]['cpu_variant'], 'status-cpu-variant-profile')\n        else:\n            require(value.get('active_cpu_variant') == '', 'status-idle-cpu-variant')\n        self.snapshots.append(result.stdout.decode())\n        self._wait_last_status = wait_status_projection(value)\n        return value\n"

def restore_status_protocol(text):
    """Reverse only the new method; the whole old helper digest proves closure."""
    text=restore_command_output_diagnostics(text)
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name=='status')
    lines=text.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno]=ORIGINAL_STATUS.splitlines(keepends=True)
    return ''.join(lines)

class StatusProtocolControls(unittest.TestCase):
    def value(self,**changes):
        value={**c.PROFILES['turbo-q5-v3'],'ok':True,'state':'ready','error':'','version':'1.1.0',
            'profile_selection':'recommended','recommended_profile':c.PROFILES['turbo-q5-v3'],
            'compatibility_profile':c.PROFILES['small-v2'],'compatibility_required':False,
            'active_backend':'cpu','active_cpu_variant':'avx2'}
        value.update(changes);return value
    def checker(self):
        v=guest.Checker.__new__(guest.Checker);v.profile_id='turbo-q5-v3';v.snapshots=[];v.prefix=[];return v
    def invoke(self,value,code=0,stderr=b'',verb='status',check=True):
        raw=value if type(value)is bytes else json.dumps(value).encode()
        response=subprocess.CompletedProcess([],code,stdout=raw,stderr=stderr);v=self.checker()
        with mock.patch.object(guest.subprocess,'run',return_value=response) as called:
            result=v.status(verb,check=check)
        return result,v,called
    def reject(self,value,code=0,stderr=b''):
        with self.assertRaises((c.Invalid,ValueError,TypeError)):self.invoke(value,code,stderr)
    def test_success_and_official_setup_error_exit_zero_are_preserved(self):
        for state in ('ready','queued','downloading','unavailable','error'):
            value=self.value(state=state,error=PRIVATE if state=='error' else '')
            result,v,called=self.invoke(value)
            self.assertEqual(result,value);self.assertEqual(len(v.snapshots),1)
            self.assertEqual(called.call_args.kwargs['timeout'],20)
            self.assertEqual(called.call_args.args[0],['/usr/bin/arctic-dictation','status'])
    def test_valid_error_exit_one_is_observed_under_original_budget(self):
        value=self.value(ok=False,state='error',error=PRIVATE)
        result,v,_=self.invoke(value,1)
        self.assertEqual(result,value);self.assertEqual(v._wait_last_status,('error','cpu'))
        v.status=mock.Mock(return_value=result);budgets=[]
        def wait(fn,seconds):budgets.append(seconds);return fn()
        with mock.patch.object(guest,'wait',side_effect=wait):
            result=v.observe('terminal-state',lambda:(s if (s:=v.status()).get('state')=='error' else None),10)
        self.assertEqual(budgets,[10]);self.assertEqual(result,value)
    def test_exit_types_and_ok_state_error_mismatch_are_rejected(self):
        for code in (-9,2,7,255,True,False,1.0,'1',None):
            with self.subTest(code_type=type(code).__name__):self.reject(self.value(ok=False,state='error',error=PRIVATE),code)
        for code,ok in ((0,False),(1,True),(0,None),(0,1),(1,0),(1,'false')):
            self.reject(self.value(ok=ok,state='error',error=PRIVATE),code)
        for state in ('ready','recording','transcribing','queued','unavailable',None,1):
            self.reject(self.value(ok=False,state=state,error=PRIVATE),1)
        for error in ('',None,False,17,[],{}):self.reject(self.value(ok=False,state='error',error=error),1)
    def test_stderr_rejected_without_private_export(self):
        for stderr in (PRIVATE.encode(),b'\n',PRIVATE,None,False):
            self.reject(self.value(ok=False,state='error',error=PRIVATE),1,stderr)
        v=self.checker();v.gates={'gpu-runtime-failure-cpu-retry'};v.report={'gates':[]}
        v.cmd=mock.Mock(return_value=subprocess.CompletedProcess([],1,stdout=json.dumps(self.value(ok=False,state='error',error=PRIVATE)).encode(),stderr=PRIVATE.encode()))
        self.assertFalse(v.gate('gpu-runtime-failure-cpu-retry',lambda:v.status()))
        self.assertEqual(v.report['gates'][0]['code'],'status-command-outcome')
        self.assertNotIn(PRIVATE,json.dumps(v.report))
    def test_malformed_duplicate_nested_nonfinite_nonobject_json_rejects_privately(self):
        raw=json.dumps(self.value()).encode()
        bads=(PRIVATE.encode(),b'{'+PRIVATE.encode(),b'[]',b'null',b'0',b'true',
            raw[:-1]+b',"ok":true}',raw.replace(b'"active_backend": "cpu"',b'"active_backend": NaN'),
            raw.replace(b'"recommended_profile": {',b'"recommended_profile": {"profile":"duplicate",'))
        for bad in bads:self.reject(bad)
        for bad in (b'{'+PRIVATE.encode(),raw[:-1]+b',"ok":true}'):
            v=self.checker();v.gates={'gpu-runtime-failure-cpu-retry'};v.report={'gates':[]}
            v.cmd=mock.Mock(return_value=subprocess.CompletedProcess([],0,stdout=bad,stderr=b''))
            self.assertFalse(v.gate('gpu-runtime-failure-cpu-retry',lambda:v.status()))
            self.assertNotIn(PRIVATE,json.dumps(v.report));self.assertEqual(v.report['gates'][0]['observations'],{})
    def test_original_profile_backend_and_cpu_validation_remains(self):
        for key,bad,code in [('model','small','status-profile-descriptor-pin'),
            ('download_bytes',678117115.0,'status-profile-descriptor-pin'),
            ('active_backend','untrusted','status-backend-unknown'),
            ('active_cpu_variant','baseline','status-cpu-variant-profile'),
            ('compatibility_required',True,'optimized-cpu-incompatible')]:
            with self.assertRaisesRegex(c.Invalid,'^'+code+'$'):
                self.invoke(self.value(ok=False,state='error',error=PRIVATE,**{key:bad}),1)
    def test_action_command_check_and_args_remain_exact(self):
        for verb,args in [('start',()),('stop',()),('cancel',()),('set-backend',('vulkan',)),('set-language',('he',))]:
            for check in (True,False):
                response=subprocess.CompletedProcess([],1,stdout=json.dumps(self.value(ok=False,state='error',error=PRIVATE)).encode(),stderr=b'');v=self.checker()
                with mock.patch.object(guest.subprocess,'run',return_value=response) as called:
                    if check:
                        with self.assertRaisesRegex(c.Invalid,'^command-failed$'):v.status(verb,*args,check=check)
                    else:self.assertEqual(v.status(verb,*args,check=check)['state'],'error')
                    self.assertEqual(called.call_args.args[0],['/usr/bin/arctic-dictation',verb,*args])
                    self.assertEqual(called.call_args.kwargs['timeout'],20)
    def test_status_and_whole_command_byte_limits_remain_exact(self):
        with self.assertRaisesRegex(c.Invalid,'^status-byte-bound$'):self.invoke(b' '*16385)
        response=subprocess.CompletedProcess([],0,stdout=b' '*16777216,stderr=b'')
        with mock.patch.object(guest.subprocess,'run',return_value=response):
            with self.assertRaisesRegex(c.Invalid,'^command-output-bound$'):self.checker().status()
    def test_complete_old_helper_byte_and_ast_closure(self):
        text=Path(guest.__file__).read_text();restored=restore_status_protocol(text)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),ORIGINAL_GUEST_SHA256)
        old=ast.parse(restored);new=ast.parse(restore_command_output_diagnostics(text))
        for name in ('run','wait','gate','gpu_failure','microphone','transcribe'):
            select=lambda t:next(n for n in ast.walk(t) if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(select(new),include_attributes=False),ast.dump(select(old),include_attributes=False))

if __name__=='__main__':unittest.main()

