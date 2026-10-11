/* Hosted real GTK semantics, not a browser timing benchmark. */
#include <gtk/gtk.h>
#include <string.h>
const struct {
  const char *action_and_target;
  const char *accelerators[9];
} accels [] = {
  /* Page Menu accels */
  { "win.page-menu", { "F10", NULL } },
  { "win.new-tab", { "<Primary>T", NULL } },
  { "win.open", { "<Primary>O", NULL } },
  { "win.save-as", { "<Primary>S", NULL } },
  { "win.save-as-application", { "<shift><Primary>A", NULL } },
  { "win.screenshot", { "<shift><Primary>S", NULL } },
  { "win.undo", { "<Primary>Z", NULL } },
  { "win.redo", { "<shift><Primary>Z", NULL } },
  { "win.copy", { "<Primary>C", NULL } },
  { "win.cut", { "<Primary>X", NULL } },
  { "win.paste", { "<Primary>V", NULL } },
  { "win.paste-as-plain-text", { "<shift><Primary>V", NULL } },
  { "win.zoom-in", { "<Primary>plus", "<Primary>KP_Add", "<Primary>equal", "ZoomIn", NULL } },
  { "win.zoom-out", { "<Primary>minus", "<Primary>KP_Subtract", "ZoomOut", NULL } },
  { "win.zoom-normal", { "<Primary>0", "<Primary>KP_0", NULL } },
  { "win.print", { "<Primary>P", NULL } },
  { "win.find", { "<Primary>F", NULL } },
  { "win.find-prev", { "<shift><Primary>G", NULL } },
  { "win.find-next", { "<Primary>G", NULL } },
  { "win.bookmark-page", { "<Primary>D", "AddFavorite", NULL } },
  { "win.add-search-engine", { NULL } },
  { "win.bookmarks", { "<alt><Primary>D", NULL } },
  { "win.show-downloads", { "<shift><Primary>Y", NULL } },
  { "win.encoding", { NULL } },
  { "win.page-source", { "<Primary>U", NULL } },
  { "win.toggle-inspector", { "<shift><Primary>I", "F12", NULL } },
  { "win.toggle-reader-mode", { "<alt><Primary>r", NULL } },

  { "win.select-all", { "<Primary>A", NULL } },

  { "win.send-to", { "Send", NULL } },
  { "win.location", { "<Primary>L", "<alt>D", "F6", "Go", "OpenURL", NULL } },
  { "win.location-search", {"<Primary>K", NULL} },
  { "win.home", { "<alt>Home", NULL } },
  { "win.tabs-view", { "<shift><Primary>O", NULL } },

  /* Toggle actions */
  { "win.browse-with-caret", { "F7", NULL } },
  { "win.fullscreen", { "F11", NULL } },

  /* Navigation */
  { "toolbar.stop", { "Escape", "Stop", NULL } },
  { "toolbar.reload", { "<Primary>R", "F5", "Refresh", "Reload", NULL } },
  { "toolbar.reload-bypass-cache", { "<shift><Primary>R", "<shift>F5" } },
  { "toolbar.combined-stop-reload", { NULL } },

  /* Tabs */
  { "tab.duplicate", { "<shift><Primary>K", NULL } },
  { "tab.close", { "<Primary>W", NULL } },
  { "tab.mute", { "<Primary>M", NULL } },
  { "tab.pin", { NULL } }
}, accels_navigation_ltr [] = {
  { "toolbar.navigation-back", { "<alt>Left", "<alt>KP_Left", "<alt>KP_4", "Back", NULL } },
  { "toolbar.navigation-forward", { "<alt>Right", "<alt>KP_Right", "<alt>KP_6", "Forward", NULL } }
}, accels_navigation_rtl [] = {
  { "toolbar.navigation-back", { "<alt>Right", "<alt>KP_Right", "<alt>KP_6", "Back", NULL } },
  { "toolbar.navigation-forward", { "<alt>Left", "<alt>KP_Left", "<alt>KP_4", "Forward", NULL } }
}, *accels_navigation_ltr_rtl;


static guint setter_calls;
static void counted_setter(GtkApplication *app,const char *name,const char *const *values) {
  setter_calls++;
  gtk_application_set_accels_for_action(app,name,values);
}
#define gtk_application_set_accels_for_action counted_setter
static void defaults(GtkApplication *app) {guint i;
  /* Defaults belong to the application, not to individual windows. */
  if (!g_object_get_data (G_OBJECT (app),
                          "ephy-window-default-accelerators-registered-50-6")) {
    for (i = 0; i < G_N_ELEMENTS (accels); i++) {
      gtk_application_set_accels_for_action (GTK_APPLICATION (app),
                                             accels[i].action_and_target,
                                             accels[i].accelerators);
    }
    g_object_set_data (G_OBJECT (app),
                       "ephy-window-default-accelerators-registered-50-6",
                       GINT_TO_POINTER (TRUE));
  }

  accels_navigation_ltr_rtl = gtk_widget_get_default_direction () == GTK_TEXT_DIR_LTR ?
                              accels_navigation_ltr : accels_navigation_rtl;
  for (i = 0; i < G_N_ELEMENTS (accels_navigation_ltr); i++) {
    gtk_application_set_accels_for_action (GTK_APPLICATION (app),
                                           accels_navigation_ltr_rtl[i].action_and_target,
                                           accels_navigation_ltr_rtl[i].accelerators);
  }
}
#undef gtk_application_set_accels_for_action
static void equal_accels(GtkApplication *app,const char *name,const char *const *expected) {
  char **actual=gtk_application_get_accels_for_action(app,name);
  guint i;
  for(i=0;expected[i]&&actual[i];i++) {
    guint a,b;GdkModifierType am,bm;
    g_assert_true(gtk_accelerator_parse(actual[i],&a,&am));
    g_assert_true(gtk_accelerator_parse(expected[i],&b,&bm));
    g_assert_cmpuint(a,==,b);g_assert_cmpuint(am,==,bm);
  }
  g_assert_null(expected[i]);g_assert_null(actual[i]);g_strfreev(actual);
}
static GtkApplication *application(const char *id) {
  GtkApplication *app=gtk_application_new(id,G_APPLICATION_NON_UNIQUE);
  GError *error=NULL;g_assert_true(g_application_register(G_APPLICATION(app),NULL,&error));
  g_assert_no_error(error);return app;
}
static void action(GSimpleAction *action,GVariant *parameter,gpointer data) {
  (void)action;(void)parameter;(*(guint *)data)++;
}
static void window_action(GtkWidget *window,guint *counter) {
  GSimpleActionGroup *group=g_simple_action_group_new();
  GSimpleAction *a=g_simple_action_new("new-tab",NULL);
  g_signal_connect(a,"activate",G_CALLBACK(action),counter);
  g_action_map_add_action(G_ACTION_MAP(group),G_ACTION(a));
  gtk_widget_insert_action_group(window,"win",G_ACTION_GROUP(group));
  g_object_unref(a);g_object_unref(group);
}
int main(void) {
  gtk_init();gtk_widget_set_default_direction(GTK_TEXT_DIR_LTR);
  GtkApplication *one=application("org.arctic.AcceleratorControl.One");
  GtkApplication *two=application("org.arctic.AcceleratorControl.Two");
  GtkWidget *first=gtk_application_window_new(one);guint first_count=0,second_count=0;
  defaults(one);g_assert_cmpuint(setter_calls,==,45);
  for(guint i=0;i<G_N_ELEMENTS(accels);i++)equal_accels(one,accels[i].action_and_target,accels[i].accelerators);
  window_action(first,&first_count);
  GtkWidget *second=gtk_application_window_new(one);defaults(one);
  g_assert_cmpuint(setter_calls,==,47);
  window_action(second,&second_count);
  g_assert_true(gtk_widget_activate_action(first,"win.new-tab",NULL));
  g_assert_true(gtk_widget_activate_action(second,"win.new-tab",NULL));
  g_assert_cmpuint(first_count,==,1);g_assert_cmpuint(second_count,==,1);
  gtk_widget_set_default_direction(GTK_TEXT_DIR_RTL);defaults(one);
  g_assert_cmpuint(setter_calls,==,49);
  for(guint i=0;i<G_N_ELEMENTS(accels_navigation_rtl);i++)equal_accels(one,accels_navigation_rtl[i].action_and_target,accels_navigation_rtl[i].accelerators);
  gtk_widget_set_default_direction(GTK_TEXT_DIR_LTR);defaults(one);g_assert_cmpuint(setter_calls,==,51);
  defaults(two);g_assert_cmpuint(setter_calls,==,96);
  const char *remap[]={"F13",NULL},*empty[]={NULL};
  gtk_application_set_accels_for_action(one,"app.preferences",remap);
  gtk_application_set_accels_for_action(one,"app.webextension-command-guid-command",remap);
  defaults(one);equal_accels(one,"app.preferences",remap);
  equal_accels(one,"app.webextension-command-guid-command",remap);
  gtk_application_set_accels_for_action(one,"app.webextension-command-guid-command",empty);
  defaults(one);equal_accels(one,"app.webextension-command-guid-command",empty);
  /* Explicit foreign default mutation policy, not an equivalence claim. */
  gtk_application_set_accels_for_action(one,"win.new-tab",remap);defaults(one);equal_accels(one,"win.new-tab",remap);
  gtk_window_destroy(GTK_WINDOW(first));gtk_window_destroy(GTK_WINDOW(second));
  g_object_unref(one);g_object_unref(two);
  GtkApplication *fresh=application("org.arctic.AcceleratorControl.Fresh");
  guint before=setter_calls;defaults(fresh);g_assert_cmpuint(setter_calls,==,before+45);
  g_object_unref(fresh);
  g_print("HOSTED_REAL_GTK_GETTER_WINDOW_ACTION_GROUP_DIRECTION_DYNAMIC_DEFAULT_CONTROL_PASS\n");
  return 0;
}
