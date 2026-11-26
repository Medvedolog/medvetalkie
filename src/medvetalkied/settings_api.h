#ifndef MT_CORE_SETTINGS_API_H
#define MT_CORE_SETTINGS_API_H

#include "medvetalkie/settings.h"
#include <json-c/json.h>

/* NULL means the action does not belong to the settings domain. */
json_object *mt_core_settings_query(mt_settings_store *store, const char *action);
json_object *mt_core_settings_command(mt_settings_store *store, int allow_writes,
                                       const char *id, const char *action,
                                       json_object *args);
json_object *mt_core_display_settings(mt_settings_store *store);

#endif
