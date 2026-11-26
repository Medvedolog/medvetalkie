/* MedveTalkie Core API Alpha: framed JSON/Unix IPC + opt-in local SQLite settings.
 * No Bluetooth, audio or display hardware operations are performed here.
 */
#define _GNU_SOURCE
#include "medvetalkie/ipc.h"
#include "medvetalkie/service.h"
#include "medvetalkie/settings.h"
#include "settings_api.h"
#include "bt_inventory.h"
#include "bt_bluez.h"

#include <errno.h>
#include <json-c/json.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <sys/un.h>
#include <unistd.h>

#define MT_MAX_CLIENTS 8u
static volatile sig_atomic_t stopping;
static atomic_uint clients = ATOMIC_VAR_INIT(0);
static mt_settings_store settings_store;
static int settings_enabled;
static int local_settings_writes;
static const char *bluetooth_sysfs_root = "/sys";

static void stop_signal(int signal_number)
{
    (void)signal_number;
    stopping = 1;
}

static json_object *base_reply(const char *type)
{
    json_object *reply = json_object_new_object();
    json_object_object_add(reply, "v", json_object_new_int(1));
    json_object_object_add(reply, "type", json_object_new_string(type));
    return reply;
}

static void set_error(json_object *reply, const char *code, const char *message)
{
    json_object *error = json_object_new_object();
    json_object_object_add(error, "code", json_object_new_string(code));
    json_object_object_add(error, "message", json_object_new_string(message));
    json_object_object_add(reply, "error", error);
}

static int valid_id(const char *id)
{
    size_t i, n;
    if (!id || (n = strlen(id)) == 0 || n > 64) return 0;
    for (i = 0; i < n; i++) {
        unsigned char c = (unsigned char)id[i];
        if (!((c >= 'a' && c <= 'z') ||
              (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '_' ||
              c == '.' || c == ':'))
            return 0;
    }
    return 1;
}

static json_object *process_request(const char *input, size_t size)
{
    struct json_tokener *tokener = json_tokener_new();
    json_object *request = NULL, *field, *reply;
    const char *kind, *action;
    size_t offset;

    if (!tokener) return NULL;
    request = json_tokener_parse_ex(tokener, input, (int)size);
    offset = json_tokener_get_parse_end(tokener);
    if (json_tokener_get_error(tokener) != json_tokener_success ||
        !request || !json_object_is_type(request, json_type_object)) {
        reply = base_reply("error");
        set_error(reply, "BAD_REQUEST", "Malformed JSON object");
        goto cleanup;
    }
    while (offset < size && (input[offset] == ' ' || input[offset] == '\n' ||
                             input[offset] == '\t' || input[offset] == '\r'))
        ++offset;
    if (offset != size) {
        reply = base_reply("error");
        set_error(reply, "BAD_REQUEST", "Unexpected data after JSON");
        goto cleanup;
    }
    if (!json_object_object_get_ex(request, "v", &field) ||
        !json_object_is_type(field, json_type_int) ||
        json_object_get_int64(field) != 1) {
        reply = base_reply("error");
        set_error(reply, "UNSUPPORTED_VERSION", "Only IPC major version 1 is supported");
        goto cleanup;
    }
    if (!json_object_object_get_ex(request, "type", &field) ||
        !json_object_is_type(field, json_type_string)) {
        reply = base_reply("error");
        set_error(reply, "BAD_REQUEST", "Missing request type");
        goto cleanup;
    }
    kind = json_object_get_string(field);
    if (strcmp(kind, "command") == 0) {
        json_object *id, *operation, *args = NULL;
        if (!json_object_object_get_ex(request, "id", &id) ||
            !json_object_is_type(id, json_type_string) ||
            !valid_id(json_object_get_string(id))) {
            reply = base_reply("error");
            set_error(reply, "BAD_REQUEST", "Invalid command id");
            goto cleanup;
        }
        if (!json_object_object_get_ex(request, "action", &operation) ||
            !json_object_is_type(operation, json_type_string)) {
            reply = base_reply("rejected");
            json_object_object_add(reply, "id",
                                   json_object_new_string(json_object_get_string(id)));
            set_error(reply, "BAD_REQUEST", "Missing command action");
            goto cleanup;
        }
        (void)json_object_object_get_ex(request, "args", &args);
        reply = mt_core_settings_command(settings_enabled ? &settings_store : NULL,
                                          local_settings_writes,
                                          json_object_get_string(id),
                                          json_object_get_string(operation), args);
        if (reply) goto cleanup;
        reply = base_reply("rejected");
        json_object_object_add(reply, "id",
                               json_object_new_string(json_object_get_string(id)));
        set_error(reply, "NOT_READY", "This hardware command is not implemented");
        goto cleanup;
    }
    if (strcmp(kind, "query") != 0 ||
        !json_object_object_get_ex(request, "action", &field) ||
        !json_object_is_type(field, json_type_string)) {
        reply = base_reply("error");
        set_error(reply, "BAD_REQUEST", "Expected query with an action");
        goto cleanup;
    }
    action = json_object_get_string(field);

    if (strcmp(action, "health") == 0 || strcmp(action, "system.health") == 0) {
        reply = base_reply("health");
        json_object_object_add(reply, "service", json_object_new_string("medvetalkied"));
        json_object_object_add(reply, "status", json_object_new_string("ready"));
        json_object_object_add(reply, "core", json_object_new_string("reachable"));
        json_object_object_add(reply, "bluetooth", json_object_new_string("not_implemented"));
        json_object_object_add(reply, "audio", json_object_new_string("not_implemented"));
    } else if (strcmp(action, "system.status") == 0) {
        json_object *state = json_object_new_object();
        reply = base_reply("snapshot");
        mt_settings_snapshot snapshot;
        int have_settings = settings_enabled &&
                            mt_settings_read(&settings_store, &snapshot) == 0;
        json_object_object_add(reply, "revision",
                               json_object_new_int64(have_settings ? snapshot.revision : 0));
        json_object_object_add(state, "desired_mode", json_object_new_string("UNSET"));
        json_object_object_add(state, "effective_mode", json_object_new_string("UNKNOWN"));
        json_object_object_add(state, "bluetooth", json_object_new_string("NOT_READY"));
        json_object_object_add(state, "audio", json_object_new_string("NOT_READY"));
        json_object_object_add(state, "display", json_object_new_string("NOT_READY"));
        if (have_settings) {
            json_object *display = json_object_new_object();
            json_object_object_add(display, "spi_mhz", json_object_new_int(snapshot.spi_mhz));
            json_object_object_add(display, "fps", json_object_new_int(snapshot.fps));
            json_object_object_add(display, "screensaver_enabled",
                                   json_object_new_boolean(snapshot.screensaver_enabled));
            json_object_object_add(state, "desired_display", display);
        }
        json_object_object_add(reply, "state", state);
    } else if (strcmp(action, "system.capabilities") == 0) {
        json_object *capabilities = json_object_new_object();
        reply = base_reply("capabilities");
        json_object_object_add(reply, "service", json_object_new_string("medvetalkied"));
        json_object_object_add(capabilities, "core_ipc_v1", json_object_new_boolean(1));
        json_object_object_add(capabilities, "web_read_only", json_object_new_boolean(1));
        json_object_object_add(capabilities, "bluetooth_management", json_object_new_boolean(0));
        json_object_object_add(capabilities, "bt_controller_inventory", json_object_new_boolean(1));
        json_object_object_add(capabilities, "bt_bluez_observation", json_object_new_boolean(1));
        json_object_object_add(capabilities, "hfp_audio", json_object_new_boolean(0));
        json_object_object_add(capabilities, "ble_gatt", json_object_new_boolean(0));
        json_object_object_add(capabilities, "settings_read", json_object_new_boolean(settings_enabled));
        json_object_object_add(capabilities, "settings_write",
                               json_object_new_boolean(settings_enabled && local_settings_writes));
        json_object_object_add(capabilities, "display_control", json_object_new_boolean(0));
        json_object_object_add(reply, "capabilities", capabilities);
    } else if (strcmp(action, "bt.controllers") == 0) {
        reply = mt_bt_controllers(bluetooth_sysfs_root);
    } else if (strcmp(action, "bt.bluez") == 0) {
        reply = mt_bluez_query();
    } else {
        reply = mt_core_settings_query(settings_enabled ? &settings_store : NULL, action);
        if (!reply) {
            reply = base_reply("error");
            set_error(reply, "NOT_SUPPORTED", "This action is not implemented");
        }
    }

cleanup:
    if (request) json_object_put(request);
    json_tokener_free(tokener);
    return reply;
}

static void handle_connection(int fd)
{
    struct ucred cred;
    socklen_t cred_len = sizeof(cred);
    struct timeval timeout = {0, 500000};
    char input[MT_IPC_MAX_FRAME + 1];
    json_object *reply;
    const char *serialized;
    int bytes;
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    /* Alpha: same-UID clients only. Separate systemd group/roles are future work. */
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &cred_len) != 0 ||
        cred.uid != geteuid())
        return;

    bytes = mt_ipc_read_frame(fd, input, sizeof(input));
    if (bytes < 0) return;  /* Truncated or oversized frames are dropped. */
    reply = process_request(input, (size_t)bytes);
    if (!reply) return;
    serialized = json_object_to_json_string_ext(reply, JSON_C_TO_STRING_PLAIN);
    if (serialized)
        (void)mt_ipc_write_frame(fd, serialized, strlen(serialized));
    json_object_put(reply);
}

static void *client_worker(void *argument)
{
    int fd = *(int *)argument;
    free(argument);
    handle_connection(fd);
    close(fd);
    atomic_fetch_sub(&clients, 1);
    return NULL;
}

static int ipc_server(const char *path)
{
    struct sockaddr_un address = {0};
    struct stat bound, current;
    int server, rc = 0;
    mode_t mask;

    if (!path || path[0] != '/' ||
        strlen(path) >= sizeof(address.sun_path)) return 64;
    server = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server < 0) return 1;
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, path, strlen(path) + 1);
    mask = umask(0077);
    if (bind(server, (const struct sockaddr *)&address, sizeof(address)) != 0) {
        perror("IPC bind (existing socket is never removed automatically)");
        umask(mask);
        close(server);
        return 1;
    }
    umask(mask);
    if (lstat(path, &bound) != 0) {
        close(server);
        return 1;
    }
    /* Restrict the filesystem socket explicitly; umask(0077) alone gives 0700. */
    if (chmod(path, 0600) != 0 || listen(server, 16) != 0) {
        rc = 1;
        goto cleanup;
    }
    signal(SIGTERM, stop_signal);
    signal(SIGINT, stop_signal);
    while (!stopping) {
        fd_set fds;
        struct timeval delay = {0, 200000};
        int ready, client, *arg;
        pthread_t thread;
        FD_ZERO(&fds);
        FD_SET(server, &fds);
        ready = select(server + 1, &fds, NULL, NULL, &delay);
        if (ready < 0) {
            if (errno == EINTR) continue;
            rc = 1;
            break;
        }
        if (ready == 0) continue;
        client = accept(server, NULL, NULL);
        if (client < 0) {
            if (errno == EINTR) continue;
            rc = 1;
            break;
        }
        if (atomic_load(&clients) >= MT_MAX_CLIENTS) {
            close(client);
            continue;
        }
        arg = malloc(sizeof(*arg));
        if (!arg) { close(client); continue; }
        *arg = client;
        atomic_fetch_add(&clients, 1);
        if (pthread_create(&thread, NULL, client_worker, arg) != 0) {
            atomic_fetch_sub(&clients, 1);
            free(arg);
            close(client);
            continue;
        }
        pthread_detach(thread);
    }
cleanup:
    close(server);
    /* Detached workers must release the settings handle before shutdown. */
    while (atomic_load(&clients) != 0) {
        struct timespec pause = {0, 10000000L};
        (void)nanosleep(&pause, NULL);
    }
    /* Do not unlink a replacement socket placed by another process. */
    if (lstat(path, &current) == 0 && S_ISSOCK(current.st_mode) &&
        current.st_dev == bound.st_dev && current.st_ino == bound.st_ino)
        (void)unlink(path);
    return rc;
}

int main(int argc, char **argv)
{
    const char *socket_path = NULL, *db_path = NULL;
    int i, result;
    if (argc == 2 && (strcmp(argv[1], "--version") == 0 ||
                      strcmp(argv[1], "--help") == 0 ||
                      strcmp(argv[1], "-h") == 0))
        return mt_scaffold_main("medvetalkied", argc, argv);
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--ipc-socket") && i + 1 < argc)
            socket_path = argv[++i];
        else if (!strcmp(argv[i], "--db-path") && i + 1 < argc)
            db_path = argv[++i];
        else if (!strcmp(argv[i], "--allow-local-settings"))
            local_settings_writes = 1;
        else if (!strcmp(argv[i], "--bluetooth-sysfs-root") && i + 1 < argc)
            bluetooth_sysfs_root = argv[++i];
        else {
            fprintf(stderr, "Unknown or incomplete option: %s\n", argv[i]);
            return 64;
        }
    }
    if (!socket_path || bluetooth_sysfs_root[0] != '/' ||
        (local_settings_writes && !db_path)) {
        fputs("Usage: medvetalkied --ipc-socket ABS_PATH "
              "[--db-path ABS_PATH [--allow-local-settings]] "
              "[--bluetooth-sysfs-root ABS_PATH]\n", stderr);
        return 64;
    }
    if (db_path) {
        if (mt_settings_open(&settings_store, db_path) != 0) {
            fputs("Failed to open owner-private SQLite settings database\n", stderr);
            return 1; /* Never silently fall back to volatile settings. */
        }
        settings_enabled = 1;
    }
    if (!dbus_threads_init_default()) {
        fputs("Cannot initialize D-Bus thread support\n", stderr);
        if (settings_enabled) mt_settings_close(&settings_store);
        return 1;
    }
    result = ipc_server(socket_path);
    if (settings_enabled) mt_settings_close(&settings_store);
    return result;
}
