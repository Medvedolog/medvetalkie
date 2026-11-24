#include "medvetalkie/ipc.h"

#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

static int read_exact(int fd, void *data, size_t length)
{
    size_t done = 0;
    while (done < length) {
        ssize_t n = recv(fd, (char *)data + done, length - done, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) {
            if (n == 0) errno = EPIPE;
            return -1;
        }
        done += (size_t)n;
    }
    return 0;
}

static int write_exact(int fd, const void *data, size_t length)
{
    size_t done = 0;
    while (done < length) {
        ssize_t n = send(fd, (const char *)data + done, length - done, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) {
            if (n == 0) errno = EPIPE;
            return -1;
        }
        done += (size_t)n;
    }
    return 0;
}

int mt_ipc_read_frame(int fd, char *buffer, size_t capacity)
{
    uint32_t wire, len;
    if (!buffer || capacity < 2) { errno = EINVAL; return -1; }
    if (read_exact(fd, &wire, sizeof(wire)) != 0) return -1;
    len = ntohl(wire);
    if (len == 0 || len > MT_IPC_MAX_FRAME || (size_t)len >= capacity) {
        errno = EMSGSIZE;
        return -1;
    }
    if (read_exact(fd, buffer, len) != 0) return -1;
    buffer[len] = '\0';
    if (memchr(buffer, '\0', len)) { errno = EINVAL; return -1; }
    return (int)len;
}

int mt_ipc_write_frame(int fd, const char *message, size_t length)
{
    uint32_t wire;
    if (!message || length == 0 || length > MT_IPC_MAX_FRAME) {
        errno = EMSGSIZE;
        return -1;
    }
    wire = htonl((uint32_t)length);
    if (write_exact(fd, &wire, sizeof(wire)) != 0) return -1;
    return write_exact(fd, message, length);
}

int mt_ipc_exchange(const char *path, const char *request,
                    char *reply, size_t reply_capacity)
{
    struct sockaddr_un address = {0};
    struct timeval timeout = {1, 500000};
    int fd, result, error;
    if (!path || !request || strlen(path) >= sizeof(address.sun_path)) {
        errno = EINVAL;
        return -1;
    }
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, path, strlen(path) + 1);
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    if (connect(fd, (const struct sockaddr *)&address, sizeof(address)) != 0 ||
        mt_ipc_write_frame(fd, request, strlen(request)) != 0) {
        error = errno;
        close(fd);
        errno = error;
        return -1;
    }
    result = mt_ipc_read_frame(fd, reply, reply_capacity);
    error = errno;
    close(fd);
    if (result < 0) errno = error;
    return result;
}
