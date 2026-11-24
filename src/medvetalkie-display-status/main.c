/* MedveTalkie display status bridge.
 * Polls the ONE Core API and writes a bounded MTSTATUS1 snapshot for the
 * independent ST7789 renderer. No radio operations and no shell execution.
 */
#define _POSIX_C_SOURCE 200809L
#include "medvetalkie/ipc.h"
#include <json-c/json.h>
#include <arpa/inet.h>
#include <errno.h>
#include <ifaddrs.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t terminate_requested;
static void stop(int sig) {(void)sig;terminate_requested=1;}

typedef struct {
    const char *mode, *headset1, *headset2, *voice;
    const char *network, *radio, *battery, *fault;
    unsigned usb, connected;
} status_snapshot;

static int known_mode(const char *mode)
{
    static const char *const modes[]={
        "STANDBY","INTERCOM","PAIRING","DEGRADED","ERROR",
        "SOLO_STEREO","ANDROID_MEDIA","ANDROID_BRIDGE_CALL",
        "PHONE_DIRECT","RADIO","GAME","STARTING","BOOT"
    };
    if(!mode)return 0;
    for(size_t i=0;i<sizeof(modes)/sizeof(*modes);++i)
        if(!strcmp(mode,modes[i]))return 1;
    return 0;
}

/* Check for assigned non-loopback IPv4, not internet connectivity.
 * No scan, DHCP changes, or network control is performed. */
static const char *observe_network(void)
{
    struct ifaddrs *ifaces=NULL;
    const char *network="NO_LINK";
    if(getifaddrs(&ifaces)!=0)return "UNKNOWN";
    for(struct ifaddrs *p=ifaces;p;p=p->ifa_next){
        if(!p->ifa_addr || p->ifa_addr->sa_family!=AF_INET)continue;
        if(!strcmp(p->ifa_name,"lo"))continue;
        if(!strncmp(p->ifa_name,"end",3)||
           !strncmp(p->ifa_name,"eth",3)||
           !strncmp(p->ifa_name,"en",2)){
            network="LAN";break;
        }
        if(!strncmp(p->ifa_name,"wlan",4)||
           !strncmp(p->ifa_name,"wl",2))network="WIFI";
    }
    freeifaddrs(ifaces);
    return network;
}

static json_object *query(const char *socket_path,const char *action)
{
    char request[128],response[MT_IPC_MAX_FRAME+1];
    json_object *result,*type;
    if(snprintf(request,sizeof(request),
         "{\"v\":1,\"type\":\"query\",\"action\":\"%s\"}",action)>=(int)sizeof(request))
        return NULL;
    if(mt_ipc_exchange(socket_path,request,response,sizeof(response))<0)
        return NULL;
    result=json_tokener_parse(response);
    if(!result||!json_object_is_type(result,json_type_object)) {
        if(result)json_object_put(result);
        return NULL;
    }
    if(!json_object_object_get_ex(result,"type",&type) ||
       !json_object_is_type(type,json_type_string) ||
       !strcmp(json_object_get_string(type),"error")){
        json_object_put(result);return NULL;
    }
    return result;
}
static const char *string_field(json_object *obj,const char *key)
{
    json_object *value=NULL;
    if(!obj || !json_object_object_get_ex(obj,key,&value) ||
       !json_object_is_type(value,json_type_string))return NULL;
    return json_object_get_string(value);
}
static int unsigned_field(json_object *obj,const char *key,unsigned *out)
{
    json_object *value=NULL;
    if(!obj || !json_object_object_get_ex(obj,key,&value) ||
       !json_object_is_type(value,json_type_int) ||
       json_object_get_int64(value)<0 ||
       json_object_get_int64(value)>32)return -1;
    *out=(unsigned)json_object_get_int(value);
    return 0;
}

static void collect(const char *socket_path,status_snapshot *s)
{
    json_object *core,*bt,*bluez,*state=NULL,*devices=NULL;
    memset(s,0,sizeof(*s));
    s->mode="CORE_OFFLINE";
    s->headset1=s->headset2="UNASSIGNED"; /* No role binding yet. */
    s->voice="NOT_VERIFIED";             /* HFP+SCO+mic never inferred. */
    s->network=observe_network();
    s->radio="NOT_AVAILABLE";
    s->battery="UNKNOWN";
    s->fault="CORE_OFFLINE";
    core=query(socket_path,"system.status");
    if(!core)return;
    s->mode="UNKNOWN";
    s->fault="NONE";
    if(json_object_object_get_ex(core,"state",&state) &&
       json_object_is_type(state,json_type_object)){
        const char *effective=string_field(state,"effective_mode");
        const char *desired=string_field(state,"desired_mode");
        if(known_mode(effective))s->mode=effective;
        else if(effective && !strcmp(effective,"UNKNOWN") &&
                desired && !strcmp(desired,"UNSET"))
            s->mode="STANDBY"; /* UI idle only: NOT INTERCOM/HFP readiness. */
    }
    bt=query(socket_path,"bt.controllers");
    if(bt) {
        if(unsigned_field(bt,"usb_controller_count",&s->usb)!=0)
            s->fault="BT_FAILED";
        json_object_put(bt);
    } else s->fault="BT_FAILED";
    bluez=query(socket_path,"bt.bluez");
    if(bluez) {
        unsigned count=0;
        if(json_object_object_get_ex(bluez,"devices",&devices) &&
           json_object_is_type(devices,json_type_array)) {
            size_t total=json_object_array_length(devices);
            if(total>96)total=96;
            for(size_t i=0;i<total;i++){
                json_object *device=json_object_array_get_idx(devices,(int)i);
                json_object *connected=NULL;
                if(json_object_object_get_ex(device,"connected",&connected) &&
                   json_object_is_type(connected,json_type_boolean) &&
                   json_object_get_boolean(connected))++count;
            }
            s->connected=count>32?32:count;
        } else s->fault="BT_FAILED";
        json_object_put(bluez);
    } else s->fault="BT_FAILED";
    /* A missing kernel HCI is not a usable Bluetooth controller. */
    if(s->usb==0 && !strcmp(s->fault,"NONE"))s->fault="BT_FAILED";
    json_object_put(core);
}

static int publish(const char *path,const status_snapshot *s)
{
    char tmp[512],payload[1024];
    int fd;
    FILE *out;
    if(strlen(path)>440)return -1;
    snprintf(tmp,sizeof(tmp),"%s.tmp.XXXXXX",path);
    int len=snprintf(payload,sizeof(payload),
        "MTSTATUS1\n"
        "mode=%s\nheadset1=%s\nheadset2=%s\nvoice=%s\n"
        "network=%s\nradio=%s\nbattery=%s\nfault=%s\n"
        "bt_usb=%u\nbt_connected=%u\n",
        s->mode,s->headset1,s->headset2,s->voice,s->network,
        s->radio,s->battery,s->fault,s->usb,s->connected);
    if(len<0 || len>=(int)sizeof(payload))return -1;
    mode_t mask=umask(0077);
    fd=mkstemp(tmp);
    umask(mask);
    if(fd<0)return -1;
    if(fchmod(fd,0600)!=0){
        close(fd);unlink(tmp);return -1;
    }
    out=fdopen(fd,"w");
    if(!out){close(fd);unlink(tmp);return -1;}
    int ok=fwrite(payload,1,(size_t)len,out)==(size_t)len &&
           fflush(out)==0 && fsync(fd)==0 && fclose(out)==0;
    if(!ok){unlink(tmp);return -1;}
    if(rename(tmp,path)!=0){unlink(tmp);return -1;}
    return 0;
}

int main(int argc,char **argv)
{
    const char *socket_path=MT_IPC_DEFAULT_SOCKET,*output=NULL;
    int once=0,interval=2;
    for(int i=1;i<argc;i++){
        if(!strcmp(argv[i],"--ipc-socket")&&i+1<argc)
            socket_path=argv[++i];
        else if(!strcmp(argv[i],"--output")&&i+1<argc)
            output=argv[++i];
        else if(!strcmp(argv[i],"--once"))once=1;
        else if(!strcmp(argv[i],"--interval")&&i+1<argc){
            const char *s=argv[++i];
            if(strlen(s)!=1 || s[0]<'1' || s[0]>'9')return 64;
            interval=s[0]-'0';
        } else if(!strcmp(argv[i],"--version")){
            puts("medvetalkie-display-status 0.0.1-alpha");return 0;
        } else {
            fputs("Usage: display-status --output ABS_PATH "
                  "[--ipc-socket ABS_PATH] [--interval 1..9] [--once]\n",stderr);
            return 64;
        }
    }
    if(!output || output[0]!='/' || socket_path[0]!='/')return 64;
    struct sigaction handler={0};handler.sa_handler=stop;
    sigemptyset(&handler.sa_mask);
    (void)sigaction(SIGTERM,&handler,NULL);
    (void)sigaction(SIGINT,&handler,NULL);
    do{
        status_snapshot s;
        collect(socket_path,&s);
        if(publish(output,&s)!=0){
            fprintf(stderr,"Cannot publish status snapshot: %s\n",strerror(errno));
            return 1;
        }
        if(once)break;
        struct timespec pause={interval,0};
        while(nanosleep(&pause,&pause)!=0 && errno==EINTR && !terminate_requested){}
    }while(!terminate_requested);
    return 0;
}
