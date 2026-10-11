"""Compile the actual SceneFX submit function against finite GL/EGL controls.

Used by the RPM %check on its patched source tree. This proves source call
ordering and branch behavior; it does not simulate scanout or qualify an image.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


def submit_function(source):
    text = (source / 'render/fx_renderer/fx_pass.c').read_text()
    begin = text.index('static bool render_pass_submit(')
    end = text.index('\nstatic void render_pass_add_texture(', begin)
    return text[begin:end]


STUBS = r'''
#define _POSIX_C_SOURCE 200809L
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef int64_t GLint64;
typedef int EGLSyncKHR;
#define EGL_NO_SYNC_KHR 0
#define GL_GPU_DISJOINT_EXT 1
#define GL_TIMESTAMP_EXT 2
#define GL_FRAMEBUFFER 3
struct wlr_render_pass { int unused; };
struct wlr_egl { int unused; };
struct fx_renderer {
    struct wlr_egl *egl;
    struct { void (*glGetInteger64vEXT)(int, GLint64 *);
             void (*glQueryCounterEXT)(int, int); } procs;
};
struct fx_render_timer { int id; GLint64 gl_cpu_end; struct timespec cpu_end; };
struct fx_buffer { struct fx_renderer *renderer; void *buffer; };
struct fx_gles_render_pass {
    struct wlr_render_pass base; struct fx_buffer *buffer;
    struct fx_render_timer *timer; void *signal_timeline;
    int signal_point, prev_ctx, blur_padding_region;
    void *fx_offscreen_buffers;
};
static char events[128];
static int failure;
static void event(char c) { size_t n = strlen(events); if (n >= 126) abort(); events[n] = c; }
static struct fx_gles_render_pass *fx_get_render_pass(struct wlr_render_pass *p) {
    return (struct fx_gles_render_pass *)p;
}
static void push_fx_debug(struct fx_renderer *r) { (void)r; event('p'); }
static void pop_fx_debug(struct fx_renderer *r) { (void)r; event('q'); }
#define TRACY_BOTH_ZONES_START(x) ((void)(x))
#define TRACY_BOTH_ZONES_END ((void)0)
#define TRACY_GPU_ZONE_COLLECT(x) ((void)(x))
static void glFlush(void) { event('F'); }
static void glFinish(void) { event('Z'); }
static void glBindFramebuffer(int t, int f) { (void)t; (void)f; event('B'); }
static EGLSyncKHR wlr_egl_create_sync(struct wlr_egl *e, int fd) {
    (void)e; (void)fd; event('S'); return failure == 1 ? 0 : 1;
}
static int wlr_egl_dup_fence_fd(struct wlr_egl *e, EGLSyncKHR s) {
    (void)e; (void)s; event('D'); return failure == 2 ? -1 : 7;
}
static void wlr_egl_destroy_sync(struct wlr_egl *e, EGLSyncKHR s) { (void)e; (void)s; event('d'); }
static bool wlr_drm_syncobj_timeline_import_sync_file(void *t, int p, int fd) {
    (void)t; (void)p; (void)fd; event('I'); return failure != 3;
}
static int tracked_close(int fd) { (void)fd; event('c'); return 0; }
#define close tracked_close
static bool wlr_egl_restore_context(int *c) { (void)c; event('R'); return true; }
static void wlr_drm_syncobj_timeline_unref(void *t) { (void)t; event('U'); }
static void wlr_buffer_unlock(void *b) { (void)b; event('L'); }
static void pixman_region32_fini(int *r) { (void)r; event('i'); }
static void tracked_free(void *p) { (void)p; event('X'); }
#define free tracked_free
static void get_integer(int key, GLint64 *v) { (void)key; *v = 1; event('g'); }
static void query_counter(int id, int key) { (void)id; (void)key; event('t'); }
'''


MAIN = r'''
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    failure = atoi(argv[2]);
    struct wlr_egl egl = {0};
    struct fx_renderer renderer = {.egl = &egl, .procs = {get_integer, query_counter}};
    struct fx_buffer buffer = {.renderer = &renderer, .buffer = &buffer};
    struct fx_render_timer timer = {0};
    struct fx_gles_render_pass pass = {.buffer = &buffer,
        .signal_timeline = atoi(argv[1]) ? &buffer : NULL,
        .timer = atoi(argv[3]) ? &timer : NULL};
    bool ok = render_pass_submit(&pass.base);
    if (pass.fx_offscreen_buffers != NULL) return 3;
    printf("%s:%d\n", events, ok);
    return 0;
}
'''


class SubmitControls(unittest.TestCase):
    source = None

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        (root / 'submit.c').write_text(STUBS + submit_function(cls.source) + MAIN)
        cls.binary = root / 'submit'
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                        str(root / 'submit.c'), '-o', str(cls.binary)], check=True)

    def run_submit(self, selector=None, timeline=False, failure=0, timer=False):
        env = dict(os.environ)
        env.pop('WLR_RENDERER_FORCE_SOFTWARE', None)
        if selector is not None:
            env['WLR_RENDERER_FORCE_SOFTWARE'] = selector
        result = subprocess.run([str(self.binary), str(int(timeline)), str(failure), str(int(timer))],
                                env=env, check=True, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stderr, '')
        return result.stdout.strip()

    def test_forced_software_finishes_before_context_restore_and_buffer_unlock(self):
        self.assertEqual(self.run_submit('1'), 'pFZBqRULiX:1')

    def test_hardware_unset_zero_and_invalid_selectors_keep_the_original_flush_path(self):
        for selector in (None, '', '0', 'true', '01', '1 ', 'yes'):
            with self.subTest(selector=selector):
                self.assertEqual(self.run_submit(selector), 'pFBqRULiX:1')

    def test_signal_timeline_import_is_unchanged_even_when_software_is_forced(self):
        for selector in (None, '0', '1'):
            with self.subTest(selector=selector):
                self.assertEqual(self.run_submit(selector, timeline=True), 'pSDdIcBqRULiX:1')

    def test_all_original_timeline_failures_keep_failure_and_cleanup_order(self):
        for failure, expected in ((1, 'pSBqRULiX:0'), (2, 'pSDdBqRULiX:0'),
                                  (3, 'pSDdIcBqRULiX:0')):
            for selector in (None, '1'):
                with self.subTest(failure=failure, selector=selector):
                    self.assertEqual(self.run_submit(selector, timeline=True, failure=failure), expected)

    def test_timer_queries_precede_the_same_safe_completion(self):
        self.assertEqual(self.run_submit('1', timer=True), 'pgtgFZBqRULiX:1')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    options, remaining = parser.parse_known_args()
    SubmitControls.source = options.source
    unittest.main(argv=[__file__] + remaining)
