/* Audit-only map/runtime proof. Does not emit input or invoke GTK activation. */
#ifndef ARCTIC_PROOF_H
#define ARCTIC_PROOF_H
#include <errno.h>
#include <stdint.h>
#include <time.h>
#include <dirent.h>
#ifndef ARCTIC_SOURCE_SHA
#error "Exact generated source/header hash is required"
#endif
static int arctic_dir = -1;
static int arctic_map_only = 0;
static int arctic_argc;
static const char **arctic_argv;
static void arctic_fail(const char *s) { fprintf(stderr, "arctic-input-proof: %s\n",s); exit(112); }
static FILE *arctic_output(const char *name) {
 int fd=openat(arctic_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)arctic_fail("unused regular owned proof file required");
 FILE *f=fdopen(fd,"wb");if(!f){close(fd);arctic_fail("proof stream open failed");}return f;
}
static void arctic_finish(FILE *f) {
 if(fflush(f)||ferror(f)||fsync(fileno(f))){fclose(f);arctic_fail("proof stream incomplete");}
 if(fclose(f))arctic_fail("proof stream close failed");
}
static void arctic_string(FILE *f,const char *s) {
 fputc('"',f);
 for(const unsigned char *p=(const unsigned char *)s;*p;p++) {
  if(*p=='"'||*p=='\\')fprintf(f,"\\%c",*p);
  else if(*p<32)fprintf(f,"\\u%04x",(unsigned)*p);
  else fputc(*p,f);
 }
 fputc('"',f);
}
static void arctic_initialize(int argc,const char **argv) {
 if(argc<5||argc>128||strcmp(argv[3],"--")||
   (strcmp(argv[1],"--arctic-proof-dir")&&strcmp(argv[1],"--arctic-map-only")))
  arctic_fail("explicit --arctic-proof-dir DIR -- or --arctic-map-only DIR -- required");
 if(argv[2][0]!='/'||strlen(argv[2])>4096)arctic_fail("absolute bounded proof directory required");
 arctic_map_only=!strcmp(argv[1],"--arctic-map-only");
 arctic_dir=open(argv[2],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 struct stat st;
 if(arctic_dir<0||fstat(arctic_dir,&st)||!S_ISDIR(st.st_mode)||st.st_uid!=geteuid()||(st.st_mode&0777)!=0700)
  arctic_fail("existing private0700 directory owned by this UID required");
 size_t escaped=0;
 for(int i=0;i<argc;i++) {
  if(strlen(argv[i])>4096)arctic_fail("argument bound exceeded");
  escaped+=3; /* JSON quotes and one separator. */
  for(const unsigned char *p=(const unsigned char *)argv[i];*p;p++)
   escaped+=*p<32?6:(*p=='"'||*p=='\\'?2:1);
  if(escaped>32768)arctic_fail("escaped argument proof bound exceeded before parse/input");
 }
 arctic_argc=argc;arctic_argv=argv;
}
static void arctic_copy_proc(const char *path,const char *name) {
 FILE *in=fopen(path,"rb");if(!in)arctic_fail("actual own proc proof unavailable");
 FILE *out=arctic_output(name);unsigned char b[4096];size_t total=0,n;
 while((n=fread(b,1,sizeof(b),in))) {
  total+=n;if(total>262144||fwrite(b,1,n,out)!=n)arctic_fail("actual proc proof overflow/write failure");
 }
 if(ferror(in)||fclose(in))arctic_fail("actual proc proof read incomplete");
 arctic_finish(out);
}
static void arctic_record_map(FILE *source,size_t size,size_t used) {
 if(!size||size>262144||used==0||used>4096)arctic_fail("uploaded map/name bound differs");
 long offset=ftell(source);if(offset<0)arctic_fail("actual upload offset unavailable");
 char *b=calloc(size+1,1);if(!b)arctic_fail("map allocation failed");
 size_t got=0;while(got<size){ssize_t n=pread(fileno(source),b+got,size-got,(off_t)got);
  if(n<0&&errno==EINTR)continue;
  if(n<=0)arctic_fail("actual upload map read failed");
  got+=(size_t)n;
 }
 if(b[size-1]!='\0')arctic_fail("actual upload map framing failed");
 FILE *out=arctic_output("uploaded-map.xkb");if(fwrite(b,1,size,out)!=size)arctic_fail("map preservation failed");arctic_finish(out);
 if(ftell(source)!=offset)arctic_fail("actual upload offset changed");
 struct xkb_context *ctx=xkb_context_new(XKB_CONTEXT_NO_FLAGS);
 struct xkb_keymap *map=ctx?xkb_keymap_new_from_string(ctx,b,XKB_KEYMAP_FORMAT_TEXT_V1,XKB_KEYMAP_COMPILE_NO_FLAGS):NULL;
 if(!map)arctic_fail("actual map cannot compile");
 xkb_keycode_t min=xkb_keymap_min_keycode(map),max=xkb_keymap_max_keycode(map),sentinel=xkb_keymap_key_by_name(map,"ARCTIC_UNUSED");
 if(min!=9||max!=used+9||sentinel!=max)arctic_fail("named un-emitted high endpoint missing");
 /* The sentinel has no symbol and is not in wtype's keymap array or commands. */
 const xkb_keysym_t *syms=NULL;
 int count=xkb_keymap_key_get_syms_by_level(map,sentinel,0,0,&syms);
 for(int i=0;i<count;i++)if(syms[i]!=XKB_KEY_NoSymbol)arctic_fail("sentinel unexpectedly has a symbol");
 struct timespec ts;if(clock_gettime(CLOCK_MONOTONIC,&ts))arctic_fail("actual monotonic clock unavailable");
 out=arctic_output("producer-identity.json");
 fprintf(out,"{\"schema\":\"arctic-private-input-v1\",\"pid\":%ld,\"uid\":%ld,\"gid\":%ld,\"monotonic_ns\":%llu,\"source_sha256\":",
  (long)getpid(),(long)geteuid(),(long)getegid(),(unsigned long long)ts.tv_sec*1000000000ULL+(unsigned long long)ts.tv_nsec);
 arctic_string(out,ARCTIC_SOURCE_SHA);
 fprintf(out,",\"map_only\":%s,\"minimum\":%u,\"maximum\":%u,\"last_emitted_named_code\":%zu,\"sentinel\":%u,\"map_bytes\":%zu,\"argv\":[",
  arctic_map_only?"true":"false",min,max,used+8,sentinel,size);
 for(int i=0;i<arctic_argc;i++){if(i)fputc(',',out);arctic_string(out,arctic_argv[i]);}
 fprintf(out,"],\"return_codes\":[");
 int written=0;
 for(xkb_keycode_t key=min;key<=max;key++) {
  for(xkb_layout_index_t group=0;group<xkb_keymap_num_layouts_for_key(map,key);group++)
   for(xkb_level_index_t level=0;level<xkb_keymap_num_levels_for_key(map,key,group);level++) {
    count=xkb_keymap_key_get_syms_by_level(map,key,group,level,&syms);
    for(int i=0;i<count;i++)if(syms[i]==0xff0d) {
     if(written>=64)arctic_fail("Return proof entry bound exceeded before input");
     if(written++)fputc(',',out);
     fprintf(out,"{\"keycode\":%u,\"group\":%u,\"level\":%u}",key,group,level);
    }
   }
 }
 fprintf(out,"]}\n");
 long identity_bytes=ftell(out);
 if(identity_bytes<0||identity_bytes>65536)arctic_fail("identity JSON bound exceeded before input");
 arctic_finish(out);
 arctic_copy_proc("/proc/self/stat","producer-stat.txt");
 arctic_copy_proc("/proc/self/maps","producer-maps.txt");
 xkb_keymap_unref(map);xkb_context_unref(ctx);free(b);
}
#endif

