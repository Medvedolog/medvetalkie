/* Passive HCI/USB inventory. Never scans, pairs or changes controller state. */
#define _GNU_SOURCE
#include "bt_inventory.h"
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif
#define MAX_CONTROLLERS 32

struct controller {
    char hci[32];
    char address[32];
    char port[80];
    char vid[16];
    char pid[16];
    char product[128];
    char serial[128];
    int usb;
};

/* Kernel sysfs attributes are short; ignore missing or malformed fields. */
static void attribute(const char *dir, const char *attr, char *out, size_t cap)
{
    char path[PATH_MAX];
    size_t n;
    FILE *file;
    out[0] = '\0';
    if (snprintf(path, sizeof(path), "%s/%s", dir, attr) >= (int)sizeof(path))
        return;
    file = fopen(path, "r");
    if (!file) return;
    if (!fgets(out, (int)cap, file)) {
        fclose(file);
        out[0] = '\0';
        return;
    }
    fclose(file);
    n = strcspn(out, "\r\n");
    out[n] = '\0';
    for (size_t i = 0; i < n; ++i)
        if ((unsigned char)out[i] < 32 || (unsigned char)out[i] == 127)
            out[i] = ' ';
}

static int hci_name(const char *s)
{
    if (strncmp(s, "hci", 3) != 0 || !isdigit((unsigned char)s[3]))
        return 0;
    for (s += 3; *s; ++s)
        if (!isdigit((unsigned char)*s)) return 0;
    return 1;
}

static int hex4(const char *s)
{
    if (strlen(s) != 4) return 0;
    for (int i = 0; i < 4; ++i)
        if (!isxdigit((unsigned char)s[i])) return 0;
    return 1;
}

static int valid_usb_port(const char *s)
{
    int dash = 0;
    if (!*s || strlen(s) >= 80) return 0;
    for (; *s; ++s) {
        if (*s == '-') dash = 1;
        else if (!isdigit((unsigned char)*s) && *s != '.') return 0;
    }
    return dash;
}

static void usb_parent(const char *hci_dir, struct controller *out)
{
    char link[PATH_MAX], resolved[PATH_MAX], parent[PATH_MAX];
    struct stat st;
    if (snprintf(link, sizeof(link), "%s/device", hci_dir) >= (int)sizeof(link))
        return;
    if (!realpath(link, resolved)) return;
    if (stat(resolved, &st) != 0 || !S_ISDIR(st.st_mode)) return;
    if (strlen(resolved) >= sizeof(parent)) return;
    strcpy(parent, resolved);
    while (strcmp(parent, "/") != 0) {
        char vid[16], pid[16];
        char *slash;
        attribute(parent, "idVendor", vid, sizeof(vid));
        attribute(parent, "idProduct", pid, sizeof(pid));
        if (hex4(vid) && hex4(pid)) {
            char *port = strrchr(parent, '/');
            port = port ? port + 1 : parent;
            if (!valid_usb_port(port)) return;
            strcpy(out->port, port);
            strcpy(out->vid, vid);
            strcpy(out->pid, pid);
            attribute(parent, "product", out->product, sizeof(out->product));
            attribute(parent, "serial", out->serial, sizeof(out->serial));
            out->usb = 1;
            return;
        }
        slash = strrchr(parent, '/');
        if (!slash || slash == parent) break;
        *slash = '\0';
    }
}

static int compare_controller(const void *a, const void *b)
{
    const struct controller *x = a, *y = b;
    int r;
    if (x->usb != y->usb) return y->usb - x->usb;
    r = strcmp(x->port, y->port);
    if (r) return r;
    r = strcmp(x->address, y->address);
    return r ? r : strcmp(x->hci, y->hci);
}

static json_object *base(const char *type)
{
    json_object *reply = json_object_new_object();
    json_object_object_add(reply, "v", json_object_new_int(1));
    json_object_object_add(reply, "type", json_object_new_string(type));
    return reply;
}

json_object *mt_bt_controllers(const char *root)
{
    char dir[PATH_MAX], path[PATH_MAX];
    struct controller entries[MAX_CONTROLLERS] = {{0}};
    unsigned count = 0, usb_count = 0;
    DIR *d;
    struct dirent *entry;
    json_object *reply, *list;

    if (!root || root[0] != '/' ||
        snprintf(dir, sizeof(dir), "%s/class/bluetooth", root) >= (int)sizeof(dir))
        return NULL;
    d = opendir(dir);
    if (!d) {
        json_object *error = json_object_new_object();
        reply = base("error");
        json_object_object_add(error, "code", json_object_new_string("NOT_READY"));
        json_object_object_add(error, "message",
                               json_object_new_string("Kernel Bluetooth sysfs is unavailable"));
        json_object_object_add(reply, "error", error);
        return reply;
    }

    while ((entry = readdir(d)) != NULL) {
        struct stat st;
        struct controller *item;
        if (!hci_name(entry->d_name)) continue;
        if (snprintf(path, sizeof(path), "%s/%s", dir, entry->d_name) >=
            (int)sizeof(path)) continue;
        if (stat(path, &st) != 0 || !S_ISDIR(st.st_mode)) continue;
        if (count >= MAX_CONTROLLERS) continue; /* Bounded inventory. */
        item = &entries[count++];
        snprintf(item->hci, sizeof(item->hci), "%s", entry->d_name);
        attribute(path, "address", item->address, sizeof(item->address));
        usb_parent(path, item);
        if (item->usb) ++usb_count;
    }
    closedir(d);
    qsort(entries, count, sizeof(entries[0]), compare_controller);
    reply = base("controllers");
    list = json_object_new_array();
    for (unsigned i = 0; i < count; ++i) {
        const struct controller *item = &entries[i];
        json_object *controller = json_object_new_object();
        json_object_object_add(controller, "hci", json_object_new_string(item->hci));
        json_object_object_add(controller, "address",
            item->address[0] ? json_object_new_string(item->address) : json_object_new_null());
        json_object_object_add(controller, "transport",
            json_object_new_string(item->usb ? "usb" : "non_usb_or_unknown"));
        json_object_object_add(controller, "identity_verified", json_object_new_boolean(0));
        json_object_object_add(controller, "hfp_ready", json_object_new_boolean(0));
        json_object_object_add(controller, "hfp_observed",
                               json_object_new_string("NOT_CHECKED"));
        if (item->usb) {
            json_object *usb = json_object_new_object();
            json_object_object_add(usb, "port", json_object_new_string(item->port));
            json_object_object_add(usb, "vid", json_object_new_string(item->vid));
            json_object_object_add(usb, "pid", json_object_new_string(item->pid));
            if (item->product[0])
                json_object_object_add(usb, "product",
                                       json_object_new_string(item->product));
            /* Serial numbers must not leak through a future web endpoint. */
            json_object_object_add(controller, "usb", usb);
        }
        json_object_array_add(list, controller);
    }
    json_object_object_add(reply, "status", json_object_new_string("KERNEL_ENUMERATED"));
    json_object_object_add(reply, "source", json_object_new_string("kernel_sysfs"));
    json_object_object_add(reply, "bluez_state", json_object_new_string("NOT_CHECKED"));
    json_object_object_add(reply, "controller_count", json_object_new_int((int)count));
    json_object_object_add(reply, "usb_controller_count", json_object_new_int((int)usb_count));
    json_object_object_add(reply, "controllers", list);
    return reply;
}
