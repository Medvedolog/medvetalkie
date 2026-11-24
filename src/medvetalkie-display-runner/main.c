/* Launch the existing Bjorni ST7789 screensaver with desired settings from
 * the unified Core API. Local explicit startup only; no auto-start or hot reload.
 * No shell interpolation: only validated integer arguments are forwarded.
 */
#define _GNU_SOURCE
#include "medvetalkie/ipc.h"
#include <errno.h>
#include <json-c/json.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int fail(const char *message)
{
    fprintf(stderr, "medvetalkie-display-runner: %s\n", message);
    return 1;
}

static int trusted_script(const char *path)
{
    struct stat st;
    if (!path || path[0] != '/' || lstat(path, &st) != 0 ||
        !S_ISREG(st.st_mode) || (st.st_mode & 0022) != 0)
        return 0; /* No symlinks or group/world-writable scripts. */
    if (geteuid() == 0 && st.st_uid != 0)
        return 0; /* Root must never execute a non-root-owned script. */
    return 1;
}

static int get_display(const char *socket_path, int *spi, int *fps, int *enabled)
{
    const char *request =
        "{\"v\":1,\"type\":\"query\",\"action\":\"settings.get\"}";
    char response[MT_IPC_MAX_FRAME + 1];
    json_object *root, *type, *settings, *display, *field;
    int bytes;
    bytes = mt_ipc_exchange(socket_path, request, response, sizeof(response));
    if (bytes < 0) return -1;
    root = json_tokener_parse(response);
    if (!root || !json_object_is_type(root, json_type_object)) {
        if (root) json_object_put(root);
        return -1;
    }
    if (!json_object_object_get_ex(root, "type", &type) ||
        !json_object_is_type(type, json_type_string) ||
        strcmp(json_object_get_string(type), "settings") != 0 ||
        !json_object_object_get_ex(root, "settings", &settings) ||
        !json_object_is_type(settings, json_type_object) ||
        !json_object_object_get_ex(settings, "display", &display) ||
        !json_object_is_type(display, json_type_object))
        goto invalid;
    if (!json_object_object_get_ex(display, "spi_mhz", &field) ||
        !json_object_is_type(field, json_type_int) ||
        json_object_get_int64(field) < 1 || json_object_get_int64(field) > 16)
        goto invalid;
    *spi = json_object_get_int(field);
    if (!json_object_object_get_ex(display, "fps", &field) ||
        !json_object_is_type(field, json_type_int) ||
        json_object_get_int64(field) < 1 || json_object_get_int64(field) > 60)
        goto invalid;
    *fps = json_object_get_int(field);
    if (!json_object_object_get_ex(display, "screensaver_enabled", &field) ||
        !json_object_is_type(field, json_type_boolean))
        goto invalid;
    *enabled = json_object_get_boolean(field);
    json_object_put(root);
    return 0;
invalid:
    json_object_put(root);
    return -1;
}

int main(int argc, char **argv)
{
    const char *socket_path = MT_IPC_DEFAULT_SOCKET;
    const char *script = NULL;
    int run = 0, spi = 0, fps = 0, enabled = 0;
    char spi_string[8], fps_string[8];
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--ipc-socket") && i + 1 < argc)
            socket_path = argv[++i];
        else if (!strcmp(argv[i], "--script") && i + 1 < argc)
            script = argv[++i];
        else if (!strcmp(argv[i], "--dry-run"))
            run = 0;
        else if (!strcmp(argv[i], "--run"))
            run = 1;
        else if (!strcmp(argv[i], "--version")) {
            puts("medvetalkie-display-runner 0.0.1-alpha");
            return 0;
        } else {
            return fail("usage: --ipc-socket ABS_PATH --script ABS_PATH [--dry-run|--run]");
        }
    }
    if (!socket_path || socket_path[0] != '/' || !trusted_script(script))
        return fail("absolute IPC socket and a trusted local script are required");
    if (get_display(socket_path, &spi, &fps, &enabled) != 0)
        return fail("cannot read validated desired display settings from Core API");
    if (!enabled) {
        puts("Bjorni screensaver disabled in desired settings; no action taken");
        return 0;
    }
    snprintf(spi_string, sizeof(spi_string), "%d", spi);
    snprintf(fps_string, sizeof(fps_string), "%d", fps);
    if (!run) {
        printf("DRY_RUN: Bjorni script=%s spi_mhz=%s fps=%s (hardware unchanged)\n",
               script, spi_string, fps_string);
        return 0;
    }
    /* This is a startup handoff, not a live control daemon. The renderer
     * may still reject missing SPI/GPIO access and needs bench testing. */
    char *const parameters[] = {
        (char *)"/bin/bash", (char *)script,
        (char *)"--spi-mhz", spi_string,
        (char *)"--fps", fps_string, NULL
    };
    execv("/bin/bash", parameters);
    fprintf(stderr, "Cannot exec Bjorni script: %s\n", strerror(errno));
    return 1;
}
