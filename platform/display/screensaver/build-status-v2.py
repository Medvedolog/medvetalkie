#!/usr/bin/env python3
"""Generate an optional v2 ST7789 renderer from the same proven C source.

Original screensaver.c and the existing launcher are never modified.
The generated C retains one SPI/GPIO owner, Bjorni, strict freshness and faults.
"""
import argparse
from pathlib import Path

HERE=Path(__file__).resolve().parent
ORIGINAL=HERE/"screensaver.c"

def exactly(source,old,new):
    if source.count(old)!=1:
        raise ValueError("Renderer source changed: expected exactly one "+repr(old[:45]))
    return source.replace(old,new)

def enhance(source):
    source=exactly(source,'#include "../st7789-test.c"',
                   '#include "'+str((HERE.parent/"st7789-test.c").resolve())+'"')
    source=exactly(source,"    unsigned bt_usb, bt_connected;\n} display_status;",
                   """    unsigned bt_usb, bt_connected;
    int h1_battery,h2_battery,h1_rssi,h2_rssi,h1_volume,h2_volume;
    char h1_profile[24],h2_profile[24];
} display_status;""")
    source=exactly(source,'    strcpy(s->fault,"CORE_OFFLINE");\n}',
                   """    strcpy(s->fault,"CORE_OFFLINE");
    s->h1_battery=s->h2_battery=s->h1_volume=s->h2_volume=-1;
    s->h1_rssi=s->h2_rssi=-128;
    strcpy(s->h1_profile,"UNKNOWN");strcpy(s->h2_profile,"UNKNOWN");
}""")
    marker='        if (!strcmp(line,"bt_usb") || !strcmp(line,"bt_connected")) {'
    source=exactly(source,marker,"""        if (!strcmp(line,"h1_battery") || !strcmp(line,"h2_battery") ||
            !strcmp(line,"h1_volume") || !strcmp(line,"h2_volume") ||
            !strcmp(line,"h1_rssi") || !strcmp(line,"h2_rssi")) {
            char *end=NULL;errno=0;long v=strtol(sep,&end,10);
            int is_rssi=strstr(line,"rssi")!=NULL;
            int max=(strstr(line,"battery")!=NULL)?100:150;
            if(errno || end==sep || *end ||
               (is_rssi ? (v < -128 || v > 20) : (v < -1 || v > max))) {
                fclose(file);return 0;
            }
            if(!strcmp(line,"h1_battery"))next.h1_battery=(int)v;
            else if(!strcmp(line,"h2_battery"))next.h2_battery=(int)v;
            else if(!strcmp(line,"h1_rssi"))next.h1_rssi=(int)v;
            else if(!strcmp(line,"h2_rssi"))next.h2_rssi=(int)v;
            else if(!strcmp(line,"h1_volume"))next.h1_volume=(int)v;
            else next.h2_volume=(int)v;
            continue;
        }
"""+marker)
    source=exactly(source,'        else if(!strcmp(line,"fault"))dest=next.fault;',
                   '''        else if(!strcmp(line,"fault"))dest=next.fault;
        else if(!strcmp(line,"h1_profile"))dest=next.h1_profile;
        else if(!strcmp(line,"h2_profile"))dest=next.h2_profile;''')
    source=exactly(source,'        if(strlen(sep)>=24 || !status_token(sep)){fclose(file);return 0;}',
                   '''        int is_profile=!strcmp(line,"h1_profile") || !strcmp(line,"h2_profile");
        if(strlen(sep)>=24 ||
           (is_profile ? (strcmp(sep,"HFP") && strcmp(sep,"A2DP") && strcmp(sep,"UNKNOWN"))
                       : !status_token(sep))){fclose(file);return 0;}''')
    first=source.index('static void status_row(')
    last=source.index('\nstatic unsigned read_le(',first)
    return source[:first]+V2_SCREEN+source[last:]

V2_SCREEN=r'''static uint16_t status_colour(const char *value)
{
    if(!strcmp(value,"HFP_READY") || !strcmp(value,"A2DP_READY"))return rgb(50,215,125);
    if(!strcmp(value,"PROFILE_PENDING") || !strcmp(value,"CONNECTED_NO_AUDIO"))
        return rgb(255,181,64);
    if(!strcmp(value,"DISCONNECTED"))return rgb(250,90,100);
    return rgb(126,149,163);
}
static void status_meter(int x,int y,int w,int value,uint16_t colour)
{
    rect(x,y,w,4,rgb(47,67,79));
    if(value>=0)rect(x,y,w*(value>100?100:value)/100,4,colour);
}
static void status_headset(int y,int idx,const char *state,const char *profile,
                           int battery,int rssi,int volume)
{
    uint16_t white=rgb(236,244,250),muted=rgb(142,164,180),c=status_colour(state);
    char label[28],buf[32];
    rect(9,y,302,62,rgb(19,37,51));
    rect(9,y,4,62,c);
    snprintf(label,sizeof(label),"ГАРНИТУРА %d",idx);
    ru_text(18,y+7,label,1,white);
    text(114,y+7,profile,1,c);
    text(161,y+7,state,1,c);
    ru_text(18,y+22,"ЗАРЯД",1,muted);
    if(battery>=0)snprintf(buf,sizeof(buf),"%d%%",battery);
    else strcpy(buf,"--");
    text(75,y+22,buf,1,battery>=0&&battery<=15?rgb(255,85,90):white);
    status_meter(110,y+25,45,battery,battery>=0&&battery<=15?rgb(250,85,90):rgb(50,215,125));
    ru_text(170,y+22,"ГРОМКОСТЬ",1,muted);
    if(volume>=0)snprintf(buf,sizeof(buf),"%d%%",volume);
    else strcpy(buf,"--");
    text(260,y+22,buf,1,white);
    status_meter(170,y+37,128,volume,rgb(42,220,227));
    ru_text(18,y+43,"СИГНАЛ",1,muted);
    if(rssi!=-128)snprintf(buf,sizeof(buf),"%d DBM",rssi);
    else strcpy(buf,"--");
    text(91,y+43,buf,1,white);
}
static void render_status(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));
    uint16_t white=rgb(236,244,250),cyan=rgb(42,220,227);
    uint16_t amber=rgb(255,181,64),green=rgb(50,215,125),red=rgb(250,72,85);
    rect(0,0,WIDTH,30,rgb(15,32,45));
    text(9,11,"MEDVETALKIE",2,cyan);
    struct tm tm;char clock[16]="--:--";
    if(localtime_r(&wall,&tm))strftime(clock,sizeof(clock),"%H:%M",&tm);
    text(266,12,clock,1,white);
    rect(9,33,302,25,rgb(25,48,61));
    ru_text(16,42,"РЕЖИМ",1,rgb(155,188,204));
    text(79,42,s->mode,1,strcmp(s->fault,"NONE")?red:amber);
    ru_text(224,42,"СВЯЗЬ",1,rgb(155,188,204));
    disc(297,45,4,!strcmp(s->voice,"READY")?green:amber);
    status_headset(61,1,s->headset1,s->h1_profile,
                   s->h1_battery,s->h1_rssi,s->h1_volume);
    status_headset(125,2,s->headset2,s->h2_profile,
                   s->h2_battery,s->h2_rssi,s->h2_volume);
    rect(9,189,302,32,rgb(18,38,48));
    ru_text(16,195,"СЕТЬ",1,rgb(155,188,204));
    text(62,195,s->network,1,white);
    char bt[32];
    snprintf(bt,sizeof(bt),"USB:%u ACL:%u",s->bt_usb,s->bt_connected);
    text(130,195,bt,1,cyan);
    ru_text(16,208,"РАДИО",1,rgb(155,188,204));
    text(75,208,s->radio,1,white);
    rect(0,223,WIDTH,17,strcmp(s->fault,"NONE")?rgb(100,24,31):rgb(16,44,49));
    if(strcmp(s->fault,"NONE")){
        ru_text(12,229,"ОШИБКА",1,white);
        text(110,228,s->fault,1,white);
    } else {
        ru_text(12,229,"БАТАРЕЯ",1,white);
        text(120,228,s->battery,1,white);
    }
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    output=Path(args.output)
    if not output.is_absolute():
        parser.error("Use absolute output path")
    output.write_text(enhance(ORIGINAL.read_text()))
    print(output)

if __name__=="__main__":
    main()
