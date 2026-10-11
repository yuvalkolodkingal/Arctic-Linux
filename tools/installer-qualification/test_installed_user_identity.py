"""Exact Source challenge and consumer controls; no guest/PAM qualification."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from PIL import Image

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

D = load('actual_installed_user_driver', HERE / 'driver.py')
F = load('actual_installed_user_consumer_fixture', HERE / 'test_active_contract.py')
A = F.A
P = load('actual_serial_neighbor_helper', HERE / 'screen-diagnostic.py')

def restore_driver_source(value):
    """Strict whole-byte inverse before the older observer rollback fixture."""
    begin = '# BEGIN INSTALLED_USER_NONCE_IDENTITY\n'
    end = '# END INSTALLED_USER_NONCE_IDENTITY\n\n\n'
    if value.count(begin) != 1 or value.count(end) != 1:
        raise AssertionError('UID identity block count differs')
    start = value.index(begin); last = value.index(end, start) + len(end)
    value = value[:start] + value[last:]
    pairs = (
        ('(frame.f_code is not console_prompt.__code__ and frame.f_code is not console_user_identity.__code__)',
         'frame.f_code is not console_prompt.__code__'),
        ('    nonce = uuid.uuid4().hex\n    shell = console_user_identity(vm,startup,out,nonce,password)\n',
         "    shell = console_prompt(vm,startup,out,'installed-login-shell','arcticqual@arctic-qual ~ >',password,archive=False)\n    nonce = uuid.uuid4().hex\n"),
        ('                login_shell=shell,\n',
         "                login_shell={key: shell[key] for key in ('prompt_kind','observed_line_sha256','observed_ns')},\n"),
    )
    for child, original in pairs:
        if value.count(child) != 1:
            raise AssertionError('UID identity inverse occurrence differs')
        value = value.replace(child, original, 1)
    if hashlib.sha256(value.encode()).hexdigest() != '2c91055fd85e75dbb88ea45bf611e12688e498677c91d377f92c83fa06d8e06c':
        raise AssertionError('UID identity whole historical Driver differs')
    return value

class InstalledUserIdentityControls(unittest.TestCase):
    nonce = '1234567890abcdef1234567890abcdef'
    secret = 'f'*32

    def exercise(self, outputs, late=False, console=True, size=(1280,720)):
        clock = [0.0]; calls = []; iterator = iter(outputs); prior = [b'']
        with tempfile.TemporaryDirectory(prefix='owned-user-proof-') as temporary:
            root = Path(temporary); probe = root/'probe.png'
            def shot(_):
                Image.new('RGB', size).save(probe)
                return probe
            vm = types.SimpleNamespace(alive=lambda:True, shot=shot,
                type_text=lambda text, gap: calls.append(('command', text, gap)),
                keys=lambda *keys: calls.append(('keys', keys)))
            def ocr(*args, **kwargs):
                prior[0] = next(iterator, prior[0])
                if late: clock[0] = 46.0
                return types.SimpleNamespace(stdout=prior[0])
            def sleep(seconds): clock[0] += seconds
            with patch.object(D.time,'monotonic',side_effect=lambda:clock[0]), \
                    patch.object(D.time,'sleep',side_effect=sleep), \
                    patch.object(D.time,'monotonic_ns',side_effect=lambda:int(clock[0]*1e9)+1), \
                    patch.object(D.subprocess,'run',side_effect=ocr):
                try:
                    proof = D.console_user_identity(vm,types.SimpleNamespace(console_screen=lambda _:console),
                                                    root,self.nonce,self.secret)
                except BaseException as error:
                    return error, calls, probe.exists(), clock[0]
                return proof, calls, probe.exists(), clock[0]

    def test_nonce_command_cannot_echo_complete_output_and_real_host_identity_is_not_installed_identity(self):
        command = D.installed_user_command(self.nonce)
        expected = D.installed_user_line(self.nonce)
        self.assertNotIn(expected, command)
        self.assertNotIn('ARCTIC-USER ', command)
        result = subprocess.run(['/bin/sh','-c',command],capture_output=True,check=True,timeout=5)
        self.assertEqual(result.stderr,b'')
        self.assertEqual(result.stdout.decode().strip(),
                         'ARCTIC-USER '+self.nonce+' uid='+str(os.getuid())+' user='+subprocess.check_output(['id','-un'],text=True).strip())
        if os.getuid() != 1000 or subprocess.check_output(['id','-un'],text=True).strip() != 'arcticqual':
            self.assertNotEqual(result.stdout.decode().strip(), expected)
        for wrong in ('', '0'*31, 'A'*32, '0'*32+';', '\n'+'0'*32):
            with self.subTest(fixed_case=len(wrong)), self.assertRaises(RuntimeError):
                D.installed_user_command(wrong)

    def test_actual_response_is_required_before_sudo_and_no_cosmetic_prompt_is_required(self):
        # Positive metadata is explicitly synthetic; actual Source functions
        # and physical-image parser execute, but no PAM/input claim follows.
        proof,calls,present,_ = self.exercise([b'valid different nonsecret shell view\n',
            (D.installed_user_line(self.nonce)+'\n').encode()])
        self.assertIs(type(proof),dict)
        self.assertEqual(proof['nonce'],self.nonce)
        self.assertEqual(proof['username'],'arcticqual');self.assertEqual(proof['uid'],1000)
        self.assertEqual(proof['observed_line_sha256'],A.digest(D.installed_user_line(self.nonce).encode()))
        self.assertEqual(len([x for x in calls if x[0]=='command']),1)
        self.assertFalse(present)
        self.assertNotIn(self.secret,str(proof))

    def test_expected_output_before_command_does_not_attest_fresh_challenge(self):
        error,calls,_,_=self.exercise([(D.installed_user_line(self.nonce)+'\n').encode()])
        self.assertIs(type(error),RuntimeError);self.assertEqual(calls,[])

    def test_wrong_nonce_user_root_and_duplicate_records_refuse(self):
        wrong = (
            D.installed_user_line('0'*32),
            'ARCTIC-USER '+self.nonce+' uid=0 user=root',
            'ARCTIC-USER '+self.nonce+' uid=1000 user=other',
            D.installed_user_line(self.nonce)+'\n'+D.installed_user_line(self.nonce),
        )
        for index,line in enumerate(wrong):
            with self.subTest(fixed_case=index):
                error,calls,_,_=self.exercise([b'nonsecret console view\n',(line+'\n').encode()])
                self.assertIs(type(error),RuntimeError)
                self.assertEqual(len([x for x in calls if x[0]=='command']),1)

    def test_known_failed_login_and_returned_password_prompt_never_get_an_input_fallback(self):
        for line in (b'Login incorrect\n',b'arctic-qual login:\n',b'arctic-qual login: arcticqual\n'):
            error,calls,_,_=self.exercise([line]);self.assertIs(type(error),RuntimeError);self.assertEqual(calls,[])
        error,calls,_,elapsed=self.exercise([b'Password:\n'])
        self.assertIs(type(error),RuntimeError);self.assertEqual(calls,[]);self.assertEqual(elapsed,45.0)

    def test_private_echo_missing_console_bad_dimensions_and_expired_clock_refuse(self):
        error,calls,present,_=self.exercise([(self.secret+'\n').encode()])
        self.assertIs(type(error),RuntimeError);self.assertEqual(calls,[]);self.assertTrue(present)
        error,calls,_,_=self.exercise([b'nonsecret view\n'],console=False)
        self.assertIs(type(error),RuntimeError);self.assertEqual(calls,[])
        error,calls,_,_=self.exercise([b'nonsecret view\n'],late=True)
        self.assertIs(type(error),RuntimeError);self.assertEqual(calls,[])
        error,calls,present,_=self.exercise([b'nonsecret view\n',(D.installed_user_line(self.nonce)+'\n').encode()],size=(1280,721))
        self.assertIs(type(error),RuntimeError);self.assertTrue(present)

    def test_active_consumer_requires_correlated_identity_and_all_original_prompt_guards(self):
        report,state,_,media,_ = F.fixture()
        value=state['host']['password_prompt_evidence'];auth=state['host']['installed_boot']['authentication']
        def check(p,a):
            A.password_prompts_check(p,state['build'],state['required_images'],media.__getitem__,a)
        check(value,auth)
        for kind in ('old-cosmetic','nonce','username','uid','uid-bool','extra','hash','order','auth-user','auth-root','auth-status'):
            p=copy.deepcopy(value);a=copy.deepcopy(auth)
            if kind=='old-cosmetic':p['login_shell']={'prompt_kind':'installed-user-shell','observed_line_sha256':A.digest(b'arcticqual@arctic-qual ~ >'),'observed_ns':2}
            elif kind=='nonce':p['login_shell']['nonce']='0'*32
            elif kind=='username':p['login_shell']['username']='root'
            elif kind=='uid':p['login_shell']['uid']=0
            elif kind=='uid-bool':p['login_shell']['uid']=True
            elif kind=='extra':p['login_shell']['private']='never export'
            elif kind=='hash':p['login_shell']['observed_line_sha256']='0'*64
            elif kind=='order':p['login_shell']['observed_ns']=p['sudo']['observed_ns']
            elif kind=='auth-user':a['username']='root'
            elif kind=='auth-root':a['uid']=0
            else:a['status']='unproven'
            with self.subTest(fixed_case=kind),self.assertRaises(RuntimeError):check(p,a)

    def test_original_boot_calls_actual_challenge_before_sudo_and_correlates_root_helper_nonce(self):
        # Only OCR/VM metadata are synthetic. Execute the original wrapped boot,
        # actual challenge, password guards and original strict UART parser.
        _,state,_,media,_=F.fixture()
        G=load('actual_uid_boot_guest_parser',HERE/'guest.py')
        for failed in (False,True):
            with self.subTest(fixed_case=failed),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);(root/'data').mkdir()
                (root/'data/active-credentials.json').write_text(json.dumps({'password':self.secret}))
                helper=A.strict_json(media['host/installed-boot.json'])
                phase=['getty'];nonce=[None];entered=[];shots={}
                def type_text(value,gap):
                    entered.append(value)
                    if value==self.secret:phase[0]='shell' if phase[0]=='getty' else 'done'
                    elif value.startswith('sh -c '):
                        nonce[0]=value.rsplit(' ',1)[1];phase[0]='identity'
                    elif value.startswith('sudo sh /dev/sr0 '):
                        self.assertEqual(value.rsplit(' ',1)[1],nonce[0]);phase[0]='sudo'
                        helper['authentication']['nonce']=nonce[0]
                        (root/'serial-installed.log').write_bytes((
                            'ARCTIC-ACTIVE-INSTALLED-READY='+nonce[0]+' user=arcticqual uid=1000\n'
                            'ARCTIC-ACTIVE-INSTALLED '+json.dumps(helper,sort_keys=True)+'\n').encode())
                def shot(label):
                    p=root/(label+'.png');Image.new('RGB',(1280,720)).save(p);shots[label]=p;return p
                def ocr(*args,**kwargs):
                    value={'getty':'Password:','shell':'different cosmetic shell view','sudo':'[sudo] password for arcticqual:'}.get(phase[0])
                    if phase[0]=='identity':value='ARCTIC-USER '+nonce[0]+(' uid=0 user=root' if failed else ' uid=1000 user=arcticqual')
                    return types.SimpleNamespace(stdout=(value+'\n').encode())
                vm=types.SimpleNamespace(alive=lambda:True,shot=shot,cmd=lambda *a,**k:{'return':{}},
                    keys=lambda *a:None,type_text=type_text)
                startup=types.SimpleNamespace(console_screen=lambda p:True)
                vmtest=types.SimpleNamespace(looks_like_boot_menu=lambda p:False,classify=lambda p:'login')
                with patch.object(D.subprocess,'run',side_effect=ocr),patch.object(D.time,'sleep'), \
                        patch.object(D,'load',return_value=G), \
                        patch.object(D,'ocr_provenance',return_value=state['build']['ocr_host']):
                    if failed:
                        with self.assertRaises(RuntimeError):D.boot_installed(vm,startup,vmtest,root,state['context'])
                        self.assertEqual(entered.count(self.secret),1)
                        self.assertFalse(any(x.startswith('sudo ') for x in entered))
                    else:
                        report,serial,prompts=D.boot_installed(vm,startup,vmtest,root,state['context'])
                        self.assertEqual(report['authentication']['nonce'],prompts['login_shell']['nonce'])
                        self.assertEqual(entered.count(self.secret),2)
                        identity=next(i for i,x in enumerate(entered) if x.startswith('sh -c '))
                        sudo=next(i for i,x in enumerate(entered) if x.startswith('sudo '))
                        self.assertLess(identity,sudo)
                        self.assertEqual(serial['sha256'],A.digest((root/'serial-installed.log').read_bytes()))
                        self.assertFalse(shots['installed-login-shell-probe'].exists())

    def test_whole_driver_inverse_rejects_unrelated_original_byte_change(self):
        value=(HERE/'driver.py').read_text();restore_driver_source(value)
        with self.assertRaises(AssertionError):restore_driver_source(value.replace('gap=.15','gap=.16',1))

    def test_equal_but_distinct_code_clone_cannot_attach_owned_prompt_observation(self):
        code=D.console_user_identity.__code__.replace()
        self.assertEqual(code,D.console_user_identity.__code__)
        self.assertIsNot(code,D.console_user_identity.__code__)
        clone=types.FunctionType(code,D.__dict__)
        for owned,function in ((True,D.console_user_identity),(False,clone)):
            with self.subTest(fixed_case=owned),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);probe=root/'owned.png';Image.new('RGB',(1280,720)).save(probe)
                count=[0]
                def alive():count[0]+=1;return count[0]==1
                vm=types.SimpleNamespace(alive=alive,shot=lambda _:probe)
                owner={'phase':'installed-display','codes':set()}
                with patch.object(D,'_AUTH_ACTIVE',owner),patch.object(D.time,'sleep'), \
                        patch.object(D.subprocess,'run',return_value=types.SimpleNamespace(stdout=b'Password:\n')):
                    with self.assertRaises(RuntimeError):function(vm,types.SimpleNamespace(console_screen=lambda _:True),root,self.nonce,self.secret)
                if owned:
                    self.assertEqual(owner['phase'],'installed-shell')
                    self.assertEqual(owner['codes'],{'installer-inner-driver-installed-auth-prompt-getty-password'})
                else:self.assertEqual(owner,{'phase':'installed-display','codes':set()})

    def test_original_closed_assertion_id_tracks_the_stricter_identity_guard(self):
        _,state,_,media,_=F.fixture()
        p=copy.deepcopy(state['host']['password_prompt_evidence'])
        p['login_shell']['uid']=0
        with self.assertRaises(RuntimeError) as caught:
            A.password_prompts_check(p,state['build'],state['required_images'],media.__getitem__,
                                    state['host']['installed_boot']['authentication'])
        proof=caught.exception._arctic_installer_assertion
        self.assertIs(proof[0],A.require.__globals__['_ASSERTION_TOKEN'])
        self.assertEqual(proof[1],'active-134')

    def test_new_neighbor_classes_do_not_admit_or_export_unknown_operand(self):
        m=P.scanner()
        for char,label in (('=','ascii-equals'),('!','ascii-exclamation'),('\x07','terminal-bel'),
                           ('\x08','terminal-backspace'),('>','ascii-angle-close')):
            original=char+P.PUBLIC_LITERAL+';';view,boundaries,removed=m.classification_view(original)
            match=m.EXTERNAL_RULES[3][1].search(view)
            observed=P.serial_source_context(m,match,'source-view',original,boundaries,removed)
            self.assertEqual(observed['preceding'],label)
            self.assertEqual(observed['following'],'ascii-semicolon')
            self.assertEqual(observed['whole_record'],'unknown')
            self.assertFalse(observed['privacy_admitted']);self.assertFalse(observed['runtime_cause_proven'])
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):m.external_text(original.encode())

if __name__=='__main__':unittest.main(verbosity=2)
