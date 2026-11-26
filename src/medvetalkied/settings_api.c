/* Local-only, schema-whitelisted configuration API.
 * Saving settings does NOT imply the display or audio device changed.
 */
#include "settings_api.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static json_object *response(const char *type)
{
    json_object *r = json_object_new_object();
    json_object_object_add(r, "v", json_object_new_int(1));
    json_object_object_add(r, "type", json_object_new_string(type));
    return r;
}

static json_object *error_reply(const char *type, const char *id,
                                const char *code, const char *message)
{
    json_object *r = response(type);
    json_object *e = json_object_new_object();
    if (id) json_object_object_add(r, "id", json_object_new_string(id));
    json_object_object_add(e, "code", json_object_new_string(code));
    json_object_object_add(e, "message", json_object_new_string(message));
    json_object_object_add(r, "error", e);
    return r;
}

static json_object *display_json(const mt_settings_snapshot *s)
{
    json_object *d = json_object_new_object();
    json_object_object_add(d, "spi_mhz", json_object_new_int(s->spi_mhz));
    json_object_object_add(d, "fps", json_object_new_int(s->fps));
    json_object_object_add(d, "screensaver_enabled",
                           json_object_new_boolean(s->screensaver_enabled));
    return d;
}

json_object *mt_core_display_settings(mt_settings_store *store)
{
    mt_settings_snapshot s;
    json_object *r;
    if (mt_settings_read(store, &s) != 0)
        return error_reply("error", NULL, "NOT_READY", "Settings database unavailable");
    r = response("display");
    json_object_object_add(r, "revision", json_object_new_int64(s.revision));
    json_object_object_add(r, "desired", display_json(&s));
    json_object_object_add(r, "observed", json_object_new_string("UNKNOWN"));
    json_object_object_add(r, "hardware_applied", json_object_new_boolean(0));
    return r;
}

json_object *mt_core_settings_query(mt_settings_store *store, const char *action)
{
    mt_settings_snapshot s;
    json_object *r, *settings;
    if (strcmp(action, "display.status") == 0)
        return mt_core_display_settings(store);
    if (strcmp(action, "settings.get") != 0) return NULL;
    if (mt_settings_read(store, &s) != 0)
        return error_reply("error", NULL, "NOT_READY", "Settings database unavailable");
    r = response("settings");
    settings = json_object_new_object();
    json_object_object_add(settings, "device_name",
                           json_object_new_string(s.device_name));
    json_object_object_add(settings, "display", display_json(&s));
    json_object_object_add(r, "revision", json_object_new_int64(s.revision));
    json_object_object_add(r, "settings", settings);
    return r;
}

static int valid_name(const char *s, size_t length)
{
    size_t i;
    if (!s || length == 0 || length > MT_DEVICE_NAME_MAX ||
        strlen(s) != length) return 0;
    for (i = 0; i < length; ++i) {
        unsigned char c = (unsigned char)s[i];
        if (c < 32 || c == 127) return 0;
    }
    return 1;
}

/* Validate every key (including unknown ones) before any DB writes. */
static int parse_patch(json_object *args, int64_t *expected,
                       mt_settings_patch_data *out)
{
    json_object *field, *display;
    int seen = 0;
    if (!args || !json_object_is_type(args, json_type_object) ||
        !json_object_object_get_ex(args, "expected_revision", &field) ||
        !json_object_is_type(field, json_type_int) ||
        json_object_get_int64(field) < 0) return -1;
    *expected = json_object_get_int64(field);
    if (json_object_object_length(args) < 2) return -1;
    memset(out, 0, sizeof(*out));
    json_object_object_foreach(args, key, val) {
        if (!strcmp(key, "expected_revision")) continue;
        if (!strcmp(key, "device_name")) {
            const char *s;
            size_t n;
            if (!json_object_is_type(val, json_type_string)) return -1;
            s = json_object_get_string(val);
            n = (size_t)json_object_get_string_len(val);
            if (!valid_name(s, n)) return -1;
            memcpy(out->device_name, s, n + 1);
            out->change_name = seen = 1;
        } else if (!strcmp(key, "display")) {
            if (!json_object_is_type(val, json_type_object) ||
                json_object_object_length(val) == 0) return -1;
            display = val;
            json_object_object_foreach(display, property, entry) {
                if (!strcmp(property, "spi_mhz")) {
                    if (!json_object_is_type(entry, json_type_int) ||
                        json_object_get_int64(entry) < 1 ||
                        json_object_get_int64(entry) > 16) return -1;
                    out->spi_mhz = json_object_get_int(entry);
                    out->change_spi = seen = 1;
                } else if (!strcmp(property, "fps")) {
                    if (!json_object_is_type(entry, json_type_int) ||
                        json_object_get_int64(entry) < 1 ||
                        json_object_get_int64(entry) > 60) return -1;
                    out->fps = json_object_get_int(entry);
                    out->change_fps = seen = 1;
                } else if (!strcmp(property, "screensaver_enabled")) {
                    if (!json_object_is_type(entry, json_type_boolean)) return -1;
                    out->screensaver_enabled = json_object_get_boolean(entry);
                    out->change_screensaver = seen = 1;
                } else {
                    return -1;
                }
            }
        } else {
            return -1;
        }
    }
    return seen ? 0 : -1;
}

json_object *mt_core_settings_command(mt_settings_store *store, int allow_writes,
                                       const char *id, const char *action,
                                       json_object *args)
{
    mt_settings_patch_data patch;
    mt_settings_snapshot snapshot;
    json_object *r;
    int64_t expected;
    int result;
    char operation[64];
    if (strcmp(action, "settings.patch") != 0) return NULL;
    if (!store || !store->db)
        return error_reply("rejected", id, "NOT_READY", "Settings database disabled");
    if (!allow_writes)
        return error_reply("rejected", id, "PERMISSION_DENIED",
                           "Explicit --allow-local-settings is required");
    if (parse_patch(args, &expected, &patch) != 0)
        return error_reply("rejected", id, "BAD_REQUEST",
                           "Invalid settings.patch payload or revision");
    result = mt_settings_patch(store, &patch, expected, &snapshot);
    if (result == 1)
        return error_reply("rejected", id, "REVISION_CONFLICT",
                           "Settings changed; query settings.get before retry");
    if (result != 0)
        return error_reply("rejected", id, "DATABASE_ERROR",
                           "Atomic settings transaction failed");
    r = response("result");
    json_object_object_add(r, "id", json_object_new_string(id));
    snprintf(operation, sizeof(operation), "settings-%lld",
             (long long)snapshot.revision);
    json_object_object_add(r, "operation", json_object_new_string(operation));
    json_object_object_add(r, "ok", json_object_new_boolean(1));
    json_object_object_add(r, "revision", json_object_new_int64(snapshot.revision));
    json_object_object_add(r, "applied", json_object_new_string("saved_only"));
    json_object_object_add(r, "hardware_applied", json_object_new_boolean(0));
    return r;
}
