/* Linux x86-64, no libc/ELF interpreter. One approved mango handoff only.
 * Seals original initial-stack argv/envp before isolated diagnostic Python.
 * This is new Mango-specific forwarding code, not the synthetic provider.
 */
typedef unsigned long usize;
#ifndef TRACE_LOGGER
#define TRACE_LOGGER "/run/arctic-mango-trace/owned-logger.py"
#endif
#ifndef TRACE_PYTHON
#define TRACE_PYTHON "/usr/bin/python3.14"
#endif
static long sys3(long nr,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r):"a"(nr),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
static void die(long s){sys3(60,s,0,0);__builtin_unreachable();}
static usize len(const char *s){usize n=0;while(n<=65536&&s[n])++n;return n;}
static int equal(const char*a,const char*b){while(*a&&*a==*b){++a;++b;}return *a==*b;}
static int full(long fd,const char *p,usize n){while(n){long k=sys3(1,fd,(long)p,n);if(k==-4)continue;if(k<=0)return -1;p+=k;n-=k;}return 0;}
static long mem(const char *name){long fd=sys3(319,(long)name,2,0);if(fd<3)die(70);return fd;}
static void seal(long fd){if(sys3(72,fd,1033,15)<0)die(74);}
static void decimal(long fd,char *out){char tmp[24];usize n=0;do{tmp[n++]=(char)('0'+fd%10);fd/=10;}while(fd&&n<23);if(fd)die(74);for(usize i=0;i<n;++i)out[i]=tmp[n-i-1];out[n]=0;}
void handoff_start(usize *sp){
 usize argc=*sp;char **argv=(char **)(sp+1);
 if(argc!=2||argv[2]||!equal(argv[1],"mango"))die(64);
 char **envp=argv+argc+1;usize total=0,count=0;
 for(char **p=envp;*p;++p){usize n=len(*p);if(n>65536||++count>4096||total+n+1>1048562)die(65);total+=n+1;}
 long envfd=mem("arctic-trace-env"),argfd=mem("arctic-trace-argv");
 const char em[]="ARCTIC_ENV_V1",am[]="ARCTIC_TRACE_ARGV_V1";
 if(full(envfd,em,sizeof(em))||full(argfd,am,sizeof(am))||full(argfd,argv[1],len(argv[1])+1))die(74);
 for(char **p=envp;*p;++p)if(full(envfd,*p,len(*p)+1))die(74);
 if(!count&&full(envfd,"",1))die(74);seal(envfd);seal(argfd);
 char en[24],an[24];decimal(envfd,en);decimal(argfd,an);
 char *args[]={"python3.14","-I","-S",TRACE_LOGGER,en,an,(char*)0};
 char *diag[]={"PATH=/usr/bin:/bin","LANG=C.UTF-8",(char*)0};
 sys3(59,(long)TRACE_PYTHON,(long)args,(long)diag);
 sys3(3,envfd,0,0);sys3(3,argfd,0,0);die(126);
}
__asm__(".global _start\n_start:\n mov %rsp,%rdi\n and $-16,%rsp\n call handoff_start\n");
