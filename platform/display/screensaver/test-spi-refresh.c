/* Hardware-free SPI protocol/dirty-region regression checks. */
#define SCREENSAVER_TEST
#include "screensaver.c"
#include <assert.h>
#include <stdarg.h>

static uint16_t panel[WIDTH*HEIGHT];
static unsigned dc, opcode, x0, x1, y0, y1, cursor;
static size_t pixel_bytes, pixel_writes, windows;
static int interrupt_pixel_once;
int __wrap_ioctl(int fd,unsigned long request,...)
{
    (void)fd;assert(request==GPIO_V2_LINE_SET_VALUES_IOCTL);
    va_list args;va_start(args,request);
    struct gpio_v2_line_values *values=va_arg(args,struct gpio_v2_line_values*);
    va_end(args);
    if(values->mask&1)dc=(unsigned)(values->bits&1);
    return 0;
}
ssize_t __wrap_write(int fd,const void *buffer,size_t length)
{
    (void)fd;
    const uint8_t *data=buffer;
    if(!dc) {
        assert(length==1);opcode=data[0];
        assert(opcode==0x2a || opcode==0x2b || opcode==0x2c);
        if(opcode==0x2c){cursor=0;++windows;}
        return (ssize_t)length;
    }
    if(opcode==0x2a || opcode==0x2b) {
        assert(length==4);
        unsigned first=((unsigned)data[0]<<8)|data[1],last=((unsigned)data[2]<<8)|data[3];
        if(opcode==0x2a){x0=first;x1=last;assert(x0<=x1 && x1<WIDTH);}
        else{y0=first;y1=last;assert(y0<=y1 && y1<HEIGHT);}
    } else {
        assert(opcode==0x2c && length>0 && length<=pixel_chunk && length%2==0);
        if(interrupt_pixel_once){interrupt_pixel_once=0;errno=EINTR;return -1;}
        unsigned width=x1-x0+1,height=y1-y0+1;
        assert(cursor+length/2<=width*height);
        for(size_t i=0;i<length;i+=2) {
            unsigned x=x0+cursor%width,y=y0+cursor/width;
            panel[y*WIDTH+x]=(uint16_t)(((uint16_t)data[i]<<8)|data[i+1]);
            ++cursor;
        }
        pixel_bytes+=length;++pixel_writes;
    }
    return (ssize_t)length;
}
static void reset_counts(void){pixel_bytes=0;pixel_writes=0;windows=0;}
static void correct(void){assert(!memcmp(panel,pixels,sizeof(panel)));}
static size_t old_tile_payload(void)
{
    size_t bytes=0;
    for(int y=0;y<HEIGHT;y+=16)
        for(int x=0;x<WIDTH;x+=16)
            if(tile_changed(x,y))bytes+=16*16*2;
    return bytes;
}
int main(int argc,char **argv)
{
    assert(argc==2);load_bjorni(argv[1]);
    spi_fd=100;lines_fd=101;pixel_chunk=4096;
    refresh(1);correct();assert(windows==1 && pixel_bytes==WIDTH*HEIGHT*2);
    assert(pixel_writes==(WIDTH*HEIGHT*2+4095)/4096);
    reset_counts();refresh(0);correct();assert(windows==0 && pixel_bytes==0);
    pixels[7*WIDTH+7]=0xffff;
    interrupt_pixel_once=1;
    reset_counts();refresh(0);correct();
    assert(windows==1 && pixel_bytes==2 && x0==7 && x1==7 && y0==7 && y1==7);
    pixels[15*WIDTH+15]=0x1234;pixels[16*WIDTH+16]=0xabcd;
    pixels[WIDTH*HEIGHT-1]=0xf800;pixels[0]=0x07e0;
    reset_counts();refresh(0);correct();
    unsigned random=42;
    for(int f=0;f<10;++f) {
        for(int i=0;i<300;++i) {
            random=random*1664525u+1013904223u;
            pixels[random%(WIDTH*HEIGHT)]=(uint16_t)(random>>16);
        }
        size_t old=old_tile_payload();
        reset_counts();refresh(0);correct();assert(pixel_bytes<=old);
    }
    size_t before=0,after=0;
    for(int f=0;f<30;++f) {
        render(f*.1,(time_t)1795534620+f/10,1);
        before+=old_tile_payload();
        reset_counts();refresh(0);correct();after+=pixel_bytes;
    }
    assert(after<before);
    printf("PASS SPI: big-endian pixels, full/unchanged/single-pixel/edge/random/animation frames, EINTR\n");
    printf("Pixel payload in 30-frame host sample: %zu -> %zu bytes (%.0f%% smaller)\n",
           before,after,100.*(1-(double)after/before));
    pixel_chunk=1024;reset_counts();refresh(1);correct();
    assert(pixel_writes==150);
    return 0;
}
