"""Original installed TTY flow and input methods; no actual guest/PAM claim."""
import ast, contextlib, hashlib, importlib.util, io, json, os, re, subprocess
from pathlib import Path
import tempfile, unittest
from types import SimpleNamespace
from unittest import mock
HERE=Path(__file__).resolve().parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
D=load('installed_auth_actual_driver',HERE/'driver.py');V=load('installed_auth_original_VM',HERE.parent/'lib/vmtest.py')
class InstalledAuthDiagnostics(unittest.TestCase):
    def run_original(self,reply='accepted',ocr=b'Login incorrect\n',private_echo=False):
        from PIL import Image
        token='1'*32; secret='f'*32;clock=[0.0];calls=[]
        class VM(V.VM):
            def __init__(self,path):self.path=path
            def alive(self):return True
            def cmd(self,name,**arguments):
                # Never retain private input key events or arguments.
                if name in ('input-send-event','send-key'):calls.append(name)
                if name=='input-send-event' and reply=='refused':return {'error':{'desc':'private transport refusal'}}
                if name=='input-send-event' and reply=='exception':raise OSError('private transport exception')
                return {'return':{}}
            def shot(self,name):return str(self.path)
        def now():clock[0]+=.5;return clock[0]
        def wait(x):clock[0]+=x
        seen=[0]
        def ocr_call(*a,**kw):
            seen[0]+=1
            return SimpleNamespace(stdout=secret.encode()+b'\n' if private_echo else b'Password:\n' if seen[0]==1 else ocr)
        with tempfile.TemporaryDirectory(prefix='owned-installed-auth-source-') as t:
            root=Path(t);(root/'data').mkdir();(root/'data/active-credentials.json').write_text(json.dumps({'password':secret}));png=root/'prompt.png';Image.new('RGB',(1280,720)).save(png)
            vm=VM(png);before=set(vm.__dict__)
            startup=SimpleNamespace(console_screen=lambda path:True);vmtest=SimpleNamespace(looks_like_boot_menu=lambda path:False,classify=lambda path:'login')
            with mock.patch.object(D.time,'monotonic',side_effect=now),mock.patch.object(D.time,'sleep',side_effect=wait),mock.patch.object(D.subprocess,'run',side_effect=ocr_call):
                try:D.boot_installed(vm,startup,vmtest,root,{})
                except BaseException as e:error=e
                else:raise AssertionError('Original negative TTY fixture was accepted')
            self.assertEqual(set(vm.__dict__),before);self.assertIsNone(D._AUTH_ACTIVE)
            output=io.StringIO()
            with mock.patch.dict(os.environ,{'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN':token}),contextlib.redirect_stdout(output):D.diagnose('driver-installed-proof',error)
            text=output.getvalue();self.assertNotIn(secret,text);self.assertNotIn('private transport',text);self.assertNotIn('Login incorrect',text)
            raw=(HERE/'runner.py').read_bytes();node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='inner_codes');ns={'re':re,'_driver':D};exec(compile(ast.Module(body=[node],type_ignores=[]),'original_inner_codes','exec'),ns)
            codes=ns['inner_codes'](text.encode(),token);self.assertTrue(codes);self.assertTrue(all(x in D.DIAGNOSTIC_CODES for x in codes))
            self.assertTrue(all(x in D.AUTH_DIAGNOSTIC_CODES for x in D.installed_auth_codes(error)))
            return error,codes,calls
    def test_exact_original_boot_and_console_behavior_rolls_back(self):
        child=(HERE/'driver.py').read_text();base=subprocess.check_output(['git','-C',str(HERE),'show','0d10f5bb05be466ecba00b98ef9e4a568af2dcb3:tools/installer-qualification/driver.py'],text=True)
        a=child.index('# BEGIN INSTALLED_AUTH_FINITE_OBSERVER');b=child.index('# END INSTALLED_AUTH_FINITE_OBSERVER',a)+len('# END INSTALLED_AUTH_FINITE_OBSERVER\n\n');child=child[:a]+child[b:]
        child=child.replace("            if stage == 'driver-installed-proof':\n                for observation in installed_auth_codes(error):\n                    print('ARCTIC-INSTALLER-INNER ' + token + ' ' + observation, flush=True)\n",'',1)
        child=child.replace('        observe_installed_prompt(label, observed_line)\n','',1).replace('@observed_installed_auth\n','',1)
        self.assertEqual(child,base)
    def test_original_QMP_acceptance_does_not_claim_guest_delivery_or_PAM(self):
        e,codes,calls=self.run_original();self.assertIs(type(e),RuntimeError)
        self.assertIn('installer-inner-driver-installed-auth-getty-input-qmp-primary-accepted',codes)
        self.assertIn('installer-inner-driver-installed-auth-prompt-login-incorrect',codes)
        self.assertIn('installer-inner-driver-installed-auth-guest-input-delivery-unproven',codes)
        self.assertIn('installer-inner-driver-installed-auth-pam-result-unproven',codes)
    def test_original_primary_refusal_and_send_key_fallback_are_distinct(self):
        e,codes,calls=self.run_original(reply='refused')
        self.assertIn('installer-inner-driver-installed-auth-getty-input-qmp-primary-refused',codes)
        self.assertIn('installer-inner-driver-installed-auth-getty-input-qmp-send-key-accepted',codes)
        self.assertIn('input-send-event',calls);self.assertIn('send-key',calls)
    def test_original_input_exception_preserved_without_error_text(self):
        e,codes,calls=self.run_original(reply='exception');self.assertIs(type(e),OSError)
        self.assertTrue(any(x.endswith('-qmp-primary-exception') for x in codes))
    def test_unknown_OCR_operand_never_printed_or_hashed(self):
        e,codes,calls=self.run_original(ocr=b'private arbitrary operand\n')
        self.assertIn('installer-inner-driver-installed-auth-prompt-unknown',codes)
        self.assertFalse(any('arbitrary' in x or 'operand' in x for x in codes))
    def test_original_secret_nonappearance_guard_still_blocks_before_prompt_observation(self):
        e,codes,calls=self.run_original(private_echo=True);self.assertIs(type(e),RuntimeError)
        self.assertNotIn('installer-inner-driver-installed-auth-prompt-getty-password',codes)
        self.assertNotIn('installer-inner-driver-installed-auth-getty-input-qmp-primary-accepted',codes)
    def test_foreign_proof_and_copied_or_invalid_rows_do_not_emit(self):
        e=RuntimeError('private');self.assertEqual(D.installed_auth_codes(e),())
        for proof in [(object(),()),(D._AUTH_PROOF_TOKEN,['private']),(D._AUTH_PROOF_TOKEN,('private',)),(D._AUTH_PROOF_TOKEN,tuple(['private']*97))]:
            e.__dict__['_arctic_installer_installed_auth_observation']=proof;self.assertEqual(D.installed_auth_codes(e),())
        def foreign(*a,**kw):raise RuntimeError('private')
        self.assertIs(D.observed_installed_auth(foreign),foreign)
    def test_actual_valid_proof_copied_to_foreign_error_does_not_attest(self):
        owned,codes,calls=self.run_original();foreign=RuntimeError('private')
        foreign.__dict__['_arctic_installer_installed_auth_observation']=owned.__dict__['_arctic_installer_installed_auth_observation']
        self.assertEqual(D.installed_auth_codes(foreign),())
    def test_foreign_prompt_caller_cannot_mint_known_context(self):
        owner={'phase':'installed-display','codes':set()}
        with mock.patch.object(D,'_AUTH_ACTIVE',owner):D.observe_installed_prompt('installed-getty-password','Password:')
        self.assertEqual(owner,{'phase':'installed-display','codes':set()})
if __name__=='__main__':unittest.main(verbosity=2)
