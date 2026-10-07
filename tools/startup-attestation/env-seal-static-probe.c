/* x86_64 Linux synthetic fixture. No libc, interpreter, startup hook or Mango.
 * Syscall numbers/UAPI are pinned alongside. Captures untouched initial envp.
 * A candidate startup carrier remains a separate unbound executable contract. */
typedef unsigned long usize;
static long call3(long nr,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r):"a"(nr),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
static void finish(long status){call3(60,status,0,0);__builtin_unreachable();}
static usize bounded_len(const char *s){usize n=0;while(n<=65536&&s[n])n++;return n;}
static int full(long fd,const char *s,usize n){while(n){long k=call3(1,fd,(long)s,n);if(k==-4)continue;if(k<=0)return -1;s+=k;n-=k;}return 0;}
void probe_start(usize *stack){usize argc=*stack;char **argv=(char **)(stack+1);if(argc!=1||argv[1])finish(64);char **envp=argv+2;usize total=0,count=0;for(char **p=envp;*p;p++){usize n=bounded_len(*p);if(n>65536||++count>4096||total+n+1>1048562)finish(65);total+=n+1;}
 long fd=call3(319,(long)"arctic-synthetic-env",2,0);if(fd<3)finish(70);
 const char magic[]="ARCTIC_ENV_V1";if(full(fd,magic,sizeof(magic)))finish(74);
 for(char **p=envp;*p;p++)if(full(fd,*p,bounded_len(*p)+1))finish(74);
 if(!count&&full(fd,"",1))finish(74);
 if(call3(72,fd,1033,15)<0)finish(74);
 char number[24],digits[24];usize n=0;unsigned long value=(unsigned long)fd;do{digits[n++]=(char)('0'+value%10);value/=10;}while(value&&n<23);if(value)finish(74);for(usize i=0;i<n;i++)number[i]=digits[n-i-1];number[n]=0;
 char *args[]={"python3.14","-I","-S","/run/arctic-safe/synthetic-handoff-observer.py",number,(char *)0};
 char *diagnostic_env[]={"PATH=/usr/bin:/bin","LANG=C.UTF-8",(char *)0};
 call3(59,(long)"/usr/bin/python3.14",(long)args,(long)diagnostic_env);call3(3,fd,0,0);finish(126);
}
__asm__(".global _start\n_start:\n mov %rsp,%rdi\n and $-16,%rsp\n call probe_start\n");
