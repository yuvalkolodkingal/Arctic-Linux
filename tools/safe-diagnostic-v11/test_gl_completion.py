"""Actual local dynamic-linker/owned-counter controls, without GL hardware or a VM."""
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
ABI = struct.Struct('<8sII16sIIQQQQQQIIQQQQQQ')
FLAGS = ['-std=c11', '-O2', '-fPIC', '-shared', '-fno-omit-frame-pointer',
         '-fstack-protector-strong', '-D_FORTIFY_SOURCE=3', '-Wall', '-Wextra', '-Werror',
         '-Wl,-z,relro,-z,now']
GL_STUB = r'''
#define _GNU_SOURCE
#include <stdatomic.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
static _Atomic unsigned flushes, finishes, events;
static _Atomic uint64_t order;
static unsigned delay, close_fd;
void fixture_fault(unsigned wait, unsigned close) { delay=wait; close_fd=close; }
static void event(unsigned kind) {
 unsigned index=atomic_fetch_add(&events,1);
 if(index<18) { uint64_t previous=atomic_load(&order);
   while(!atomic_compare_exchange_weak(&order,&previous,previous*10+kind)) {} }
}
void glFlush(void) { atomic_fetch_add(&flushes,1); event(1);
 if(close_fd&1) { close_fd&=~1U; close(198); } }
void glFinish(void) { atomic_fetch_add(&finishes,1); event(2); if(delay)usleep(delay);
 if(close_fd&2)glFlush();
 if(close_fd&4) { close_fd&=~4U; close(198); }
 if(close_fd&8) { close_fd&=~8U; int fd=open("/dev/null",O_RDWR);
   if(fd<0||dup2(fd,198)<0)_exit(21);
   close(fd); } }
unsigned fixture_flushes(void) { return atomic_load(&flushes); }
unsigned fixture_finishes(void) { return atomic_load(&finishes); }
uint64_t fixture_order(void) { return atomic_load(&order); }
'''
SCENE_STUB = r'''
extern void glFlush(void);
__attribute__((noinline)) void scene_submit(void) {
 glFlush(); __asm__ volatile("" ::: "memory");
}
'''
TARGET = r'''
#define _GNU_SOURCE
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
extern void scene_submit(void),fixture_fault(unsigned,unsigned);
extern unsigned fixture_flushes(void),fixture_finishes(void);
extern uint64_t fixture_order(void);
static void four(void) { for(unsigned i=0;i<4;i++)scene_submit(); }
static void *worker(void *unused) { (void)unused;for(unsigned i=0;i<20000;i++)scene_submit();return NULL; }
int main(int argc,char **argv) {
 const char *mode=argc>1?argv[1]:"ordinary";
 unsigned child_flush=0,child_finish=0,child_fd=0,child_preload=0;
 if(!strcmp(mode,"child-exec")) {
   four(); printf("%u %u %u %u\n",fixture_flushes(),fixture_finishes(),
     fcntl(198,F_GETFD)>=0,getenv("LD_PRELOAD")!=NULL);return 0;
 }
 if(!strcmp(mode,"fork")||!strcmp(mode,"exec")) {
   int p[2];if(pipe(p))return 3;pid_t child=fork();if(child<0)return 4;
   if(child==0) {
     close(p[0]);if(dup2(p[1],1)<0)return 5;close(p[1]);
     if(!strcmp(mode,"exec"))execl(argv[0],argv[0],"child-exec",(char*)NULL);
     four();dprintf(1,"%u %u %u %u\n",fixture_flushes(),fixture_finishes(),
       fcntl(198,F_GETFD)>=0,getenv("LD_PRELOAD")!=NULL);_exit(0);
   }
   close(p[1]);FILE *input=fdopen(p[0],"r");
   if(!input||fscanf(input,"%u %u %u %u",&child_flush,&child_finish,&child_fd,&child_preload)!=4)return 6;
   fclose(input);int status;if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status))return 7;
 }
 if(!strcmp(mode,"replace-fd")) { int fd=open("/dev/null",O_RDWR);if(fd<0||dup2(fd,198)<0)return 8;close(fd); }
 if(!strcmp(mode,"changed-header")) { if(pwrite(198,"XXXXXXXX",8,0)!=8)return 9; }
 if(!strcmp(mode,"changed-mode")) { if(fchmod(198,0644))return 10; }
 if(!strcmp(mode,"truncate")) { if(ftruncate(198,0))return 11; }
 if(!strcmp(mode,"saturate")) { uint64_t max=UINT64_C(9223372036854775807);if(pwrite(198,&max,8,96)!=8)return 12; }
 if(!strcmp(mode,"sequence-end")) { uint64_t max=UINT64_C(9223372036854775807);if(pwrite(198,&max,8,128)!=8)return 13; }
 if(!strcmp(mode,"close-during-flush"))fixture_fault(0,1);
 if(!strcmp(mode,"reenter-finish"))fixture_fault(0,2);
 if(!strcmp(mode,"close-during-finish"))fixture_fault(0,4);
 if(!strcmp(mode,"replace-during-finish"))fixture_fault(0,8);
 if(!strcmp(mode,"delay-finish"))fixture_fault(100000,0);
 if(!strcmp(mode,"threads")) { pthread_t first,second;
   if(pthread_create(&first,NULL,worker,NULL)||pthread_create(&second,NULL,worker,NULL))return 14;
   pthread_join(first,NULL);pthread_join(second,NULL);
 } else four();
 int flags=fcntl(198,F_GETFD);
 printf("{\"real_flush\":%u,\"real_finish\":%u,\"order\":%"PRIu64",\"preload\":%u,\"fd_cloexec\":%u,"
        "\"child_flush\":%u,\"child_finish\":%u,\"child_fd\":%u,\"child_preload\":%u,\"fd_open\":%u}\n",
   fixture_flushes(),fixture_finishes(),fixture_order(),getenv("LD_PRELOAD")!=NULL,
   flags>=0&&(flags&FD_CLOEXEC)!=0,child_flush,child_finish,child_fd,child_preload,flags>=0);
 return 0;
}
'''


class InterpositionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='arctic-local-gl-control-')
        cls.root = Path(cls.temporary.name)
        for name, raw in (('fixture-gl.c', GL_STUB), ('fixture-scene.c', SCENE_STUB), ('fixture-target.c', TARGET)):
            (cls.root / name).write_text(raw)
        cls.preload = cls.root / 'gl-completion.so'
        cls.gl = cls.root / 'libfixture-gl.so'
        cls.scene = cls.root / 'libfixture-scene.so'
        cls.target = cls.root / 'fixture-target'
        def cc(*args): subprocess.run(['gcc', *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        cc(*FLAGS, str(HERE/'gl-completion.c'), '-ldl', '-pthread', '-o', str(cls.preload))
        cc(*FLAGS, str(cls.root/'fixture-gl.c'), '-o', str(cls.gl))
        cc(*FLAGS, '-fno-optimize-sibling-calls', str(cls.root/'fixture-scene.c'), '-L'+str(cls.root),
           '-lfixture-gl', '-Wl,-rpath,'+str(cls.root), '-o', str(cls.scene))
        cc('-std=c11','-O2','-Wall','-Wextra','-Werror',str(cls.root/'fixture-target.c'),
           '-L'+str(cls.root),'-lfixture-scene','-lfixture-gl','-Wl,-rpath,'+str(cls.root),'-pthread','-o',str(cls.target))
        disassembly=subprocess.check_output(['objdump','-d',str(cls.scene)],text=True)
        calls=re.findall(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*call\s+[^\n]*<glFlush@plt>',disassembly,re.M)
        assert len(calls)==1
        address, encoded=calls[0]
        cls.return_offset=int(address,16)+len(encoded.split())

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    @contextlib.contextmanager
    def invoke(self, *, mode='ordinary', changes=None, permissions=0o600, preload=True, chain=False, fd_kind='regular'):
        try: os.fstat(198)
        except OSError: pass
        else: raise AssertionError('never overwrite an acquired foreign test descriptor')
        name=self.root/('counter-'+str(time.monotonic_ns()))
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,permissions)
        os.fchmod(fd,permissions)
        fields=[b'ARCTGL11',1,144,b'\x4a'*16,os.getuid(),0,0,self.target.stat().st_dev,self.target.stat().st_ino,
                self.scene.stat().st_dev,self.scene.stat().st_ino,self.return_offset,0,0,0,0,0,0,0,0]
        os.write(fd,ABI.pack(*fields))
        extra=[]
        source_fd=fd
        if fd_kind=='pipe':source_fd,other=os.pipe();extra.extend((source_fd,other))
        if fd_kind=='directory':source_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);extra.append(source_fd)
        os.dup2(source_fd,198,inheritable=True)
        def prepare():
            values=list(fields);values[5]=os.getpid()
            values[6]=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
            for index,value in (changes or {}).items():values[index]=value
            if fd_kind=='regular':os.pwrite(198,ABI.pack(*values),0)
        env={**os.environ}
        env.pop('LD_PRELOAD',None)
        if preload:env['LD_PRELOAD']=str(self.preload)
        argv=[str(self.target),mode]
        if chain:argv=['/bin/sh','-c','exec "$@"','arctic-owned-chain',*argv]
        proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,pass_fds=(198,),preexec_fn=prepare)
        try:
            yield proc,fd
        finally:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=5)
            if proc.stdout:proc.stdout.close()
            if proc.stderr:proc.stderr.close()
            os.close(198);os.close(fd)
            for item in extra:os.close(item)
            name.unlink()

    def finished(self,proc,fd):
        stdout,stderr=proc.communicate(timeout=5)
        self.assertEqual(proc.returncode,0)
        self.assertEqual(stderr,b'')
        self.assertLess(len(stdout),2048)
        raw=os.pread(fd,144,0)
        return json.loads(stdout),ABI.unpack(raw) if len(raw)==144 else None

    def coherent(self,fd):
        for _ in range(4):
            active_before=os.pread(fd,4,92);before=os.pread(fd,8,128)
            raw=os.pread(fd,144,0);active_after=os.pread(fd,4,92);after=os.pread(fd,8,128)
            if len(raw)!=144 or len(before)!=8 or len(after)!=8:return None
            values=ABI.unpack(raw)
            if active_before==active_after==b'\0'*4 and before==after and struct.unpack('<Q',before)[0]==values[18] and values[13]==0:
                return values
        return None

    def test_real_symbols_order_and_original_script_chain_are_proven(self):
        self.assertEqual(ABI.size,144)
        for chain in (False,True):
            with self.subTest(chain=chain),self.invoke(chain=chain)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['real_flush'],value['real_finish'],value['order']),(4,4,12121212))
                self.assertEqual((value['preload'],value['fd_cloexec']),(0,1))
                self.assertEqual((record[12],record[13],*record[14:18],record[18]),(2,0,4,4,4,4,8))
                self.assertEqual(record[5],proc.pid)
        with self.invoke(preload=False)as(proc,fd):
            value,record=self.finished(proc,fd)
            self.assertEqual((value['real_flush'],value['real_finish'],value['order']),(4,0,1111))
            self.assertEqual((record[12],*record[14:18]),(0,0,0,0,0))

    def test_fork_and_exec_children_do_not_receive_finish_or_modify_parent_counts(self):
        for mode in ('fork','exec'):
            with self.subTest(mode=mode),self.invoke(mode=mode)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['child_flush'],value['child_finish'],value['child_preload']),(4,0,0))
                self.assertEqual(value['child_fd'],mode=='fork')
                self.assertEqual((value['real_flush'],value['real_finish']), (4,4))
                self.assertEqual(record[14:18],(4,4,4,4))

    def test_foreign_headers_process_identity_and_initial_values_remain_passthrough(self):
        for changes in ({0:b'FOREIGN!'},{1:2},{2:129},{3:b'\0'*16},{4:os.getuid()+1},{5:1},{6:1},
                        {7:0},{8:0},{12:1},{13:2},{14:1},{15:1},{16:1},{17:1},{18:1},{19:1}):
            with self.subTest(fields=tuple(changes)),self.invoke(changes=changes)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['real_flush'],value['real_finish'],value['preload']),(4,0,1))
                self.assertNotEqual(record[12],2)

    def test_exact_caller_inode_and_return_address_are_independent_of_total_calls(self):
        for changes in ({9:0},{10:1},{11:self.return_offset+1}):
            with self.subTest(fields=tuple(changes)),self.invoke(changes=changes)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['real_flush'],value['real_finish']),(4,4))
                self.assertEqual((record[12],*record[14:18]),(2,4,4,0,0))

    def test_descriptor_type_mode_and_replacement_preserve_foreign_objects(self):
        for fd_kind in ('pipe','directory'):
            with self.subTest(fd_kind=fd_kind),self.invoke(fd_kind=fd_kind)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['real_flush'],value['real_finish']),(4,0))
                self.assertEqual(record[12],0)
        for mode in ('replace-fd','changed-header','changed-mode','truncate'):
            with self.subTest(mode=mode),self.invoke(mode=mode)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['real_flush'],value['real_finish']),(4,0))
                if record:self.assertNotEqual(record[12],2)
        with self.invoke(permissions=0o644)as(proc,fd):
            value,record=self.finished(proc,fd)
            self.assertEqual((value['real_flush'],value['real_finish'],record[12]),(4,0,0))

    def test_finish_is_counted_only_after_return_and_rechecked_owned_descriptor(self):
        with self.invoke(mode='delay-finish')as(proc,fd):
            deadline=time.monotonic()+2;observed=False
            while time.monotonic()<deadline and proc.poll()is None:
                record=self.coherent(fd)
                if record and record[12]==2 and record[14]>record[15]:observed=True;break
            value,record=self.finished(proc,fd)
            self.assertTrue(observed)
            self.assertEqual((value['real_flush'],value['real_finish'],*record[14:18]),(4,4,4,4,4,4))
        with self.invoke(mode='close-during-flush')as(proc,fd):
            value,record=self.finished(proc,fd)
            self.assertEqual((value['real_flush'],value['real_finish']),(4,0))
            self.assertEqual(record[14:18],(1,0,1,0))

    def test_concurrent_calls_have_coherent_sequence_samples_and_no_counter_wrap(self):
        with self.invoke(mode='threads')as(proc,fd):
            samples=[];deadline=time.monotonic()+5
            while proc.poll()is None and time.monotonic()<deadline:
                record=self.coherent(fd)
                if record and record[12]==2:samples.append(record)
            value,record=self.finished(proc,fd)
            self.assertEqual((value['real_flush'],value['real_finish']),(40000,40000))
            self.assertEqual((record[12],*record[14:18]),(2,40000,40000,40000,40000))
            self.assertTrue(samples)
            for sample in samples:
                total,done,scene,scene_done=sample[14:18]
                self.assertTrue(done<=total and scene<=total and scene_done<=done and scene_done<=scene)
                self.assertEqual(sample[13],0)
        for mode in ('saturate','sequence-end'):
            with self.subTest(mode=mode),self.invoke(mode=mode)as(proc,fd):
                _,record=self.finished(proc,fd)
                self.assertEqual(record[12],3)
                self.assertLessEqual(max(record[14:18]),9223372036854775807)
                self.assertLessEqual(record[18],9223372036854775807)

    def test_real_function_reentry_is_passthrough_and_finish_loss_is_not_completed(self):
        with self.invoke(mode='reenter-finish')as(proc,fd):
            value,record=self.finished(proc,fd)
            self.assertEqual((value['real_flush'],value['real_finish'],value['order']),(8,4,121121121121))
            self.assertEqual((record[12],*record[14:18],record[18]),(2,4,4,4,4,8))
        for mode,fd_open in (('close-during-finish',0),('replace-during-finish',1)):
            with self.subTest(mode=mode),self.invoke(mode=mode)as(proc,fd):
                value,record=self.finished(proc,fd)
                self.assertEqual((value['real_flush'],value['real_finish'],value['fd_open']),(4,1,fd_open))
                self.assertEqual(record[14:18],(1,0,1,0))

    def test_shared_library_has_only_fixed_gl_export_and_no_executable_stack(self):
        symbols=subprocess.check_output(['nm','-D','--defined-only',str(self.preload)],text=True)
        self.assertEqual([line.split()[-1]for line in symbols.splitlines()if' T 'in line],['glFlush'])
        program=subprocess.check_output(['readelf','-W','-l',str(self.preload)],text=True)
        stack=next(line for line in program.splitlines()if'GNU_STACK'in line)
        self.assertIn(' RW ',stack);self.assertNotIn('RWE',stack)
        self.assertIn('GNU_RELRO',program)
        self.assertIn('BIND_NOW',subprocess.check_output(['readelf','-d',str(self.preload)],text=True))


if __name__=='__main__':unittest.main()
