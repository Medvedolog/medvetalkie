/* MedveTalkie core: read-only Unix IPC health prototype. No hardware claims. */
#define _GNU_SOURCE
#include "medvetalkie/service.h"
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static void stop_signal(int signum) { (void)signum; stopping = 1; }

static int read_all(int fd, void *buf, size_t n)
{
    size_t done = 0;
    while (done < n) {
        ssize_t got = read(fd, (char *)buf + done, n - done);
        if (got <= 0) return -1;
        done += (size_t)got;
    }
    return 0;
}

static int write_all(int fd, const void *buf, size_t n)
{
    size_t done = 0;
    while (done < n) {
        ssize_t sent = send(fd, (const char *)buf + done, n - done, MSG_NOSIGNAL);
        if (sent <= 0) return -1;
        done += (size_t)sent;
    }
    return 0;
}

static void handle_connection(int fd)
{
    struct ucred cred;
    socklen_t clen = sizeof(cred);
    struct timeval timeout = {1, 0};
    uint32_t wirelen, length;
    char input[256];
    const char *reply = "{\"v\":1,\"type\":\"health\",\"service\":\"medvetalkied\",\"status\":\"ready\",\"bluetooth\":\"not_implemented\",\"audio\":\"not_implemented\"}";
    uint32_t outlen = htonl((uint32_t)strlen(reply));
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &clen) != 0 ||
        cred.uid != geteuid())
        return;
    if (read_all(fd, &wirelen, sizeof(wirelen)) != 0) return;
    length = ntohl(wirelen);
    if (length == 0 || length >= sizeof(input)) return;
    if (read_all(fd, input, length) != 0) return;
    input[length] = 0;
    if (strcmp(input, "{\"v\":1,\"type\":\"query\",\"action\":\"health\"}") != 0)
        return;
    if (write_all(fd, &outlen, sizeof(outlen)) != 0) return;
    (void)write_all(fd, reply, strlen(reply));
}

static int ipc_server(const char *path)
{
    struct sockaddr_un addr = {0};
    int fd, rc = 0;
    mode_t oldmask;
    if (!path || strlen(path) >= sizeof(addr.sun_path)) return 64;
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return 1;
    addr.sun_family = AF_UNIX;
    strcpy(addr.sun_path, path);
    oldmask = umask(0077);
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        perror("bind IPC socket (existing socket is not removed automatically)");
        umask(oldmask);
        close(fd);
        return 1;
    }
    umask(oldmask);
    if (listen(fd, 8) != 0) { rc = 1; goto cleanup; }
    signal(SIGTERM, stop_signal);
    signal(SIGINT, stop_signal);
    while (!stopping) {
        fd_set readers;
        struct timeval delay = {0, 200000};
        int ready;
        FD_ZERO(&readers);
        FD_SET(fd, &readers);
        ready = select(fd + 1, &readers, NULL, NULL, &delay);
        if (ready < 0) {
            if (errno == EINTR) continue;
            rc = 1; break;
        }
        if (ready > 0) {
            int client = accept(fd, NULL, NULL);
            if (client >= 0) { handle_connection(client); close(client); }
        }
    }
cleanup:
    close(fd);
    unlink(path);
    return rc;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--ipc-socket") == 0)
        return ipc_server(argv[2]);
    return mt_scaffold_main("medvetalkied", argc, argv);
}
