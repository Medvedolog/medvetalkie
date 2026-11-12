/* Read-only USB inventory for MedveTalkie. No role assignment or shell execution. */
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <limits.h>
#include <sys/stat.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static void attribute(const char *dir, const char *name, char *dst, size_t cap)
{
    char path[PATH_MAX];
    FILE *f;
    size_t i;
    dst[0] = '\0';
    if (snprintf(path, sizeof(path), "%s/%s", dir, name) >= (int)sizeof(path))
        return;
    f = fopen(path, "r");
    if (!f)
        return;
    if (!fgets(dst, (int)cap, f))
        dst[0] = '\0';
    fclose(f);
    for (i = 0; dst[i]; ++i) {
        if (dst[i] == '\n' || dst[i] == '\r') {
            dst[i] = '\0';
            break;
        }
        if (dst[i] == '\t' || (unsigned char)dst[i] < 32)
            dst[i] = ' ';
    }
}

static int usb_device_name(const char *name)
{
    const unsigned char *p = (const unsigned char *)name;
    if (!isdigit(*p))
        return 0;
    while (isdigit(*p))
        ++p;
    if (*p++ != '-')
        return 0;
    if (!isdigit(*p))
        return 0;
    while (*p) {
        if (!isdigit(*p) && *p != '.')
            return 0;
        ++p;
    }
    return 1;
}

int main(int argc, char **argv)
{
    const char *root = "/sys/bus/usb/devices";
    DIR *d;
    struct dirent *entry;
    if (argc == 3 && strcmp(argv[1], "--sysfs") == 0)
        root = argv[2]; /* allows deterministic fixture testing */
    else if (argc != 1) {
        fprintf(stderr, "Usage: %s [--sysfs DIRECTORY]\n", argv[0]);
        return 64;
    }
    d = opendir(root);
    if (!d) {
        fprintf(stderr, "Cannot open USB sysfs %s: %s\n", root, strerror(errno));
        return 1;
    }
    puts("port\tvid\tpid\tserial\tmanufacturer\tproduct\tbusnum\tdevnum");
    while ((entry = readdir(d)) != NULL) {
        char dir[PATH_MAX];
        char vid[128], pid[128], serial[256], vendor[256], product[256];
        char bus[64], dev[64];
        struct stat st;
        if (!usb_device_name(entry->d_name))
            continue;
        if (snprintf(dir, sizeof(dir), "%s/%s", root, entry->d_name) >= (int)sizeof(dir))
            continue;
        if (stat(dir, &st) != 0 || !S_ISDIR(st.st_mode))
            continue;
        attribute(dir, "idVendor", vid, sizeof(vid));
        attribute(dir, "idProduct", pid, sizeof(pid));
        if (!vid[0] || !pid[0])
            continue;
        attribute(dir, "serial", serial, sizeof(serial));
        attribute(dir, "manufacturer", vendor, sizeof(vendor));
        attribute(dir, "product", product, sizeof(product));
        attribute(dir, "busnum", bus, sizeof(bus));
        attribute(dir, "devnum", dev, sizeof(dev));
        printf("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
               entry->d_name, vid, pid, serial, vendor, product, bus, dev);
    }
    if (closedir(d) != 0)
        return 1;
    return 0;
}
