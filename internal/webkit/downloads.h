//go:build cgo && webkit

/* Included by shim.c. Rows own downloads until dismissed or the window is destroyed. */
typedef struct {
    WebKitDownload *download;
    GtkWidget *row, *label, *progress, *cancel, *open, *show;
    GCancellable *dialog;
    gboolean failed, finished;
} DownloadRow;

static void download_row_free(gpointer data) {
    DownloadRow *r = data;
    g_object_set_data(G_OBJECT(r->download), "arctic-failed", GINT_TO_POINTER(1));
    g_cancellable_cancel(r->dialog);
    g_signal_handlers_disconnect_by_data(r->download, r);
    if (!r->finished)
        webkit_download_cancel(r->download);
    g_object_unref(r->download);
    g_object_unref(r->dialog);
    g_free(r);
}

static void download_action_cb(GSimpleAction *a, GVariant *param, gpointer data) {
    (void)a;
    GFile *f = g_file_new_for_path(g_variant_get_string(param, NULL));
    GtkFileLauncher *l = gtk_file_launcher_new(f);
    if (GPOINTER_TO_INT(data))
        gtk_file_launcher_open_containing_folder(l, S.window, NULL, NULL, NULL);
    else
        gtk_file_launcher_launch(l, S.window, NULL, NULL, NULL);
    g_object_unref(l);
    g_object_unref(f);
}

static void download_open_cb(GtkButton *button, gpointer data) {
    DownloadRow *r = data;
    const char *dest = webkit_download_get_destination(r->download);
    if (!dest || r->failed || !r->finished)
        return;
    GVariant *target = g_variant_ref_sink(g_variant_new_string(dest));
    download_action_cb(NULL, target, GINT_TO_POINTER(GTK_WIDGET(button) == r->show));
    g_variant_unref(target);
}

static void download_cancel_cb(GtkButton *button, gpointer data) {
    (void)button;
    DownloadRow *r = data;
    if (r->finished) {
        gtk_box_remove(GTK_BOX(S.download_list), r->row);
        return;
    }
    g_cancellable_cancel(r->dialog);
    webkit_download_cancel(r->download);
}

static void download_progress_cb(WebKitDownload *d, GParamSpec *ps, gpointer data) {
    (void)ps;
    DownloadRow *r = data;
    WebKitURIResponse *response = webkit_download_get_response(d);
    if (response && webkit_uri_response_get_content_length(response))
        gtk_progress_bar_set_fraction(GTK_PROGRESS_BAR(r->progress), webkit_download_get_estimated_progress(d));
    else
        gtk_progress_bar_pulse(GTK_PROGRESS_BAR(r->progress));
}

static void download_failed_cb(WebKitDownload *d, GError *err, gpointer data) {
    (void)d;
    DownloadRow *r = data;
    r->failed = TRUE;
    g_object_set_data(G_OBJECT(d), "arctic-failed", GINT_TO_POINTER(1));
    g_cancellable_cancel(r->dialog);
    gboolean cancelled = g_error_matches(err, WEBKIT_DOWNLOAD_ERROR, WEBKIT_DOWNLOAD_ERROR_CANCELLED_BY_USER);
    gtk_progress_bar_set_text(GTK_PROGRESS_BAR(r->progress), cancelled ? "Cancelled" : "Download failed");
    gtk_progress_bar_set_show_text(GTK_PROGRESS_BAR(r->progress), TRUE);
    if (cancelled)
        return;
    GNotification *n = g_notification_new("Download failed");
    g_notification_set_body(n, "Open Downloads in the app to review the transfer.");
    g_application_send_notification(G_APPLICATION(S.app), "download-failed", n);
    g_object_unref(n);
}

static void download_finished_cb(WebKitDownload *d, gpointer data) {
    DownloadRow *r = data;
    r->finished = TRUE;
    gtk_button_set_label(GTK_BUTTON(r->cancel), "Dismiss");
    const char *dest = webkit_download_get_destination(d);
    if (r->failed || !dest)
        return;
    gtk_progress_bar_set_fraction(GTK_PROGRESS_BAR(r->progress), 1);
    gtk_widget_set_visible(r->open, TRUE);
    gtk_widget_set_visible(r->show, TRUE);
    goDownloadFinished(S.cfg.handle, (char *)dest);
    char *name = g_path_get_basename(dest);
    GNotification *n = g_notification_new("Download finished");
    g_notification_set_body(n, name);
    g_notification_set_default_action_and_target(n, "app.download-show", "s", dest);
    g_notification_add_button_with_target(n, "Open", "app.download-open", "s", dest);
    g_notification_add_button_with_target(n, "Show in folder", "app.download-show", "s", dest);
    char *tag = g_strdup_printf("download-%s", name);
    g_application_send_notification(G_APPLICATION(S.app), tag, n);
    g_free(tag);
    g_free(name);
    g_object_unref(n);
}

/* The asynchronous completion owns a download reference, never a borrowed row pointer. */
static void save_download_cb(GObject *dialog, GAsyncResult *result, gpointer data) {
    WebKitDownload *d = data;
    GError *error = NULL;
    GFile *file = gtk_file_dialog_save_finish(GTK_FILE_DIALOG(dialog), result, &error);
    if (file) {
        char *path = g_file_get_path(file);
        if (path && !g_object_get_data(G_OBJECT(d), "arctic-failed")) {
            /* WebKit's no-overwrite check protects a file created after the chooser opened. */
            webkit_download_set_destination(d, path);
        } else
            webkit_download_cancel(d);
        g_free(path);
        g_object_unref(file);
    } else
        webkit_download_cancel(d);
    g_clear_error(&error);
    g_object_unref(d);
}

static gboolean decide_destination_cb(WebKitDownload *d, const char *suggested, gpointer data) {
    DownloadRow *r = data;
    WebKitURIResponse *resp = webkit_download_get_response(d);
    const char *mime = resp ? webkit_uri_response_get_mime_type(resp) : NULL;
    char *path = goDownloadDestination(S.cfg.handle, (char *)(suggested ? suggested : ""), (char *)(mime ? mime : ""));
    if (!path) {
        webkit_download_cancel(d);
        return TRUE;
    }
    char *name = g_path_get_basename(path);
    gtk_label_set_text(GTK_LABEL(r->label), name);
    webkit_download_set_allow_overwrite(d, FALSE);
    if (S.cfg.ask_download) {
        GtkFileDialog *dialog = gtk_file_dialog_new();
        gtk_file_dialog_set_title(dialog, "Save download as a new file");
        gtk_file_dialog_set_initial_name(dialog, name);
        char *dir = g_path_get_dirname(path);
        GFile *folder = g_file_new_for_path(dir);
        gtk_file_dialog_set_initial_folder(dialog, folder);
        gtk_file_dialog_save(dialog, S.window, r->dialog, save_download_cb, g_object_ref(d));
        g_object_unref(folder);
        g_object_unref(dialog);
        g_free(dir);
    } else
        webkit_download_set_destination(d, path);
    g_free(name);
    free(path);
    return TRUE;
}

static void download_started_cb(WebKitNetworkSession *s, WebKitDownload *d, gpointer data) {
    (void)s;
    (void)data;
    if (!S.download_list) {
        webkit_download_cancel(d);
        return;
    }
    DownloadRow *r = g_new0(DownloadRow, 1);
    r->download = g_object_ref(d);
    r->dialog = g_cancellable_new();
    r->row = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_widget_set_margin_start(r->row, 12);
    gtk_widget_set_margin_end(r->row, 12);
    gtk_widget_set_margin_top(r->row, 6);
    gtk_widget_set_margin_bottom(r->row, 6);
    GtkWidget *actions = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    r->label = gtk_label_new("Download");
    gtk_label_set_ellipsize(GTK_LABEL(r->label), PANGO_ELLIPSIZE_MIDDLE);
    gtk_widget_set_hexpand(r->label, TRUE);
    r->progress = gtk_progress_bar_new();
    r->cancel = gtk_button_new_with_label("Cancel");
    r->open = gtk_button_new_with_label("Open");
    r->show = gtk_button_new_with_label("Show in folder");
    gtk_widget_set_visible(r->open, FALSE);
    gtk_widget_set_visible(r->show, FALSE);
    gtk_box_append(GTK_BOX(r->row), r->label);
    gtk_box_append(GTK_BOX(r->row), r->progress);
    gtk_box_append(GTK_BOX(r->row), actions);
    gtk_box_append(GTK_BOX(actions), r->cancel);
    gtk_box_append(GTK_BOX(actions), r->open);
    gtk_box_append(GTK_BOX(actions), r->show);
    g_signal_connect(r->cancel, "clicked", G_CALLBACK(download_cancel_cb), r);
    g_signal_connect(r->open, "clicked", G_CALLBACK(download_open_cb), r);
    g_signal_connect(r->show, "clicked", G_CALLBACK(download_open_cb), r);
    g_object_set_data_full(G_OBJECT(r->row), "download", r, download_row_free);
    gtk_box_append(GTK_BOX(S.download_list), r->row);
    gtk_revealer_set_reveal_child(GTK_REVEALER(S.downloads), TRUE);
    g_signal_connect(d, "decide-destination", G_CALLBACK(decide_destination_cb), r);
    g_signal_connect(d, "failed", G_CALLBACK(download_failed_cb), r);
    g_signal_connect(d, "finished", G_CALLBACK(download_finished_cb), r);
    g_signal_connect(d, "notify::estimated-progress", G_CALLBACK(download_progress_cb), r);
}
