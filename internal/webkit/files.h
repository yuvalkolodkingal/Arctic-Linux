//go:build cgo && webkit

/* Native asynchronous upload chooser. No page script can choose a filesystem path. */
static void upload_selected_cb(GObject *dialog, GAsyncResult *result, gpointer data) {
    WebKitFileChooserRequest *request = data;
    GError *error = NULL;
    GListModel *files = NULL;
    if (webkit_file_chooser_request_get_select_multiple(request))
        files = gtk_file_dialog_open_multiple_finish(GTK_FILE_DIALOG(dialog), result, &error);
    else {
        GFile *file = gtk_file_dialog_open_finish(GTK_FILE_DIALOG(dialog), result, &error);
        if (file) {
            GListStore *store = g_list_store_new(G_TYPE_FILE);
            g_list_store_append(store, file);
            g_object_unref(file);
            files = G_LIST_MODEL(store);
        }
    }
    GPtrArray *paths = g_ptr_array_new_with_free_func(g_free);
    if (files) {
        for (guint i = 0; i < g_list_model_get_n_items(files); i++) {
            GFile *file = g_list_model_get_item(files, i);
            char *path = g_file_get_path(file);
            if (path)
                g_ptr_array_add(paths, path);
            g_object_unref(file);
        }
        g_object_unref(files);
    }
    if (paths->len) {
        g_ptr_array_add(paths, NULL);
        webkit_file_chooser_request_select_files(request, (const char *const *)paths->pdata);
    } else
        webkit_file_chooser_request_cancel(request);
    g_ptr_array_unref(paths);
    g_clear_error(&error);
    g_object_unref(request);
}

static gboolean upload_requested_cb(WebKitWebView *view, WebKitFileChooserRequest *request, gpointer data) {
    (void)data;
    GtkFileDialog *dialog = gtk_file_dialog_new();
    gtk_file_dialog_set_title(dialog, "Choose files to upload");
    GtkFileFilter *filter = webkit_file_chooser_request_get_mime_types_filter(request);
    if (filter) {
        GListStore *filters = g_list_store_new(GTK_TYPE_FILE_FILTER);
        g_list_store_append(filters, filter);
        gtk_file_dialog_set_filters(dialog, G_LIST_MODEL(filters));
        g_object_unref(filters);
    }
    GtkRoot *root = gtk_widget_get_root(GTK_WIDGET(view));
    GtkWindow *parent = GTK_IS_WINDOW(root) ? GTK_WINDOW(root) : S.window;
    if (webkit_file_chooser_request_get_select_multiple(request))
        gtk_file_dialog_open_multiple(dialog, parent, NULL, upload_selected_cb, g_object_ref(request));
    else
        gtk_file_dialog_open(dialog, parent, NULL, upload_selected_cb, g_object_ref(request));
    g_object_unref(dialog);
    return TRUE;
}
