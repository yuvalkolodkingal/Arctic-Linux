//go:build cgo && webkit

// The C side of the web-app window: GTK 4 and WebKitGTK 6.0 plumbing only. Every decision
// (scope, navigation, permissions, downloads, crashes, theme) is made in Go through the
// go* callbacks in exports.go; this file never holds policy. Everything runs on the main
// thread.
#ifndef ARCTIC_WEBKIT_SHIM_H
#define ARCTIC_WEBKIT_SHIM_H

#include <stdint.h>

typedef struct {
    const char *app_id;       /* GApplication id = Wayland app_id = desktop id */
    const char *app_name;
    const char *icon_name;
    const char *start_uri;    /* "Back to <App>" goes here */
    const char *open_uri;     /* first page */
    const char *data_dir;     /* WebKit profile */
    const char *cache_dir;
    int keep_running, background, ask_download;
    int devtools;
    int software;             /* rendering=software: no hardware acceleration */
    double zoom;
    int width, height, maximized;
    const char *notice;       /* banner text shown once at start, or NULL */
    uintptr_t handle;         /* runtime/cgo.Handle of the Go controller */
} ArcticConfig;

/* Decisions from goDecidePolicy (policy.Use …). */
enum { ARCTIC_USE = 0, ARCTIC_IGNORE = 1, ARCTIC_EXTERNAL = 2, ARCTIC_POPUP = 3, ARCTIC_LOAD_IN_APP = 4 };

/* Permission kinds (policy.Perm*) and answers. */
enum { ARCTIC_DENY = 0, ARCTIC_ALLOW = 1, ARCTIC_ASK = 2 };

int arctic_run(const ArcticConfig *cfg, int argc, char **argv);
const char *arctic_webkit_version(void);
char *arctic_base_domain(const char *host);
void arctic_set_theme(const char *css, int dark, const char *ground);
void arctic_load(const char *uri);
void arctic_load_alternate_html(const char *html, const char *uri);
void arctic_open_external(const char *uri);
void arctic_allow_certificate(const char *host, const char *pem);
void arctic_set_devtools(int enabled);
void arctic_set_options(int keep_running, int ask_download);
void arctic_banner(const char *text, const char *primary);
void arctic_present(void);
void arctic_quit(void);
void arctic_idle(uintptr_t handle);

#endif
