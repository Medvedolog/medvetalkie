/* Standalone animated Bjorni clock for the verified MSP2008/ST7789 wiring.
 * The launcher embeds this file, the bench driver and the owner's GIF frames.
 */
#define main st7789_bench_main
#include "../st7789-test.c"
#undef main
#include <math.h>
#include <signal.h>

static uint16_t pixels[WIDTH * HEIGHT], previous[WIDTH * HEIGHT];
static uint16_t sprites[35][80 * 112];
static volatile sig_atomic_t stopping;
static double last_fps, last_spi_ms;
static unsigned spi_mhz = 1, target_fps = 25, status_seconds = 8;
static size_t pixel_chunk = 1024;
static const double pi = 3.14159265358979323846;
static void stop_requested(int signum) { (void)signum; stopping = 1; }

static uint16_t rgb(unsigned r, unsigned g, unsigned b)
{
    return (uint16_t)(((r & 248) << 8) | ((g & 252) << 3) | (b >> 3));
}
static uint16_t rainbow(double phase)
{
    double h = phase - floor(phase), x = h * 6;
    unsigned f = (unsigned)((x - floor(x)) * 255);
    switch ((int)x) {
    case 0: return rgb(255, f, 0);
    case 1: return rgb(255 - f, 255, 0);
    case 2: return rgb(0, 255, f);
    case 3: return rgb(0, 255 - f, 255);
    case 4: return rgb(f, 0, 255);
    default: return rgb(255, 0, 255 - f);
    }
}
static void dot(int x, int y, uint16_t colour)
{
    if (x >= 0 && x < WIDTH && y >= 0 && y < HEIGHT)
        pixels[y * WIDTH + x] = colour;
}
static void rect(int x, int y, int w, int h, uint16_t colour)
{
    for (int j = y; j < y + h; ++j)
        for (int i = x; i < x + w; ++i) dot(i, j, colour);
}
static void disc(int x, int y, int radius, uint16_t colour)
{
    for (int dy = -radius; dy <= radius; ++dy)
        for (int dx = -radius; dx <= radius; ++dx)
            if (dx * dx + dy * dy <= radius * radius) dot(x + dx, y + dy, colour);
}
static void line(int x0, int y0, int x1, int y1, uint16_t colour)
{
    int dx = abs(x1-x0), sx = x0 < x1 ? 1 : -1;
    int dy = -abs(y1-y0), sy = y0 < y1 ? 1 : -1, error = dx + dy;
    for (;;) {
        dot(x0, y0, colour);
        if (x0 == x1 && y0 == y1) break;
        int twice = 2 * error;
        if (twice >= dy) { error += dy; x0 += sx; }
        if (twice <= dx) { error += dx; y0 += sy; }
    }
}
struct letter { char c; uint8_t rows[7]; };
static const struct letter font[] = {
 {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
 {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
 {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
 {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
 {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
 {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
 {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
 {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
 {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
 {'I',{14,4,4,4,4,4,14}}, {'J',{7,2,2,2,2,18,12}},
 {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
 {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
 {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
 {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
 {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
 {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
 {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
 {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
 {':',{0,4,4,0,4,4,0}}, {'.',{0,0,0,0,0,6,6}},
 {'-',{0,0,0,31,0,0,0}}, {'!',{4,4,4,4,4,0,4}},
 {'/',{1,2,2,4,8,8,16}}
};
static void text(int x, int y, const char *str, int scale, uint16_t colour)
{
    for (; *str; ++str, x += scale * 6) {
        for (size_t i = 0; i < sizeof(font)/sizeof(font[0]); ++i) {
            if (font[i].c != *str) continue;
            for (int row = 0; row < 7; ++row)
                for (int col = 0; col < 5; ++col)
                    if (font[i].rows[row] & (1u << (4-col)))
                        rect(x + col*scale, y + row*scale, scale, scale, colour);
            break;
        }
    }
}

/* Status UI shares the existing SPI/GPIO owner with the Bjorni animation.
 * A separate unprivileged Core-IPC bridge writes a small, atomically replaced
 * status file. This renderer never talks to BlueZ or infers HFP readiness.
 */
#include <sys/stat.h>

typedef struct {
    char mode[24], headset1[24], headset2[24], voice[24];
    char network[24], radio[24], battery[24], fault[24];
    unsigned bt_usb, bt_connected;
} display_status;

static const char *status_file;
static double last_status_poll = -1, status_visible_since;
static display_status current_status;
static int status_initialized;

static int status_token(const char *value)
{
    static const char *const known[] = {
        "BOOT", "STARTING", "STANDBY", "UNCONFIGURED", "UNKNOWN",
        "INTERCOM", "SOLO_STEREO", "ANDROID_MEDIA", "PHONE_DIRECT",
        "ANDROID_BRIDGE_CALL", "PAIRING", "RADIO", "GAME", "DEGRADED",
        "ERROR", "CORE_OFFLINE", "UNASSIGNED", "DISCONNECTED",
        "CONNECTING", "CONNECTED_NO_AUDIO", "PROFILE_PENDING",
        "HFP_READY", "A2DP_READY", "RECOVERING", "NOT_VERIFIED",
        "NOT_READY", "READY", "NONE", "LAN", "WIFI", "LTE",
        "NO_LINK", "NOT_AVAILABLE", "LOW", "GOOD", "BT_FAILED",
        "AUDIO_FAILED", "LOW_BATTERY"
    };
    for (size_t i=0;i<sizeof(known)/sizeof(*known);++i)
        if (!strcmp(value,known[i])) return 1;
    return 0;
}
static void default_status(display_status *s)
{
    memset(s,0,sizeof(*s));
    strcpy(s->mode,"CORE_OFFLINE");
    strcpy(s->headset1,"UNASSIGNED");
    strcpy(s->headset2,"UNASSIGNED");
    strcpy(s->voice,"NOT_VERIFIED");
    strcpy(s->network,"UNKNOWN");
    strcpy(s->radio,"NOT_AVAILABLE");
    strcpy(s->battery,"UNKNOWN");
    strcpy(s->fault,"CORE_OFFLINE");
}
static int parse_status_file(const char *path, display_status *out)
{
    struct stat st;
    char line[128];
    FILE *file;
    time_t now=time(NULL);
    if (!path || lstat(path,&st) || !S_ISREG(st.st_mode) ||
        st.st_size < 12 || st.st_size > 1024 ||
        st.st_mtime > now+5 || now-st.st_mtime > 12) return 0;
    file=fopen(path,"r");
    if(!file)return 0;
    display_status next;
    default_status(&next);
    if (!fgets(line,sizeof(line),file) || strcmp(line,"MTSTATUS1\n")) {
        fclose(file);return 0;
    }
    /* The only accepted fields are whitelisted status enums and counts.
     * No free text, paths, commands, MAC addresses or credentials. */
    while(fgets(line,sizeof(line),file)) {
        char *sep=strchr(line,'=');
        size_t n=strlen(line);
        if (!sep || n==0 || n>=sizeof(line)-1 || line[n-1]!='\n') {
            fclose(file);return 0;
        }
        line[n-1]=0;
        *sep++=0;
        if (!strcmp(line,"bt_usb") || !strcmp(line,"bt_connected")) {
            unsigned count=0;
            if(!*sep){fclose(file);return 0;}
            for(const char *p=sep;*p;++p) {
                if(*p<'0'||*p>'9'){fclose(file);return 0;}
                count=count*10u+(unsigned)(*p-'0');
                if(count>32){fclose(file);return 0;}
            }
            if(!strcmp(line,"bt_usb"))next.bt_usb=count;
            else next.bt_connected=count;
            continue;
        }
        char *dest=NULL;
        if(!strcmp(line,"mode"))dest=next.mode;
        else if(!strcmp(line,"headset1"))dest=next.headset1;
        else if(!strcmp(line,"headset2"))dest=next.headset2;
        else if(!strcmp(line,"voice"))dest=next.voice;
        else if(!strcmp(line,"network"))dest=next.network;
        else if(!strcmp(line,"radio"))dest=next.radio;
        else if(!strcmp(line,"battery"))dest=next.battery;
        else if(!strcmp(line,"fault"))dest=next.fault;
        else {fclose(file);return 0;}
        if(strlen(sep)>=24 || !status_token(sep)){fclose(file);return 0;}
        strcpy(dest,sep);
    }
    if(ferror(file)){fclose(file);return 0;}
    fclose(file);
    *out=next;
    return 1;
}

/* 5x7 Cyrillic uppercase glyphs for fixed Russian dashboard labels. */
struct ru_glyph { unsigned unicode; uint8_t rows[7]; };
static const struct ru_glyph ru_font[]={
 {0x410,{14,17,17,31,17,17,17}}, /* А */
 {0x411,{31,16,16,30,17,17,30}}, /* Б */
 {0x412,{30,17,17,30,17,17,30}}, /* В */
 {0x413,{31,16,16,16,16,16,16}}, /* Г */
 {0x414,{14,10,10,10,10,31,17}}, /* Д */
 {0x415,{31,16,16,30,16,16,31}}, /* Е */
 {0x416,{21,21,14,4,14,21,21}},  /* Ж */
 {0x417,{14,17,1,6,1,17,14}},   /* З */
 {0x418,{17,19,21,21,21,25,17}},/* И */
 {0x419,{10,0,17,19,21,25,17}}, /* Й */
 {0x41a,{17,18,20,24,20,18,17}},/* К */
 {0x41b,{7,9,17,17,17,17,17}},  /* Л */
 {0x41c,{17,27,21,21,17,17,17}},/* М */
 {0x41d,{17,17,17,31,17,17,17}},/* Н */
 {0x41e,{14,17,17,17,17,17,14}},/* О */
 {0x41f,{31,17,17,17,17,17,17}},/* П */
 {0x420,{30,17,17,30,16,16,16}},/* Р */
 {0x421,{14,17,16,16,16,17,14}},/* С */
 {0x422,{31,4,4,4,4,4,4}},      /* Т */
 {0x423,{17,17,17,15,1,17,14}}, /* У */
 {0x424,{4,14,21,21,21,14,4}},  /* Ф */
 {0x425,{17,17,10,4,10,17,17}}, /* Х */
 {0x426,{17,17,17,17,17,31,1}}, /* Ц */
 {0x427,{17,17,17,15,1,1,1}},   /* Ч */
 {0x428,{21,21,21,21,21,21,31}},/* Ш */
 {0x429,{21,21,21,21,21,31,1}}, /* Щ */
 {0x42a,{24,8,14,9,9,9,14}},    /* Ъ */
 {0x42b,{17,17,29,21,21,21,29}},/* Ы */
 {0x42c,{16,16,30,17,17,17,30}},/* Ь */
 {0x42d,{14,17,1,7,1,17,14}},   /* Э */
 {0x42e,{18,21,21,29,21,21,18}},/* Ю */
 {0x42f,{15,17,17,15,5,9,17}}  /* Я */
};
static void ru_text(int x,int y,const char *str,int scale,uint16_t colour)
{
    const unsigned char *p=(const unsigned char *)str;
    while(*p && x<WIDTH-5*scale){
        unsigned cp=0;
        if(*p<128){cp=*p++;if(cp>='a'&&cp<='z')cp-=32;}
        else if(p[0]==0xd0 && p[1]>=0x90 && p[1]<=0xbf) {
            cp=0x410u+(unsigned)(p[1]-0x90);p+=2;
        } else if(p[0]==0xd1 && p[1]>=0x80 && p[1]<=0x8f) {
            cp=0x440u+(unsigned)(p[1]-0x80);p+=2;
            if(cp>=0x430&&cp<=0x44f)cp-=0x20;
        } else {++p;x+=6*scale;continue;}
        if(cp<128){
            char single[]={ (char)cp,0 };
            text(x,y,single,scale,colour);
        } else {
            for(size_t i=0;i<sizeof(ru_font)/sizeof(*ru_font);++i){
                if(ru_font[i].unicode!=cp)continue;
                for(int row=0;row<7;++row)
                    for(int col=0;col<5;++col)
                        if(ru_font[i].rows[row]&(1u<<(4-col)))
                            rect(x+col*scale,y+row*scale,scale,scale,colour);
                break;
            }
        }
        x+=6*scale;
    }
}
static void status_row(int y,const char *title,const char *value,uint16_t colour)
{
    ru_text(15,y,title,2,rgb(137,164,185));
    text(176,y+2,value,1,colour);
}
static void render_status(time_t wall,const display_status *s)
{
    memset(pixels,0,sizeof(pixels));
    uint16_t white=rgb(236,244,250),cyan=rgb(42,220,227);
    uint16_t amber=rgb(255,181,64),green=rgb(50,215,125),red=rgb(250,72,85);
    uint16_t colour=green;
    if(strcmp(s->fault,"NONE"))colour=red;
    else if(strcmp(s->mode,"STANDBY") || strcmp(s->voice,"READY"))colour=amber;
    rect(0,0,WIDTH,30,rgb(15,32,45));
    ru_text(12,9,"MEDVETALKIE",2,cyan);
    struct tm tm;
    char clock[16]="--:--";
    if(localtime_r(&wall,&tm))strftime(clock,sizeof(clock),"%H:%M",&tm);
    text(264,12,clock,1,white);
    rect(10,39,300,31,rgb(22,38,52));
    ru_text(17,49,"РЕЖИМ",2,white);
    text(133,50,s->mode,1,colour);
    status_row(81,"ГАРНИТУРА 1",s->headset1,white);
    status_row(103,"ГАРНИТУРА 2",s->headset2,white);
    rect(13,124,294,1,rgb(37,65,81));
    status_row(135,"ГОЛОС",s->voice,strcmp(s->voice,"READY")?amber:green);
    char bt[24];
    snprintf(bt,sizeof(bt),"USB %u / ACL %u",s->bt_usb,s->bt_connected);
    status_row(156,"СЕТЬ",s->network,white);
    status_row(177,"БТ",bt,cyan);
    status_row(198,"РАДИО",s->radio,rgb(176,192,205));
    rect(0,223,WIDTH,17,strcmp(s->fault,"NONE")?rgb(100,24,31):rgb(23,47,55));
    if(strcmp(s->fault,"NONE")){
        ru_text(12,229,"ОШИБКА",1,white);
        text(110,228,s->fault,1,white);
    } else {
        ru_text(12,229,"БАТАРЕЯ",1,white);
        text(120,228,s->battery,1,white);
    }
}

static unsigned read_le(FILE *file, int count)
{
    unsigned result = 0;
    for (int i = 0; i < count; ++i) {
        int c = fgetc(file);
        if (c == EOF) { fputs("Truncated Bjorni sprite\n", stderr); exit(1); }
        result |= (unsigned)c << (8*i);
    }
    return result;
}
static void load_bjorni(const char *path)
{
    FILE *file = fopen(path, "rb");
    if (!file) die("Open Bjorni sprite");
    char magic[8];
    if (fread(magic, 1, sizeof(magic), file) != sizeof(magic) ||
        memcmp(magic, "BJORN01\0", 8) || read_le(file, 4) != 80 ||
        read_le(file, 4) != 112 || read_le(file, 4) != 35 ||
        read_le(file, 4) != 280) {
        fputs("Invalid Bjorni sprite format\n", stderr); exit(1);
    }
    uint16_t palette[64];
    unsigned offsets[36];
    for (int i = 0; i < 64; ++i) palette[i] = (uint16_t)read_le(file, 2);
    for (int i = 0; i < 36; ++i) offsets[i] = read_le(file, 4);
    if (offsets[0] != 0) { fputs("Invalid sprite offsets\n", stderr); exit(1); }
    for (int f = 0; f < 35; ++f) {
        unsigned pos = 0;
        if (offsets[f+1] < offsets[f] || offsets[f+1]-offsets[f] > 80*112) {
            fputs("Invalid sprite run count\n", stderr); exit(1);
        }
        for (unsigned i = offsets[f]; i < offsets[f+1]; ++i) {
            unsigned run = read_le(file, 2), count = run >> 6;
            if (!count || count > 80*112-pos) {
                fputs("Invalid sprite run length\n", stderr); exit(1);
            }
            for (unsigned j = 0; j < count; ++j)
                sprites[f][pos++] = palette[run & 63];
        }
        if (pos != 80*112) { fputs("Incomplete sprite frame\n", stderr); exit(1); }
    }
    if (fgetc(file) != EOF) { fputs("Trailing sprite data\n", stderr); exit(1); }
    fclose(file);
}
static void bear(int x, int y, double seconds)
{
    int frame = (int)(seconds / .280) % 35;
    for (int j = 0; j < 112; ++j)
        for (int i = 0; i < 80; ++i)
            if (sprites[frame][j*80+i]) dot(x+i, y+j, sprites[frame][j*80+i]);
}
static int time_synced(void)
{
    const char *path = getenv("MEDVETALKIE_SYNC_STATUS");
    if (!path) return 0;
    FILE *file = fopen(path, "r");
    if (!file) return 0;
    int status = fgetc(file) == '1';
    fclose(file);
    return status;
}
static void render(double t, time_t wall, int synced)
{
    memset(pixels, 0, sizeof(pixels)); /* exact black background */
    uint16_t white = 0xffff, cyan = rgb(0,255,240), yellow = rgb(255,240,0);
    const char *brand = "MEDVETALKIE";
    int tx = 95 + (int)(7*sin(t*.8)), ty = 7 + (int)(2*sin(t*1.7));
    for (int i = 0; brand[i]; ++i) {
        char ch[] = {brand[i],0};
        text(tx+i*12, ty, ch, 2, rainbow(i*.08 + t*.07));
    }
    struct tm local;
    if (!localtime_r(&wall, &local)) { fputs("Cannot read local time\n",stderr); exit(1); }
    char clock[16], date[40], zone[16];
    strftime(clock, sizeof(clock), "%H:%M:%S", &local);
    strftime(date, sizeof(date), "%d.%m.%Y", &local);
    strftime(zone, sizeof(zone), "%Z", &local);
    for (int i = 0; clock[i]; ++i) {
        char ch[] = {clock[i],0};
        text(66+i*24, 35, ch, 4, i<6 ? white : cyan);
    }
    text(109, 72, date, 1, rgb(170,195,220));
    text(175, 72, zone, 1, cyan);
    disc(241, 74, 2, synced ? rgb(40,255,70) : rgb(255,160,0));
    text(247, 71, synced ? "SYNC" : "LOCAL", 1, synced ? rgb(40,255,70) : rgb(255,160,0));

    int bx = 120, by = 94; /* let the GIF animate; avoid needless full-sprite transfers */
    bear(bx, by, t);
    /* Alternating throws: star, star, mushroom. The object rests in the hand. */
    double cycle = fmod(t, 4.0), u = cycle < 1.8 ? cycle/1.8 : 1;
    int turn = (int)(t/4), direction = turn%2 ? -1 : 1;
    int ox = bx+40 + (int)(direction*(-28+56*u));
    int oy = by+76 - (int)(80*4*u*(1-u));
    if (turn%3 == 2) {
        rect(ox-2,oy,5,9,white);
        for (int dy=-7;dy<=0;++dy) {
            int r=(int)sqrt(64-dy*dy);
            rect(ox-r,oy+dy,2*r+1,1,rgb(255,30,65));
        }
        disc(ox-3,oy-4,1,white); disc(ox+4,oy-3,1,white);
    } else {
        for (int i=0;i<10;++i) {
            double a=t*4+i*pi/5-pi/2, b=t*4+(i+1)*pi/5-pi/2;
            double ra=i%2 ? 4:10, rb=(i+1)%2 ? 4:10;
            line(ox+(int)(ra*cos(a)),oy+(int)(ra*sin(a)),
                 ox+(int)(rb*cos(b)),oy+(int)(rb*sin(b)),yellow);
        }
        disc(ox,oy,3,white);
    }
    if (cycle>1.8 && cycle<2.2) {
        double spread=(cycle-1.8)*35;
        for (int i=0;i<8;++i) {
            double a=i*pi/4;
            disc(ox+(int)((12+spread)*cos(a)),oy+(int)((12+spread)*sin(a)),1,rainbow(i/8.));
        }
    }
    /* A rotating pinwheel on the right and a bright moving sweep below. */
    for (int i=0;i<8;++i) {
        double angle=t*2.5+i*pi/4;
        int x=270+(int)(20*cos(angle)), y=140+(int)(20*sin(angle));
        line(270,140,x,y,rainbow(i/8.)); disc(x,y,4,rainbow(i/8.));
    }
    disc(270,140,4,white);
    text(20,112,cycle<1.8 ? "HOP!" : "HEY!",1,cyan);
    text(20,127,"BJORNI",1,rgb(255,170,60));
    char stats[32];
    snprintf(stats,sizeof(stats),"%4.1f FPS",last_fps);
    text(20,151,stats,1,white);
    snprintf(stats,sizeof(stats),"SPI %3.0fMS",last_spi_ms);
    text(20,164,stats,1,rgb(140,170,195));
    snprintf(stats,sizeof(stats),"%u MHZ",spi_mhz);
    text(20,177,stats,1,rgb(140,170,195));
    for (int x=10;x<310;x+=10) rect(x,220,1,x%50==10?6:3,rgb(45,65,85));
    double p=fmod(t*1.4,2.0); if(p>1)p=2-p;
    int sx=12+(int)(292*p);
    rect(sx,214,4,14,white);
    rect(12,232,296,1,rgb(40,55,70));
}
/* Compare 16x16 tiles, merging adjacent changed tiles and trimming unchanged
 * edges. Pack pixels across rows to reduce spidev write/syscall overhead.
 */
static void send_pixel_block(const uint8_t *data, size_t length)
{
    ssize_t sent;
    do { sent=write(spi_fd,data,length); } while(sent<0 && errno==EINTR);
    if(sent<0)die("SPI pixel write");
    if((size_t)sent!=length){errno=EIO;die("Short SPI pixel write");}
}
static void send_rect(int x, int y, int w, int h)
{
    uint8_t columns[]={(uint8_t)(x>>8),(uint8_t)x,(uint8_t)((x+w-1)>>8),(uint8_t)(x+w-1)};
    uint8_t rows[]={(uint8_t)(y>>8),(uint8_t)y,(uint8_t)((y+h-1)>>8),(uint8_t)(y+h-1)};
    command(0x2a,columns,4); command(0x2b,rows,4); command(0x2c,NULL,0);
    uint8_t block[4096];size_t used=0;
    for(int j=y;j<y+h;++j) {
        for(int i=0;i<w;++i) {
            uint16_t p=pixels[j*WIDTH+x+i];
            block[used++]=(uint8_t)(p>>8);block[used++]=(uint8_t)p;
            if(used==pixel_chunk){send_pixel_block(block,used);used=0;}
        }
    }
    if(used)send_pixel_block(block,used);
}
static int tile_changed(int tx, int ty)
{
    for(int y=ty;y<ty+16;++y)
        if(memcmp(&pixels[y*WIDTH+tx],&previous[y*WIDTH+tx],16*sizeof(uint16_t)))return 1;
    return 0;
}
static void refresh(int first)
{
    if(first)send_rect(0,0,WIDTH,HEIGHT);
    else for(int y=0;y<HEIGHT;y+=16) {
        for(int x=0;x<WIDTH;) {
            if(!tile_changed(x,y)){x+=16;continue;}
            int start=x;
            do{x+=16;}while(x<WIDTH && tile_changed(x,y));
            int left=x,right=start-1,top=y+16,bottom=y-1;
            for(int j=y;j<y+16;++j)
                for(int i=start;i<x;++i)
                    if(pixels[j*WIDTH+i]!=previous[j*WIDTH+i]) {
                        if(i<left)left=i;
                        if(i>right)right=i;
                        if(j<top)top=j;
                        if(j>bottom)bottom=j;
                    }
            if(right>=left)send_rect(left,top,right-left+1,bottom-top+1);
        }
    }
    memcpy(previous,pixels,sizeof(pixels));
}
static double monotonic_seconds(void)
{
    struct timespec now;
    if(clock_gettime(CLOCK_MONOTONIC,&now)<0)die("CLOCK_MONOTONIC");
    return now.tv_sec+now.tv_nsec/1e9;
}
static void ppm(const char *path)
{
    FILE *file=fopen(path,"wb");if(!file)die(path);
    fprintf(file,"P6\n%d %d\n255\n",WIDTH,HEIGHT);
    for(int i=0;i<WIDTH*HEIGHT;++i) {
        uint16_t p=pixels[i];
        unsigned char out[]={(unsigned char)(((p>>11)&31)*255/31),
                             (unsigned char)(((p>>5)&63)*255/63),
                             (unsigned char)((p&31)*255/31)};
        if(fwrite(out,1,3,file)!=3)die("Write preview");
    }
    if(fclose(file))die("Close preview");
}
static unsigned setting(const char *value, unsigned max, const char *name)
{
    if(!value || !*value){fprintf(stderr,"Missing %s\n",name);exit(2);}
    for(const char *p=value;*p;++p)
        if(*p<'0' || *p>'9'){fprintf(stderr,"Invalid %s: %s\n",name,value);exit(2);}
    char *end;errno=0;unsigned long number=strtoul(value,&end,10);
    if(errno || *end || number<1 || number>max) {
        fprintf(stderr,"%s must be between 1 and %u\n",name,max);exit(2);
    }
    return (unsigned)number;
}
#ifndef SCREENSAVER_TEST
int main(int argc,char **argv)
{
    int bgr=0;const char *preview=NULL,*asset=getenv("MEDVETALKIE_SPRITE");
    status_file=getenv("MEDVETALKIE_STATUS_FILE");
    double frame=0;
    const char *mhz_env=getenv("MEDVETALKIE_SPI_MHZ"),*fps_env=getenv("MEDVETALKIE_FPS");
    const char *status_env=getenv("MEDVETALKIE_STATUS_SECONDS");
    if(mhz_env)spi_mhz=setting(mhz_env,16,"SPI MHz");
    if(fps_env)target_fps=setting(fps_env,60,"FPS limit");
    if(status_env)status_seconds=setting(status_env,120,"Status seconds");
    for(int i=1;i<argc;++i) {
        if(!strcmp(argv[i],"--bgr"))bgr=1;
        else if(!strcmp(argv[i],"--no-sync"))continue; /* launcher handles this */
        else if(!strcmp(argv[i],"--preview") && i+1<argc)preview=argv[++i];
        else if(!strcmp(argv[i],"--status-file") && i+1<argc)status_file=argv[++i];
        else if(!strcmp(argv[i],"--status-seconds") && i+1<argc)
            status_seconds=setting(argv[++i],120,"Status seconds");
        else if(!strcmp(argv[i],"--spi-mhz") && i+1<argc)
            spi_mhz=setting(argv[++i],16,"SPI MHz");
        else if(!strcmp(argv[i],"--fps") && i+1<argc)
            target_fps=setting(argv[++i],60,"FPS limit");
        else if(!strcmp(argv[i],"--frame") && i+1<argc) {
            char *end;frame=strtod(argv[++i],&end);
            if(*end || !isfinite(frame) || frame<0 || frame>86400){fputs("Invalid frame time\n",stderr);return 2;}
        } else if(!strcmp(argv[i],"--help")) {
            puts("Bjorni screensaver: --bgr, --no-sync, --spi-mhz N, --fps N\n"
                 "Defaults: 1 MHz SPI (verified wiring), up to 25 FPS. Try 4 MHz first.\n"
                 "--preview FILE.ppm --frame SECONDS --status-file FILE --status-seconds N (1..120).\n"
                 "Uses current local system time. Ctrl+C stops and releases GPIO.\n"
                 "MEDVETALKIE_PROXY sets the HTTPS time-sync proxy (launcher).\n"
                 "MEDVETALKIE_TZ overrides the local timezone, e.g. Europe/Moscow.\n"
                 "MEDVETALKIE_STATUS_SECONDS selects standby dashboard dwell (default 8).");return 0;
        } else {fprintf(stderr,"Unknown/incomplete option: %s\n",argv[i]);return 2;}
    }
    if(!asset){fputs("Run using medvetalkie-screensaver.sh\n",stderr);return 2;}
    load_bjorni(asset);
    const char *zone=getenv("MEDVETALKIE_TZ");if(zone && setenv("TZ",zone,1))die("TZ");tzset();
    if(status_file && status_file[0]!='/'){
        fputs("Status file path must be absolute\n",stderr);return 2;
    }
    if(preview){
        if(status_file){
            display_status state;default_status(&state);
            (void)parse_status_file(status_file,&state);
            render_status(time(NULL),&state);
        }else render(frame,time(NULL),1);
        ppm(preview);return 0;
    }
    if(geteuid()!=0){fputs("Run as root to access SPI/GPIO\n",stderr);return 1;}
    struct sigaction action={0};action.sa_handler=stop_requested;sigemptyset(&action.sa_mask);
    if(sigaction(SIGINT,&action,NULL) || sigaction(SIGTERM,&action,NULL))die("sigaction");
    atexit(cleanup);
    spi_fd=open("/dev/spidev1.0",O_WRONLY|O_CLOEXEC);if(spi_fd<0)die("/dev/spidev1.0");
    uint32_t mode=SPI_MODE_0,speed=1000000;uint8_t bits=8,lsb=0;
    if(ioctl(spi_fd,SPI_IOC_WR_MODE32,&mode)<0 || ioctl(spi_fd,SPI_IOC_WR_BITS_PER_WORD,&bits)<0 ||
       ioctl(spi_fd,SPI_IOC_WR_LSB_FIRST,&lsb)<0 || ioctl(spi_fd,SPI_IOC_WR_MAX_SPEED_HZ,&speed)<0)
        die("Configure SPI");
    request_controls();display_init(bgr);
    speed=spi_mhz*1000000u;
    if(ioctl(spi_fd,SPI_IOC_WR_MAX_SPEED_HZ,&speed)<0)die("Set requested SPI speed");
    FILE *buffer_info=fopen("/sys/module/spidev/parameters/bufsiz","r");
    if(buffer_info) {
        unsigned available=0;
        if(fscanf(buffer_info,"%u",&available)==1 && available>=2)
            pixel_chunk=available>=4096 ? 4096 : (available & ~1u);
        fclose(buffer_info);
    }
    printf("SPI requested %u MHz, pixel chunks %zu bytes, FPS limit %u, status %u s\n",
           spi_mhz,pixel_chunk,target_fps,status_seconds);fflush(stdout);
    puts("Bjorni + live clock. HTTPS time check every 15 minutes. Ctrl+C to stop.");
    double start=monotonic_seconds(), report=start, spi_total=0;
    status_visible_since=start;
    unsigned frames=0;int first=1;
    while(!stopping) {
        double begin=monotonic_seconds();
        int show_status=0;
        if(status_file){
            if(last_status_poll<0 || begin-last_status_poll>=0.5){
                display_status fresh;default_status(&fresh);
                (void)parse_status_file(status_file,&fresh);
                if(!status_initialized || memcmp(&fresh,&current_status,sizeof(fresh))){
                    current_status=fresh;
                    status_visible_since=begin;
                    status_initialized=1;
                }
                last_status_poll=begin;
            }
            show_status=strcmp(current_status.mode,"STANDBY") ||
                        strcmp(current_status.fault,"NONE") ||
                        begin-status_visible_since<(double)status_seconds;
        }
        if(show_status)render_status(time(NULL),&current_status);
        else render(begin-start,time(NULL),time_synced());
        double transfer=monotonic_seconds();refresh(first);first=0;
        double end=monotonic_seconds();spi_total+=end-transfer;++frames;
        if(end-report>=1) {
            last_fps=frames/(end-report);last_spi_ms=1000*spi_total/frames;
            report=end;spi_total=0;frames=0;
        }
        double delay=1.0/(show_status?2.0:target_fps)-(monotonic_seconds()-begin);
        if(delay>0) {
            struct timespec nap={(time_t)delay,(long)((delay-floor(delay))*1e9)};
            (void)nanosleep(&nap,NULL);
        }
    }
    command(0x28,NULL,0); /* display off; BLK remains wired to 3.3 V */
    return 0;
}
#endif
