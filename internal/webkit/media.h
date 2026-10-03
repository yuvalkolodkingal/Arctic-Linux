//go:build cgo && webkit

/* MPRIS for ordinary top-level HTML media. There is no page-to-native message handler.
 * Evaluation runs in an isolated world and only returns a bounded snapshot. WebRTC streams
 * are excluded. Unsupported site-specific next/previous actions are never advertised. */
static struct {
    GDBusConnection *bus;
    GDBusNodeInfo *node;
    guint root_id, player_id, owner, timer;
    gboolean pending, available, playing, seekable;
    gint64 position, duration;
    double volume, rate;
    char *title, *artist, *track;
    guint64 track_serial;
    guint generation;
} M;

static const char *media_prefix =
    "(()=>{const all=[...document.querySelectorAll('audio,video')].filter(e=>!e.srcObject&&(e.currentSrc||e.src));"
    "const e=all.find(e=>!e.paused&&!e.ended)||all.find(e=>e.readyState>0);";

static GVariant *media_metadata(void) {
    GVariantBuilder b;
    g_variant_builder_init(&b, G_VARIANT_TYPE_VARDICT);
    if (M.available) {
        g_variant_builder_add(&b, "{sv}", "mpris:trackid", g_variant_new_object_path(M.track ? M.track : "/org/mpris/MediaPlayer2/TrackList/NoTrack"));
        g_variant_builder_add(&b, "{sv}", "xesam:title", g_variant_new_string(M.title ? M.title : S.cfg.app_name));
        const char *artists[] = {M.artist ? M.artist : "", NULL};
        g_variant_builder_add(&b, "{sv}", "xesam:artist", g_variant_new_strv(artists, -1));
        if (M.duration > 0)
            g_variant_builder_add(&b, "{sv}", "mpris:length", g_variant_new_int64(M.duration));
    }
    return g_variant_builder_end(&b);
}

static GVariant *media_get(GDBusConnection *bus, const char *sender, const char *path, const char *iface,
                           const char *property, GError **error, gpointer data) {
    (void)bus;
    (void)sender;
    (void)path;
    (void)iface;
    (void)error;
    (void)data;
    if (!strcmp(property, "Identity"))
        return g_variant_new_string(S.cfg.app_name);
    if (!strcmp(property, "DesktopEntry"))
        return g_variant_new_string(S.cfg.app_id);
    if (!strcmp(property, "SupportedUriSchemes") || !strcmp(property, "SupportedMimeTypes"))
        return g_variant_new_strv(NULL, 0);
    if (!strcmp(property, "CanRaise") || !strcmp(property, "CanQuit"))
        return g_variant_new_boolean(TRUE);
    if (!strcmp(property, "HasTrackList") || !strcmp(property, "CanGoNext") || !strcmp(property, "CanGoPrevious"))
        return g_variant_new_boolean(FALSE);
    if (!strcmp(property, "Metadata"))
        return media_metadata();
    if (!strcmp(property, "PlaybackStatus"))
        return g_variant_new_string(!M.available ? "Stopped" : M.playing ? "Playing" : "Paused");
    if (!strcmp(property, "Position"))
        return g_variant_new_int64(M.position);
    if (!strcmp(property, "Rate")) return g_variant_new_double(M.rate > 0 ? M.rate : 1);
    if (!strcmp(property, "Volume")) return g_variant_new_double(M.volume);
    if (!strcmp(property, "MinimumRate")) return g_variant_new_double(0.25);
    if (!strcmp(property, "MaximumRate")) return g_variant_new_double(4);
    if (!strcmp(property, "CanSeek"))
        return g_variant_new_boolean(M.available && M.seekable);
    if (!strcmp(property, "CanPlay") || !strcmp(property, "CanPause") || !strcmp(property, "CanControl"))
        return g_variant_new_boolean(M.available);
    return NULL;
}

static void media_changed(void) {
    if (!M.bus || !M.owner)
        return;
    GVariantBuilder changed, invalid;
    g_variant_builder_init(&changed, G_VARIANT_TYPE_VARDICT);
    const char *props[] = {"PlaybackStatus", "Metadata", "CanPlay", "CanPause", "CanControl", "CanSeek", NULL};
    for (const char **p = props; *p; p++)
        g_variant_builder_add(&changed, "{sv}", *p, media_get(NULL, NULL, NULL, NULL, *p, NULL, NULL));
    g_variant_builder_init(&invalid, G_VARIANT_TYPE("as"));
    g_dbus_connection_emit_signal(
        M.bus, NULL, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "PropertiesChanged",
        g_variant_new("(sa{sv}as)", "org.mpris.MediaPlayer2.Player", &changed, &invalid), NULL);
}

static gboolean media_in_scope(void) {
    if (!S.view || S.quitting)
        return FALSE;
    const char *uri = webkit_web_view_get_uri(S.view);
    return uri && (g_str_has_prefix(uri, "https://") || g_str_has_prefix(uri, "http://")) &&
           !(goURIChanged(S.cfg.handle, (char *)uri) & 1);
}

typedef struct { GDBusMethodInvocation *inv; guint generation; } MediaCommand;

static void media_command_done(GObject *view, GAsyncResult *result, gpointer data) {
    MediaCommand *command = data;
    GDBusMethodInvocation *inv = command->inv;
    GError *error = NULL;
    JSCValue *value = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(view), result, &error);
    if (error)
        g_dbus_method_invocation_return_error(inv, G_IO_ERROR, G_IO_ERROR_FAILED,
                                              "The page could not perform the media action");
    else
        g_dbus_method_invocation_return_value(inv, NULL);
    if (!error && value && jsc_value_is_number(value) && command->generation == M.generation && M.bus) {
        double position = jsc_value_to_double(value);
        if (position >= 0 && position <= 86400000) {
            M.position = (gint64)(position * 1000000);
            g_dbus_connection_emit_signal(M.bus, NULL, "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player", "Seeked", g_variant_new("(x)", M.position), NULL);
        }
    }
    g_clear_object(&value);
    g_clear_error(&error);
    g_object_unref(inv);
    g_free(command);
}

static void media_method(GDBusConnection *bus, const char *sender, const char *path, const char *iface,
                         const char *method, GVariant *params, GDBusMethodInvocation *inv, gpointer data) {
    (void)bus;
    (void)sender;
    (void)path;
    (void)iface;
    (void)data;
    if (!strcmp(method, "Raise")) {
        arctic_present();
        g_dbus_method_invocation_return_value(inv, NULL);
        return;
    }
    if (!strcmp(method, "Quit")) {
        g_dbus_method_invocation_return_value(inv, NULL);
        arctic_quit();
        return;
    }
    if (!media_in_scope() || !M.available) {
        g_dbus_method_invocation_return_error(inv, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "No controllable media");
        return;
    }
    char *action = NULL;
    if (!strcmp(method, "PlayPause"))
        action = g_strdup("e.paused?e.play():e.pause()");
    else if (!strcmp(method, "Play"))
        action = g_strdup("e.play()");
    else if (!strcmp(method, "Pause") || !strcmp(method, "Stop"))
        action = g_strdup("e.pause()");
    else if (M.seekable && (!strcmp(method, "Seek") || !strcmp(method, "SetPosition"))) {
        gint64 position;
        if (!strcmp(method, "Seek")) {
            gint64 offset;
            g_variant_get(params, "(x)", &offset);
            /* Clamp before addition to avoid signed overflow from arbitrary D-Bus clients. */
            offset = CLAMP(offset, -M.position, M.duration - M.position);
            position = M.position + offset;
        } else {
            const char *track;
            g_variant_get(params, "(&ox)", &track, &position);
            if (g_strcmp0(track, M.track)) {
                g_dbus_method_invocation_return_value(inv, NULL);
                return;
            }
        }
        position = CLAMP(position, 0, M.duration);
        char seconds[G_ASCII_DTOSTR_BUF_SIZE];
        g_ascii_dtostr(seconds, sizeof seconds, (double)position / 1000000);
        action = g_strdup_printf("e.currentTime=%s", seconds);
    }
    if (!action) {
        g_dbus_method_invocation_return_error(inv, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "Unsupported media action");
        return;
    }
    gboolean seek = !strcmp(method, "Seek") || !strcmp(method, "SetPosition");
    char *script = g_strdup_printf("%sif(!e)throw Error('No media');%s;return %s;})()", media_prefix, action,
                                   seek ? "e.currentTime" : "true");
    MediaCommand *command = g_new0(MediaCommand, 1);
    command->inv = g_object_ref(inv); command->generation = M.generation;
    webkit_web_view_evaluate_javascript(S.view, script, -1, "arctic-media", NULL, NULL, media_command_done, command);
    g_free(script);
    g_free(action);
}

static gboolean media_set(GDBusConnection *bus, const char *sender, const char *path, const char *iface,
                          const char *property, GVariant *value, GError **error, gpointer data) {
    (void)bus; (void)sender; (void)path; (void)iface; (void)data;
    double n = g_variant_get_double(value);
    gboolean volume = !strcmp(property, "Volume");
    if (!media_in_scope() || !M.available || (!volume && strcmp(property, "Rate")) ||
        !(n >= (volume ? 0 : 0.25) && n <= (volume ? 1 : 4))) {
        g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "Unsupported media property value");
        return FALSE;
    }
    char number[G_ASCII_DTOSTR_BUF_SIZE]; g_ascii_dtostr(number, sizeof number, n);
    char *script = g_strdup_printf("%sif(e)e.%s=%s;return true;})()", media_prefix,
                                   volume ? "volume" : "playbackRate", number);
    webkit_web_view_evaluate_javascript(S.view, script, -1, "arctic-media", NULL, NULL, NULL, NULL);
    g_free(script);
    if (volume) M.volume = n; else M.rate = n;
    return TRUE;
}

static const GDBusInterfaceVTable media_vtable = {.method_call = media_method, .get_property = media_get, .set_property = media_set};
static const char *media_xml =
    "<node><interface name='org.mpris.MediaPlayer2'>"
    "<method name='Raise'/><method name='Quit'/>"
    "<property name='CanQuit' type='b' access='read'/><property name='CanRaise' type='b' access='read'/>"
    "<property name='HasTrackList' type='b' access='read'/><property name='Identity' type='s' access='read'/>"
    "<property name='DesktopEntry' type='s' access='read'/><property name='SupportedUriSchemes' type='as' "
    "access='read'/>"
    "<property name='SupportedMimeTypes' type='as' access='read'/></interface>"
    "<interface name='org.mpris.MediaPlayer2.Player'>"
    "<method name='Play'/><method name='Pause'/><method name='PlayPause'/><method name='Stop'/><method "
    "name='Next'/><method name='Previous'/>"
    "<method name='Seek'><arg type='x' direction='in'/></method>"
    "<method name='SetPosition'><arg type='o' direction='in'/><arg type='x' direction='in'/></method>"
    "<method name='OpenUri'><arg type='s' direction='in'/></method><signal name='Seeked'><arg type='x'/></signal>"
    "<property name='PlaybackStatus' type='s' access='read'/><property name='Metadata' type='a{sv}' access='read'/>"
    "<property name='Position' type='x' access='read'/><property name='Rate' type='d' access='readwrite'/>"
    "<property name='Volume' type='d' access='readwrite'/><property name='MinimumRate' type='d' access='read'/>"
    "<property name='MaximumRate' type='d' access='read'/><property name='CanGoNext' type='b' access='read'/>"
    "<property name='CanGoPrevious' type='b' access='read'/><property name='CanPlay' type='b' access='read'/>"
    "<property name='CanPause' type='b' access='read'/><property name='CanSeek' type='b' access='read'/>"
    "<property name='CanControl' type='b' access='read'/></interface></node>";

static double media_number(JSCValue *v, const char *key) {
    JSCValue *p = jsc_value_object_get_property(v, key);
    double n = jsc_value_to_double(p);
    g_object_unref(p);
    return n;
}
static char *media_text(JSCValue *v, const char *key) {
    JSCValue *p = jsc_value_object_get_property(v, key);
    char *s = jsc_value_to_string(p);
    g_object_unref(p);
    if (!s || !g_utf8_validate(s, -1, NULL)) {
        g_free(s);
        return g_strdup("");
    }
    char *bounded = g_utf8_substring(s, 0, MIN(512, g_utf8_strlen(s, -1)));
    g_free(s);
    return bounded;
}
static void media_reset(void) {
    M.available = M.playing = M.seekable = FALSE;
    M.position = M.duration = 0;
    g_clear_pointer(&M.track, g_free);
    if (M.owner) {
        g_bus_unown_name(M.owner);
        M.owner = 0;
    }
}
static void media_snapshot(GObject *view, GAsyncResult *result, gpointer data) {
    M.pending = FALSE;
    GError *error = NULL;
    JSCValue *value = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(view), result, &error);
    if (GPOINTER_TO_UINT(data) != M.generation || !media_in_scope()) {
        g_clear_object(&value);
        g_clear_error(&error);
        return;
    }
    if (error || !value || !jsc_value_is_object(value) || !media_number(value, "available"))
        media_reset();
    else {
        M.available = TRUE;
        M.volume = media_number(value, "volume"); M.rate = media_number(value, "rate");
        M.playing = media_number(value, "playing") != 0;
        M.seekable = media_number(value, "seekable") != 0;
        M.position = (gint64)media_number(value, "position");
        M.duration = (gint64)media_number(value, "duration");
        char *title = media_text(value, "title"), *artist = media_text(value, "artist");
        if (!M.track || g_strcmp0(title, M.title) || g_strcmp0(artist, M.artist)) {
            g_free(M.track);
            M.track = g_strdup_printf("/org/arcticlinux/track/t%" G_GUINT64_FORMAT, ++M.track_serial);
        }
        g_free(M.title); g_free(M.artist);
        M.title = title; M.artist = artist;
        if (!M.owner && M.bus) {
            const char *last = strrchr(S.cfg.app_id, '.');
            char *name = g_strdup_printf("org.mpris.MediaPlayer2.Arctic_%s", last ? last + 1 : S.cfg.app_id);
            M.owner = g_bus_own_name_on_connection(M.bus, name, G_BUS_NAME_OWNER_FLAGS_NONE, NULL, NULL, NULL, NULL);
            g_free(name);
        }
        media_changed();
    }
    g_clear_object(&value);
    g_clear_error(&error);
}
static gboolean media_poll(gpointer data) {
    (void)data;
    if (!media_in_scope()) {
        media_reset();
        return G_SOURCE_CONTINUE;
    }
    if (M.pending)
        return G_SOURCE_CONTINUE;
    M.pending = TRUE;
    char *script = g_strdup_printf(
        "%sif(!e)return {available:0};const m=navigator.mediaSession?.metadata;"
        "const us=n=>Number.isFinite(n)?Math.max(0,Math.min(n,86400000))*1e6:0;"
        "return "
        "{available:1,playing:!e.paused&&!e.ended?1:0,seekable:Number.isFinite(e.duration)&&e.seekable.length>0?1:0,"
        "volume:e.volume,rate:e.playbackRate,position:us(e.currentTime),duration:us(e.duration),title:String(m?.title||document.title).slice(0,512),"
        "artist:String(m?.artist||'').slice(0,512)};})()",
        media_prefix);
    webkit_web_view_evaluate_javascript(S.view, script, -1, "arctic-media", NULL, NULL, media_snapshot,
                                        GUINT_TO_POINTER(M.generation));
    g_free(script);
    return G_SOURCE_CONTINUE;
}
static void media_start(void) {
    M.bus = g_application_get_dbus_connection(G_APPLICATION(S.app));
    if (!M.bus)
        return;
    M.node = g_dbus_node_info_new_for_xml(media_xml, NULL);
    M.root_id = g_dbus_connection_register_object(M.bus, "/org/mpris/MediaPlayer2", M.node->interfaces[0],
                                                  &media_vtable, NULL, NULL, NULL);
    M.player_id = g_dbus_connection_register_object(M.bus, "/org/mpris/MediaPlayer2", M.node->interfaces[1],
                                                    &media_vtable, NULL, NULL, NULL);
    if (M.root_id && M.player_id)
        M.timer = g_timeout_add_seconds(2, media_poll, NULL);
}
static void media_stop(void) {
    M.generation++;
    media_reset();
    if (M.timer)
        g_source_remove(M.timer);
    if (M.root_id)
        g_dbus_connection_unregister_object(M.bus, M.root_id);
    if (M.player_id)
        g_dbus_connection_unregister_object(M.bus, M.player_id);
    g_clear_pointer(&M.node, g_dbus_node_info_unref);
    g_clear_pointer(&M.title, g_free);
    g_clear_pointer(&M.artist, g_free);
    M.bus = NULL;
}
