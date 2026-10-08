// Test-only persistent wlroots virtual pointer. Protocol: swaywm/wlr-protocols,
// unstable/wlr-virtual-pointer-unstable-v1.xml (MIT, Josef Gajdusek, 2019).
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
struct wl_proxy;
struct wl_message { const char *name,*signature; const struct wl_interface **types; };
struct wl_interface {const char *name; int version,method_count; const struct wl_message *methods; int event_count; const struct wl_message *events;};
extern const struct wl_interface wl_registry_interface,wl_seat_interface;
extern void *wl_display_connect(const char*);
extern void wl_display_disconnect(void*);
extern int wl_display_roundtrip(void*),wl_display_flush(void*);
extern struct wl_proxy *wl_proxy_marshal_flags(struct wl_proxy*,uint32_t,const struct wl_interface*,uint32_t,uint32_t,...);
extern int wl_proxy_add_listener(struct wl_proxy*,void (**)(void),void*);
extern void wl_proxy_destroy(struct wl_proxy*);
static const struct wl_message pointer_methods[]={
 {"motion","uff",NULL},{"motion_absolute","uuuuu",NULL},{"button","uuu",NULL},
 {"axis","uuf",NULL},{"frame","",NULL},{"axis_source","u",NULL},
 {"axis_stop","uu",NULL},{"axis_discrete","uufi",NULL},{"destroy","",NULL}};
static const struct wl_interface pointer_interface={"zwlr_virtual_pointer_v1",2,9,pointer_methods,0,NULL};
static const struct wl_interface *create_types[]={&wl_seat_interface,&pointer_interface};
static const struct wl_message manager_methods[]={{"create_virtual_pointer","?on",create_types},{"destroy","",NULL}};
static const struct wl_interface manager_interface={"zwlr_virtual_pointer_manager_v1",1,2,manager_methods,0,NULL};
static struct wl_proxy *manager;
static void global(void *data,struct wl_proxy *reg,uint32_t name,const char *interface,uint32_t version){
 if(!strcmp(interface,manager_interface.name)) manager=wl_proxy_marshal_flags(reg,0,&manager_interface,1,0,name,manager_interface.name,1,NULL);
}
static void removed(void*d,struct wl_proxy*r,uint32_t n){}
static uint32_t stamp(){struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1000+t.tv_nsec/1000000;}
int main(){
 void *display=wl_display_connect(NULL); if(!display){perror("connect");return 1;}
 struct wl_proxy *reg=wl_proxy_marshal_flags(display,1,&wl_registry_interface,1,0,NULL);
 void (*listener[])(void)={(void(*)(void))global,(void(*)(void))removed};
 wl_proxy_add_listener(reg,listener,NULL);wl_display_roundtrip(display);
 if(!manager){fputs("No virtual-pointer protocol\n",stderr);return 2;}
 struct wl_proxy *pointer=wl_proxy_marshal_flags(manager,0,&pointer_interface,1,0,NULL,NULL);
 wl_display_roundtrip(display);puts("READY");fflush(stdout);
 char line[160];unsigned x,y,w,h,state;int steps;
 while(fgets(line,sizeof(line),stdin)){
  if(sscanf(line,"move %u %u %u %u",&x,&y,&w,&h)==4)wl_proxy_marshal_flags(pointer,1,NULL,1,0,stamp(),x,y,w,h);
  else if(sscanf(line,"button %u",&state)==1)wl_proxy_marshal_flags(pointer,2,NULL,1,0,stamp(),272,state);
  else if(sscanf(line,"scroll %d",&steps)==1){wl_proxy_marshal_flags(pointer,5,NULL,1,0,0);wl_proxy_marshal_flags(pointer,7,NULL,1,0,stamp(),0,steps*10*256,steps);}
  else if(!strncmp(line,"quit",4))break;
  wl_proxy_marshal_flags(pointer,4,NULL,1,0);wl_display_roundtrip(display);puts("OK");fflush(stdout);
 }
 wl_proxy_marshal_flags(pointer,8,NULL,1,1);wl_proxy_marshal_flags(manager,1,NULL,1,1);wl_proxy_destroy(reg);wl_display_flush(display);wl_display_disconnect(display);
}
