/* Synthetic BlueZ ObjectManager DBus-message fixture. No radio/bus needed. */
#include "bt_bluez.h"
/* Unit test assertions MUST execute in -DCMAKE_BUILD_TYPE=Release builds. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <dbus/dbus.h>
#include <json-c/json.h>
#include <stdio.h>
#include <string.h>

static void put_prop(DBusMessageIter *properties, const char *key,
                     int type, const void *pointer)
{
    DBusMessageIter entry, value;
    char signature[2] = {(char)type, 0};
    assert(dbus_message_iter_open_container(properties, DBUS_TYPE_DICT_ENTRY,
                                            NULL, &entry));
    assert(dbus_message_iter_append_basic(&entry, DBUS_TYPE_STRING, &key));
    assert(dbus_message_iter_open_container(&entry, DBUS_TYPE_VARIANT,
                                            signature, &value));
    assert(dbus_message_iter_append_basic(&value, type, pointer));
    assert(dbus_message_iter_close_container(&entry, &value));
    assert(dbus_message_iter_close_container(properties, &entry));
}

static void append_object(DBusMessageIter *objects,
                          const char *path, const char *interface,
                          const char *address, const char *alias,
                          int device, dbus_bool_t present, dbus_bool_t second)
{
    DBusMessageIter obj, interfaces, iface, props;
    const char *parent = "/org/bluez/hci0";
    assert(dbus_message_iter_open_container(objects, DBUS_TYPE_DICT_ENTRY, NULL, &obj));
    assert(dbus_message_iter_append_basic(&obj, DBUS_TYPE_OBJECT_PATH, &path));
    assert(dbus_message_iter_open_container(&obj, DBUS_TYPE_ARRAY,
                                            "{sa{sv}}", &interfaces));
    assert(dbus_message_iter_open_container(&interfaces, DBUS_TYPE_DICT_ENTRY,
                                            NULL, &iface));
    assert(dbus_message_iter_append_basic(&iface, DBUS_TYPE_STRING, &interface));
    assert(dbus_message_iter_open_container(&iface, DBUS_TYPE_ARRAY,
                                            "{sv}", &props));
    put_prop(&props, "Address", DBUS_TYPE_STRING, &address);
    put_prop(&props, "Alias", DBUS_TYPE_STRING, &alias);
    if (device) {
        put_prop(&props, "Adapter", DBUS_TYPE_OBJECT_PATH, &parent);
        put_prop(&props, "Connected", DBUS_TYPE_BOOLEAN, &present);
        put_prop(&props, "Paired", DBUS_TYPE_BOOLEAN, &second);
    } else {
        put_prop(&props, "Powered", DBUS_TYPE_BOOLEAN, &present);
        put_prop(&props, "Discovering", DBUS_TYPE_BOOLEAN, &second);
    }
    assert(dbus_message_iter_close_container(&iface, &props));
    assert(dbus_message_iter_close_container(&interfaces, &iface));
    assert(dbus_message_iter_close_container(&obj, &interfaces));
    assert(dbus_message_iter_close_container(objects, &obj));
}

static json_object *field(json_object *parent, const char *name)
{
    json_object *found = NULL;
    assert(json_object_object_get_ex(parent, name, &found));
    return found;
}
int main(void)
{
    DBusMessage *message = dbus_message_new_signal(
        "/org/medvetalkie/Fixture", "org.medvetalkie.Fixture", "Observed");
    DBusMessageIter root, objects;
    json_object *parsed, *adapters, *devices, *adapter, *device;
    assert(message);
    dbus_message_iter_init_append(message, &root);
    assert(dbus_message_iter_open_container(&root, DBUS_TYPE_ARRAY,
                                            "{oa{sa{sv}}}", &objects));
    append_object(&objects, "/org/bluez/hci0", "org.bluez.Adapter1",
                  "F4:12:34:56:78:90", "UGREEN Adapter", 0, TRUE, FALSE);
    append_object(&objects, "/org/bluez/hci0/dev_12_34_56_78_90_AB",
                  "org.bluez.Device1", "12:34:56:78:90:AB",
                  "Helmet 1", 1, TRUE, TRUE);
    append_object(&objects, "/org/bluez/hci0/dev_12_34_56_78_90_AC",
                  "org.bluez.Device1", "12:34:56:78:90:AC",
                  "Helmet 2", 1, FALSE, TRUE);
    append_object(&objects, "/org/bluez/hci1", "org.bluez.Media1",
                  "00:00:00:00:00:00", "Other interface", 0, TRUE, TRUE);
    assert(dbus_message_iter_close_container(&root, &objects));
    assert(strcmp(dbus_message_get_signature(message), "a{oa{sa{sv}}}") == 0);
    parsed = mt_bluez_parse(message);
    assert(strcmp(json_object_get_string(field(parsed, "type")), "bluez") == 0);
    assert(strcmp(json_object_get_string(field(parsed, "status")), "OBSERVED") == 0);
    assert(json_object_get_int(field(parsed, "adapter_count")) == 1);
    assert(json_object_get_int(field(parsed, "device_count")) == 2);
    adapters = field(parsed, "adapters");
    devices = field(parsed, "devices");
    adapter = json_object_array_get_idx(adapters, 0);
    assert(json_object_get_boolean(field(adapter, "powered")) == TRUE);
    assert(json_object_get_boolean(field(adapter, "discovering")) == FALSE);
    assert(strcmp(json_object_get_string(field(adapter, "address")),
                  "F4:12:34:56:78:90") == 0);
    device = json_object_array_get_idx(devices, 0);
    assert(json_object_get_boolean(field(device, "connected")) == TRUE);
    assert(json_object_get_boolean(field(device, "paired")) == TRUE);
    assert(strcmp(json_object_get_string(field(device, "hfp_audio")),
                  "NOT_VERIFIED") == 0);
    assert(strcmp(json_object_get_string(field(device, "sco_transport")),
                  "NOT_CHECKED") == 0);
    device = json_object_array_get_idx(devices, 1);
    assert(json_object_get_boolean(field(device, "connected")) == FALSE);
    assert(json_object_get_boolean(field(device, "paired")) == TRUE);
    assert(json_object_object_get(device, "hfp_ready") == NULL);
    json_object_put(parsed);
    dbus_message_unref(message);

    /* Missing or malformed ObjectManager snapshot is NOT_READY, not empty. */
    parsed = mt_bluez_parse(NULL);
    assert(strcmp(json_object_get_string(field(field(parsed, "error"), "code")),
                  "NOT_READY") == 0);
    json_object_put(parsed);
    message = dbus_message_new_signal(
        "/org/medvetalkie/Fixture", "org.medvetalkie.Fixture", "Malformed");
    assert(message);
    parsed = mt_bluez_parse(message);
    assert(strcmp(json_object_get_string(field(field(parsed, "error"), "code")),
                  "NOT_READY") == 0);
    json_object_put(parsed);
    dbus_message_unref(message);
    puts("PASS: BlueZ Adapter1/Device1 parser, HFP not inferred from Connected, malformed bus snapshot");
    return 0;
}
