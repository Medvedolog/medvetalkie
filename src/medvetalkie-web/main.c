/* Isolated Web Alpha diagnostic endpoint; not yet connected to core IPC. */
#include <civetweb.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested;

static void handle_signal(int number)
{
    (void)number;
    stop_requested = 1;
}

static int health_handler(struct mg_connection *conn, void *user_data)
{
    const struct mg_request_info *request = mg_get_request_info(conn);
    const char *json = "{\"service\":\"medvetalkie-web\",\"status\":\"ready\",\"core\":\"not_connected\"}\n";
    int is_get = request && request->request_method &&
                 strcmp(request->request_method, "GET") == 0;
    (void)user_data;
    if (!is_get) {
        const char *error = "{\"error\":\"method_not_allowed\"}\n";
        mg_printf(conn, "HTTP/1.1 405 Method Not Allowed\r\n"
                        "Content-Type: application/json\r\n"
                        "Cache-Control: no-store\r\n"
                        "Content-Length: %zu\r\n"
                        "Connection: close\r\n\r\n%s", strlen(error), error);
        return 1;
    }
    mg_printf(conn, "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    "Cache-Control: no-store\r\n"
                    "Content-Length: %zu\r\n"
                    "Connection: close\r\n\r\n%s", strlen(json), json);
    return 1;
}

int main(int argc, char **argv)
{
    const char *options[] = {
        "listening_ports", "127.0.0.1:8765",
        "num_threads", "4",
        "enable_keep_alive", "no",
        NULL
    };
    struct mg_callbacks callbacks = {0};
    struct mg_context *context;

    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("medvetalkie-web 0.0.1-alpha");
        return 0;
    }
    if (argc != 1) {
        fprintf(stderr, "Usage: %s [--version]\n", argv[0]);
        return 64;
    }
    signal(SIGTERM, handle_signal);
    signal(SIGINT, handle_signal);

    context = mg_start(&callbacks, NULL, options);
    if (!context) {
        fputs("Failed to start loopback-only web server\n", stderr);
        return 1;
    }
    mg_set_request_handler(context, "/api/v1/health", health_handler, NULL);
    while (!stop_requested)
        sleep(1);
    mg_stop(context);
    return 0;
}
