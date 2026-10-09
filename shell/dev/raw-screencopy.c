// Private frame fixture: preserve the compositor's native pixels without Grim's
// logical-output resampling. Protocol XML is MIT, Simon Ser, 2018.
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include "screencopy-client.h"

struct output { struct wl_output *object; char *name; };
static struct output outputs[16];
static size_t count;
static struct wl_shm *shm;
static struct zwlr_screencopy_manager_v1 *manager;
static uint32_t width, height, stride, flags, format;
static unsigned char *pixels;
static int done;

static void geometry(void *d, struct wl_output *o, int32_t x, int32_t y,
        int32_t pw, int32_t ph, int32_t sub, const char *make,
        const char *model, int32_t transform) {}
static void mode(void *d, struct wl_output *o, uint32_t f, int32_t w,
        int32_t h, int32_t refresh) {}
static void output_done(void *d, struct wl_output *o) {}
static void scale(void *d, struct wl_output *o, int32_t factor) {}
static void name(void *data, struct wl_output *o, const char *value) {
    struct output *output = data;
    free(output->name);
    output->name = strdup(value);
}
static void description(void *d, struct wl_output *o, const char *value) {}
static const struct wl_output_listener output_listener = {
    geometry, mode, output_done, scale, name, description
};
static void global(void *data, struct wl_registry *registry, uint32_t id,
        const char *interface, uint32_t version) {
    if (!strcmp(interface, wl_shm_interface.name)) {
        shm = wl_registry_bind(registry, id, &wl_shm_interface, 1);
    } else if (!strcmp(interface, zwlr_screencopy_manager_v1_interface.name)) {
        manager = wl_registry_bind(registry, id,
            &zwlr_screencopy_manager_v1_interface, 1);
    } else if (!strcmp(interface, wl_output_interface.name)) {
        assert(version >= 4 && count < 16);
        struct output *output = &outputs[count++];
        output->object = wl_registry_bind(registry, id, &wl_output_interface, 4);
        wl_output_add_listener(output->object, &output_listener, output);
    }
}
static void removed(void *data, struct wl_registry *registry, uint32_t id) {}
static const struct wl_registry_listener registry_listener = {global, removed};

static void buffer(void *data, struct zwlr_screencopy_frame_v1 *frame,
        uint32_t f, uint32_t w, uint32_t h, uint32_t s) {
    assert(!pixels && w > 0 && h > 0 && w <= 8192 && h <= 8192);
    assert(s >= w * 4 && (uint64_t)s * h < 64 * 1024 * 1024);
    fprintf(stderr, "native screencopy format=%#x width=%u height=%u stride=%u\n", f, w, h, s);
    assert(f == WL_SHM_FORMAT_XRGB8888 || f == WL_SHM_FORMAT_ARGB8888 ||
           f == WL_SHM_FORMAT_XBGR8888 || f == WL_SHM_FORMAT_ABGR8888);
    width = w; height = h; stride = s; format = f;
    size_t size = (size_t)stride * height;
    int fd = memfd_create("arctic-private-screencopy", MFD_CLOEXEC);
    assert(fd >= 0 && ftruncate(fd, size) == 0);
    pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    assert(pixels != MAP_FAILED);
    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
    struct wl_buffer *target = wl_shm_pool_create_buffer(pool, 0,
        width, height, stride, format);
    zwlr_screencopy_frame_v1_copy(frame, target);
    wl_shm_pool_destroy(pool);
    close(fd);
}
static void frame_flags(void *data, struct zwlr_screencopy_frame_v1 *frame,
        uint32_t value) { flags = value; }
static void ready(void *data, struct zwlr_screencopy_frame_v1 *frame,
        uint32_t hi, uint32_t lo, uint32_t ns) { done = 1; }
static void failed(void *data, struct zwlr_screencopy_frame_v1 *frame) {
    fputs("native screencopy failed\n", stderr);
    exit(1);
}
static const struct zwlr_screencopy_frame_v1_listener frame_listener = {
    buffer, frame_flags, ready, failed
};
int main(int argc, char **argv) {
    assert(argc == 3 && !strncmp(argv[1], "HEADLESS-", 9));
    struct wl_display *display = wl_display_connect(NULL);
    assert(display);
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    assert(wl_display_roundtrip(display) >= 0);
    assert(wl_display_roundtrip(display) >= 0 && shm && manager);
    struct wl_output *selected = NULL;
    for (size_t i = 0; i < count; i++) {
        if (outputs[i].name && !strcmp(outputs[i].name, argv[1])) {
            assert(!selected);
            selected = outputs[i].object;
        }
    }
    assert(selected);
    struct zwlr_screencopy_frame_v1 *frame =
        zwlr_screencopy_manager_v1_capture_output(manager, 0, selected);
    zwlr_screencopy_frame_v1_add_listener(frame, &frame_listener, NULL);
    while (!done) assert(wl_display_dispatch(display) >= 0);
    FILE *file = fopen(argv[2], "wb");
    assert(file && fprintf(file, "P6\n%u %u\n255\n", width, height) > 0);
    for (uint32_t y = 0; y < height; y++) {
        uint32_t row = (flags & ZWLR_SCREENCOPY_FRAME_V1_FLAGS_Y_INVERT) ? height - 1 - y : y;
        for (uint32_t x = 0; x < width; x++) {
            uint32_t pixel;
            memcpy(&pixel, pixels + row * stride + x * 4, sizeof(pixel));
            unsigned char rgb[] = {pixel >> 16, pixel >> 8, pixel};
            if (format == WL_SHM_FORMAT_XBGR8888 || format == WL_SHM_FORMAT_ABGR8888) {
                rgb[0] = pixel;
                rgb[2] = pixel >> 16;
            }
            assert(fwrite(rgb, 1, 3, file) == 3);
        }
    }
    assert(fclose(file) == 0);
    wl_display_disconnect(display);
    return 0;
}
