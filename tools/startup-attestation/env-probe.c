/* Synthetic-fixture environment observation only. No Mango or startup target. */
#include <errno.h>
#include <stddef.h>
#include <string.h>
#include <unistd.h>
static int full(int fd,const char *p,size_t n){while(n){ssize_t k=write(fd,p,n);if(k<0&&errno==EINTR)continue;if(k<=0)return -1;p+=k;n-=(size_t)k;}return 0;}
int main(int argc,char **argv,char **envp){(void)argv;if(argc!=1)return 64;size_t total=0;unsigned count=0;for(char **p=envp;*p;p++){size_t n=strnlen(*p,65537);if(n>65536||++count>4096||total+n+1>1048576)return 65;total+=n+1;if(full(1,*p,n+1))return 74;}return 0;}
