#!/usr/bin/env python3
"""Generate an optional v2 ST7789 renderer from the same proven C source.

Original screensaver.c and the existing launcher are never modified.
The generated C retains one SPI/GPIO owner, Bjorni, strict freshness and faults.
"""
import argparse
import base64
import zlib
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
    # The original bitmap font lacks percent and plus symbols used by metrics.
    source=exactly(source," {'/',{1,2,2,4,8,8,16}}", """ {'/',{1,2,2,4,8,8,16}},
 {'%',{17,18,2,4,8,9,17}}, {'+',{0,4,4,31,4,4,0}}""")
    first=source.index('static void status_row(')
    last=source.index('\nstatic unsigned read_le(',first)
    screen=V2_SCREEN.replace("/* BEAR_PIXEL_RESOURCE */", bear_pixel_resource())
    return source[:first]+screen+source[last:]


def bear_pixel_resource():
    """Decode the user-supplied pixel-art head (with added blue earcups) at build time.

    The renderer itself contains static RGB565 pixels only; no runtime PNG,
    decompression, filesystem reads or image decoding on the Orange Pi.
    """
    encoded=(HERE / "medvetalkie-headphones.rgb565.z.b64").read_text().strip()
    blob=zlib.decompress(base64.b64decode(encoded,validate=True))
    width,height=88,72
    if len(blob)!=width*height*3:
        raise ValueError("Wrong size for MedveTalkie headphone bear sprite")
    colors=[]
    mask=[]
    for i in range(0,len(blob),3):
        colors.append(blob[i]|(blob[i+1]<<8))
        mask.append(blob[i+2])
    if any(v not in (0,1) for v in mask):
        raise ValueError("Invalid bear transparency mask")
    chunks=lambda entries: "\\n".join(
        "    "+",".join(str(v) for v in entries[i:i+22])+","
        for i in range(0,len(entries),22))
    return (f"/* Reference-derived bear head, {width}x{height}, RGB565; generated from versioned asset. */\\n"
            f"static const uint16_t bear_rgb565[{width*height}]={{\\n"+chunks(colors)+
            "\\n};\\n"
            f"static const uint8_t bear_alpha[{width*height}]={{\\n"+chunks(mask)+
            "\\n};\\n")

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
/* BEAR_PIXEL_RESOURCE */
/* Source-derived brown smiling face with actual blue over-ear headphones. */
static void happy_bear(int x,int y,int k,uint16_t cup)
{
    const int w=(k<=1)?62:108, h=(k<=1)?51:88;
    const int left=x-w/2, top=y-h/2;
    (void)cup; /* The headset colours are part of the approved pixel sprite. */
    for(int dy=0;dy<h;dy++){
        int sy=dy*72/h;
        for(int dx=0;dx<w;dx++){
            int sx=dx*88/w;
            unsigned index=(unsigned)(sy*88+sx);
            if(bear_alpha[index])dot(left+dx,top+dy,bear_rgb565[index]);
        }
    }
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
    uint16_t white=rgb(238,246,255),dim=rgb(162,188,209),c=state_colour(state);
    char buf[30];
    rect(x,39,149,149,base);
    rect(x,39,149,3,c);
    text(x+10,47,name,2,white);
    disc(x+132,54,5,c);
    /* Face occupies its own row; labels must never cross the headphones. */
    happy_bear(x+74,105,2,rgb(43,164,246));
    text(x+10,151,profile,1,c);
    if(battery>=0)snprintf(buf,sizeof(buf),"%d%%",battery);
    else strcpy(buf,"--");
    text(x+53,151,buf,1,white);
    if(rssi!=-128)snprintf(buf,sizeof(buf),"%d",rssi);
    else strcpy(buf,"--");
    text(x+104,151,buf,1,dim);
    bar_v2(x+10,169,129,volume,rgb(39,194,246));
    if(volume>=0)snprintf(buf,sizeof(buf),"%d%%",volume);
    else strcpy(buf,"--");
    text(x+106,178,buf,1,white);
    ru_text(x+10,178,"ГРОМКОСТЬ",1,dim);
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
    happy_bear(79,110,2,rgb(39,174,248));
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
static void render_game_v2(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));topbar_v2(wall,s->mode);
    rect(8,40,304,147,rgb(12,45,76));
    happy_bear(83,110,2,rgb(45,166,246));
    ru_text(163,63,"ИГРЫ",2,rgb(235,245,252));
    ru_text(163,105,"РЕЖИМ",1,rgb(145,180,201));
    text(163,121,s->mode,1,rgb(59,226,139));
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
    happy_bear(270,111,1,rgb(43,164,246));
    rect(8,195,304,37,rgb(18,51,64));
    text(20,208,strcmp(s->fault,"NONE")?s->fault:"SYSTEM OK",1,
         strcmp(s->fault,"NONE")?rgb(255,95,106):rgb(60,224,132));
}
static void render_status(time_t wall,const display_status *s)
{
    if(strcmp(s->fault,"NONE") && strcmp(s->fault,"CORE_OFFLINE"))
        render_warning_v2(wall,s);
    else if(!strcmp(s->mode,"RADIO"))render_radio_v2(wall,s);
    else if(!strcmp(s->mode,"GAME"))render_game_v2(wall,s);
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
