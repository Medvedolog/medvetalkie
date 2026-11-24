#ifndef MEDVETALKIE_SETTINGS_H
#define MEDVETALKIE_SETTINGS_H

#include <pthread.h>
#include <sqlite3.h>
#include <stdint.h>

/* Persist desired configuration only; no hardware state or passwords. */
#define MT_SETTINGS_SCHEMA_VERSION 1
#define MT_DEVICE_NAME_MAX 64

typedef struct {
    sqlite3 *db;
    pthread_mutex_t mutex;
} mt_settings_store;

typedef struct {
    int64_t revision;
    char device_name[MT_DEVICE_NAME_MAX + 1];
    int spi_mhz;
    int fps;
    int screensaver_enabled;
} mt_settings_snapshot;

typedef struct {
    int change_name;
    int change_spi;
    int change_fps;
    int change_screensaver;
    char device_name[MT_DEVICE_NAME_MAX + 1];
    int spi_mhz;
    int fps;
    int screensaver_enabled;
} mt_settings_patch_data;

/* Only a new/existing owner-private absolute-path SQLite DB is accepted. */
int mt_settings_open(mt_settings_store *store, const char *path);
void mt_settings_close(mt_settings_store *store);
int mt_settings_read(mt_settings_store *store, mt_settings_snapshot *out);

/* 0 committed, 1 stale revision, -1 database failure.
 * All fields update in one transaction. */
int mt_settings_patch(mt_settings_store *store,
                      const mt_settings_patch_data *patch, int64_t expected,
                      mt_settings_snapshot *result);

#endif
