#ifndef MT_BT_BLUEZ_H
#define MT_BT_BLUEZ_H
#include <dbus/dbus.h>
#include <json-c/json.h>

/* Passive BlueZ ObjectManager snapshot. Does not pair, connect, or scan. */
json_object *mt_bluez_query(void);
/* Parser is exported solely for synthetic GetManagedObjects fixture tests. */
json_object *mt_bluez_parse(DBusMessage *reply);
#endif
