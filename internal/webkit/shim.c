//go:build cgo && webkit

// GTK 4 / WebKitGTK 6.0 plumbing for arctic-webapp-host (see shim.h). One GtkApplication per
// process; its id is the web app's id, so GTK gives the window that Wayland app_id and a
// second start is forwarded to this process over D-Bus. Nothing here decides anything: the
// go* functions (exports.go) do.
#include "shim.h"
#include "_cgo_export.h"

#include <glib-unix.h>
#include <gtk/gtk.h>
#include <libsoup/soup.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <webkit/webkit.h>

typedef struct {
    ArcticConfig cfg;              /* strings duplicated */
    GtkApplication *app;
    GtkWindow *window;
    WebKitWebView *view;
    WebKitNetworkSession *session;
    WebKitSettings *settings;
    WebKitUserContentManager *ucm;
    GtkWidget *header, *back, *forward, *reload, *back_to_app, *host_label;
    GtkWidget *revealer, *banner_label, *banner_primary, *banner_secondary;
    GtkWidget *search_bar, *search_entry;
    WebKitPermissionRequest *pending; /* the banner's permission request (ref held) */
    int pending_kind;
    char *pending_origin;
    int banner_action;                /* 0 permission, 1 reload */
    GtkCssProvider *css;
    GFileMonitor *theme_monitor;
    GHashTable *notifications;        /* tag → WebKitNotification (ref) */
    gboolean first_notice_shown;
} Shim;

static Shim S;

static char *dup_or_null(const char *s) { return s ? g_strdup(s) : NULL; }

/* ---------------------------------------------------------------- small helpers */

const char *arctic_webkit_version(void) {
    static char buf[32];
    snprintf(buf, sizeof buf, "%u.%u.%u", webkit_get_major_version(), webkit_get_minor_version(),
             webkit_get_micro_version());
    return buf;
}

char *arctic_base_domain(const char *host) {
    GError *err = NULL;
    const char *d = soup_tld_get_base_domain(host, &err);
    if (!d) {
        g_clear_error(&err);
        return NULL;
    }
    return strdup(d);
}

void arctic_open_external(const char *uri) {
    if (!uri) return;
    GtkUriLauncher *l = gtk_uri_launcher_new(uri);
    gtk_uri_launcher_launch(l, S.window, NULL, NULL, NULL);
    g_object_unref(l);
}

void arctic_load(const char *uri) {
    if (S.view && uri) webkit_web_view_load_uri(S.view, uri);
}

void arctic_load_alternate_html(const char *html, const char *uri) {
    if (S.view && html && uri) webkit_web_view_load_alternate_html(S.view, html, uri, NULL);
}

void arctic_present(void) {
    if (S.window) gtk_window_present(S.window);
}

void arctic_quit(void) {
    if (S.app) g_application_quit(G_APPLICATION(S.app));
}

void arctic_set_devtools(int enabled) {
    S.cfg.devtools = enabled;
    if (S.settings) webkit_settings_set_enable_developer_extras(S.settings, enabled ? TRUE : FALSE);
}

void arctic_allow_certificate(const char *host, const char *pem) {
    if (!S.session || !host || !pem) return;
    GError *err = NULL;
    GTlsCertificate *cert = g_tls_certificate_new_from_pem(pem, -1, &err);
    if (!cert) {
        g_clear_error(&err);
        return;
    }
    webkit_network_session_allow_tls_certificate_for_host(S.session, cert, host);
    g_object_unref(cert);
}

static gboolean idle_cb(gpointer data) {
    goIdle((uintptr_t)data);
    return G_SOURCE_REMOVE;
}

void arctic_idle(uintptr_t handle) { g_idle_add(idle_cb, (gpointer)handle); }

/* Theme: the host's own CSS, the colour scheme (by property name: GTK 4.20 has
 * gtk-interface-color-scheme, older ones the prefer-dark flag) and the view's background. */
static void set_enum_by_nick(GObject *obj, const char *prop, const char *nick) {
    GParamSpec *ps = g_object_class_find_property(G_OBJECT_GET_CLASS(obj), prop);
    if (!ps || !G_IS_PARAM_SPEC_ENUM(ps)) return;
    GEnumValue *v = g_enum_get_value_by_nick(G_PARAM_SPEC_ENUM(ps)->enum_class, nick);
    if (v) g_object_set(obj, prop, v->value, NULL);
}

void arctic_set_theme(const char *css, int dark, const char *ground) {
    GdkDisplay *display = gdk_display_get_default();
    if (!display) return;
    if (!S.css) {
        S.css = gtk_css_provider_new();
        gtk_style_context_add_provider_for_display(display, GTK_STYLE_PROVIDER(S.css),
                                                   GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    }
    gtk_css_provider_load_from_string(S.css, css ? css : "");
    GtkSettings *gs = gtk_settings_get_default();
    if (gs) {
        if (g_object_class_find_property(G_OBJECT_GET_CLASS(gs), "gtk-interface-color-scheme"))
            set_enum_by_nick(G_OBJECT(gs), "gtk-interface-color-scheme", dark ? "dark" : "light");
        else if (g_object_class_find_property(G_OBJECT_GET_CLASS(gs), "gtk-application-prefer-dark-theme"))
            g_object_set(gs, "gtk-application-prefer-dark-theme", dark ? TRUE : FALSE, NULL);
    }
    GdkRGBA rgba;
    if (S.view && ground && gdk_rgba_parse(&rgba, ground)) webkit_web_view_set_background_color(S.view, &rgba);
}

/* ---------------------------------------------------------------- banner */

static void hide_banner(void) {
    if (S.revealer) gtk_revealer_set_reveal_child(GTK_REVEALER(S.revealer), FALSE);
}

static void finish_permission(gboolean allow, gboolean remember) {
    if (!S.pending) return;
    if (allow)
        webkit_permission_request_allow(S.pending);
    else
        webkit_permission_request_deny(S.pending);
    if (remember) goPermissionDecided(S.cfg.handle, S.pending_kind, S.pending_origin, allow ? 1 : 0);
    g_clear_object(&S.pending);
    g_clear_pointer(&S.pending_origin, g_free);
}

static void banner_primary_cb(GtkButton *b, gpointer data) {
    (void)b;
    (void)data;
    hide_banner();
    if (S.banner_action == 1) {
        webkit_web_view_reload(S.view);
        return;
    }
    finish_permission(TRUE, TRUE);
}

static void banner_secondary_cb(GtkButton *b, gpointer data) {
    (void)b;
    (void)data;
    hide_banner();
    finish_permission(FALSE, TRUE);
}

/* arctic_banner shows a notice with one primary action (reload) or none. */
void arctic_banner(const char *text, const char *primary) {
    if (!S.revealer) return;
    finish_permission(FALSE, FALSE);
    S.banner_action = 1;
    gtk_label_set_text(GTK_LABEL(S.banner_label), text ? text : "");
    gtk_widget_set_visible(S.banner_primary, primary != NULL);
    if (primary) gtk_button_set_label(GTK_BUTTON(S.banner_primary), primary);
    gtk_widget_set_visible(S.banner_secondary, FALSE);
    gtk_revealer_set_reveal_child(GTK_REVEALER(S.revealer), TRUE);
}

static void ask_permission(WebKitPermissionRequest *req, int kind, const char *origin, const char *what) {
    if (S.pending) { /* one question at a time: later ones are refused */
        webkit_permission_request_deny(req);
        return;
    }
    S.pending = g_object_ref(req);
    S.pending_kind = kind;
    S.pending_origin = g_strdup(origin);
    S.banner_action = 0;
    char *host = NULL;
    GUri *u = g_uri_parse(origin, G_URI_FLAGS_NONE, NULL);
    if (u) {
        host = g_strdup(g_uri_get_host(u));
        g_uri_unref(u);
    }
    char *text = g_strdup_printf("%s wants to %s.", host ? host : origin, what);
    gtk_label_set_text(GTK_LABEL(S.banner_label), text);
    gtk_button_set_label(GTK_BUTTON(S.banner_primary), "Allow");
    gtk_widget_set_visible(S.banner_primary, TRUE);
    gtk_widget_set_visible(S.banner_secondary, TRUE);
    gtk_revealer_set_reveal_child(GTK_REVEALER(S.revealer), TRUE);
    g_free(text);
    g_free(host);
}

/* ---------------------------------------------------------------- policy */

static char *origin_of_view(WebKitWebView *view) {
    const char *uri = webkit_web_view_get_uri(view);
    if (!uri) return g_strdup("");
    WebKitSecurityOrigin *o = webkit_security_origin_new_for_uri(uri);
    char *s = webkit_security_origin_to_string(o);
    webkit_security_origin_unref(o);
    return s ? s : g_strdup("");
}

static gboolean permission_cb(WebKitWebView *view, WebKitPermissionRequest *req, gpointer data) {
    (void)data;
    int kind = 10;
    const char *what = "use a device";
    if (WEBKIT_IS_NOTIFICATION_PERMISSION_REQUEST(req)) {
        kind = 0;
        what = "show notifications";
    } else if (WEBKIT_IS_USER_MEDIA_PERMISSION_REQUEST(req)) {
        WebKitUserMediaPermissionRequest *um = WEBKIT_USER_MEDIA_PERMISSION_REQUEST(req);
        if (webkit_user_media_permission_is_for_display_device(um)) {
            kind = 3;
            what = "share your screen";
        } else if (webkit_user_media_permission_is_for_video_device(um)) {
            kind = 1;
            what = webkit_user_media_permission_is_for_audio_device(um) ? "use your camera and microphone" : "use your camera";
        } else {
            kind = 2;
            what = "use your microphone";
        }
    } else if (WEBKIT_IS_GEOLOCATION_PERMISSION_REQUEST(req)) {
        kind = 4;
        what = "know your location";
    } else if (WEBKIT_IS_CLIPBOARD_PERMISSION_REQUEST(req)) {
        kind = 5;
        what = "read your clipboard";
    } else if (WEBKIT_IS_DEVICE_INFO_PERMISSION_REQUEST(req)) {
        kind = 7;
    } else if (WEBKIT_IS_MEDIA_KEY_SYSTEM_PERMISSION_REQUEST(req)) {
        kind = 8;
    } else if (WEBKIT_IS_WEBSITE_DATA_ACCESS_PERMISSION_REQUEST(req)) {
        kind = 9;
        what = "use its data while you're on this site";
    }
    char *origin = origin_of_view(view);
    int answer = goPermission(S.cfg.handle, kind, origin);
    if (answer == ARCTIC_ALLOW)
        webkit_permission_request_allow(req);
    else if (answer == ARCTIC_ASK && view == S.view)
        ask_permission(req, kind, origin, what);
    else
        webkit_permission_request_deny(req);
    g_free(origin);
    return TRUE;
}

static WebKitWebView *new_view(WebKitWebView *related);

static gboolean decide_policy_cb(WebKitWebView *view, WebKitPolicyDecision *decision, WebKitPolicyDecisionType type,
                                 gpointer data) {
    gboolean popup = GPOINTER_TO_INT(data);
    if (type == WEBKIT_POLICY_DECISION_TYPE_RESPONSE) {
        WebKitResponsePolicyDecision *rd = WEBKIT_RESPONSE_POLICY_DECISION(decision);
        WebKitURIResponse *resp = webkit_response_policy_decision_get_response(rd);
        int attachment = 0;
        SoupMessageHeaders *hdrs = webkit_uri_response_get_http_headers(resp);
        if (hdrs) {
            const char *cd = soup_message_headers_get_one(hdrs, "Content-Disposition");
            if (cd && g_ascii_strncasecmp(cd, "attachment", 10) == 0) attachment = 1;
        }
        int can_show = webkit_response_policy_decision_is_mime_type_supported(rd) ? 1 : 0;
        const char *mime = webkit_uri_response_get_mime_type(resp);
        if (goDecideResponse(S.cfg.handle, (char *)(mime ? mime : ""), can_show, attachment) == 1) {
            webkit_policy_decision_download(decision);
            return TRUE;
        }
        return FALSE;
    }
    WebKitNavigationPolicyDecision *nd = WEBKIT_NAVIGATION_POLICY_DECISION(decision);
    WebKitNavigationAction *action = webkit_navigation_policy_decision_get_navigation_action(nd);
    WebKitURIRequest *req = webkit_navigation_action_get_request(action);
    const char *uri = webkit_uri_request_get_uri(req);
    guint mods = webkit_navigation_action_get_modifiers(action);
    int modifiers = (mods & (GDK_CONTROL_MASK | GDK_SHIFT_MASK)) ? 1 : 0;
    int middle = webkit_navigation_action_get_mouse_button(action) == 2 ? 1 : 0;
    int new_window = type == WEBKIT_POLICY_DECISION_TYPE_NEW_WINDOW_ACTION ? 1 : 0;
    int d = goDecidePolicy(S.cfg.handle, (char *)(uri ? uri : ""), (int)webkit_navigation_action_get_navigation_type(action),
                           webkit_navigation_action_is_user_gesture(action) ? 1 : 0, new_window, modifiers, middle,
                           popup ? 1 : 0);
    switch (d) {
    case ARCTIC_USE:
    case ARCTIC_POPUP:
        webkit_policy_decision_use(decision);
        break;
    case ARCTIC_EXTERNAL:
        webkit_policy_decision_ignore(decision);
        arctic_open_external(uri);
        break;
    case ARCTIC_LOAD_IN_APP:
        webkit_policy_decision_ignore(decision);
        webkit_web_view_load_uri(S.view, uri);
        break;
    default:
        webkit_policy_decision_ignore(decision);
    }
    (void)view;
    return TRUE;
}

/* ---------------------------------------------------------------- popups (OAuth) */

static void popup_title_cb(WebKitWebView *view, GParamSpec *ps, gpointer win) {
    (void)ps;
    const char *t = webkit_web_view_get_title(view);
    const char *uri = webkit_web_view_get_uri(view);
    char *host = NULL;
    if (uri) {
        GUri *u = g_uri_parse(uri, G_URI_FLAGS_NONE, NULL);
        if (u) {
            host = g_strdup_printf("%s%s", g_strcmp0(g_uri_get_scheme(u), "https") == 0 ? "" : "Not secure · ",
                                   g_uri_get_host(u) ? g_uri_get_host(u) : "");
            g_uri_unref(u);
        }
    }
    char *title = g_strdup_printf("Pop-up: %s — %s", t && *t ? t : "", host ? host : "");
    gtk_window_set_title(GTK_WINDOW(win), title);
    g_free(title);
    g_free(host);
}

static void popup_ready_cb(WebKitWebView *view, gpointer win) {
    WebKitWindowProperties *wp = webkit_web_view_get_window_properties(view);
    GdkRectangle g = {0};
    webkit_window_properties_get_geometry(wp, &g);
    int w = g.width > 0 ? CLAMP(g.width, 480, 1200) : 600;
    int h = g.height > 0 ? CLAMP(g.height, 400, 900) : 700;
    gtk_window_set_default_size(GTK_WINDOW(win), w, h);
    gtk_window_present(GTK_WINDOW(win));
}

static void popup_close_cb(WebKitWebView *view, gpointer win) {
    (void)view;
    gtk_window_destroy(GTK_WINDOW(win));
}

static GtkWidget *create_cb(WebKitWebView *view, WebKitNavigationAction *action, gpointer data) {
    (void)action;
    (void)data;
    WebKitWebView *popup = new_view(view);
    GtkWidget *win = gtk_window_new();
    gtk_window_set_transient_for(GTK_WINDOW(win), S.window);
    gtk_window_set_application(GTK_WINDOW(win), S.app);
    gtk_window_set_title(GTK_WINDOW(win), "Pop-up");
    gtk_window_set_titlebar(GTK_WINDOW(win), gtk_header_bar_new());
    gtk_window_set_child(GTK_WINDOW(win), GTK_WIDGET(popup));
    g_signal_connect(popup, "ready-to-show", G_CALLBACK(popup_ready_cb), win);
    g_signal_connect(popup, "close", G_CALLBACK(popup_close_cb), win);
    g_signal_connect(popup, "notify::title", G_CALLBACK(popup_title_cb), win);
    g_signal_connect(popup, "notify::uri", G_CALLBACK(popup_title_cb), win);
    return GTK_WIDGET(popup);
}

/* ---------------------------------------------------------------- notifications */

static void notification_closed_cb(WebKitNotification *n, gpointer data) {
    (void)data;
    char *tag = g_strdup_printf("n%" G_GUINT64_FORMAT, webkit_notification_get_id(n));
    g_application_withdraw_notification(G_APPLICATION(S.app), tag);
    g_hash_table_remove(S.notifications, tag);
    g_free(tag);
}

static gboolean show_notification_cb(WebKitWebView *view, WebKitNotification *n, gpointer data) {
    (void)view;
    (void)data;
    char *tag = g_strdup_printf("n%" G_GUINT64_FORMAT, webkit_notification_get_id(n));
    GNotification *gn = g_notification_new(webkit_notification_get_title(n));
    const char *body = webkit_notification_get_body(n);
    if (body && *body) g_notification_set_body(gn, body);
    GIcon *icon = g_themed_icon_new(S.cfg.icon_name ? S.cfg.icon_name : S.cfg.app_id);
    g_notification_set_icon(gn, icon);
    g_object_unref(icon);
    g_notification_set_default_action_and_target(gn, "app.notification-clicked", "s", tag);
    g_hash_table_replace(S.notifications, g_strdup(tag), g_object_ref(n));
    g_signal_connect(n, "closed", G_CALLBACK(notification_closed_cb), NULL);
    g_application_send_notification(G_APPLICATION(S.app), tag, gn);
    g_object_unref(gn);
    g_free(tag);
    return TRUE;
}

static void notification_clicked_cb(GSimpleAction *a, GVariant *param, gpointer data) {
    (void)a;
    (void)data;
    const char *tag = g_variant_get_string(param, NULL);
    arctic_present();
    WebKitNotification *n = g_hash_table_lookup(S.notifications, tag);
    if (n) webkit_notification_clicked(n);
}

static void init_notification_permissions_cb(WebKitWebContext *ctx, gpointer data) {
    (void)data;
    char *origins = goNotificationOrigins(S.cfg.handle);
    GList *allowed = NULL;
    if (origins) {
        char **parts = g_strsplit(origins, "\n", -1);
        for (char **p = parts; *p; p++)
            if (**p) allowed = g_list_prepend(allowed, webkit_security_origin_new_for_uri(*p));
        g_strfreev(parts);
        free(origins);
    }
    webkit_web_context_initialize_notification_permissions(ctx, allowed, NULL);
    g_list_free_full(allowed, (GDestroyNotify)webkit_security_origin_unref);
}

/* ---------------------------------------------------------------- downloads */

static void download_finished_cb(WebKitDownload *d, gpointer data) {
    (void)data;
    const char *dest = webkit_download_get_destination(d);
    if (dest) goDownloadFinished(S.cfg.handle, (char *)dest);
}

static gboolean decide_destination_cb(WebKitDownload *d, const char *suggested, gpointer data) {
    (void)data;
    WebKitURIResponse *resp = webkit_download_get_response(d);
    const char *mime = resp ? webkit_uri_response_get_mime_type(resp) : NULL;
    char *path = goDownloadDestination(S.cfg.handle, (char *)(suggested ? suggested : ""), (char *)(mime ? mime : ""));
    if (!path) {
        webkit_download_cancel(d);
        return TRUE;
    }
    webkit_download_set_allow_overwrite(d, FALSE);
    webkit_download_set_destination(d, path);
    free(path);
    return TRUE;
}

static void download_started_cb(WebKitNetworkSession *s, WebKitDownload *d, gpointer data) {
    (void)s;
    (void)data;
    g_signal_connect(d, "decide-destination", G_CALLBACK(decide_destination_cb), NULL);
    g_signal_connect(d, "finished", G_CALLBACK(download_finished_cb), NULL);
}

/* ---------------------------------------------------------------- loading, errors, crashes */

static void update_nav_buttons(void) {
    gtk_widget_set_sensitive(S.back, webkit_web_view_can_go_back(S.view));
    gtk_widget_set_sensitive(S.forward, webkit_web_view_can_go_forward(S.view));
}

static void title_cb(WebKitWebView *view, GParamSpec *ps, gpointer data) {
    (void)ps;
    (void)data;
    const char *t = webkit_web_view_get_title(view);
    gtk_window_set_title(S.window, t && *t ? t : S.cfg.app_name);
}

static void uri_cb(WebKitWebView *view, GParamSpec *ps, gpointer data) {
    (void)ps;
    (void)data;
    const char *uri = webkit_web_view_get_uri(view);
    if (!uri) return;
    int away = goURIChanged(S.cfg.handle, (char *)uri);
    gtk_widget_set_visible(S.back_to_app, away & 1);
    gtk_widget_set_visible(S.host_label, away != 0);
    if (away) {
        GUri *u = g_uri_parse(uri, G_URI_FLAGS_NONE, NULL);
        if (u) {
            char *text = g_strdup_printf("%s%s", (away & 2) ? "Not secure · " : "", g_uri_get_host(u) ? g_uri_get_host(u) : "");
            gtk_label_set_text(GTK_LABEL(S.host_label), text);
            g_free(text);
            g_uri_unref(u);
        }
    }
    update_nav_buttons();
}

static void load_changed_cb(WebKitWebView *view, WebKitLoadEvent ev, gpointer data) {
    (void)data;
    update_nav_buttons();
    gtk_button_set_icon_name(GTK_BUTTON(S.reload), ev == WEBKIT_LOAD_FINISHED ? "view-refresh-symbolic" : "process-stop-symbolic");
    if (ev == WEBKIT_LOAD_FINISHED) {
        const char *uri = webkit_web_view_get_uri(view);
        if (uri) goLoadFinished(S.cfg.handle, (char *)uri);
    }
}

static gboolean load_failed_cb(WebKitWebView *view, WebKitLoadEvent ev, const char *uri, GError *err, gpointer data) {
    (void)view;
    (void)ev;
    (void)data;
    if (g_error_matches(err, WEBKIT_NETWORK_ERROR, WEBKIT_NETWORK_ERROR_CANCELLED) ||
        g_error_matches(err, WEBKIT_POLICY_ERROR, WEBKIT_POLICY_ERROR_FRAME_LOAD_INTERRUPTED_BY_POLICY_CHANGE) ||
        g_error_matches(err, WEBKIT_MEDIA_ERROR, WEBKIT_MEDIA_ERROR_WILL_HANDLE_LOAD))
        return FALSE;
    char *html = goLoadFailed(S.cfg.handle, (char *)(uri ? uri : ""), (char *)(err ? err->message : ""), 0);
    if (!html) return FALSE;
    webkit_web_view_load_alternate_html(S.view, html, uri, NULL);
    free(html);
    return TRUE;
}

static gboolean tls_failed_cb(WebKitWebView *view, const char *uri, GTlsCertificate *cert, GTlsCertificateFlags errors,
                              gpointer data) {
    (void)view;
    (void)cert;
    (void)errors;
    (void)data;
    char *html = goLoadFailed(S.cfg.handle, (char *)(uri ? uri : ""), "", 1);
    if (!html) return FALSE;
    webkit_web_view_load_alternate_html(S.view, html, uri, NULL);
    free(html);
    return TRUE;
}

static void terminated_cb(WebKitWebView *view, WebKitWebProcessTerminationReason reason, gpointer data) {
    (void)data;
    if (goProcessTerminated(S.cfg.handle, (int)reason) == 1)
        webkit_web_view_reload(view);
    else
        arctic_banner("This page stopped working.", "Reload");
}

static void fullscreen_cb(WebKitWebView *view, gpointer data) {
    (void)view;
    gtk_widget_set_visible(S.header, GPOINTER_TO_INT(data) == 0);
}

/* ---------------------------------------------------------------- views and the window */

static WebKitWebView *new_view(WebKitWebView *related) {
    WebKitWebView *v;
    if (related)
        v = WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "related-view", related, "settings", S.settings,
                                         "user-content-manager", S.ucm, NULL));
    else
        v = WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "network-session", S.session, "settings", S.settings,
                                         "user-content-manager", S.ucm, NULL));
    g_signal_connect(v, "decide-policy", G_CALLBACK(decide_policy_cb), GINT_TO_POINTER(related != NULL));
    g_signal_connect(v, "permission-request", G_CALLBACK(permission_cb), NULL);
    g_signal_connect(v, "create", G_CALLBACK(create_cb), NULL);
    g_signal_connect(v, "show-notification", G_CALLBACK(show_notification_cb), NULL);
    return v;
}

static void back_cb(GtkButton *b, gpointer d) {
    (void)b;
    (void)d;
    webkit_web_view_go_back(S.view);
}
static void forward_cb(GtkButton *b, gpointer d) {
    (void)b;
    (void)d;
    webkit_web_view_go_forward(S.view);
}
static void reload_cb(GtkButton *b, gpointer d) {
    (void)b;
    (void)d;
    if (webkit_web_view_is_loading(S.view))
        webkit_web_view_stop_loading(S.view);
    else
        webkit_web_view_reload(S.view);
}
static void back_to_app_cb(GtkButton *b, gpointer d) {
    (void)b;
    (void)d;
    webkit_web_view_load_uri(S.view, S.cfg.start_uri);
}

/* Keyboard shortcuts (bubble phase: a page that handles a key itself keeps it). */
static void zoom_by(double f) {
    double z = webkit_web_view_get_zoom_level(S.view);
    z = f == 0 ? 1.0 : CLAMP(z * f, 0.3, 5.0);
    webkit_web_view_set_zoom_level(S.view, z);
}

static gboolean shortcut_cb(GtkWidget *w, GVariant *args, gpointer data) {
    (void)w;
    (void)args;
    const char *what = data;
    if (!strcmp(what, "find")) {
        gtk_search_bar_set_search_mode(GTK_SEARCH_BAR(S.search_bar), TRUE);
        gtk_widget_grab_focus(S.search_entry);
    } else if (!strcmp(what, "zoom-in")) {
        zoom_by(1.1);
    } else if (!strcmp(what, "zoom-out")) {
        zoom_by(1 / 1.1);
    } else if (!strcmp(what, "zoom-reset")) {
        zoom_by(0);
    } else if (!strcmp(what, "reload")) {
        webkit_web_view_reload(S.view);
    } else if (!strcmp(what, "reload-hard")) {
        webkit_web_view_reload_bypass_cache(S.view);
    } else if (!strcmp(what, "back")) {
        webkit_web_view_go_back(S.view);
    } else if (!strcmp(what, "forward")) {
        webkit_web_view_go_forward(S.view);
    } else if (!strcmp(what, "print")) {
        WebKitPrintOperation *op = webkit_print_operation_new(S.view);
        webkit_print_operation_run_dialog(op, S.window);
        g_object_unref(op);
    } else if (!strcmp(what, "copy-link")) {
        const char *uri = webkit_web_view_get_uri(S.view);
        if (uri) gdk_clipboard_set_text(gtk_widget_get_clipboard(GTK_WIDGET(S.window)), uri);
    } else if (!strcmp(what, "fullscreen")) {
        if (gtk_window_is_fullscreen(S.window))
            gtk_window_unfullscreen(S.window);
        else
            gtk_window_fullscreen(S.window);
    } else if (!strcmp(what, "close")) {
        gtk_window_close(S.window);
    } else if (!strcmp(what, "quit")) {
        gtk_window_close(S.window);
    } else if (!strcmp(what, "inspector")) {
        if (!S.cfg.devtools) return FALSE;
        webkit_web_inspector_show(webkit_web_view_get_inspector(S.view));
    } else if (!strcmp(what, "escape")) {
        if (!gtk_revealer_get_reveal_child(GTK_REVEALER(S.revealer))) return FALSE;
        hide_banner();
        finish_permission(FALSE, FALSE);
    }
    return TRUE;
}

static void add_shortcuts(GtkWidget *window) {
    static const struct {
        const char *keys, *action;
    } map[] = {
        {"<Control>f", "find"},           {"<Control>equal", "zoom-in"},   {"<Control>plus", "zoom-in"},
        {"<Control>KP_Add", "zoom-in"},   {"<Control>minus", "zoom-out"},  {"<Control>KP_Subtract", "zoom-out"},
        {"<Control>0", "zoom-reset"},     {"F5", "reload"},                {"<Control>r", "reload"},
        {"<Control><Shift>r", "reload-hard"}, {"<Alt>Left", "back"},       {"<Alt>Right", "forward"},
        {"Back", "back"},                 {"Forward", "forward"},          {"<Control>p", "print"},
        {"<Control>l", "copy-link"},      {"F11", "fullscreen"},           {"<Control>w", "close"},
        {"<Control>q", "quit"},           {"F12", "inspector"},            {"<Control><Shift>i", "inspector"},
        {"Escape", "escape"},
    };
    GtkEventController *c = gtk_shortcut_controller_new();
    gtk_event_controller_set_propagation_phase(c, GTK_PHASE_BUBBLE);
    for (size_t i = 0; i < G_N_ELEMENTS(map); i++) {
        GtkShortcutTrigger *t = gtk_shortcut_trigger_parse_string(map[i].keys);
        if (!t) continue;
        GtkShortcutAction *a = gtk_callback_action_new(shortcut_cb, (gpointer)map[i].action, NULL);
        gtk_shortcut_controller_add_shortcut(GTK_SHORTCUT_CONTROLLER(c), gtk_shortcut_new(t, a));
    }
    gtk_widget_add_controller(window, c);
}

/* Mouse buttons 8 and 9 go back and forward. */
static void mouse_cb(GtkGestureClick *g, int n, double x, double y, gpointer d) {
    (void)n;
    (void)x;
    (void)y;
    (void)d;
    guint b = gtk_gesture_single_get_current_button(GTK_GESTURE_SINGLE(g));
    if (b == 8) webkit_web_view_go_back(S.view);
    if (b == 9) webkit_web_view_go_forward(S.view);
}

/* Find bar. */
static void find_changed_cb(GtkSearchEntry *e, gpointer d) {
    (void)d;
    WebKitFindController *fc = webkit_web_view_get_find_controller(S.view);
    const char *text = gtk_editable_get_text(GTK_EDITABLE(e));
    if (!text || !*text) {
        webkit_find_controller_search_finish(fc);
        return;
    }
    webkit_find_controller_search(fc, text, WEBKIT_FIND_OPTIONS_CASE_INSENSITIVE | WEBKIT_FIND_OPTIONS_WRAP_AROUND, G_MAXUINT);
}
static void find_next_cb(GtkSearchEntry *e, gpointer d) {
    (void)e;
    (void)d;
    webkit_find_controller_search_next(webkit_web_view_get_find_controller(S.view));
}
static void find_prev_cb(GtkSearchEntry *e, gpointer d) {
    (void)e;
    (void)d;
    webkit_find_controller_search_previous(webkit_web_view_get_find_controller(S.view));
}
static gboolean find_key_cb(GtkEventControllerKey *k, guint keyval, guint code, GdkModifierType state, gpointer d) {
    (void)k;
    (void)code;
    (void)d;
    if ((keyval == GDK_KEY_Return || keyval == GDK_KEY_KP_Enter) && (state & GDK_SHIFT_MASK)) {
        find_prev_cb(NULL, NULL);
        return TRUE;
    }
    return FALSE;
}
static void find_stop_cb(GtkSearchEntry *e, gpointer d) {
    (void)e;
    (void)d;
    webkit_find_controller_search_finish(webkit_web_view_get_find_controller(S.view));
    gtk_search_bar_set_search_mode(GTK_SEARCH_BAR(S.search_bar), FALSE);
    gtk_widget_grab_focus(GTK_WIDGET(S.view));
}

static gboolean close_request_cb(GtkWindow *w, gpointer d) {
    (void)d;
    goCloseRequest(S.cfg.handle, gtk_widget_get_width(GTK_WIDGET(w)), gtk_widget_get_height(GTK_WIDGET(w)),
                   gtk_window_is_maximized(w) ? 1 : 0, webkit_web_view_get_zoom_level(S.view));
    return FALSE;
}

static GtkWidget *icon_button(const char *icon, const char *tip, GCallback cb) {
    GtkWidget *b = gtk_button_new_from_icon_name(icon);
    gtk_widget_set_tooltip_text(b, tip);
    g_signal_connect(b, "clicked", cb, NULL);
    return b;
}

static void build_window(void) {
    GtkWidget *win = gtk_application_window_new(S.app);
    S.window = GTK_WINDOW(win);
    gtk_widget_add_css_class(win, "arctic-webapp");
    gtk_window_set_title(S.window, S.cfg.app_name);
    gtk_window_set_icon_name(S.window, S.cfg.icon_name ? S.cfg.icon_name : S.cfg.app_id);
    gtk_window_set_default_size(S.window, S.cfg.width, S.cfg.height);
    if (S.cfg.maximized) gtk_window_maximize(S.window);

    S.header = gtk_header_bar_new();
    S.back = icon_button("go-previous-symbolic", "Back (Alt+Left)", G_CALLBACK(back_cb));
    S.forward = icon_button("go-next-symbolic", "Forward (Alt+Right)", G_CALLBACK(forward_cb));
    S.reload = icon_button("view-refresh-symbolic", "Reload (F5)", G_CALLBACK(reload_cb));
    gtk_header_bar_pack_start(GTK_HEADER_BAR(S.header), S.back);
    gtk_header_bar_pack_start(GTK_HEADER_BAR(S.header), S.forward);
    gtk_header_bar_pack_start(GTK_HEADER_BAR(S.header), S.reload);
    char *label = g_strdup_printf("Back to %s", S.cfg.app_name);
    S.back_to_app = gtk_button_new_with_label(label);
    g_free(label);
    g_signal_connect(S.back_to_app, "clicked", G_CALLBACK(back_to_app_cb), NULL);
    S.host_label = gtk_label_new("");
    gtk_widget_add_css_class(S.host_label, "arctic-host");
    gtk_header_bar_pack_end(GTK_HEADER_BAR(S.header), S.back_to_app);
    gtk_header_bar_pack_end(GTK_HEADER_BAR(S.header), S.host_label);
    gtk_widget_set_visible(S.back_to_app, FALSE);
    gtk_widget_set_visible(S.host_label, FALSE);
    gtk_window_set_titlebar(S.window, S.header);

    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);

    S.search_bar = gtk_search_bar_new();
    gtk_widget_add_css_class(S.search_bar, "arctic-findbar");
    S.search_entry = gtk_search_entry_new();
    gtk_search_bar_set_child(GTK_SEARCH_BAR(S.search_bar), S.search_entry);
    gtk_search_bar_connect_entry(GTK_SEARCH_BAR(S.search_bar), GTK_EDITABLE(S.search_entry));
    gtk_search_bar_set_show_close_button(GTK_SEARCH_BAR(S.search_bar), TRUE);
    g_signal_connect(S.search_entry, "search-changed", G_CALLBACK(find_changed_cb), NULL);
    g_signal_connect(S.search_entry, "activate", G_CALLBACK(find_next_cb), NULL);
    g_signal_connect(S.search_entry, "next-match", G_CALLBACK(find_next_cb), NULL);
    g_signal_connect(S.search_entry, "previous-match", G_CALLBACK(find_prev_cb), NULL);
    g_signal_connect(S.search_entry, "stop-search", G_CALLBACK(find_stop_cb), NULL);
    GtkEventController *fk = gtk_event_controller_key_new();
    g_signal_connect(fk, "key-pressed", G_CALLBACK(find_key_cb), NULL);
    gtk_widget_add_controller(S.search_entry, fk);
    gtk_box_append(GTK_BOX(box), S.search_bar);

    /* The banner sits under the header, outside the page, so a page can't fake it. */
    S.revealer = gtk_revealer_new();
    GtkWidget *bbox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_add_css_class(bbox, "arctic-banner");
    S.banner_label = gtk_label_new("");
    gtk_label_set_wrap(GTK_LABEL(S.banner_label), TRUE);
    gtk_label_set_xalign(GTK_LABEL(S.banner_label), 0);
    gtk_widget_set_hexpand(S.banner_label, TRUE);
    S.banner_secondary = gtk_button_new_with_label("Block");
    S.banner_primary = gtk_button_new_with_label("Allow");
    gtk_widget_add_css_class(S.banner_primary, "suggested-action");
    g_signal_connect(S.banner_primary, "clicked", G_CALLBACK(banner_primary_cb), NULL);
    g_signal_connect(S.banner_secondary, "clicked", G_CALLBACK(banner_secondary_cb), NULL);
    gtk_box_append(GTK_BOX(bbox), S.banner_label);
    gtk_box_append(GTK_BOX(bbox), S.banner_secondary);
    gtk_box_append(GTK_BOX(bbox), S.banner_primary);
    gtk_revealer_set_child(GTK_REVEALER(S.revealer), bbox);
    gtk_box_append(GTK_BOX(box), S.revealer);

    S.view = new_view(NULL);
    gtk_widget_set_vexpand(GTK_WIDGET(S.view), TRUE);
    webkit_web_view_set_zoom_level(S.view, S.cfg.zoom > 0 ? S.cfg.zoom : 1.0);
    g_signal_connect(S.view, "notify::title", G_CALLBACK(title_cb), NULL);
    g_signal_connect(S.view, "notify::uri", G_CALLBACK(uri_cb), NULL);
    g_signal_connect(S.view, "load-changed", G_CALLBACK(load_changed_cb), NULL);
    g_signal_connect(S.view, "load-failed", G_CALLBACK(load_failed_cb), NULL);
    g_signal_connect(S.view, "load-failed-with-tls-errors", G_CALLBACK(tls_failed_cb), NULL);
    g_signal_connect(S.view, "web-process-terminated", G_CALLBACK(terminated_cb), NULL);
    g_signal_connect(S.view, "enter-fullscreen", G_CALLBACK(fullscreen_cb), GINT_TO_POINTER(1));
    g_signal_connect(S.view, "leave-fullscreen", G_CALLBACK(fullscreen_cb), GINT_TO_POINTER(0));
    GtkGesture *click = gtk_gesture_click_new();
    gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(click), 0);
    g_signal_connect(click, "pressed", G_CALLBACK(mouse_cb), NULL);
    gtk_widget_add_controller(GTK_WIDGET(S.view), GTK_EVENT_CONTROLLER(click));
    gtk_box_append(GTK_BOX(box), GTK_WIDGET(S.view));

    gtk_window_set_child(S.window, box);
    add_shortcuts(win);
    g_signal_connect(win, "close-request", G_CALLBACK(close_request_cb), NULL);
    update_nav_buttons();
    goThemeChanged(S.cfg.handle); /* applies the theme now that the view exists */
    if (S.cfg.notice && !S.first_notice_shown) {
        S.first_notice_shown = TRUE;
        arctic_banner(S.cfg.notice, NULL);
    }
    webkit_web_view_load_uri(S.view, S.cfg.open_uri);
}

/* ---------------------------------------------------------------- application */

static void theme_monitor_cb(GFileMonitor *m, GFile *f, GFile *other, GFileMonitorEvent ev, gpointer d) {
    (void)m;
    (void)other;
    (void)d;
    if (ev != G_FILE_MONITOR_EVENT_CHANGES_DONE_HINT && ev != G_FILE_MONITOR_EVENT_CREATED &&
        ev != G_FILE_MONITOR_EVENT_RENAMED && ev != G_FILE_MONITOR_EVENT_MOVED_IN && ev != G_FILE_MONITOR_EVENT_CHANGED)
        return;
    char *name = g_file_get_basename(f);
    if (name && (!strcmp(name, "theme") || !strcmp(name, "current"))) goThemeChanged(S.cfg.handle);
    g_free(name);
}

static gboolean unix_signal_cb(gpointer data) {
    goSignal(S.cfg.handle, GPOINTER_TO_INT(data));
    return G_SOURCE_CONTINUE;
}

static void startup_cb(GApplication *app, gpointer d) {
    (void)d;
    g_set_application_name(S.cfg.app_name);
    S.session = webkit_network_session_new(S.cfg.data_dir, S.cfg.cache_dir);
    char *cookies = g_build_filename(S.cfg.data_dir, "cookies.sqlite", NULL);
    webkit_cookie_manager_set_persistent_storage(webkit_network_session_get_cookie_manager(S.session), cookies,
                                                 WEBKIT_COOKIE_PERSISTENT_STORAGE_SQLITE);
    g_free(cookies);
    webkit_network_session_set_itp_enabled(S.session, TRUE);
    webkit_network_session_set_persistent_credential_storage_enabled(S.session, FALSE);
    webkit_website_data_manager_set_favicons_enabled(webkit_network_session_get_website_data_manager(S.session), TRUE);
    g_signal_connect(S.session, "download-started", G_CALLBACK(download_started_cb), NULL);

    WebKitWebContext *ctx = webkit_web_context_get_default();
    webkit_web_context_set_spell_checking_enabled(ctx, TRUE);
    g_signal_connect(ctx, "initialize-notification-permissions", G_CALLBACK(init_notification_permissions_cb), NULL);

    S.settings = webkit_settings_new();
    webkit_settings_set_hardware_acceleration_policy(S.settings, S.cfg.software ? WEBKIT_HARDWARE_ACCELERATION_POLICY_NEVER
                                                                                : WEBKIT_HARDWARE_ACCELERATION_POLICY_ALWAYS);
    webkit_settings_set_enable_developer_extras(S.settings, S.cfg.devtools ? TRUE : FALSE);
    webkit_settings_set_enable_media_stream(S.settings, TRUE);
    webkit_settings_set_javascript_can_open_windows_automatically(S.settings, FALSE);
    webkit_settings_set_enable_site_specific_quirks(S.settings, TRUE);
    webkit_settings_set_enable_back_forward_navigation_gestures(S.settings, TRUE);
    S.ucm = webkit_user_content_manager_new();

    GSimpleAction *clicked = g_simple_action_new("notification-clicked", G_VARIANT_TYPE_STRING);
    g_signal_connect(clicked, "activate", G_CALLBACK(notification_clicked_cb), NULL);
    g_action_map_add_action(G_ACTION_MAP(app), G_ACTION(clicked));
    g_object_unref(clicked);
    S.notifications = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_object_unref);

    g_unix_signal_add(SIGTERM, unix_signal_cb, GINT_TO_POINTER(SIGTERM));
    g_unix_signal_add(SIGINT, unix_signal_cb, GINT_TO_POINTER(SIGINT));
    g_unix_signal_add(SIGHUP, unix_signal_cb, GINT_TO_POINTER(SIGHUP));

    char *dir = g_build_filename(g_get_user_config_dir(), "arctic", NULL);
    GFile *f = g_file_new_for_path(dir);
    S.theme_monitor = g_file_monitor_directory(f, G_FILE_MONITOR_WATCH_MOVES, NULL, NULL);
    if (S.theme_monitor) g_signal_connect(S.theme_monitor, "changed", G_CALLBACK(theme_monitor_cb), NULL);
    g_object_unref(f);
    g_free(dir);
    /* Only the primary instance gets here: it owns the pid file. The session exists now, so
     * stored certificate exceptions can be applied. */
    goStartup(S.cfg.handle);
}

static void activate_cb(GApplication *app, gpointer d) {
    (void)app;
    (void)d;
    if (!S.window) build_window();
    gtk_window_present(S.window);
}

static void open_cb(GApplication *app, GFile **files, int n, const char *hint, gpointer d) {
    (void)hint;
    (void)d;
    if (!S.window) {
        /* First start with --url: that page is the first one. */
        if (n > 0) {
            char *uri = g_file_get_uri(files[0]);
            g_free((char *)S.cfg.open_uri);
            S.cfg.open_uri = uri;
        }
        activate_cb(app, NULL);
        return;
    }
    gtk_window_present(S.window);
    for (int i = 0; i < n && i < 1; i++) {
        char *uri = g_file_get_uri(files[i]);
        goOpen(S.cfg.handle, uri);
        g_free(uri);
    }
}

static void shutdown_cb(GApplication *app, gpointer d) {
    (void)app;
    (void)d;
    goShutdown(S.cfg.handle);
}

int arctic_run(const ArcticConfig *cfg, int argc, char **argv) {
    memset(&S, 0, sizeof S);
    S.cfg = *cfg;
    S.cfg.app_id = dup_or_null(cfg->app_id);
    S.cfg.app_name = dup_or_null(cfg->app_name);
    S.cfg.icon_name = dup_or_null(cfg->icon_name);
    S.cfg.start_uri = dup_or_null(cfg->start_uri);
    S.cfg.open_uri = dup_or_null(cfg->open_uri);
    S.cfg.data_dir = dup_or_null(cfg->data_dir);
    S.cfg.cache_dir = dup_or_null(cfg->cache_dir);
    S.cfg.notice = dup_or_null(cfg->notice);
    S.app = gtk_application_new(S.cfg.app_id, G_APPLICATION_HANDLES_OPEN);
    g_signal_connect(S.app, "startup", G_CALLBACK(startup_cb), NULL);
    g_signal_connect(S.app, "activate", G_CALLBACK(activate_cb), NULL);
    g_signal_connect(S.app, "open", G_CALLBACK(open_cb), NULL);
    g_signal_connect(S.app, "shutdown", G_CALLBACK(shutdown_cb), NULL);
    int status = g_application_run(G_APPLICATION(S.app), argc, argv);
    g_object_unref(S.app);
    return status;
}
