/* BlueZ passive ObjectManager adapter.
 * GetManagedObjects is read-only. Paired/Connected != HFP audio readiness.
 */
#include "bt_bluez.h"
#include <stdio.h>
#include <string.h>

enum { MT_MAX_BLUEZ_ADAPTERS = 16, MT_MAX_BLUEZ_DEVICES = 96 };

static json_object *base(const char *type)
{
    json_object *out = json_object_new_object();
    json_object_object_add(out, "v", json_object_new_int(1));
    json_object_object_add(out, "type", json_object_new_string(type));
    return out;
}

static json_object *not_ready(const char *reason)
{
    json_object *out = base("error");
    json_object *error = json_object_new_object();
    json_object_object_add(error, "code", json_object_new_string("NOT_READY"));
    json_object_object_add(error, "message", json_object_new_string(reason));
    json_object_object_add(out, "error", error);
    return out;
}

static void put_string(json_object *object, const char *key,
                       const char *value)
{
    if (value)
        json_object_object_add(object, key, json_object_new_string_len(
                                value, (int)strnlen(value, 256)));
    else
        json_object_object_add(object, key, json_object_new_null());
}

static int property_value(DBusMessageIter *entry, const char *want,
                          int expected, char *string, size_t cap,
                          dbus_bool_t *boolean, int *present)
{
    DBusMessageIter it, value;
    const char *key = NULL;
    if (dbus_message_iter_get_arg_type(entry) != DBUS_TYPE_DICT_ENTRY) return 0;
    dbus_message_iter_recurse(entry, &it);
    if (dbus_message_iter_get_arg_type(&it) != DBUS_TYPE_STRING) return 0;
    dbus_message_iter_get_basic(&it, &key);
    if (!key || strcmp(key, want) != 0) return 0;
    if (!dbus_message_iter_next(&it) ||
        dbus_message_iter_get_arg_type(&it) != DBUS_TYPE_VARIANT) return 0;
    dbus_message_iter_recurse(&it, &value);
    if (dbus_message_iter_get_arg_type(&value) != expected) return 0;
    if (expected == DBUS_TYPE_BOOLEAN) {
        dbus_message_iter_get_basic(&value, boolean);
    } else if (expected == DBUS_TYPE_STRING || expected == DBUS_TYPE_OBJECT_PATH) {
        const char *data = NULL;
        dbus_message_iter_get_basic(&value, &data);
        if (!data || strlen(data) >= cap) return 0;
        memcpy(string, data, strlen(data) + 1);
    } else return 0;
    *present = 1;
    return 1;
}

static json_object *interface_to_json(const char *path,
                                      const char *interface,
                                      DBusMessageIter *properties)
{
    int adapter = strcmp(interface, "org.bluez.Adapter1") == 0;
    int device = strcmp(interface, "org.bluez.Device1") == 0;
    json_object *out;
    char address[32] = "", alias[129] = "", parent[256] = "";
    int has_address = 0, has_alias = 0, has_parent = 0;
    int has_powered = 0, has_discovering = 0;
    int has_paired = 0, has_connected = 0;
    dbus_bool_t powered = 0, discovering = 0, paired = 0, connected = 0;
    DBusMessageIter prop;
    if (!adapter && !device) return NULL;
    if (dbus_message_iter_get_arg_type(properties) != DBUS_TYPE_ARRAY)
        return NULL;
    dbus_message_iter_recurse(properties, &prop);
    while (dbus_message_iter_get_arg_type(&prop) == DBUS_TYPE_DICT_ENTRY) {
        (void)property_value(&prop, "Address", DBUS_TYPE_STRING,
                             address, sizeof(address), NULL, &has_address);
        (void)property_value(&prop, "Alias", DBUS_TYPE_STRING,
                             alias, sizeof(alias), NULL, &has_alias);
        if (adapter) {
            (void)property_value(&prop, "Powered", DBUS_TYPE_BOOLEAN,
                                 NULL, 0, &powered, &has_powered);
            (void)property_value(&prop, "Discovering", DBUS_TYPE_BOOLEAN,
                                 NULL, 0, &discovering, &has_discovering);
        } else {
            (void)property_value(&prop, "Adapter", DBUS_TYPE_OBJECT_PATH,
                                 parent, sizeof(parent), NULL, &has_parent);
            (void)property_value(&prop, "Paired", DBUS_TYPE_BOOLEAN,
                                 NULL, 0, &paired, &has_paired);
            (void)property_value(&prop, "Connected", DBUS_TYPE_BOOLEAN,
                                 NULL, 0, &connected, &has_connected);
        }
        dbus_message_iter_next(&prop);
    }
    out = json_object_new_object();
    put_string(out, "path", path);
    put_string(out, "address", has_address ? address : NULL);
    put_string(out, "alias", has_alias ? alias : NULL);
    if (adapter) {
        if (has_powered)
            json_object_object_add(out, "powered", json_object_new_boolean(powered));
        else
            json_object_object_add(out, "powered", json_object_new_null());
        if (has_discovering)
            json_object_object_add(out, "discovering", json_object_new_boolean(discovering));
        else
            json_object_object_add(out, "discovering", json_object_new_null());
    } else {
        put_string(out, "adapter_path", has_parent ? parent : NULL);
        if (has_paired)
            json_object_object_add(out, "paired", json_object_new_boolean(paired));
        else
            json_object_object_add(out, "paired", json_object_new_null());
        if (has_connected)
            json_object_object_add(out, "connected", json_object_new_boolean(connected));
        else
            json_object_object_add(out, "connected", json_object_new_null());
        json_object_object_add(out, "hfp_audio",
                               json_object_new_string("NOT_VERIFIED"));
        json_object_object_add(out, "sco_transport",
                               json_object_new_string("NOT_CHECKED"));
    }
    return out;
}

json_object *mt_bluez_parse(DBusMessage *reply)
{
    DBusMessageIter root, objects;
    json_object *out, *adapters, *devices;
    unsigned count_adapters = 0, count_devices = 0;
    int truncated = 0;
    if (!reply || !dbus_message_has_signature(reply, "a{oa{sa{sv}}}") ||
        !dbus_message_iter_init(reply, &root) ||
        dbus_message_iter_get_arg_type(&root) != DBUS_TYPE_ARRAY)
        return not_ready("BlueZ returned an invalid ObjectManager snapshot");
    adapters = json_object_new_array();
    devices = json_object_new_array();
    dbus_message_iter_recurse(&root, &objects);
    while (dbus_message_iter_get_arg_type(&objects) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter obj, interfaces;
        const char *path = NULL;
        dbus_message_iter_recurse(&objects, &obj);
        if (dbus_message_iter_get_arg_type(&obj) != DBUS_TYPE_OBJECT_PATH) {
            dbus_message_iter_next(&objects);
            continue;
        }
        dbus_message_iter_get_basic(&obj, &path);
        if (!path || !dbus_message_iter_next(&obj) ||
            dbus_message_iter_get_arg_type(&obj) != DBUS_TYPE_ARRAY) {
            dbus_message_iter_next(&objects);
            continue;
        }
        dbus_message_iter_recurse(&obj, &interfaces);
        while (dbus_message_iter_get_arg_type(&interfaces) == DBUS_TYPE_DICT_ENTRY) {
            DBusMessageIter iface;
            const char *name = NULL;
            json_object *item;
            dbus_message_iter_recurse(&interfaces, &iface);
            if (dbus_message_iter_get_arg_type(&iface) != DBUS_TYPE_STRING) {
                dbus_message_iter_next(&interfaces);
                continue;
            }
            dbus_message_iter_get_basic(&iface, &name);
            if (!name || !dbus_message_iter_next(&iface)) {
                dbus_message_iter_next(&interfaces);
                continue;
            }
            item = interface_to_json(path, name, &iface);
            if (item) {
                if (!strcmp(name, "org.bluez.Adapter1")) {
                    if (count_adapters < MT_MAX_BLUEZ_ADAPTERS) {
                        json_object_array_add(adapters, item);
                        ++count_adapters;
                    } else {
                        truncated = 1;
                        json_object_put(item);
                    }
                } else {
                    if (count_devices < MT_MAX_BLUEZ_DEVICES) {
                        json_object_array_add(devices, item);
                        ++count_devices;
                    } else {
                        truncated = 1;
                        json_object_put(item);
                    }
                }
            }
            dbus_message_iter_next(&interfaces);
        }
        dbus_message_iter_next(&objects);
    }
    out = base("bluez");
    json_object_object_add(out, "source", json_object_new_string("bluez_dbus"));
    json_object_object_add(out, "status", json_object_new_string("OBSERVED"));
    json_object_object_add(out, "adapter_count", json_object_new_int(count_adapters));
    json_object_object_add(out, "device_count", json_object_new_int(count_devices));
    json_object_object_add(out, "truncated", json_object_new_boolean(truncated));
    json_object_object_add(out, "adapters", adapters);
    json_object_object_add(out, "devices", devices);
    return out;
}

json_object *mt_bluez_query(void)
{
    DBusError error;
    DBusConnection *connection;
    DBusMessage *message, *reply;
    json_object *result;
    dbus_error_init(&error);
    connection = dbus_bus_get_private(DBUS_BUS_SYSTEM, &error);
    if (!connection) {
        dbus_error_free(&error);
        return not_ready("Cannot connect to system D-Bus / BlueZ");
    }
    dbus_connection_set_exit_on_disconnect(connection, FALSE);
    message = dbus_message_new_method_call("org.bluez", "/",
                                            "org.freedesktop.DBus.ObjectManager",
                                            "GetManagedObjects");
    if (!message) {
        dbus_connection_close(connection);
        dbus_connection_unref(connection);
        return not_ready("Cannot allocate BlueZ ObjectManager query");
    }
    reply = dbus_connection_send_with_reply_and_block(connection, message, 400, &error);
    dbus_message_unref(message);
    if (!reply) {
        dbus_error_free(&error);
        dbus_connection_close(connection);
        dbus_connection_unref(connection);
        return not_ready("BlueZ is offline, inaccessible, or timed out");
    }
    result = mt_bluez_parse(reply);
    dbus_message_unref(reply);
    dbus_connection_close(connection);
    dbus_connection_unref(connection);
    dbus_error_free(&error);
    return result;
}
