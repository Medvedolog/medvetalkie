/* SQLite storage for desired settings only, versioned schema 1. */
#define _POSIX_C_SOURCE 200809L
#include "medvetalkie/settings.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int sql(mt_settings_store *store, const char *statement)
{
    return sqlite3_exec(store->db, statement, NULL, NULL, NULL) == SQLITE_OK ? 0 : -1;
}

static int read_locked(mt_settings_store *store, mt_settings_snapshot *out)
{
    sqlite3_stmt *stmt = NULL;
    const unsigned char *name;
    int rc;
    static const char query[] =
        "SELECT revision,device_name,spi_mhz,fps,screensaver_enabled "
        "FROM settings WHERE id=1";
    if (sqlite3_prepare_v2(store->db, query, -1, &stmt, NULL) != SQLITE_OK)
        return -1;
    rc = sqlite3_step(stmt);
    if (rc != SQLITE_ROW) {
        sqlite3_finalize(stmt);
        return -1;
    }
    name = sqlite3_column_text(stmt, 1);
    if (!name || sqlite3_column_bytes(stmt, 1) <= 0 ||
        sqlite3_column_bytes(stmt, 1) > MT_DEVICE_NAME_MAX) {
        sqlite3_finalize(stmt);
        return -1;
    }
    out->revision = sqlite3_column_int64(stmt, 0);
    memcpy(out->device_name, name, (size_t)sqlite3_column_bytes(stmt, 1));
    out->device_name[sqlite3_column_bytes(stmt, 1)] = '\0';
    out->spi_mhz = sqlite3_column_int(stmt, 2);
    out->fps = sqlite3_column_int(stmt, 3);
    out->screensaver_enabled = sqlite3_column_int(stmt, 4);
    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return rc == SQLITE_DONE ? 0 : -1;
}

int mt_settings_open(mt_settings_store *store, const char *path)
{
    struct stat info;
    sqlite3_stmt *stmt = NULL;
    mode_t mask;
    int version = -1;
    if (!store || !path || path[0] != '/' || strstr(path, "/../") ||
        strstr(path, "/./") || strlen(path) > 1024) return -1;
    if (lstat(path, &info) == 0) {
        if (!S_ISREG(info.st_mode) || (info.st_mode & 0077)) return -1;
    } else if (errno != ENOENT) {
        return -1;
    }
    memset(store, 0, sizeof(*store));
    if (pthread_mutex_init(&store->mutex, NULL) != 0) return -1;
    mask = umask(0077);
    int rc = sqlite3_open_v2(path, &store->db,
                             SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE |
                             SQLITE_OPEN_FULLMUTEX, NULL);
    umask(mask);
    if (rc != SQLITE_OK) goto error;
    sqlite3_busy_timeout(store->db, 300);
    if (sqlite3_prepare_v2(store->db, "PRAGMA user_version", -1, &stmt, NULL) != SQLITE_OK)
        goto error;
    if (sqlite3_step(stmt) == SQLITE_ROW) version = sqlite3_column_int(stmt, 0);
    sqlite3_finalize(stmt);
    stmt = NULL;
    if (version == 0) {
        if (sql(store, "BEGIN IMMEDIATE") ||
            sql(store, "CREATE TABLE IF NOT EXISTS settings ("
                "id INTEGER PRIMARY KEY CHECK(id=1),"
                "revision INTEGER NOT NULL CHECK(revision>=0),"
                "device_name TEXT NOT NULL,"
                "spi_mhz INTEGER NOT NULL CHECK(spi_mhz BETWEEN 1 AND 16),"
                "fps INTEGER NOT NULL CHECK(fps BETWEEN 1 AND 60),"
                "screensaver_enabled INTEGER NOT NULL CHECK(screensaver_enabled IN (0,1)))") ||
            sql(store, "INSERT OR IGNORE INTO settings "
                "(id,revision,device_name,spi_mhz,fps,screensaver_enabled)"
                " VALUES(1,0,'MedveTalkie',1,25,0)") ||
            sql(store, "PRAGMA user_version=1") ||
            sql(store, "COMMIT")) {
            (void)sql(store, "ROLLBACK");
            goto error;
        }
    } else if (version != MT_SETTINGS_SCHEMA_VERSION) {
        goto error; /* Fail closed; never downgrade or open a future schema. */
    }
    mt_settings_snapshot check;
    if (read_locked(store, &check) != 0) goto error;
    if (check.revision < 0 || check.spi_mhz < 1 || check.spi_mhz > 16 ||
        check.fps < 1 || check.fps > 60 ||
        (check.screensaver_enabled != 0 && check.screensaver_enabled != 1))
        goto error;
    return 0;
error:
    if (stmt) sqlite3_finalize(stmt);
    if (store->db) sqlite3_close(store->db);
    store->db = NULL;
    pthread_mutex_destroy(&store->mutex);
    return -1;
}

void mt_settings_close(mt_settings_store *store)
{
    if (!store || !store->db) return;
    pthread_mutex_lock(&store->mutex);
    sqlite3_close(store->db);
    store->db = NULL;
    pthread_mutex_unlock(&store->mutex);
    pthread_mutex_destroy(&store->mutex);
}

int mt_settings_read(mt_settings_store *store, mt_settings_snapshot *out)
{
    int rc;
    if (!store || !store->db || !out) return -1;
    pthread_mutex_lock(&store->mutex);
    rc = read_locked(store, out);
    pthread_mutex_unlock(&store->mutex);
    return rc;
}

int mt_settings_patch(mt_settings_store *store,
                      const mt_settings_patch_data *patch, int64_t expected,
                      mt_settings_snapshot *result)
{
    sqlite3_stmt *stmt = NULL;
    mt_settings_snapshot next;
    int status = -1;
    if (!store || !store->db || !patch || !result || expected < 0) return -1;
    pthread_mutex_lock(&store->mutex);
    if (sql(store, "BEGIN IMMEDIATE") != 0) goto finish;
    if (read_locked(store, &next) != 0) goto rollback;
    if (next.revision != expected) {
        status = 1;
        goto rollback;
    }
    if (next.revision == INT64_MAX) goto rollback;
    if (patch->change_name)
        memcpy(next.device_name, patch->device_name, sizeof(next.device_name));
    if (patch->change_spi) next.spi_mhz = patch->spi_mhz;
    if (patch->change_fps) next.fps = patch->fps;
    if (patch->change_screensaver)
        next.screensaver_enabled = patch->screensaver_enabled;
    if (sqlite3_prepare_v2(store->db,
          "UPDATE settings SET revision=?,device_name=?,spi_mhz=?,fps=?,"
          "screensaver_enabled=? WHERE id=1 AND revision=?",
          -1, &stmt, NULL) != SQLITE_OK) goto rollback;
    sqlite3_bind_int64(stmt, 1, next.revision + 1);
    sqlite3_bind_text(stmt, 2, next.device_name, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 3, next.spi_mhz);
    sqlite3_bind_int(stmt, 4, next.fps);
    sqlite3_bind_int(stmt, 5, next.screensaver_enabled);
    sqlite3_bind_int64(stmt, 6, expected);
    if (sqlite3_step(stmt) != SQLITE_DONE || sqlite3_changes(store->db) != 1)
        goto rollback;
    sqlite3_finalize(stmt);
    stmt = NULL;
    if (sql(store, "COMMIT") != 0) goto rollback;
    next.revision++;
    *result = next;
    status = 0;
    goto finish;
rollback:
    if (stmt) { sqlite3_finalize(stmt); stmt = NULL; }
    (void)sql(store, "ROLLBACK");
finish:
    pthread_mutex_unlock(&store->mutex);
    return status;
}
