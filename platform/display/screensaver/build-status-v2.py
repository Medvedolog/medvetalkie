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

V2_SCREEN=r'''/* Four approved 320x240 layouts. No button control, read-only status. */
static uint16_t state_colour(const char *s)
{
    if(!strcmp(s,"HFP_READY") || !strcmp(s,"A2DP_READY"))return rgb(40,217,128);
    if(!strcmp(s,"PROFILE_PENDING") || !strcmp(s,"CONNECTED_NO_AUDIO"))return rgb(251,180,61);
    if(!strcmp(s,"DISCONNECTED"))return rgb(245,70,78);
    return rgb(115,137,155);
}
static void bar_v2(int x,int y,int w,int pct,uint16_t c)
{
    rect(x,y,w,5,rgb(38,67,91));
    if(pct>=0)rect(x,y,(w*(pct>100?100:pct))/100,5,c);
}
/* Native RGB565 smiling bear in over-ear headphones (no emoji or image loader).
 * Headphones wrap around the two round ears, not merely sit next to the head.
 */
static void happy_bear(int x,int y,int k,uint16_t cup)
{
    uint16_t fur=rgb(165,106,55),ear=rgb(131,76,41),muzzle=rgb(234,191,141);
    uint16_t black=rgb(32,31,38),white=rgb(250,238,216);
    disc(x-13*k,y-11*k,7*k,ear);disc(x+13*k,y-11*k,7*k,ear);
    disc(x-13*k,y-11*k,4*k,muzzle);disc(x+13*k,y-11*k,4*k,muzzle);
    disc(x,y,19*k,fur);
    /* blue padded headband arches above the brown bear */
    for(int z=0;z<3*k;++z) {
        line(x-18*k+z,y-8*k,x-18*k+z,y-17*k,cup);
        line(x-18*k+z,y-17*k,x-11*k,y-23*k+z,cup);
        line(x-11*k,y-23*k+z,x+11*k,y-23*k+z,cup);
        line(x+11*k,y-23*k+z,x+18*k-z,y-17*k,cup);
        line(x+18*k-z,y-17*k,x+18*k-z,y-8*k,cup);
    }
    rect(x-21*k,y-8*k,7*k,17*k,cup);
    rect(x+14*k,y-8*k,7*k,17*k,cup);
    rect(x-17*k,y-6*k,3*k,13*k,rgb(190,220,241));
    rect(x+14*k,y-6*k,3*k,13*k,rgb(190,220,241));
    disc(x-7*k,y-2*k,2*k,black);disc(x+7*k,y-2*k,2*k,black);
    disc(x,y+8*k,9*k,muzzle);disc(x,y+5*k,3*k,black);
    line(x,y+8*k,x,y+11*k,black);
    line(x-6*k,y+10*k,x-3*k,y+13*k,black);
    line(x-3*k,y+13*k,x,y+14*k,black);
    line(x,y+14*k,x+3*k,y+13*k,black);
    line(x+3*k,y+13*k,x+6*k,y+10*k,black);
    dot(x-7*k,y-3*k,white);dot(x+7*k,y-3*k,white);
}
static void topbar_v2(time_t wall,const char *mode)
{
    uint16_t white=rgb(235,244,253),cyan=rgb(44,214,246);
    rect(0,0,320,31,rgb(9,24,42));
    text(9,9,"MEDVETALKIE",2,white);
    struct tm tm;
    char clock[12]="--:--";
    if(localtime_r(&wall,&tm))strftime(clock,sizeof(clock),"%H:%M",&tm);
    text(266,12,clock,1,white);
    (void)mode;
    rect(0,29,320,2,cyan);
}
static void card_v2(int x,const char *name,const char *state,const char *profile,
                    int battery,int rssi,int volume,uint16_t base)
{
    uint16_t white=rgb(234,243,253),dim=rgb(156,181,203),c=state_colour(state);
    rect(x,39,149,149,base);
    rect(x,39,149,2,c);
    text(x+11,47,name,2,white);
    happy_bear(x+42,105,1,rgb(44,164,238));
    disc(x+81,76,4,c);
    text(x+91,73,profile,1,c);
    /* show physical ACL status separately from audio profile */
    if(!strcmp(state,"DISCONNECTED"))text(x+76,90,"OFFLINE",1,c);
    else if(!strcmp(state,"UNASSIGNED"))text(x+76,90,"UNKNOWN",1,c);
    else if(!strcmp(state,"HFP_READY"))text(x+76,90,"VOICE",1,c);
    else text(x+76,90,"LINK",1,c);
    char buf[26];
    if(battery>=0)snprintf(buf,sizeof(buf),"%d%%",battery);
    else strcpy(buf,"--");
    text(x+79,107,buf,1,white);
    bar_v2(x+79,118,59,battery,battery>=0&&battery<20?rgb(239,76,77):rgb(52,223,124));
    if(rssi!=-128)snprintf(buf,sizeof(buf),"%d dBm",rssi);
    else strcpy(buf,"--");
    text(x+11,135,buf,1,dim);
    if(volume>=0)snprintf(buf,sizeof(buf),"%d%%",volume);
    else strcpy(buf,"--");
    text(x+102,135,buf,1,white);
    bar_v2(x+11,153,127,volume,rgb(40,194,237));
    ru_text(x+11,165,"ГРОМКОСТЬ",1,dim);
}
static void bottom_v2(const display_status *s)
{
    uint16_t white=rgb(234,243,253),cyan=rgb(36,205,240);
    rect(8,195,198,37,rgb(18,45,71));
    rect(212,195,100,37,rgb(18,45,71));
    ru_text(15,201,"РЕЖИМ",1,cyan);
    text(67,201,s->mode,1,white);
    ru_text(15,217,"ГОЛОС",1,cyan);
    text(70,217,!strcmp(s->voice,"READY")?"ON":"--",1,white);
    text(218,201,s->network,1,white);
    char buf[24];snprintf(buf,sizeof(buf),"BT:%u",s->bt_connected);
    text(218,217,buf,1,white);
}
static void render_intercom_v2(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));topbar_v2(wall,s->mode);
    card_v2(8,"AIRIDE",s->headset1,s->h1_profile,
            s->h1_battery,s->h1_rssi,s->h1_volume,rgb(9,43,88));
    card_v2(163,"UGREEN",s->headset2,s->h2_profile,
            s->h2_battery,s->h2_rssi,s->h2_volume,rgb(6,64,45));
    bottom_v2(s);
}
static void render_radio_v2(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));topbar_v2(wall,s->mode);
    rect(8,40,304,147,rgb(10,45,72));
    happy_bear(72,112,2,rgb(39,174,248));
    ru_text(135,66,"РАДИО",2,rgb(242,247,251));
    text(135,106,s->radio,1,rgb(57,224,138));
    ru_text(135,137,"ЧАСТОТА",1,rgb(153,184,204));
    text(216,137,"--",1,rgb(234,241,250));
    bottom_v2(s);
}
static void render_warning_v2(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));topbar_v2(wall,s->mode);
    rect(8,40,134,147,rgb(14,47,82));
    happy_bear(75,115,2,rgb(45,166,248));
    rect(149,40,163,147,rgb(94,21,37));
    ru_text(161,62,"ВНИМАНИЕ",2,rgb(255,103,107));
    ru_text(163,101,"ОШИБКА",1,rgb(245,245,250));
    text(163,122,s->fault,1,rgb(255,205,211));
    bottom_v2(s);
}
static void render_system_v2(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));topbar_v2(wall,s->mode);
    rect(8,39,304,149,rgb(12,44,75));
    ru_text(33,49,"СОСТОЯНИЕ СИСТЕМЫ",1,rgb(236,246,252));
    ru_text(20,73,"РЕЖИМ",1,rgb(154,185,203));
    text(107,73,s->mode,1,rgb(244,247,252));
    ru_text(20,96,"ГОЛОС",1,rgb(154,185,203));
    text(107,96,s->voice,1,rgb(55,221,143));
    ru_text(20,119,"СЕТЬ",1,rgb(154,185,203));
    text(107,119,s->network,1,rgb(244,247,252));
    char buf[32];snprintf(buf,sizeof(buf),"USB %u / BT %u",s->bt_usb,s->bt_connected);
    ru_text(20,142,"СВЯЗЬ",1,rgb(154,185,203));
    text(107,142,buf,1,rgb(244,247,252));
    ru_text(20,165,"РАДИО",1,rgb(154,185,203));
    text(107,165,s->radio,1,rgb(244,247,252));
    rect(8,195,304,37,rgb(18,51,64));
    text(20,208,strcmp(s->fault,"NONE")?s->fault:"SYSTEM OK",1,
         strcmp(s->fault,"NONE")?rgb(255,95,106):rgb(60,224,132));
}
static void render_status(time_t wall,const display_status *s)
{
    if(strcmp(s->fault,"NONE") && strcmp(s->fault,"CORE_OFFLINE"))
        render_warning_v2(wall,s);
    else if(!strcmp(s->mode,"RADIO"))render_radio_v2(wall,s);
    else if(!strcmp(s->mode,"GAME"))render_warning_v2(wall,s);
    else if(!strcmp(s->mode,"INTERCOM") || s->bt_connected>0)
        render_intercom_v2(wall,s);
    else render_system_v2(wall,s);
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
