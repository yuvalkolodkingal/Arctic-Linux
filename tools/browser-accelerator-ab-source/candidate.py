"""Disabled experimental Epiphany50.6 accelerator change; not a product fix."""
import difflib
import hashlib

WINDOW_SHA256 = 'e89ce90f2df97f30e855e98723ee1040e1bbd71bbf05aada9a6898000bc1fa9a'
SPEC_SHA256 = '4e0f87ba947c53bc463d2f6ee38aee592c69b89f6a17f228a64f33c19bc18d51'
MARKER = 'ephy-window-default-accelerators-registered-50-6'
OLD = '''  for (i = 0; i < G_N_ELEMENTS (accels); i++) {
    gtk_application_set_accels_for_action (GTK_APPLICATION (app),
                                           accels[i].action_and_target,
                                           accels[i].accelerators);
  }
'''
NEW = '''  /* Defaults belong to the application, not to individual windows. */
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
'''


def patched_window(raw):
    if hashlib.sha256(raw).hexdigest() != WINDOW_SHA256 or raw.count(OLD.encode()) != 1:
        raise RuntimeError('candidate_source_binding')
    result = raw.replace(OLD.encode(), NEW.encode())
    if result.replace(NEW.encode(), OLD.encode()) != raw:
        raise RuntimeError('candidate_whole_inverse')
    return result


def window_patch(raw):
    patched = patched_window(raw)
    return ''.join(difflib.unified_diff(raw.decode().splitlines(keepends=True),
        patched.decode().splitlines(keepends=True), fromfile='a/src/ephy-window.c',
        tofile='b/src/ephy-window.c')).encode()


def candidate_spec(raw):
    before = b'Patch0:         epiphany-default-bookmarks.patch\n'
    after = before + b'Patch1:         arctic-accelerator-candidate.patch\n'
    if hashlib.sha256(raw).hexdigest() != SPEC_SHA256 or raw.count(before) != 1:
        raise RuntimeError('candidate_spec_binding')
    result = raw.replace(before, after)
    if result.replace(after, before) != raw:
        raise RuntimeError('candidate_spec_inverse')
    return result
