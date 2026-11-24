#ifndef MEDVETALKIE_IPC_H
#define MEDVETALKIE_IPC_H

#include <stddef.h>

/* Shared version-1 control plane. Audio samples never use this transport. */
#define MT_IPC_MAX_FRAME 65536u
#define MT_IPC_DEFAULT_SOCKET "/run/medvetalkie/control.sock"

/* Return frame byte count, or -1 with errno. The buffer is NUL-terminated. */
int mt_ipc_read_frame(int fd, char *buffer, size_t capacity);
int mt_ipc_write_frame(int fd, const char *message, size_t length);

/* Synchronous, bounded client helper for non-realtime adapter threads only. */
int mt_ipc_exchange(const char *path, const char *request,
                    char *reply, size_t reply_capacity);

#endif
