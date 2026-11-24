/* MSP2008/ST7789 bench test. Linux GPIO chardev v2 + spidev, no libraries.
 * OPi Zero 3: DC=PC5 (header 13), RESET=PC6 (header 11).
 * CS is owned by the SPI overlay: PH9 (header 24), /dev/spidev1.0.
 * Successful writes do not prove that the display received any data.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/gpio.h>
#include <linux/spi/spidev.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

enum { WIDTH = 320, HEIGHT = 240 };
static int spi_fd = -1, lines_fd = -1;

static void cleanup(void)
{
    if (spi_fd >= 0) close(spi_fd);
    if (lines_fd >= 0) close(lines_fd);
}

static void die(const char *message)
{
    fprintf(stderr, "%s: %s\n", message, strerror(errno));
    exit(EXIT_FAILURE);
}

static void pause_ms(long ms)
{
    struct timespec delay = {ms / 1000, (ms % 1000) * 1000000L};
    while (nanosleep(&delay, &delay) < 0)
        if (errno != EINTR) die("nanosleep");
}

static int is_orangepi_zero3(void)
{
    FILE *file = fopen("/proc/device-tree/compatible", "rb");
    if (!file) return 0;
    char data[512];
    size_t length = fread(data, 1, sizeof(data), file);
    int valid = !ferror(file) && length < sizeof(data);
    fclose(file);
    if (!valid) return 0;
    for (size_t pos = 0; pos < length; ) {
        size_t part = strnlen(data + pos, length - pos);
        if (part == length - pos) return 0; /* malformed DT string list */
        if (strcmp(data + pos, "xunlong,orangepi-zero3") == 0) return 1;
        pos += part + 1;
    }
    return 0;
}

/* Discover the chip; its /dev/gpiochipN index is not stable across boots.
 * Some Armbian DTs omit GPIO line names. On a verified Orange Pi Zero 3,
 * the H616/H618 main PIO uses bank C base 64: PC5=69, PC6=70.
 * Never apply these offsets to the separate R_PIO controller or another SBC.
 */
static void request_controls(void)
{
    glob_t chips = {0};
    int selected = -1;
    unsigned int offsets[2] = {0};
    char selected_path[256] = {0};
    int known_board = is_orangepi_zero3(), selected_by_offsets = 0;
    if (glob("/dev/gpiochip*", 0, NULL, &chips) != 0) {
        fprintf(stderr, "No /dev/gpiochip* devices found\n");
        exit(EXIT_FAILURE);
    }
    for (size_t i = 0; i < chips.gl_pathc; ++i) {
        int fd = open(chips.gl_pathv[i], O_RDONLY | O_CLOEXEC);
        if (fd < 0) die(chips.gl_pathv[i]);
        struct gpiochip_info chip = {0};
        if (ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &chip) < 0)
            die("GPIO_GET_CHIPINFO_IOCTL");
        unsigned int found = 0, candidate[2] = {0}, unnamed = 0;
        int by_offsets = 0;
        for (unsigned int j = 0; j < chip.lines; ++j) {
            struct gpio_v2_line_info info = {.offset = j};
            if (ioctl(fd, GPIO_V2_GET_LINEINFO_IOCTL, &info) < 0)
                die("GPIO_V2_GET_LINEINFO_IOCTL");
            if (strcmp(info.name, "PC5") == 0) {
                found |= 1; candidate[0] = j;
            }
            if (strcmp(info.name, "PC6") == 0) {
                found |= 2; candidate[1] = j;
            }
            if (j == 69 && info.name[0] == '\0') unnamed |= 1;
            if (j == 70 && info.name[0] == '\0') unnamed |= 2;
        }
        if (found == 0 && unnamed == 3 && known_board &&
            strcmp(chip.label, "300b000.pinctrl") == 0 && chip.lines == 288) {
            candidate[0] = 69; candidate[1] = 70;
            found = 3;
            by_offsets = 1;
        }
        if (found == 3) {
            if (selected >= 0) {
                close(fd); close(selected); globfree(&chips);
                fprintf(stderr, "Ambiguous PC5/PC6 mapping on multiple chips\n");
                exit(EXIT_FAILURE);
            }
            selected = fd;
            selected_by_offsets = by_offsets;
            memcpy(offsets, candidate, sizeof(offsets));
            snprintf(selected_path, sizeof(selected_path), "%s", chips.gl_pathv[i]);
        } else {
            close(fd);
        }
    }
    globfree(&chips);
    if (selected < 0) {
        fprintf(stderr, "PC5/PC6 not found by name or verified Orange Pi Zero 3 "
                "mapping; no pins requested. Check gpiodetect and gpioinfo.\n");
        exit(EXIT_FAILURE);
    }
    struct gpio_v2_line_request request = {0};
    request.offsets[0] = offsets[0];
    request.offsets[1] = offsets[1];
    request.num_lines = 2;
    snprintf(request.consumer, sizeof(request.consumer), "medvetalkie-display-test");
    request.config.flags = GPIO_V2_LINE_FLAG_OUTPUT;
    request.config.num_attrs = 1;
    request.config.attrs[0].attr.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
    request.config.attrs[0].attr.values = 3; /* DC=high, RESET=high */
    request.config.attrs[0].mask = 3;
    if (ioctl(selected, GPIO_V2_GET_LINE_IOCTL, &request) < 0) {
        int saved = errno;
        close(selected);
        errno = saved;
        die("Request PC5/DC and PC6/RESET (busy lines are not overridden)");
    }
    close(selected);
    lines_fd = request.fd;
    printf("GPIO %s: DC=PC5 offset %u; RESET=PC6 offset %u (%s)\n",
           selected_path, offsets[0], offsets[1],
           selected_by_offsets ? "verified H618 offsets; unnamed lines" : "line names");
}

static void set_line(unsigned int index, int high)
{
    struct gpio_v2_line_values values = {
        .bits = high ? (UINT64_C(1) << index) : 0,
        .mask = UINT64_C(1) << index
    };
    if (ioctl(lines_fd, GPIO_V2_LINE_SET_VALUES_IOCTL, &values) < 0)
        die("GPIO_V2_LINE_SET_VALUES_IOCTL");
}

static void send_bytes(const uint8_t *bytes, size_t count)
{
    while (count) {
        size_t chunk = count > 1024 ? 1024 : count;
        ssize_t sent = write(spi_fd, bytes, chunk);
        if (sent < 0 && errno == EINTR) continue;
        if (sent < 0) die("SPI write");
        if ((size_t)sent != chunk) {
            errno = EIO;
            die("Short SPI write");
        }
        bytes += chunk;
        count -= chunk;
    }
}

static void command(uint8_t opcode, const uint8_t *data, size_t length)
{
    set_line(0, 0);
    send_bytes(&opcode, 1);
    set_line(0, 1);
    if (length) send_bytes(data, length);
}

static void display_init(int bgr)
{
    set_line(1, 0); pause_ms(20);
    set_line(1, 1); pause_ms(150);
    command(0x01, NULL, 0); pause_ms(150); /* software reset */
    command(0x11, NULL, 0); pause_ms(150); /* sleep out */
    uint8_t pixel_format = 0x55; /* RGB565 */
    command(0x3a, &pixel_format, 1); pause_ms(10);
    uint8_t orientation = (uint8_t)(0xa0 | (bgr ? 0x08 : 0));
    command(0x36, &orientation, 1); /* landscape, 320x240 */
    command(0x21, NULL, 0); pause_ms(10); /* IPS inversion on */
    command(0x13, NULL, 0); pause_ms(10); /* normal display mode */
    command(0x29, NULL, 0); pause_ms(120); /* display on */
}

static void draw_frame(int pattern, uint16_t colour)
{
    const uint8_t columns[] = {0, 0, 1, 0x3f}; /* 0..319 */
    const uint8_t rows[] = {0, 0, 0, 0xef}; /* 0..239 */
    const uint16_t bars[] = {0xf800, 0x07e0, 0x001f, 0xffff};
    uint8_t row[WIDTH * 2];
    command(0x2a, columns, sizeof(columns));
    command(0x2b, rows, sizeof(rows));
    command(0x2c, NULL, 0);
    for (unsigned int y = 0; y < HEIGHT; ++y) {
        for (unsigned int x = 0; x < WIDTH; ++x) {
            uint16_t pixel = colour;
            if (pattern) {
                pixel = bars[x / 80];
                if (x < 2 || x >= WIDTH - 2 || y < 2 || y >= HEIGHT - 2)
                    pixel = 0xffff;
                if (x >= 8 && x < 28 && y >= 8 && y < 28)
                    pixel = 0x0000;
                if (x >= WIDTH - 28 && x < WIDTH - 8 &&
                    y >= HEIGHT - 28 && y < HEIGHT - 8)
                    pixel = 0xffe0;
            }
            row[2 * x] = (uint8_t)(pixel >> 8);
            row[2 * x + 1] = (uint8_t)pixel;
        }
        send_bytes(row, sizeof(row));
    }
}

int main(int argc, char **argv)
{
    int bgr = 0;
    if (argc == 2 && strcmp(argv[1], "--bgr") == 0) bgr = 1;
    else if (argc > 1) {
        fprintf(stderr, "Usage: %s [--bgr]\n"
                "OPi Zero 3 + MSP2008: SPI1.0, DC=PC5, RESET=PC6, 1 MHz.\n"
                "Use --bgr only if red and blue are swapped.\n", argv[0]);
        return argc == 2 && strcmp(argv[1], "--help") == 0 ? 0 : 2;
    }
    atexit(cleanup);
    spi_fd = open("/dev/spidev1.0", O_WRONLY | O_CLOEXEC);
    if (spi_fd < 0) die("/dev/spidev1.0");
    uint32_t mode = SPI_MODE_0, speed = 1000000;
    uint8_t bits = 8, lsb = 0;
    if (ioctl(spi_fd, SPI_IOC_WR_MODE32, &mode) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_LSB_FIRST, &lsb) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0)
        die("Configure SPI mode 0 / 8 bits / MSB first / 1 MHz");
    request_controls();
    display_init(bgr);
    const uint16_t colours[] = {0xf800, 0x07e0, 0x001f, 0xffff, 0};
    const char *names[] = {"RED", "GREEN", "BLUE", "WHITE", "BLACK"};
    for (size_t i = 0; i < sizeof(colours) / sizeof(colours[0]); ++i) {
        printf("Sending %s\n", names[i]); fflush(stdout);
        draw_frame(0, colours[i]); pause_ms(1000);
    }
    draw_frame(1, 0);
    puts("Sent final RGB/white bars, white border, black upper-left marker,"
         " yellow lower-right marker. Visual confirmation is required.");
    puts("Press Enter to release GPIO lines and exit.");
    (void)getchar();
    return 0;
}
