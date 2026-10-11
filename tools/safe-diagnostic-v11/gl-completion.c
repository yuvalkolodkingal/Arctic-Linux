/* Disposable diagnostic only. No product renderer selection or log output.
 * x86_64 little-endian ABI: Python <8sII16sIIQQQQQQIIQQQQQQ>, exactly 144 bytes.
 * Only the inode/PID/start-ticks-authenticated target gets glFinish after glFlush.
 * Other executables, fork children and invalid counters remain pass-through.
 * Coherent reader: active(92)==0, sequence(128), raw144, active(92)==0,
 * sequence(128); accept only all three equal sequences and raw active==0.
 * The reader may make four immediate attempts, without waiting. Multiple GL
 * calls can be in flight; completed counts are subsets, never a <=1 gap claim.
 * Counts cover top-level calls only. Driver calls re-entering glFlush while a
 * real GL function executes pass through without counts or another glFinish.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define COUNTER_FD 198
#define MAX_COUNT UINT64_C(9223372036854775807)

#ifndef __x86_64__
#error "this diagnostic ABI is x86_64 only"
#endif
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "counter needs little endian");

struct counters {
    unsigned char magic[8];
    uint32_t version, bytes;
    unsigned char nonce[16];
    uint32_t uid, pid;
    uint64_t start_ticks, exe_dev, exe_ino, caller_dev, caller_ino, return_offset;
    _Atomic uint32_t state;
    _Atomic uint32_t active_writers;
    _Atomic uint64_t flush_calls, finish_calls, scene_flush_calls, scene_finish_calls;
    _Atomic uint64_t sequence;
    uint64_t reserved;
};

_Static_assert(sizeof(struct counters) == 144, "counter ABI size");
_Static_assert(offsetof(struct counters, nonce) == 16, "counter nonce ABI");
_Static_assert(offsetof(struct counters, uid) == 32, "counter UID ABI");
_Static_assert(offsetof(struct counters, start_ticks) == 40, "counter process ABI");
_Static_assert(offsetof(struct counters, state) == 88, "counter state ABI");
_Static_assert(offsetof(struct counters, active_writers) == 92, "counter writer ABI");
_Static_assert(offsetof(struct counters, flush_calls) == 96, "counter value ABI");
_Static_assert(offsetof(struct counters, scene_finish_calls) == 120, "counter final ABI");
_Static_assert(offsetof(struct counters, sequence) == 128, "counter generation ABI");
_Static_assert(offsetof(struct counters, reserved) == 136, "counter reserved ABI");
_Static_assert(__atomic_always_lock_free(8, 0), "counter needs lock-free 64-bit atomics");

static struct counters *record;
static unsigned char immutable[88];
static dev_t counter_dev;
static ino_t counter_ino;
static pid_t owner_pid;
static _Atomic uintptr_t scene_return;
static void (*next_flush)(void), (*next_finish)(void);
static pthread_once_t resolver_once = PTHREAD_ONCE_INIT;
static _Thread_local int resolving;
static _Thread_local int real_function_active;

void glFlush(void);

static uint64_t process_start_ticks(void) {
    char raw[4097], *tail, *save = NULL, *field, *end;
    int fd = open("/proc/self/stat", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 0;
    ssize_t bytes = read(fd, raw, sizeof(raw) - 1);
    close(fd);
    if (bytes <= 0 || bytes >= (ssize_t)sizeof(raw) - 1) return 0;
    raw[bytes] = 0;
    tail = strrchr(raw, ')');
    if (!tail) return 0;
    field = strtok_r(tail + 1, " ", &save);
    for (unsigned index = 3; index < 22 && field; index++)
        field = strtok_r(NULL, " ", &save);
    if (!field || !*field) return 0;
    errno = 0;
    uint64_t ticks = strtoull(field, &end, 10);
    return errno == 0 && *end == 0 ? ticks : 0;
}

static int valid_fd(struct stat *info) {
    return fstat(COUNTER_FD, info) == 0 && S_ISREG(info->st_mode) && info->st_size == 144
        && info->st_uid == getuid() && info->st_gid == getgid()
        && (info->st_mode & 07777) == 0600;
}

__attribute__((constructor)) static void arm_owned_target(void) {
    struct stat info, executable;
    if (sizeof(void *) != 8 || getuid() != geteuid() || getgid() != getegid() || !valid_fd(&info)) return;
    int fd = open("/proc/self/exe", O_PATH | O_CLOEXEC);
    if (fd < 0) return;
    int observed = fstat(fd, &executable);
    close(fd);
    if (observed != 0) return;
    struct counters *candidate = mmap(NULL, 144, PROT_READ | PROT_WRITE, MAP_SHARED, COUNTER_FD, 0);
    if (candidate == MAP_FAILED) return;
    unsigned nonce_bits = 0;
    for (unsigned index = 0; index < 16; index++) nonce_bits |= candidate->nonce[index];
    int valid = memcmp(candidate->magic, "ARCTGL11", 8) == 0 && candidate->version == 1
        && candidate->bytes == 144 && nonce_bits != 0 && candidate->uid == getuid()
        && candidate->pid == (uint32_t)getpid() && candidate->start_ticks != 0
        && candidate->start_ticks == process_start_ticks()
        && candidate->exe_dev == (uint64_t)executable.st_dev && candidate->exe_ino == (uint64_t)executable.st_ino
        && candidate->caller_ino != 0 && candidate->return_offset > 0 && candidate->return_offset < UINT64_C(16777216)
        && atomic_load_explicit(&candidate->sequence, memory_order_acquire) == 0
        && atomic_load_explicit(&candidate->active_writers, memory_order_acquire) == 0 && candidate->reserved == 0
        && atomic_load_explicit(&candidate->state, memory_order_acquire) == 0
        && atomic_load_explicit(&candidate->flush_calls, memory_order_relaxed) == 0
        && atomic_load_explicit(&candidate->finish_calls, memory_order_relaxed) == 0
        && atomic_load_explicit(&candidate->scene_flush_calls, memory_order_relaxed) == 0
        && atomic_load_explicit(&candidate->scene_finish_calls, memory_order_relaxed) == 0;
    if (!valid) { munmap(candidate, 144); return; }
    int flags = fcntl(COUNTER_FD, F_GETFD);
    /* Unarmed script/profile processes must retain both values for target exec. */
    if (flags < 0 || fcntl(COUNTER_FD, F_SETFD, flags | FD_CLOEXEC) < 0 || unsetenv("LD_PRELOAD") != 0) {
        munmap(candidate, 144); return;
    }
    record = candidate;
    memcpy(immutable, candidate, sizeof(immutable));
    counter_dev = info.st_dev;
    counter_ino = info.st_ino;
    owner_pid = getpid();
    atomic_store_explicit(&record->state, 1, memory_order_release);
}

static int still_owned(void) {
    struct stat info;
    return record && getpid() == owner_pid && valid_fd(&info)
        && info.st_dev == counter_dev && info.st_ino == counter_ino
        && memcmp(immutable, record, sizeof(immutable)) == 0 && record->reserved == 0;
}

static void resolve_functions(void) {
    resolving = 1;
    next_flush = (void (*)(void))dlsym(RTLD_NEXT, "glFlush");
    next_finish = (void (*)(void))dlsym(RTLD_NEXT, "glFinish");
    resolving = 0;
    if (!next_flush || next_flush == glFlush) _exit(72);
    if (still_owned()) {
        if (!next_finish || next_finish == glFlush || next_finish == next_flush) {
            atomic_store_explicit(&record->state, 3, memory_order_release);
            _exit(73);
        }
        atomic_store_explicit(&record->state, 2, memory_order_release);
    }
}

static void increment(_Atomic uint64_t *value) {
    uint64_t previous = atomic_load_explicit(value, memory_order_relaxed);
    for (unsigned attempt = 0; attempt < 4096; attempt++) {
        if (previous >= MAX_COUNT) break;
        if (atomic_compare_exchange_weak_explicit(value, &previous, previous + 1,
                                                  memory_order_acq_rel, memory_order_relaxed)) return;
    }
    atomic_store_explicit(&record->state, 3, memory_order_release);
}

static void count_group(int completed, int scene) {
    uint32_t previous = atomic_load_explicit(&record->active_writers, memory_order_acquire);
    for (unsigned attempt = 0; attempt < 4096; attempt++) {
        if (previous >= 64) break;
        if (!atomic_compare_exchange_weak_explicit(&record->active_writers, &previous, previous + 1,
                                                  memory_order_acq_rel, memory_order_relaxed)) continue;
        increment(completed ? &record->finish_calls : &record->flush_calls);
        if (scene) increment(completed ? &record->scene_finish_calls : &record->scene_flush_calls);
        increment(&record->sequence);
        atomic_fetch_sub_explicit(&record->active_writers, 1, memory_order_release);
        return;
    }
    atomic_store_explicit(&record->state, 3, memory_order_release);
}

static int matches_scene(void *return_address) {
    uintptr_t cached = atomic_load_explicit(&scene_return, memory_order_relaxed);
    if (cached) return (uintptr_t)return_address == cached;
    Dl_info library;
    struct stat info;
    if (dladdr(return_address, &library) == 0 || !library.dli_fbase || !library.dli_fname
        || (uintptr_t)return_address < (uintptr_t)library.dli_fbase
        || (uintptr_t)return_address - (uintptr_t)library.dli_fbase != record->return_offset
        || stat(library.dli_fname, &info) != 0 || !S_ISREG(info.st_mode)
        || (uint64_t)info.st_dev != record->caller_dev || (uint64_t)info.st_ino != record->caller_ino) return 0;
    atomic_store_explicit(&scene_return, (uintptr_t)return_address, memory_order_relaxed);
    return 1;
}

void glFlush(void) {
    void *return_address = __builtin_return_address(0);
    if (resolving) _exit(74);
    if (pthread_once(&resolver_once, resolve_functions) != 0) _exit(75);
    if (real_function_active) { next_flush(); return; }
    int owned = still_owned() && atomic_load_explicit(&record->state, memory_order_acquire) == 2;
    int scene = owned && matches_scene(return_address);
    if (owned) {
        count_group(0, scene);
    }
    real_function_active = 1;
    next_flush();
    real_function_active = 0;
    if (!owned || !still_owned()) return;
    real_function_active = 1;
    next_finish();
    real_function_active = 0;
    if (!still_owned()) return;
    count_group(1, scene);
}
