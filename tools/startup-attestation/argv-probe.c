/* Own synthetic argument provider only. No shell or startup/session action. */
#include <unistd.h>
#include <string.h>
int main(int argc,char **argv){
    if(argc<1||argc>33)return 64;
    for(int i=1;i<argc;i++){
        size_t n=strlen(argv[i])+1;if(n>4096)return 65;
        const char *p=argv[i];while(n){ssize_t k=write(1,p,n);if(k<=0)return 74;p+=k;n-=(size_t)k;}
    }
    return 0;
}
