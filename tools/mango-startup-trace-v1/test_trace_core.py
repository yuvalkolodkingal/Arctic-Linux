"""Owned host controls only. No Mango, display, VM, Git or device access."""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
HERE=Path(__file__).parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
T=load('owned_trace',HERE/'owned-log.py')
L=load('trace_logger',HERE/'owned-logger.py')
S=load('trace_environment',HERE/'sealed_environment.py')

def sealed(data,seal=True):
    fd=os.memfd_create('owned-test-trace',os.MFD_ALLOW_SEALING)
    os.write(fd,data)
    if seal:fcntl.fcntl(fd,1033,15)
    return fd

class Core(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='trace-core-',dir='/tmp')
        self.root=Path(self.tmp.name);self.oldroot=L.ROOT;L.ROOT=HERE
    def tearDown(self):
        L.ROOT=self.oldroot;self.tmp.cleanup()
    def pair(self,env=None,arg=None,seal=True):
        return sealed(env or L.ENV_MAGIC+b'SHELL=/bin/bash\0LANG=C.UTF-8\0_=literal\0',seal),sealed(arg or L.ARGV_MAGIC+b'mango\0',seal)
    def test_pair_byte_mapping_and_both_descriptors_close(self):
        a,b=self.pair(env=L.ENV_MAGIC+b'SHELL=/bin/bash\0LANG=C\0X=\xff $(literal);\n\0_=carrier\0')
        env,proof=L.consume_pair(a,b,os.getuid());self.assertEqual(env[b'X'],b'\xff $(literal);\n')
        self.assertEqual(proof['boundary_argv'],['mango'])
        for fd in (a,b):
            with self.assertRaises(OSError):os.fstat(fd)
    def test_first_bad_snapshot_still_closes_second(self):
        a,b=self.pair(env=b'bad')
        with self.assertRaisesRegex(RuntimeError,'magic'):L.consume_pair(a,b,os.getuid())
        for fd in (a,b):
            with self.assertRaises(OSError):os.fstat(fd)
    def test_typed_distinct_sealed_argv_shell_environment_guards(self):
        for env,arg,seal in [(None,None,False),(None,L.ARGV_MAGIC+b'mango\0-d\0',True),(L.ENV_MAGIC+b'SHELL=/bin/fish\0',None,True),(L.ENV_MAGIC+b'SHELL=/bin/bash\0BASH_ENV=x\0',None,True),(L.ENV_MAGIC+b'SHELL=/bin/bash\0SHELL=/bin/bash\0',None,True)]:
            a,b=self.pair(env,arg,seal)
            with self.subTest(env=env,arg=arg,seal=seal),self.assertRaises(RuntimeError):L.consume_pair(a,b,os.getuid())
    def test_snapshot_close_failure_fatal_all_attempted(self):
        a,b=self.pair();real=os.close;closed=[]
        def close(fd):
            closed.append(fd);real(fd)
            if fd==a:raise OSError('injected after actual close')
        with patch.object(L.os,'close',side_effect=close),self.assertRaisesRegex(OSError,'actual close'):L.consume_pair(a,b,os.getuid())
        self.assertEqual(closed,[a,b])
    def capture(self,script,stop,max_seconds=2):
        d=self.root/'capture'
        exe=Path(sys.executable).resolve();sha=hashlib.sha256(exe.read_bytes()).hexdigest()
        owner=T.OwnedLog(d,max_seconds=max_seconds)
        result=owner.capture(str(exe),[str(exe),'-c',script],sha,expected_uid=exe.stat().st_uid,trace_stop=stop)
        self.assertTrue(owner.reaped);self.assertTrue(all(getattr(owner,k) is None for k in ['sender','receiver','pidfd','gate_read','gate_write']))
        return owner,result,(d/'stderr.raw').read_bytes()
    def test_actual_child_term_handler_bytes_drained_and_reaped(self):
        script="import os,signal,time;signal.signal(signal.SIGTERM,lambda *a:(os.write(2,b'TERM-TAIL\\n'),exit(0)));os.write(2,b'INITIAL\\n');time.sleep(10)"
        ready=self.root/'capture/stderr.raw'
        owner,result,raw=self.capture(script,lambda:ready.exists() and ready.read_bytes()==b'INITIAL\n')
        self.assertEqual(raw,b'INITIAL\nTERM-TAIL\n');self.assertEqual(result['status'],'owned-trace-collected')
        self.assertTrue(result['controlled_stop']);self.assertTrue((owner.root/'log-report.json').is_file())
    def test_actual_term_resistant_child_killed_and_drained(self):
        ready=self.root/'capture/stderr.raw'
        owner,result,raw=self.capture("import signal,os,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);os.write(2,b'INITIAL\\n');time.sleep(10)",lambda:ready.exists() and ready.read_bytes()==b'INITIAL\n')
        self.assertEqual(raw,b'INITIAL\n');self.assertTrue(owner.reaped);self.assertTrue(result['controlled_stop'])
    def test_early_eof_remains_fatal_no_success_receipt(self):
        with self.assertRaisesRegex(RuntimeError,'before explicit end'):
            self.capture("import os;os.write(2,b'EARLY\\n')",lambda:False)
        self.assertFalse((self.root/'capture/log-report.json').exists())
    def test_deadline_preserves_raw_and_has_no_success(self):
        with self.assertRaisesRegex(RuntimeError,'deadline'):
            self.capture("import os,time;os.write(2,b'KEPT\\n');time.sleep(10)",lambda:False,max_seconds=.1)
        self.assertEqual((self.root/'capture/stderr.raw').read_bytes(),b'KEPT\n');self.assertFalse((self.root/'capture/log-report.json').exists())
    def test_renderer_line_sender_mixing_never_authenticates(self):
        raw=b'GL_RENDERER=one\n';mid=4
        rows=[dict(pid=1,uid=1000,gid=1000,begin=0,end=mid,sha256=T.sha(raw[:mid])),dict(pid=2,uid=1000,gid=1000,begin=mid,end=len(raw),sha256=T.sha(raw[mid:]))]
        result=T.authenticated_lines(raw,rows,dict(pid=1,uid=1000,gid=1000))
        self.assertFalse(result[0]['authenticated_writer'])
    def test_new_native_carrier_rejects_non_mango_and_preserves_accepted_bytes(self):
        observer=self.root/'observer.py';observer.write_text("import os,sys,json,fcntl; a,b=map(int,sys.argv[1:]);v=[os.pread(f,os.fstat(f).st_size,0) for f in (a,b)];s=[fcntl.fcntl(f,1034) for f in (a,b)];[os.close(f) for f in (a,b)];print(json.dumps({'raw':[x.hex() for x in v],'seals':s}))")
        binary=self.root/'carrier'
        cmd=['gcc','-Os','-nostdlib','-static','-fno-stack-protector','-fno-builtin','-fno-pie','-no-pie','-Wl,--build-id=none',f'-DTRACE_LOGGER="{observer}"',f'-DTRACE_PYTHON="{Path(sys.executable).resolve()}"',str(HERE/'native-handoff.c'),'-o',str(binary)]
        subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')})
        env={b'SHELL':b'/bin/bash',b'LANG':b'C',b'X':b'\xff ;$(literal)\n',b'_':b'carrier'}
        r=subprocess.run([str(binary),'mango'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3,check=True)
        v=json.loads(r.stdout);self.assertEqual(v['seals'],[15,15]);self.assertEqual(bytes.fromhex(v['raw'][0]),L.ENV_MAGIC+b'\0'.join(k+b'='+x for k,x in env.items())+b'\0');self.assertEqual(bytes.fromhex(v['raw'][1]),L.ARGV_MAGIC+b'mango\0')
        for args in [[],['mango','-d'],['mango --arg'],['other'],['$(touch nope)']]:
            r=subprocess.run([str(binary),*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3);self.assertEqual(r.returncode,64);self.assertEqual(r.stdout,b'')

if __name__=='__main__':unittest.main()
