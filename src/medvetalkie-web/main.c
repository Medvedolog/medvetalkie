/* Web Alpha: loopback-only read-only adapter to MedveTalkie Core API v1.
 * No remote access or mutation before authentication is implemented.
 */
#include "medvetalkie/ipc.h"
#include <civetweb.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested;
static const char *ipc_path = MT_IPC_DEFAULT_SOCKET;

static void stop_signal(int signum)
{
    (void)signum;
    stop_requested = 1;
}

static int send_response(struct mg_connection *conn, int code,
                         const char *reason, const char *content_type,
                         const char *body)
{
    mg_printf(conn,
              "HTTP/1.1 %d %s\r\n"
              "Content-Type: %s\r\n"
              "Content-Length: %zu\r\n"
              "Cache-Control: no-store\r\n"
              "X-Content-Type-Options: nosniff\r\n"
              "Content-Security-Policy: default-src 'none'; "
              "style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
              "connect-src 'self'\r\n"
              "Connection: close\r\n\r\n%s",
              code, reason, content_type, strlen(body), body);
    return 1;
}

static int method_is_get(struct mg_connection *conn)
{
    const struct mg_request_info *req = mg_get_request_info(conn);
    return req && req->request_method &&
           strcmp(req->request_method, "GET") == 0;
}

static int json_handler(struct mg_connection *conn, void *user_data)
{
    const char *action = (const char *)user_data;
    char request[160], response[MT_IPC_MAX_FRAME + 1];
    if (!method_is_get(conn))
        return send_response(conn, 405, "Method Not Allowed", "application/json",
                             "{\"error\":\"method_not_allowed\"}\n");
    if (snprintf(request, sizeof(request),
                 "{\"v\":1,\"type\":\"query\",\"action\":\"%s\"}", action) >=
        (int)sizeof(request))
        return send_response(conn, 500, "Internal Server Error", "application/json",
                             "{\"error\":\"internal_error\"}\n");
    if (mt_ipc_exchange(ipc_path, request, response, sizeof(response)) < 0)
        return send_response(conn, 503, "Service Unavailable", "application/json",
                             "{\"error\":\"core_unavailable\"}\n");
    return send_response(conn, 200, "OK", "application/json", response);
}

static int index_handler(struct mg_connection *conn, void *unused)
{
    static const char html[] =
        "<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>MedveTalkie · Web Alpha</title>"
        "<style>body{font:16px system-ui;background:#121b28;color:#eef4f8;"
        "margin:2em auto;padding:0 1em;max-width:620px}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#202c3a;"
        "padding:1em;border-radius:9px}small{color:#b6c6d3}</style>"
        "<h1>MedveTalkie</h1><p>Web Alpha · только просмотр</p>"
        "<small>Bluetooth HFP, настройки и Android BLE ещё не реализованы.</small>"
        "<h2>Core status</h2><pre id=\"status\">Загрузка…</pre>"
        "<h2>Capabilities</h2><pre id=\"caps\">Загрузка…</pre>"
        "<script>async function show(id,url){try{const r=await fetch(url,"
        "{cache:'no-store'});const d=await r.json();"
        "document.getElementById(id).textContent=JSON.stringify(d,null,2)"
        "+(r.ok?'':'\\nHTTP '+r.status)}catch(e){"
        "document.getElementById(id).textContent='Нет связи с core';}}"
        "show('status','/api/v1/status');"
        "show('caps','/api/v1/capabilities');</script></html>";
    (void)unused;
    if (!method_is_get(conn))
        return send_response(conn, 405, "Method Not Allowed", "application/json",
                             "{\"error\":\"method_not_allowed\"}\n");
    return send_response(conn, 200, "OK", "text/html; charset=utf-8", html);
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
        puts("medvetalkie-web 0.0.2-alpha");
        return 0;
    }
    if (argc == 3 && strcmp(argv[1], "--ipc-socket") == 0) {
        ipc_path = argv[2];
    } else if (argc != 1) {
        fprintf(stderr, "Usage: %s [--version] [--ipc-socket ABSOLUTE_PATH]\n", argv[0]);
        return 64;
    }
    if (ipc_path[0] != '/') {
        fputs("IPC socket path must be absolute\n", stderr);
        return 64;
    }
    signal(SIGTERM, stop_signal);
    signal(SIGINT, stop_signal);
    context = mg_start(&callbacks, NULL, options);
    if (!context) {
        fputs("Cannot start loopback-only Web Alpha\n", stderr);
        return 1;
    }
    mg_set_request_handler(context, "/", index_handler, NULL);
    mg_set_request_handler(context, "/api/v1/health", json_handler, (void *)"health");
    mg_set_request_handler(context, "/api/v1/status", json_handler, (void *)"system.status");
    mg_set_request_handler(context, "/api/v1/capabilities",
                           json_handler, (void *)"system.capabilities");
    while (!stop_requested) sleep(1);
    mg_stop(context);
    return 0;
}
