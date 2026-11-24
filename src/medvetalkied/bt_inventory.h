#ifndef MT_BT_INVENTORY_H
#define MT_BT_INVENTORY_H
#include <json-c/json.h>

/* Observes kernel HCI + USB topology. It does not query BlueZ profile state. */
json_object *mt_bt_controllers(const char *sysfs_root);
#endif
