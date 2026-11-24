/* MedveTalkie Core API Alpha: bounded, read-only JSON/Unix IPC.
 * No Bluetooth, audio or display operation is claimed to be implemented.
 */
#define _GNU_SOURCE
#include "medvetalkie/ipc.h"
#include "medvetalkie/service.h"

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
#include <sys/un.h>
#include <unistd.h>

#define MT_MAX_CLIENTS 8u
static volatile sig_atomic_t stopping;
static atomic_uint clients = ATOMIC_VAR_INIT(0);

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
        json_object *id;
        if (!json_object_object_get_ex(request, "id", &id) ||
            !json_object_is_type(id, json_type_string) ||
            !valid_id(json_object_get_string(id))) {
            reply = base_reply("error");
            set_error(reply, "BAD_REQUEST", "Invalid command id");
            goto cleanup;
        }
        reply = base_reply("rejected");
        json_object_object_add(reply, "id", json_object_new_string(json_object_get_string(id)));
        set_error(reply, "NOT_READY", "Mutating commands are not implemented in API Alpha");
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
        json_object_object_add(reply, "revision", json_object_new_int64(0));
        json_object_object_add(state, "desired_mode", json_object_new_string("UNSET"));
        json_object_object_add(state, "effective_mode", json_object_new_string("UNKNOWN"));
        json_object_object_add(state, "bluetooth", json_object_new_string("NOT_READY"));
        json_object_object_add(state, "audio", json_object_new_string("NOT_READY"));
        json_object_object_add(state, "display", json_object_new_string("NOT_READY"));
        json_object_object_add(reply, "state", state);
    } else if (strcmp(action, "system.capabilities") == 0) {
        json_object *capabilities = json_object_new_object();
        reply = base_reply("capabilities");
        json_object_object_add(reply, "service", json_object_new_string("medvetalkied"));
        json_object_object_add(capabilities, "core_ipc_v1", json_object_new_boolean(1));
        json_object_object_add(capabilities, "web_read_only", json_object_new_boolean(1));
        json_object_object_add(capabilities, "bluetooth_management", json_object_new_boolean(0));
        json_object_object_add(capabilities, "hfp_audio", json_object_new_boolean(0));
        json_object_object_add(capabilities, "ble_gatt", json_object_new_boolean(0));
        json_object_object_add(capabilities, "settings_write", json_object_new_boolean(0));
        json_object_object_add(capabilities, "display_control", json_object_new_boolean(0));
        json_object_object_add(reply, "capabilities", capabilities);
    } else {
        reply = base_reply("error");
        set_error(reply, "NOT_SUPPORTED", "This action is not implemented");
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
    /* Do not unlink a replacement socket placed by another process. */
    if (lstat(path, &current) == 0 && S_ISSOCK(current.st_mode) &&
        current.st_dev == bound.st_dev && current.st_ino == bound.st_ino)
        (void)unlink(path);
    return rc;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--ipc-socket") == 0)
        return ipc_server(argv[2]);
    return mt_scaffold_main("medvetalkied", argc, argv);
}
