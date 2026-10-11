"""Strict bindings for one diagnostic; no image or release acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import base64
import select
import time
import zlib
import selectors
import signal
import sys

REPO = 'yuvalkolodkingal/Arctic-Linux'
BRANCH = 'codex/safe-rerender-v11-20261010'
MARKER = '.github/safe-rerender-v11-20261010.activate'
PREPARATION_BASE = 'd2b71de19fc77f37b031afd98349fb08287d8abb'
IMAGE = dict(source_sha='bc0521136520daaa221e815822e88ffc44107957',
             run_id=38032256030, artifact_id=11664120624,
             name='Arctic-Linux-1.2-candidate-38032256030-1-x86_64.iso',
             bytes=1929826304,
             sha256='0ab25cc921873ba8750042a6265b6a9e42e669cd78a08d6621c140fd18468609',
             archive_bytes=1930013330,
             archive_sha256='07d60353230eccd0b077279cf6195d73dc6a57f61d9cba3c55503776a76be716',
             producer_mode='frozen-external-paired-v1',
             producer_receipt_sha256='1695aa2af6ec0da618e87c5387a03f44752121111f0bbe6900699d9549b40994')
PAIRS = ('restored-desktop', 'terminal-initial', 'terminal-repaint')
ARMS = ('default-restart', 'completion-restart')

GL_COUNTER_FD = 198
GL_COUNTER_BYTES = 144
GL_COUNTER_FORMAT = '<8sII16sIIQQQQQQIIQQQQQQ'
GL_COUNTER_MAGIC = b'ARCTGL11'
GL_CALL_RETURN_OFFSET = 0x7d7d
GL_COUNTER_MAX = 2**63-1
GL_MANGO_SHA256 = '98582eccb610fc83282d1e64e975968aff2ddcfd5124d783a2bab78b98f681ca'
GL_SCENEFX_SHA256 = '972888a419d3c68dd0a10bd33b1bc9266d129dd3ec8f1c24cd7e9c273273f6a4'


def validate_gl_completion(value, identity, arm, ctx):
    """Closed, source-bound observations of the owned probe, never GL acceptance."""
    require(type(value) is dict and set(value)=={'schema','arm','pid','start_ticks','mode','binary','counter'}
            and value['schema']=='arctic-safe-gl-completion-v1' and value['arm']==arm and arm in ARMS,
            'GL completion observation fields differ')
    require(type(value['pid']) is int and type(value['start_ticks']) is int
            and value['pid']==identity['pid'] and value['start_ticks']==identity['start_ticks'],
            'GL completion process identity differs')
    if arm=='default-restart':
        require(value['mode']=='unmodified' and value['binary'] is None and value['counter'] is None,
                'Default GL completion arm was modified')
        return value
    require(value['mode']=='owned-gl-flush-finish' and type(value['binary']) is dict
            and set(value['binary'])=={'bytes','sha256','uid','gid','mode'}
            and type(value['binary']['bytes']) is int and 0<value['binary']['bytes']<=MAX_FILE
            and type(value['binary']['uid']) is int and value['binary']['uid']==0
            and type(value['binary']['gid']) is int and value['binary']['gid']==0
            and type(value['binary']['mode']) is int and value['binary']['mode']==0o644
            and value['binary']['sha256']==ctx['bundle']['gl-completion.so'],
            'Owned GL completion binary differs')
    record=value['counter']
    fields={'bytes','uid','gid','mode','device','inode','fd','binding_id','close_on_exec','state','active_writers','sequence',
            'target_device','target_inode','caller_device','caller_inode','return_offset',
            'total_flush','completed_finish','scenefx_flush','scenefx_finish','packet_sha256'}
    require(type(record) is dict and set(record)==fields and
            all(type(record[k]) is int and 0<=record[k]<2**64 for k in fields-{'binding_id','packet_sha256','close_on_exec'})
            and record['close_on_exec'] is True,
            'Owned GL completion counter fields differ')
    require(record['bytes']==GL_COUNTER_BYTES and record['uid']==record['gid']==1000
            and record['mode']==0o600 and record['fd']==GL_COUNTER_FD
            and record['device']>0 and record['inode']>0
            and record['binding_id']==ctx['binding_id'] and record['state']==2
            and record['active_writers']==0 and record['return_offset']==GL_CALL_RETURN_OFFSET
            and all(record[k]>0 for k in ('target_device','target_inode','caller_device','caller_inode'))
            and record['scenefx_finish']>0
            and record['scenefx_finish']<=record['scenefx_flush']<=record['total_flush']
            and record['scenefx_finish']<=record['completed_finish']<=record['total_flush']
            and 0<record['sequence']<=GL_COUNTER_MAX
            and record['sequence']==record['total_flush']+record['completed_finish']
            and all(record[k]<=GL_COUNTER_MAX for k in ('total_flush','completed_finish','scenefx_flush','scenefx_finish'))
            and type(record['packet_sha256']) is str and re.fullmatch('[0-9a-f]{64}',record['packet_sha256']),
            'Owned GL completion counter provenance differs')
    return value


def validate_gl_progress(initial, observations, identity, arm, ctx):
    require(type(observations) is list and len(observations)==2
            and all(type(v) is dict and set(v)=={'kind','observation'} for v in observations)
            and [v['kind'] for v in observations]==['after-idle','after-capture'],
            'GL completion observation order differs')
    previous=validate_gl_completion(initial,identity,arm,ctx)
    for entry in observations:
        current=validate_gl_completion(entry['observation'],identity,arm,ctx)
        if arm=='completion-restart':
            old,new=previous['counter'],current['counter']
            mutable={'state','active_writers','sequence','total_flush','completed_finish',
                     'scenefx_flush','scenefx_finish','packet_sha256'}
            require(previous['binary']==current['binary'] and
                    all(old[k]==new[k] for k in set(old)-mutable) and
                    all(new[k]>=old[k] for k in ('sequence','total_flush','completed_finish','scenefx_flush','scenefx_finish')),
                    'GL completion counter identity or progress differs')
        previous=current
    return observations

RENDERER_DEBUG_LITERALS = {
    'scenefx': ('render/fx_renderer/fx_renderer.c','Creating scenefx FX renderer'),
    'egl-software': ('render/egl.c','Using software rendering'),
    'egl-device-platform': ('render/egl.c','Using EGL_PLATFORM_DEVICE_EXT'),
    'egl-gbm-platform': ('render/egl.c','Using EGL_PLATFORM_GBM_KHR'),
    'allocator-drm-dumb': ('render/allocator/drm_dumb.c','Created DRM dumb allocator'),
    'allocator-shm': ('render/allocator/shm.c','Created shm allocator'),
    'drm-atomic': ('backend/drm/drm.c','Using atomic DRM interface'),
    'drm-forced-legacy': ('backend/drm/drm.c','WLR_DRM_NO_ATOMIC set, forcing legacy DRM interface'),
    'drm-fallback-legacy': ('backend/drm/drm.c','Atomic modesetting unsupported, using legacy DRM interface'),
}
RENDERER_DEBUG_MARKERS = (*RENDERER_DEBUG_LITERALS,'allocator-gbm')


def validate_renderer_debug(value, identity):
    require(type(value) is dict and set(value)=={'schema','pid','start_ticks','source','status','bytes',
            'sha256','renderer','source_markers'} and value['schema']=='arctic-safe-renderer-debug-v1',
            'Renderer debug fields differ')
    require(type(value['pid']) is int and type(value['start_ticks']) is int
            and value['pid']==identity['pid'] and value['start_ticks']==identity['start_ticks'],
            'Renderer debug process identity differs')
    require(value['source'] in ('mango-stderr-file','pid-journal') and value['status'] in ('observed','unavailable','privacy-rejected','unbound')
            and type(value['bytes']) is int and 0<=value['bytes']<=1024**2
            and (type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256'])
                 if value['status']=='observed' else value['bytes']==0 and value['sha256'] is None),
            'Renderer debug provenance differs')
    require(type(value['renderer']) is str and value['renderer'] in ('unknown','llvmpipe','softpipe','other')
            and type(value['source_markers']) is dict and set(value['source_markers'])==set(RENDERER_DEBUG_MARKERS)
            and all(type(v) is bool for v in value['source_markers'].values()),
            'Renderer debug marker schema differs')
    flags=value['source_markers']
    require(sum(flags[k] for k in ('drm-atomic','drm-forced-legacy','drm-fallback-legacy'))<=1
            and sum(flags[k] for k in ('allocator-gbm','allocator-drm-dumb','allocator-shm'))<=1
            and (value['status']=='observed' or value['renderer']=='unknown' and not any(flags.values())),
            'Renderer debug observations are ambiguous')
    return value


DISPLAY_DRIVERS = ('simple-framebuffer', 'simpledrm', 'virtio_gpu', 'bochs-drm',
                   'qxl', 'vmwgfx', 'i915', 'amdgpu', 'nouveau', 'vkms', 'unknown')
ALLOCATOR_MARKERS = ('drm-dumb', 'gbm', 'shm', 'atomic-drm', 'legacy-drm')


def validate_display_binding(value, identity):
    """Closed observations; a missing log marker never identifies an allocator."""
    require(type(value) is dict and set(value) == {'schema', 'pid', 'start_ticks',
            'kernel_release', 'devices', 'journal_status', 'source_log_markers'}
            and value['schema'] == 'arctic-safe-display-binding-v1',
            'Display binding fields differ')
    require(type(value['pid']) is int and type(value['start_ticks']) is int
            and value['pid'] == identity['pid'] and value['start_ticks'] == identity['start_ticks'],
            'Display binding process identity differs')
    require(type(value['kernel_release']) is str and
            re.fullmatch(r'[A-Za-z0-9_.+\-]{1,100}', value['kernel_release'])
            and value['journal_status'] in ('available', 'unavailable'),
            'Display binding observation status differs')
    require(type(value['devices']) is list and len(value['devices']) <= 32,
            'Display binding device inventory differs')
    names=[]
    for device in value['devices']:
        require(type(device) is dict and set(device) == {'node', 'major', 'minor', 'driver'}
                and type(device['node']) is str and re.fullmatch('(?:card|renderD)[0-9]{1,3}', device['node'])
                and type(device['major']) is int and device['major'] == 226
                and type(device['minor']) is int and 0 <= device['minor'] <= 255
                and type(device['driver']) is str and device['driver'] in DISPLAY_DRIVERS,
                'Display binding device descriptor differs')
        names.append(device['node'])
    require(names == sorted(set(names)), 'Display binding device ordering differs')
    require(type(value['source_log_markers']) is dict
            and set(value['source_log_markers']) == set(ALLOCATOR_MARKERS)
            and all(type(flag) is bool for flag in value['source_log_markers'].values())
            and (value['journal_status'] != 'unavailable' or not any(value['source_log_markers'].values())),
            'Display binding source marker fields differ')
    return value
EXECUTION_FILES = {
    '.github/workflows/safe-rerender-v11-20261010.yml',
    *('tools/safe-diagnostic-v11/' + n for n in
      ('common.py', 'host.py', 'guest.py', 'run.sh', 'screencopy.c', 'gl-completion.c')),
    'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py',
    'tools/native-functional/native_smoke.py', 'tools/native-functional/taskbar-runtime.py',
    'tools/lib/container.sh', 'tools/lib/vmtest.py', 'tools/lib/iso_startup.py',
    'shell/dev/wlr-screencopy-unstable-v1.xml'}
SOURCE_FILES = {
    'packaging/desktop/arctic-graphics.sh',
    'packaging/sddm-wayland-mango/sddm-compositor-mango',
    'packaging/mangowm.spec', 'packaging/patches/mango-software-renderer-dmabuf.patch',
    'iso/kiwi/grub-arctic.cfg.iso-template', 'tools/test-iso.sh',
    'tools/lib/vmtest.py', 'tools/lib/iso_startup.py'}
DIAGNOSTIC_FILES = {'.github/workflows/safe-rerender-v11-20261010.yml',
    *('tools/safe-diagnostic-v11/'+name for name in
      ('README.md','common.py','execution-manifest.json','guest.py','host.py',
       'run.sh','screencopy.c','test_diagnostic.py','gl-completion.c','test_gl_completion.py'))}
CI_PATH = '.github/workflows/ci.yml'
CI_ANCHOR = b'      - codex/safe-rerender-v7-20261010\n'
CI_ADDITION = b'      - codex/safe-rerender-v11-20261010\n'
PREPARATION_FILES = DIAGNOSTIC_FILES | {CI_PATH}

MAX_FILE = 32 * 1024**2
MAX_TOTAL = 128 * 1024**2
MAX_WIRE = 200 * 1024**2
CHUNK = 18 * 1024
STAGES = ('docker-prep', 'docker-vm', 'bootstrap-cd', 'python-driver')
HOST_PHASES = ('entry', 'root-kvm', 'context', 'image', 'libraries', 'vm-capture', 'complete')
EXCEPTION_CLASSES = {'RuntimeError', 'ValueError', 'TypeError', 'AssertionError', 'OSError',
                     'FileNotFoundError', 'FileExistsError', 'PermissionError', 'TimeoutExpired', 'KeyboardInterrupt',
                     'SystemExit', 'BrokenPipeError', 'OTHER'}


def exception_class(error):
    name = type(error).__name__
    return name if name in EXCEPTION_CLASSES else 'OTHER'


HANDOFF_PHASES = ('handoff-priority', 'handoff-wrapper-acquire', 'handoff-configuration-acquire',
    'handoff-reference-protection', 'handoff-reference-label', 'handoff-policy-restore',
    'handoff-wrapper-label', 'handoff-configuration-label', 'handoff-reference-copy-label',
    'handoff-label-check', 'handoff-owned-check', 'handoff-effective-config', 'handoff-owned-records',
    'handoff-pidfd', 'handoff-old-identity', 'handoff-service-restart', 'handoff-old-exit',
    'handoff-mango-discovery', 'handoff-new-identity', 'handoff-new-argv', 'handoff-new-env',
    'handoff-new-binary', 'handoff-new-maps', 'handoff-new-libraries', 'handoff-ipc-discovery',
    'handoff-output-command', 'handoff-output-parse', 'handoff-output-config',
    'handoff-output-selection', 'handoff-security-enforcing', 'handoff-session-prefix', 'handoff-session-identity',
    'handoff-session-vt', 'handoff-session-switch', 'handoff-session-active',
    'handoff-compositor-config', 'handoff-gl-completion', 'handoff-arm-report', 'handoff-arm-directory', 'handoff-idle-counter')
GUEST_PHASES = ('entry', 'context', 'bundle', 'native-import', 'native-guard',
    'boot-flags', 'desktop-discovery', 'mango-identity', 'renderer-environment',
    'renderer-maps', 'library-resolution', 'library-owner-query', 'drm-fds',
    'kernel-framebuffer', 'kernel-drm', 'existing-debugfs', 'renderer-journal',
    'monitor-query', 'output-validation', 'workspace', 'port-open', 'port-duplex',
    'package-query', 'selinux-before', 'hello-send', 'hello-ack', 'session-contract',
    'session-handoff', *HANDOFF_PHASES, 'arm-ready', 'arm-baseline', 'capture', 'export', 'complete')
GUEST_EXCEPTION_CLASSES = EXCEPTION_CLASSES | {'ImportError', 'ModuleNotFoundError',
    'UnicodeDecodeError', 'ProcessLookupError', 'NotADirectoryError'}
GUEST_STATUS_PREFIX = 'ARCTIC-SAFE-GUEST-STATUS='

# Only exact trusted-source literals can become a fixed primary identifier.
# No free-form message, errno, pathname, command output or exception repr leaves
# the guest. Unknown messages and subclasses remain unobserved.
HANDOFF_GUARDS = {
    'Owned GL completion contract differs': 'gl-contract',
    'Owned GL completion write was incomplete': 'gl-write-incomplete',
    'Owned GL completion architecture differs': 'gl-architecture',
    'Owned GL completion executable or caller differs': 'gl-executable-caller',
    'Owned GL completion mapping inode differs': 'gl-mapping-inode',
    'Owned GL completion library is not mapped': 'gl-library-unmapped',
    'Owned GL completion process descriptor differs': 'gl-process-descriptor',
    'Owned GL completion process descriptor changed during observation': 'gl-descriptor-changed',
    'Owned GL completion coherent packet unavailable': 'gl-coherent-packet',
    'Owned GL completion immutable header differs': 'gl-header',
    'Owned GL completion counter provenance differs': 'gl-counter-provenance',
    'Guest observation command failed or exceeded bound': 'command-failed-or-bound',
    'Trusted session file protection differs': 'trusted-file-protection',
    'SDDM configuration directory is a symlink': 'sddm-directory-symlink',
    'SDDM configuration directory protection differs': 'sddm-directory-protection',
    'SDDM defaults ambiguity differs': 'sddm-defaults-ambiguity',
    'Known SELinux context syntax required': 'selinux-label-syntax',
    'Trusted script changed before label handoff': 'reference-script-changed',
    'Original trusted script SELinux label differs': 'reference-policy-label',
    'Owned label handoff differs': 'owned-label-handoff',
    'Owned restart selector differs': 'owned-selector',
    'Owned override directory differs': 'owned-directory',
    'Owned override write was incomplete': 'owned-write-incomplete',
    'Owned override handoff inode differs': 'owned-retained-inode',
    'Owned override inode differs': 'owned-inode',
    'Owned override bytes differ': 'owned-bytes',
    'Higher-priority SDDM drop-in conflict': 'higher-priority-dropin',
    'Effective diagnostic SessionCommand differs': 'effective-session-command',
    'Old Mango changed before restart': 'old-mango-identity',
    'Original Mango did not end after owned service restart': 'old-mango-not-ended',
    'One new live Mango required': 'new-mango-count',
    'Fresh actual Mango identity required': 'new-mango-identity',
    'Restart Mango argv differs': 'new-mango-argv',
    'Actual restart renderer environment differs': 'new-renderer-environment',
    'Restart Mango binary differs': 'new-mango-binary',
    'Restart renderer maps exceed bound': 'new-maps-bound',
    'Restart mapped renderer library identities differ': 'new-library-identities',
    'Restart output configuration schema differs': 'new-output-schema',
    'Restart output configuration values differ': 'new-output-values',
    'Restart output configuration differs': 'new-output-configuration',
    'Restart selected output differs': 'new-output-selection',
    'Restart SELinux enforcement differs': 'new-security-enforcing',
    'Restart Mango and fresh IPC prefix session differ': 'new-ipc-session',
    'Restart login session identity differs': 'new-login-session',
    'Restart desktop VT differs': 'new-session-vt',
    'Restart bound Wayland session is not active': 'new-session-inactive',
    'New attested desktop readiness deadline': 'new-desktop-deadline',
    'Restart compositor configuration changed': 'new-compositor-config',
    'Observed Mango CPU identity differs': 'cpu-process-identity',
    'Aggregate CPU observation differs': 'cpu-aggregate',
    'Compositor configuration link is broken': 'config-broken-link',
    'Compositor configuration protection differs': 'config-protection',
}
HANDOFF_PRIMARY_IDS = frozenset(HANDOFF_GUARDS.values())
DISCOVERY_GUARDS = {'Fresh discovery process identity differs': 'discovery-process-identity', 'Fresh discovery session identifier differs': 'discovery-session-id', 'Fresh discovery user runtime differs': 'discovery-user-runtime', 'Fresh discovery runtime protection differs': 'discovery-runtime-protection', 'Fresh discovery socket inventory exceeds bound': 'discovery-inventory-bound', 'Fresh owned Wayland endpoint is unobserved or ambiguous': 'discovery-wayland-endpoint', 'Fresh owned Mango IPC endpoint differs': 'discovery-mango-endpoint', 'Fresh discovery child environment exceeds bound': 'discovery-child-env-bound', 'Fresh discovery desktop PATH or XDG_DATA_DIRS differs': 'discovery-path-xdg', 'Fresh discovery alternate IPC path differs': 'discovery-alternate-ipc', 'Fresh discovery socket node protection differs': 'discovery-socket-protection', 'Fresh discovery socket node changed': 'discovery-socket-changed', 'ambiguous Wayland session': 'native-wayland-ambiguous', 'ambiguous or absent actual Mango IPC signature': 'native-ipc-signature', 'missing desktop PATH/XDG_DATA_DIRS': 'native-path-xdg', 'requires exactly one non-root Mango desktop': 'native-mango-count'}
DISCOVERY_IDS = frozenset(DISCOVERY_GUARDS.values())
OUTPUT_FAILURE_ROLES = {
    'handoff-output-command': 'output-command',
    'handoff-output-parse': 'output-parse',
    'handoff-output-config': 'output-configuration',
    'handoff-output-selection': 'selected-output',
    'handoff-security-enforcing': 'selinux-enforcing',
}


def discovery_failure_id(error):
    if type(error) is not RuntimeError or len(error.args)!=1 or type(error.args[0]) is not str:
        return None
    return DISCOVERY_GUARDS.get(error.args[0])



def handoff_primary_id(error, phase):
    if phase not in ('session-handoff', *HANDOFF_PHASES) or type(error) is not RuntimeError:
        return None
    args=error.args
    return HANDOFF_GUARDS.get(args[0]) if len(args)==1 and type(args[0]) is str else None


def guest_exception_class(error):
    name = type(error).__name__
    return name if name in GUEST_EXCEPTION_CLASSES else 'OTHER'


def guest_status(phase, status, error, ctx, primary_id=None, last_discovery_id=None):
    ctx = context(ctx)
    require(type(phase) is str and phase in GUEST_PHASES and type(status) is str
            and status in ('completed', 'exception'), 'Guest fixed phase differs')
    require((phase == 'complete' and error is None) if status == 'completed'
            else (type(error) is str and error in GUEST_EXCEPTION_CLASSES),
            'Guest fixed exception class differs')
    require(primary_id is None or (type(primary_id) is str and primary_id in HANDOFF_PRIMARY_IDS
            and phase in ('session-handoff', *HANDOFF_PHASES) and status=='exception'
            and error=='RuntimeError'), 'Guest fixed primary identifier differs')
    require(last_discovery_id is None or (type(last_discovery_id) is str and last_discovery_id in DISCOVERY_IDS
            and phase=='handoff-ipc-discovery' and status=='exception' and error=='RuntimeError'
            and primary_id=='new-desktop-deadline'), 'Guest last discovery identifier differs')
    return dict(schema='arctic-safe-guest-fixed-stage-v4', binding_id=ctx['binding_id'],
        execution_sha=ctx['execution_sha'], image_source_sha=IMAGE['source_sha'],
        phase=phase, status=status, exception_class=error, primary_id=primary_id, last_discovery_id=last_discovery_id,
        failure_role=OUTPUT_FAILURE_ROLES.get(phase) if status == 'exception' else None, release_acceptance=False,
        image_qualified=False, performance_acceptance=False, observer_profile_admitted=False)


def validate_guest_status(value, ctx):
    require(type(value) is dict and set(value) == {'schema', 'binding_id', 'execution_sha',
        'image_source_sha', 'phase', 'status', 'exception_class', 'primary_id', 'last_discovery_id', 'failure_role', 'release_acceptance',
        'image_qualified', 'performance_acceptance', 'observer_profile_admitted'},
        'Guest fixed status fields differ')
    require(all(value[k] is False for k in ('release_acceptance','image_qualified',
        'performance_acceptance','observer_profile_admitted')), 'Guest fixed acceptance differs')
    expected = guest_status(value['phase'], value['status'], value['exception_class'], ctx, value['primary_id'], value['last_discovery_id'])
    require(value == expected, 'Guest fixed status binding differs')
    return value


def project_guest_status(raw, ctx):
    require(type(raw) is bytes and len(raw) <= MAX_FILE, 'Guest fixed serial bound differs')
    matches = [line[len(GUEST_STATUS_PREFIX):] for line in raw.decode('utf-8').splitlines()
               if line.startswith(GUEST_STATUS_PREFIX)]
    require(len(matches) <= 1, 'Guest fixed status is ambiguous')
    if not matches:
        return None
    require(len(matches[0].encode()) <= 2048, 'Guest fixed status exceeds bound')
    return validate_guest_status(strict(matches[0]), ctx)


def exclusive_json(path, value):
    """Owned new reports only; never replace or follow a preexisting path."""
    path = Path(path)
    require(path.parent.is_dir() and not path.parent.is_symlink(), 'Owned report directory differs')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as stream:
        stream.write((json.dumps(value, sort_keys=True, allow_nan=False)+'\n').encode())


def fixed_status(stage, status, exit_code, error, raw=None, cleanup_errors=None):
    require(stage in (*STAGES, *HOST_PHASES) and status in ('completed', 'exception', 'cleanup-exception'),
            'Fixed diagnostic stage differs')
    require(exit_code is None or type(exit_code) is int and 0 <= exit_code <= 255,
            'Fixed diagnostic exit status differs')
    require(error is None or error in EXCEPTION_CLASSES, 'Fixed diagnostic exception class differs')
    value = dict(schema='arctic-safe-fixed-stage-v1', stage=stage, status=status,
                 exit_code=exit_code, exception_class=error, release_acceptance=False,
                 image_qualified=False, performance_acceptance=False, observer_profile_admitted=False)
    if raw is not None:
        require(set(raw) == {'stdout','stderr'}, 'Private output inventory differs')
        for label, record in raw.items():
            require(set(record) == {'bytes','sha256','complete'} and type(record['bytes']) is int
                    and 0 <= record['bytes'] <= MAX_FILE and type(record['complete']) is bool
                    and type(record['sha256']) is str and re.fullmatch('[0-9a-f]{64}',record['sha256']),
                    'Private output descriptor differs')
        value['private_raw_output'] = raw
    if cleanup_errors is not None:
        require(type(cleanup_errors) is list and len(cleanup_errors) <= 6,
                'Owned cleanup inventory differs')
        for item in cleanup_errors:
            require(set(item) == {'stage','exception_class'} and item['stage'] in
                    ('vm-close','port-close','temporary-cleanup','host-report','host-status')
                    and item['exception_class'] in EXCEPTION_CLASSES, 'Owned cleanup descriptor differs')
        value['cleanup_errors'] = cleanup_errors
    return value


def validate_fixed_status(value):
    require(type(value) is dict and set(value)-{'private_raw_output','cleanup_errors'} == {
            'schema','stage','status','exit_code','exception_class','release_acceptance',
            'image_qualified','performance_acceptance','observer_profile_admitted'}
            and value['schema']=='arctic-safe-fixed-stage-v1'
            and all(value[k] is False for k in ('release_acceptance','image_qualified',
                    'performance_acceptance','observer_profile_admitted')), 'Fixed stage report fields differ')
    expected=fixed_status(value['stage'],value['status'],value['exit_code'],value['exception_class'],
                          raw=value.get('private_raw_output'),cleanup_errors=value.get('cleanup_errors'))
    require(value==expected,'Fixed stage report contains arbitrary data')
    return value


def run_stage(stage, out, argv):
    """Observe exact argv without publishing argv, errors, or raw child text."""
    out = Path(out)
    require(stage in STAGES and out.is_dir() and not out.is_symlink()
            and type(argv) is list and argv and all(type(a) is str and a for a in argv),
            'Owned subprocess stage differs')
    report = out/('stage-'+stage+'.json')
    require(not report.exists() and not report.is_symlink(), 'Stage report must be new')
    proc, files, selection, hashes, counts, complete = None, {}, selectors.DefaultSelector(), {}, {}, {}
    primary, result = None, None
    old_handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    def interrupted(signum, frame):
        raise RuntimeError('Owned diagnostic stage interrupted')
    def observe():
        # Leave the owned leader unreaped until its acquired group is cleaned.
        # Its retained PID prevents reuse of this numeric process-group ID.
        return os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
    def stop():
        if proc is not None:
            observe()  # Refuse to signal if this is no longer our child.
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            # A terminated leader does not imply its descendants exited.
            # Keep its PID reserved throughout the original bounded grace.
            until=time.monotonic()+5
            while time.monotonic()<until: time.sleep(.05)
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait(timeout=5)
    try:
        for s in old_handlers: signal.signal(s,interrupted)
        for label in ('stdout','stderr'):
            path=out/('private-'+stage+'-'+label+'.log')
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            files[label]=os.fdopen(fd,'wb');hashes[label]=hashlib.sha256();counts[label]=0;complete[label]=False
        proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,start_new_session=True)
        for label in ('stdout','stderr'):
            selection.register(getattr(proc,label),selectors.EVENT_READ,label)
        deadline=time.monotonic()+1140  # Original outer 19-minute bound still applies.
        while selection.get_map():
            require(time.monotonic()<deadline, 'Private stage output deadline')
            for key,_ in selection.select(.2):
                block=os.read(key.fileobj.fileno(),65536);label=key.data
                if not block:
                    selection.unregister(key.fileobj);complete[label]=True;continue
                require(counts[label]+len(block)<=MAX_FILE, 'Private stage output bound')
                files[label].write(block);hashes[label].update(block);counts[label]+=len(block)
        until=time.monotonic()+5;info=observe()
        while info is None and time.monotonic()<until:
            time.sleep(.05);info=observe()
        require(info is not None,'Owned child exit observation deadline')
        result=info.si_status if info.si_code==os.CLD_EXITED else 128+info.si_status
        require(0<=result<=255, 'Child exit status bound')
        return result
    except BaseException as error:
        primary=error
        raise
    finally:
        secondary=None
        # A repeated TERM cannot interrupt the acquired group's KILL/reap.
        for s in old_handlers: signal.signal(s,lambda signum,frame:None)
        try: stop()
        except BaseException as error: secondary=error
        try: selection.close()
        except BaseException as error: secondary=secondary or error
        for label,stream in files.items():
            try: stream.close()
            except BaseException as error: secondary=secondary or error
        if proc is not None:
            for stream in (proc.stdout,proc.stderr):
                if stream is not None:
                    try: stream.close()
                    except BaseException as error: secondary=secondary or error
        raw={label:dict(bytes=counts.get(label,0),sha256=hashes.get(label,hashlib.sha256()).hexdigest(),
                        complete=complete.get(label,False)) for label in ('stdout','stderr')}
        try:
            exclusive_json(report,fixed_status(stage,'exception' if primary or secondary else 'completed',
                  result,exception_class(primary or secondary) if primary or secondary else None,raw=raw))
        except BaseException as error: secondary=secondary or error
        for s,handler in old_handlers.items(): signal.signal(s,handler)
        if primary is None and secondary is not None and not result: raise secondary


def require(value, message):
    if not value:
        raise RuntimeError(message)


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate diagnostic JSON key')
            result[key] = value
        return result
    def constant(_):
        raise RuntimeError('Nonfinite diagnostic JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def capture(argv, timeout=30):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0 and len(result.stdout) <= 1024**2,
            'Bounded diagnostic command failed')
    return result.stdout.decode().strip()


def regular(path, limit=MAX_FILE, owner=None):
    path = Path(path)
    require(not path.is_symlink(), 'Diagnostic symlink rejected')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit
            and (owner is None or info.st_uid == owner), 'Diagnostic regular-file identity differs')
    return path


def read_regular(path, limit=MAX_FILE, dir_fd=None):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except OSError:
        raise RuntimeError('Cannot acquire diagnostic original member') from None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
                'Diagnostic original member is nonregular or oversized')
        value = bytearray()
        while len(value) <= limit:
            part = os.read(fd, min(65536, limit+1-len(value)))
            if not part: break
            value.extend(part)
        after = os.fstat(fd)
        require(len(value) == info.st_size and len(value) <= limit
                and (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
                == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),
                'Diagnostic original member changed while read')
        return bytes(value)
    finally:
        os.close(fd)


def validate_manifest(value):
    require(type(value) is dict and set(value) == {
        'schema', 'ready', 'release_acceptance', 'image_qualified', 'performance_acceptance',
        'observer_profile_admitted', 'image', 'execution_files', 'source_files'}, 'Diagnostic manifest fields differ')
    require(value['schema'] == 'arctic-safe-diagnostic-v1' and value['ready'] is True
            and all(value[k] is False for k in ('release_acceptance', 'image_qualified',
                    'performance_acceptance', 'observer_profile_admitted')), 'Diagnostic is disabled or claims acceptance')
    require(type(value['image']) is dict and value['image'] == IMAGE
            and all(type(value['image'][k]) is type(v) for k, v in IMAGE.items()), 'Exact original image pins differ')
    require(type(value['execution_files']) is dict and set(value['execution_files']) == EXECUTION_FILES,
            'Diagnostic execution inventory differs')
    require(all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
                for v in value['execution_files'].values()), 'Diagnostic execution hash differs')
    require(type(value['source_files']) is dict and set(value['source_files']) == SOURCE_FILES,
            'Diagnostic source inventory differs')
    for v in value['source_files'].values():
        require(type(v) is dict and set(v) == {'blob_sha', 'sha256', 'bytes', 'mode'}
                and type(v['bytes']) is int and 0 < v['bytes'] < 1000000
                and v['mode'] in ('100644', '100755')
                and type(v['blob_sha']) is str and re.fullmatch('[0-9a-f]{40}', v['blob_sha'])
                and type(v['sha256']) is str and re.fullmatch('[0-9a-f]{64}', v['sha256']),
                'Diagnostic original source pin differs')
    return value


def guard(root, source):
    root, source = Path(root), Path(source)
    manifest_path = root / 'tools/safe-diagnostic-v11/execution-manifest.json'
    manifest = validate_manifest(strict(regular(manifest_path).read_bytes()))
    require(os.environ.get('GITHUB_REPOSITORY') == REPO
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Requires exact first-attempt hosted diagnostic')
    event = strict(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    head = capture(['git', '-C', str(root), 'rev-parse', 'HEAD'])
    parents = capture(['git', '-C', str(root), 'show', '-s', '--format=%P', 'HEAD']).split()
    require(len(parents) == 1 and event['before'] == parents[0]
            and event['after'] == os.environ.get('GITHUB_SHA') == head, 'Diagnostic activation ancestry differs')
    require(capture(['git', '-C', str(root), 'show', '-s', '--format=%P', parents[0]]) == PREPARATION_BASE,
            'Diagnostic preparation base differs')
    capture(['git', '-C', str(root), 'merge-base', '--is-ancestor', IMAGE['source_sha'], PREPARATION_BASE])
    prepared_paths = capture(['git', '-C', str(root), 'diff', '--no-renames', '--name-only', PREPARATION_BASE, parents[0]]).splitlines()
    require(prepared_paths==sorted(PREPARATION_FILES) and
            capture(['git','-C',str(root),'diff','--no-renames','--name-status',PREPARATION_BASE,parents[0]]).splitlines()
                == [('M\t' if name==CI_PATH else 'A\t')+name for name in sorted(PREPARATION_FILES)],
            'Diagnostic preparation changes existing product or qualification paths')
    parent_ci = subprocess.check_output(['git','-C',str(root),'show',PREPARATION_BASE+':'+CI_PATH],timeout=30)
    prepared_ci = subprocess.check_output(['git','-C',str(root),'show',parents[0]+':'+CI_PATH],timeout=30)
    require(parent_ci.count(CI_ANCHOR)==1 and CI_ADDITION not in parent_ci
            and prepared_ci==parent_ci.replace(CI_ANCHOR,CI_ANCHOR+CI_ADDITION,1),
            'Diagnostic CI exclusion differs from one reviewed branch literal')
    require(subprocess.run(['git', '-C', str(root), 'cat-file', '-e', parents[0]+':'+MARKER],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode != 0,
            'Diagnostic parent was already activated')
    require(capture(['git', '-C', str(root), 'diff', '--no-renames', '--name-only', parents[0], head]).splitlines() == [MARKER]
            and regular(root / MARKER, 41).read_bytes() == (parents[0] + '\n').encode(),
            'Requires sole marker child of reviewed diagnostic preparation')
    marker_row = capture(['git', '-C', str(root), 'ls-tree', 'HEAD', '--', MARKER]).split()
    require(len(marker_row) == 4 and marker_row[0:2] == ['100644', 'blob']
            and marker_row[3] == MARKER, 'Diagnostic activation marker mode differs')
    require(not capture(['git', '-C', str(root), 'status', '--porcelain']), 'Diagnostic checkout is dirty')
    require(manifest_path.read_bytes() == subprocess.check_output(
        ['git', '-C', str(root), 'show', 'HEAD:tools/safe-diagnostic-v11/execution-manifest.json'], timeout=30),
        'Diagnostic manifest differs from tracked bytes')
    for name, expected in manifest['execution_files'].items():
        raw = regular(root / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected
                and raw == subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + name], timeout=30),
                'Diagnostic execution pin mismatch')
        row = capture(['git', '-C', str(root), 'ls-tree', 'HEAD', '--', name]).split()
        require(len(row) == 4 and row[0] in ('100644', '100755') and row[1] == 'blob',
                'Diagnostic execution blob mode differs')
    require(capture(['git', '-C', str(source), 'rev-parse', 'HEAD']) == IMAGE['source_sha']
            and not capture(['git', '-C', str(source), 'status', '--porcelain']), 'Original image source checkout differs')
    for name, pin in manifest['source_files'].items():
        raw = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + name], timeout=30)
        row = capture(['git', '-C', str(source), 'ls-tree', 'HEAD', '--', name]).split()
        require(row == [pin['mode'], 'blob', pin['blob_sha'], name]
                and len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'],
                'Original image product source pin mismatch')
    ref = strict(capture(['gh', 'api', 'repos/' + REPO + '/git/ref/heads/' + BRANCH]))
    require(ref['ref'] == 'refs/heads/' + BRANCH and ref['object']['sha'] == head,
            'Diagnostic branch advanced before execution')
    return dict(parent_sha=parents[0], execution_sha=head, image=IMAGE, release_acceptance=False)


def context(value):
    require(type(value) is dict and set(value) == {'schema', 'image', 'execution_sha', 'binding_id', 'bundle'},
            'Guest diagnostic context fields differ')
    require(value['schema'] == 'arctic-safe-guest-context-v1' and value['image'] == IMAGE
            and all(type(value['image'][k]) is type(v) for k, v in IMAGE.items()), 'Guest original image context differs')
    require(type(value['execution_sha']) is str and re.fullmatch('[0-9a-f]{40}', value['execution_sha'])
            and type(value['binding_id']) is str and re.fullmatch('[0-9a-f]{32}', value['binding_id']),
            'Guest execution identity differs')
    require(type(value['bundle']) is dict and set(value['bundle']) ==
            {'common.py', 'guest.py', 'taskbar-runtime.py', 'native_smoke.py', 'raw-screencopy', 'screen-evidence.py', 'gl-completion.so'}
            and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in value['bundle'].values()),
            'Protected guest bundle inventory differs')
    return value


GUEST_FILES = {'guest-report.json', *(
    label + '-wayland' + suffix for label in PAIRS
    for suffix in ('.rgb', '.rgb.shm.rgb', '.rgb.json', '.log'))}


class Channel:
    """Bounded newline protocol over the one owned duplex virtio connection."""
    def __init__(self, fd, binding, transcript=None):
        self.fd, self.binding, self.transcript = fd, binding, transcript
        self.buffer = bytearray()
        self.read_bytes = self.write_bytes = 0
        self.read_sha256 = hashlib.sha256()

    def send(self, kind, payload):
        raw = (json.dumps(dict(kind=kind, binding_id=self.binding, payload=payload),
                          sort_keys=True, allow_nan=False) + '\n').encode('ascii')
        require(len(raw) <= 32 * 1024, 'Diagnostic message exceeds bound')
        self.write_bytes += len(raw)
        require(self.write_bytes <= MAX_WIRE, 'Diagnostic wire exceeds bound')
        deadline, view = time.monotonic() + 30, memoryview(raw)
        while view:
            require(select.select([], [self.fd], [], max(0, deadline-time.monotonic()))[1],
                    'Diagnostic channel write deadline')
            try:
                n = os.write(self.fd, view)
                require(n > 0, 'Diagnostic channel disconnected')
                view = view[n:]
            except BlockingIOError:
                pass

    def receive(self, timeout=30):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.buffer:
            require(len(self.buffer) <= 32 * 1024 and
                    select.select([self.fd], [], [], max(0, deadline-time.monotonic()))[0],
                    'Diagnostic channel read deadline or oversized line')
            try:
                raw = os.read(self.fd, 8192)
            except BlockingIOError:
                continue
            require(raw, 'Diagnostic channel disconnected')
            self.read_bytes += len(raw)
            self.read_sha256.update(raw)
            require(self.read_bytes <= MAX_WIRE, 'Diagnostic wire exceeds bound')
            if self.transcript:
                self.transcript.write(raw)
            self.buffer.extend(raw)
        line, _, tail = self.buffer.partition(b'\n')
        self.buffer = bytearray(tail)
        require(len(line) <= 32 * 1024, 'Diagnostic message exceeds bound')
        value = strict(line)
        require(type(value) is dict and set(value) == {'kind', 'binding_id', 'payload'}
                and value['binding_id'] == self.binding and type(value['kind']) is str
                and type(value['payload']) is dict, 'Diagnostic envelope identity differs')
        return value['kind'], value['payload']

    def expect(self, kind, payload=None, timeout=30):
        actual, value = self.receive(timeout)
        require(actual == kind and (payload is None or value == payload),
                'Diagnostic protocol order or acknowledgement differs')
        return value


def encode_files(root):
    entries, total = [], 0
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in sorted(os.listdir(directory)):
            require(name in GUEST_FILES, 'Unexpected guest evidence path')
            data = read_regular(name, dir_fd=directory)
            total += len(data)
            require(total <= MAX_TOTAL, 'Guest evidence aggregate exceeds bound')
            compressed = zlib.compress(data, 6)
            entries.append((dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                 compressed_bytes=len(compressed), chunks=(len(compressed)+CHUNK-1)//CHUNK), compressed))
    finally:
        os.close(directory)
    require({entry['path'] for entry, _ in entries} == GUEST_FILES, 'Incomplete guest evidence inventory')
    return entries, total


def export_files(channel, root):
    entries, total = encode_files(root)
    channel.send('INVENTORY', dict(files=[entry for entry, _ in entries], bytes=total))
    for entry, compressed in entries:
        for index, start in enumerate(range(0, len(compressed), CHUNK)):
            channel.send('CHUNK', dict(path=entry['path'], index=index,
                         data=base64.b64encode(compressed[start:start+CHUNK]).decode('ascii')))
    channel.send('END', dict(files=len(entries), bytes=total))


def receive_files(channel, root):
    value = channel.expect('INVENTORY')
    require(set(value) == {'files', 'bytes'} and type(value['files']) is list
            and len(value['files']) == len(GUEST_FILES) and type(value['bytes']) is int
            and 0 < value['bytes'] <= MAX_TOTAL, 'Guest inventory bound differs')
    require({v['path'] for v in value['files']} == GUEST_FILES, 'Guest inventory paths differ')
    total = 0
    for entry in value['files']:
        require(type(entry) is dict and set(entry) == {'path', 'bytes', 'sha256', 'compressed_bytes', 'chunks'}
                and type(entry['bytes']) is int and 0 <= entry['bytes'] <= MAX_FILE
                and type(entry['compressed_bytes']) is int and 0 < entry['compressed_bytes'] <= MAX_FILE+65536
                and type(entry['chunks']) is int and entry['chunks'] == (entry['compressed_bytes']+CHUNK-1)//CHUNK
                and type(entry['sha256']) is str and re.fullmatch('[0-9a-f]{64}', entry['sha256']),
                'Guest inventory file bound differs')
        compressed = bytearray()
        for index in range(entry['chunks']):
            part = channel.expect('CHUNK')
            require(set(part) == {'path', 'index', 'data'} and part['path'] == entry['path']
                    and type(part['index']) is int and part['index'] == index and type(part['data']) is str,
                    'Guest chunk order differs')
            raw = base64.b64decode(part['data'], validate=True)
            require(0 < len(raw) <= CHUNK, 'Guest chunk bound differs')
            compressed.extend(raw)
            require(len(compressed) <= entry['compressed_bytes'], 'Guest compressed size exceeded')
        require(len(compressed) == entry['compressed_bytes'], 'Guest compressed bytes differ')
        decoder = zlib.decompressobj()
        data = decoder.decompress(compressed, entry['bytes'] + 1)
        require(len(data) == entry['bytes'] and decoder.eof and not decoder.unused_data
                and not decoder.unconsumed_tail and hashlib.sha256(data).hexdigest() == entry['sha256'],
                'Guest original member length/hash/compression differs')
        total += len(data)
        require(total <= MAX_TOTAL, 'Guest aggregate evidence exceeds bound')
        with (Path(root) / entry['path']).open('xb') as output:
            output.write(data)
    require(total == value['bytes'], 'Guest inventory aggregate differs')
    channel.expect('END', dict(files=len(GUEST_FILES), bytes=total))
    return value


if __name__ == '__main__':
    # Keep raw exception text private to the owned outer wrapper; fixed reports
    # carry only enumerated stage, exit code, class and bounded stream hashes.
    try:
        require(len(sys.argv)>4 and sys.argv[3]=='--', 'Stage invocation differs')
        code=run_stage(sys.argv[1],Path(sys.argv[2]),sys.argv[4:])
    except BaseException:
        code=1
    raise SystemExit(code)

# BEGIN FIXED READONLY DRM COMPONENT (public UAPI; namespaced only)
"""Bounded DRM metadata worker prototype; no state-setting ioctl requests.

Run only in an isolated, timeout-controlled preconditioning child. GETFB2 may
allocate private GEM handles; closing this worker's separately opened card FD
releases its file-owned handles. Never reuse or close a Mango FD.
"""
import ctypes as drm_C
import errno as drm_errno
import fcntl as drm_fcntl
import json as drm_json
import os as drm_os
from pathlib import Path as drm_Path
import re as drm_re
import stat as drm_stat
import struct as drm_struct
import subprocess as drm_subprocess
import sys as drm_sys
drm_U32 = drm_C.c_uint32
drm_U64 = drm_C.c_uint64

def drm_fields(kind, names):
    return [(name, kind) for name in names.split()]

class drm_Version(drm_C.Structure):
    _fields_ = drm_fields(drm_C.c_int, 'major minor patch') + [('name_len', drm_C.c_size_t), ('name', drm_C.c_void_p), ('date_len', drm_C.c_size_t), ('date', drm_C.c_void_p), ('desc_len', drm_C.c_size_t), ('desc', drm_C.c_void_p)]

class drm_Resources(drm_C.Structure):
    _fields_ = drm_fields(drm_U64, 'fb_id_ptr crtc_id_ptr connector_id_ptr encoder_id_ptr') + drm_fields(drm_U32, 'count_fbs count_crtcs count_connectors count_encoders min_width max_width min_height max_height')

class drm_Mode(drm_C.Structure):
    _fields_ = [('clock', drm_U32)] + drm_fields(drm_C.c_uint16, 'hdisplay hsync_start hsync_end htotal hskew vdisplay vsync_start vsync_end vtotal vscan') + drm_fields(drm_U32, 'vrefresh flags type') + [('name', drm_C.c_char * 32)]

class drm_Crtc(drm_C.Structure):
    _fields_ = [('set_connectors_ptr', drm_U64)] + drm_fields(drm_U32, 'count_connectors crtc_id fb_id x y gamma_size mode_valid') + [('mode', drm_Mode)]

class drm_PlaneResources(drm_C.Structure):
    _fields_ = [('plane_id_ptr', drm_U64), ('count_planes', drm_U32)]

class drm_Plane(drm_C.Structure):
    _fields_ = drm_fields(drm_U32, 'plane_id crtc_id fb_id possible_crtcs gamma_size count_format_types') + [('format_type_ptr', drm_U64)]

class drm_ObjectProperties(drm_C.Structure):
    _fields_ = drm_fields(drm_U64, 'props_ptr prop_values_ptr') + drm_fields(drm_U32, 'count_props obj_id obj_type')

class drm_Property(drm_C.Structure):
    _fields_ = drm_fields(drm_U64, 'values_ptr enum_blob_ptr') + drm_fields(drm_U32, 'prop_id flags') + [('name', drm_C.c_char * 32)] + drm_fields(drm_U32, 'count_values count_enum_blobs')

class drm_Blob(drm_C.Structure):
    _fields_ = drm_fields(drm_U32, 'blob_id length') + [('data', drm_U64)]

class drm_Fb2(drm_C.Structure):
    _fields_ = drm_fields(drm_U32, 'fb_id width height pixel_format flags') + [('handles', drm_U32 * 4), ('pitches', drm_U32 * 4), ('offsets', drm_U32 * 4), ('modifier', drm_U64 * 4)]
drm_REQUESTS = {name: (3 << 30 | drm_C.sizeof(kind) << 16 | ord('d') << 8 | number, kind) for name, number, kind in [('version', 0, drm_Version), ('resources', 160, drm_Resources), ('crtc', 161, drm_Crtc), ('property', 170, drm_Property), ('blob', 172, drm_Blob), ('plane_resources', 181, drm_PlaneResources), ('plane', 182, drm_Plane), ('object_properties', 185, drm_ObjectProperties), ('fb2', 206, drm_Fb2)]}
drm_DRIVERS = ('simpledrm', 'simple-framebuffer', 'virtio_gpu', 'bochs-drm', 'i915', 'amdgpu', 'nouveau', 'vmwgfx', 'qxl', 'radeon', 'unknown')
drm_PROPERTY_NAMES = ('ACTIVE', 'FB_ID', 'CRTC_ID', 'FB_DAMAGE_CLIPS', 'type')
drm_OBJECT_CRTC = 3435973836
drm_OBJECT_PLANE = 4008636142

class drm_MetadataBoundsError(RuntimeError):
    pass

def drm_require(value):
    if not value:
        raise drm_MetadataBoundsError('DRM_METADATA_BOUNDS')

def drm_strict_json(raw):

    def pairs(items):
        result = {}
        for key, value in items:
            drm_require(key not in result)
            result[key] = value
        return result

    def constant(_value):
        raise drm_MetadataBoundsError('DRM_METADATA_BOUNDS')
    return drm_json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)

class drm_Query:

    def __init__(self, fd, ioctl=drm_fcntl.ioctl):
        self.fd, self.ioctl, self.calls = (fd, ioctl, 0)

    def call(self, role, obj):
        self.calls += 1
        drm_require(self.calls <= 4096 and type(obj) is drm_REQUESTS[role][1])
        raw = bytearray(drm_C.string_at(drm_C.addressof(obj), drm_C.sizeof(obj)))
        self.ioctl(self.fd, drm_REQUESTS[role][0], raw, True)
        drm_C.memmove(drm_C.addressof(obj), bytes(raw), len(raw))
        return obj

def drm_array(kind, count, bound):
    drm_require(type(count) is int and 0 <= count <= bound)
    return (kind * count)()

def drm_address(items):
    return drm_C.addressof(items) if len(items) else 0

def drm_ids(items):
    result = list(items)
    drm_require(all((0 < value <= 4294967295 for value in result)) and len(set(result)) == len(result))
    return result

def drm_object_properties(query, object_id, object_type):
    obj = drm_ObjectProperties(obj_id=object_id, obj_type=object_type)
    query.call('object_properties', obj)
    count = obj.count_props
    keys, values = (drm_array(drm_U32, count, 64), drm_array(drm_U64, count, 64))
    obj.props_ptr, obj.prop_values_ptr = (drm_address(keys), drm_address(values))
    expected = (obj.props_ptr, obj.prop_values_ptr, object_id, object_type)
    query.call('object_properties', obj)
    drm_require(obj.count_props == count and (obj.props_ptr, obj.prop_values_ptr, obj.obj_id, obj.obj_type) == expected)
    names, output = (set(), {})
    for key, value in zip(drm_ids(keys), values):
        prop = query.call('property', drm_Property(prop_id=key))
        drm_require(prop.prop_id == key and prop.values_ptr == prop.enum_blob_ptr == 0 and (prop.count_values <= 256) and (prop.count_enum_blobs <= 256))
        name = bytes(prop.name)
        if name not in [item.encode() for item in drm_PROPERTY_NAMES]:
            continue
        name = name.decode('ascii')
        drm_require(name not in names)
        names.add(name)
        if name == 'FB_DAMAGE_CLIPS':
            drm_require(prop.flags & 1 << 4 and value <= 4294967295)
            if value == 0:
                output[name] = dict(status='zero-blob', rectangles=[])
            else:
                blob = query.call('blob', drm_Blob(blob_id=value))
                length = blob.length
                drm_require(0 < length <= 4096 and length % 16 == 0)
                data = drm_array(drm_C.c_ubyte, length, 4096)
                blob.data = drm_address(data)
                query.call('blob', blob)
                drm_require(blob.blob_id == value and blob.length == length and (blob.data == drm_address(data)))
                rects = [list(rect) for rect in drm_struct.iter_unpack('=iiii', bytes(data))]
                drm_require(all((-32768 <= x1 < x2 <= 32768 and -32768 <= y1 < y2 <= 32768 for x1, y1, x2, y2 in rects)))
                output[name] = dict(status='blob-observed', rectangles=rects)
        else:
            drm_require(value <= 4294967295 and (name != 'ACTIVE' or value in (0, 1)))
            output[name] = int(value)
    return output

def drm_probe_fd(fd, ioctl=drm_fcntl.ioctl):
    """Read metadata from an owned, isolated FD; count bounded, not time bounded."""
    query = drm_Query(fd, ioctl)
    version = query.call('version', drm_Version())
    drm_require(version.name_len <= 63 and version.name is None)
    name = drm_array(drm_C.c_char, version.name_len, 63)
    version.name = drm_address(name)
    name_ptr, name_len = (version.name, version.name_len)
    query.call('version', version)
    drm_require(version.name == name_ptr and version.name_len == name_len and (version.date is None) and (version.desc is None))
    driver_bytes = bytes(name)
    driver = next((item for item in drm_DRIVERS if driver_bytes == item.encode()), 'unknown')
    drm_require(all((0 <= value <= 65535 for value in [version.major, version.minor, version.patch])))
    res = query.call('resources', drm_Resources())
    counts = (res.count_fbs, res.count_crtcs, res.count_connectors, res.count_encoders)
    buffers = [drm_array(drm_U32, count, bound) for count, bound in zip(counts, [64, 16, 32, 32])]
    pointers = tuple((drm_address(items) for items in buffers))
    res.fb_id_ptr, res.crtc_id_ptr, res.connector_id_ptr, res.encoder_id_ptr = pointers
    query.call('resources', res)
    drm_require(counts == (res.count_fbs, res.count_crtcs, res.count_connectors, res.count_encoders) and pointers == (res.fb_id_ptr, res.crtc_id_ptr, res.connector_id_ptr, res.encoder_id_ptr))
    for values in buffers:
        drm_ids(values)
    crtcs, framebuffers, planes = ([], {}, [])

    def framebuffer(fb_id):
        if fb_id == 0 or fb_id in framebuffers:
            return
        drm_require(len(framebuffers) < 64)
        fb = query.call('fb2', drm_Fb2(fb_id=fb_id))
        drm_require(fb.fb_id == fb_id and 0 < fb.width <= 16384 and (0 < fb.height <= 16384) and (fb.flags & ~3 == 0))
        valid = [i for i in range(4) if fb.pitches[i] != 0]
        drm_require(valid and valid == list(range(len(valid))))
        drm_require(all((0 < fb.pitches[i] <= 1024 * 1024 and fb.offsets[i] <= 1024 ** 3 for i in valid)))
        framebuffers[fb_id] = dict(id=fb_id, width=fb.width, height=fb.height, format=fb.pixel_format, modifier_status='explicit' if fb.flags & 2 else 'unspecified', pitches=[fb.pitches[i] for i in valid], offsets=[fb.offsets[i] for i in valid], modifiers=[fb.modifier[i] for i in valid] if fb.flags & 2 else [])
    for crtc_id in drm_ids(buffers[1]):
        crtc = query.call('crtc', drm_Crtc(crtc_id=crtc_id))
        drm_require(crtc.crtc_id == crtc_id and crtc.set_connectors_ptr == 0 and (crtc.mode_valid in (0, 1)) and (crtc.x <= 32768) and (crtc.y <= 32768))
        entry = dict(id=crtc_id, framebuffer_id=crtc.fb_id, mode_valid=bool(crtc.mode_valid), x=crtc.x, y=crtc.y, properties=drm_object_properties(query, crtc_id, drm_OBJECT_CRTC))
        if crtc.mode_valid:
            drm_require(0 < crtc.mode.hdisplay <= 16384 and 0 < crtc.mode.vdisplay <= 16384)
            entry.update(width=crtc.mode.hdisplay, height=crtc.mode.vdisplay)
        crtcs.append(entry)
        framebuffer(crtc.fb_id)
    plane_res = query.call('plane_resources', drm_PlaneResources())
    count = plane_res.count_planes
    plane_ids = drm_array(drm_U32, count, 64)
    plane_res.plane_id_ptr = drm_address(plane_ids)
    query.call('plane_resources', plane_res)
    drm_require(plane_res.count_planes == count and plane_res.plane_id_ptr == drm_address(plane_ids))
    for plane_id in drm_ids(plane_ids):
        plane = query.call('plane', drm_Plane(plane_id=plane_id))
        drm_require(plane.plane_id == plane_id and plane.format_type_ptr == 0 and (plane.count_format_types <= 256))
        planes.append(dict(id=plane_id, crtc_id=plane.crtc_id, framebuffer_id=plane.fb_id, properties=drm_object_properties(query, plane_id, drm_OBJECT_PLANE)))
        framebuffer(plane.fb_id)
    return dict(status='partial', driver=driver, driver_version=[version.major, version.minor, version.patch], crtcs=crtcs, planes=planes, framebuffers=[framebuffers[key] for key in sorted(framebuffers)], property_visibility='client-default-no-atomic-or-universal-cap-request', inventory_atomic=False, ioctl_calls=query.calls)

def drm_parse_existing_framebuffers(raw, selected_ids):
    """Project only current selected Mango framebuffer metadata, never addresses."""
    drm_require(type(raw) is bytes and len(raw) <= 65536 and (len(selected_ids) <= 64))
    text = raw.decode('ascii')
    headings = list(drm_re.finditer('^framebuffer\\[([0-9]{1,10})\\]:$', text, drm_re.M))
    drm_require(len(headings) <= 64)
    output, seen = ([], set())
    for index, heading in enumerate(headings):
        ident = int(heading.group(1))
        drm_require(0 < ident <= 4294967295 and ident not in seen)
        seen.add(ident)
        if ident not in selected_ids:
            continue
        block = text[heading.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        if not drm_re.search('^\\tallocated by = mango$', block, drm_re.M):
            continue
        patterns = {'format': '^\\tformat = .*\\(0x([0-9a-fA-F]{8})\\)$', 'modifier': '^\\tmodifier=0x([0-9a-fA-F]{1,16})$', 'size': '^\\tsize=([0-9]{1,5})x([0-9]{1,5})$', 'pitch': '^\\t\\t\\tpitch\\[0\\]=([0-9]{1,7})$'}
        matched = {key: drm_re.findall(pattern, block, drm_re.M) for key, pattern in patterns.items()}
        drm_require(all((len(items) == 1 for items in matched.values())))
        width, height = [int(value) for value in matched['size'][0]]
        pitch = int(matched['pitch'][0])
        drm_require(0 < width <= 16384 and 0 < height <= 16384 and (0 < pitch <= 1024 * 1024))
        output.append(dict(id=ident, width=width, height=height, pitch=pitch, format=int(matched['format'][0], 16), modifier=int(matched['modifier'][0], 16)))
    return dict(status='parsed' if output else 'unknown', framebuffers=output, damage_clips_status='unknown')

def drm_existing_debugfs(root, minor, selected_ids):
    """Read a fixed already-accessible file; never mount or change permissions."""
    report = dict(status='unknown', framebuffers=[], damage_clips_status='unknown')
    if not selected_ids:
        return report
    fd = None
    primary = None
    try:
        path = root / 'sys/kernel/debug/dri' / str(minor) / 'framebuffer'
        fd = drm_os.open(path, drm_os.O_RDONLY | drm_os.O_CLOEXEC | drm_os.O_NOFOLLOW)
        info = drm_os.fstat(fd)
        drm_require(drm_stat.S_ISREG(info.st_mode) and info.st_uid == 0)
        report = drm_parse_existing_framebuffers(drm_os.read(fd, 65537), selected_ids)
    except (OSError, UnicodeDecodeError, drm_MetadataBoundsError):
        pass
    except BaseException as error:
        primary = error
        raise
    finally:
        if fd is not None:
            try:
                drm_os.close(fd)
            except BaseException:
                if primary is None:
                    raise
    return report

def drm_observe_drm(native, identity, root=drm_Path('/'), ioctl=drm_fcntl.ioctl):
    """Bind device to actual Mango PID/start before and after owned FD queries.

    Call inside an isolated child with a parent deadline. Ordinary missing or
    inaccessible metadata is a closed unknown; identity/device failures reject.
    """
    expected = {key: identity[key] for key in ('pid', 'start_ticks', 'executable')}
    drm_require(type(identity['pid']) is int and type(identity['start_ticks']) is int and (identity['pid'] > 0) and (identity['start_ticks'] > 0) and (identity['executable'] == '/usr/bin/mango'))
    drm_require(native.identity(identity['pid'], 1000) == expected)
    descriptors = list((root / 'proc' / str(identity['pid']) / 'fd').iterdir())
    drm_require(len(descriptors) <= 256)
    devices = {}
    for entry in descriptors:
        try:
            target = drm_os.readlink(entry)
        except FileNotFoundError:
            continue
        if not drm_re.fullmatch('/dev/dri/card[0-9]{1,3}', target):
            continue
        node = root / target.lstrip('/')
        acquired, info = (drm_os.stat(entry), node.lstat())
        drm_require(drm_stat.S_ISCHR(acquired.st_mode) and drm_stat.S_ISCHR(info.st_mode) and (info.st_uid == 0) and (acquired.st_rdev == info.st_rdev) and (drm_os.major(info.st_rdev) == 226))
        devices[node.name] = (node, info.st_rdev, info.st_dev, info.st_ino)
    drm_require(len(devices) <= 4)
    observations = []
    for key in sorted(devices):
        node, device, filesystem_device, inode = devices[key]
        fd = None
        primary = None
        try:
            fd = drm_os.open(node, drm_os.O_RDONLY | drm_os.O_CLOEXEC | drm_os.O_NOFOLLOW)
            opened = drm_os.fstat(fd)
            drm_require(drm_stat.S_ISCHR(opened.st_mode) and opened.st_uid == 0 and (opened.st_rdev == device) and ((opened.st_dev, opened.st_ino) == (filesystem_device, inode)) and (drm_fcntl.fcntl(fd, drm_fcntl.F_GETFL) & drm_os.O_ACCMODE == drm_os.O_RDONLY))
            report = drm_probe_fd(fd, ioctl)
        except OSError as error:
            reason = 'permission' if error.errno in (drm_errno.EACCES, drm_errno.EPERM) else 'unavailable'
            report = dict(status='unknown', reason=reason)
        except BaseException as error:
            primary = error
            raise
        finally:
            if fd is not None:
                try:
                    drm_os.close(fd)
                except BaseException:
                    if primary is None:
                        raise
        current_ids = {item['id'] for item in report.get('framebuffers', [])}
        debugfs = drm_existing_debugfs(root, drm_os.minor(device), current_ids)
        observations.append(dict(node=key, major=drm_os.major(device), minor=drm_os.minor(device), existing_debugfs=debugfs, **report))
    drm_require(native.identity(identity['pid'], 1000) == expected)
    return dict(schema='arctic-safe-readonly-drm-v1', pid=identity['pid'], start_ticks=identity['start_ticks'], status='observed' if observations else 'unknown', devices=observations)

def drm_validate_snapshot(report, identity):
    """Close all exported strings and numeric inventories before admission."""
    drm_require(type(report) is dict and set(report) == {'schema', 'pid', 'start_ticks', 'status', 'devices'} and (report['schema'] == 'arctic-safe-readonly-drm-v1') and (type(report['pid']) is type(report['start_ticks']) is int) and (report['pid'] == identity['pid']) and (report['start_ticks'] == identity['start_ticks']) and (report['status'] in ('observed', 'unknown')) and (type(report['devices']) is list) and (len(report['devices']) <= 4))

    def integers(values, maximum=4294967295):
        drm_require(all((type(value) is int and 0 <= value <= maximum for value in values)))

    def props(value):
        drm_require(type(value) is dict and set(value) <= set(drm_PROPERTY_NAMES))
        for name, item in value.items():
            if name != 'FB_DAMAGE_CLIPS':
                integers([item])
                drm_require(name != 'ACTIVE' or item in (0, 1))
                continue
            drm_require(type(item) is dict and set(item) == {'status', 'rectangles'} and (item['status'] in ('zero-blob', 'blob-observed')) and (type(item['rectangles']) is list) and (len(item['rectangles']) <= 256))
            drm_require(item['status'] != 'zero-blob' or item['rectangles'] == [])
            drm_require(item['status'] != 'blob-observed' or bool(item['rectangles']))
            for rect in item['rectangles']:
                drm_require(type(rect) is list and len(rect) == 4 and all((type(v) is int for v in rect)))
                x1, y1, x2, y2 = rect
                drm_require(-32768 <= x1 < x2 <= 32768 and -32768 <= y1 < y2 <= 32768)
    nodes = set()
    for device in report['devices']:
        base = {'node', 'major', 'minor', 'status', 'existing_debugfs'}
        drm_require(type(device) is dict and base <= set(device) and (type(device['node']) is str) and drm_re.fullmatch('card[0-9]{1,3}', device['node']) and (device['node'] not in nodes) and (type(device['major']) is int) and (device['major'] == 226) and (type(device['minor']) is int) and (0 <= device['minor'] <= 4095))
        nodes.add(device['node'])
        debugfs = device['existing_debugfs']
        drm_require(type(debugfs) is dict and set(debugfs) == {'status', 'framebuffers', 'damage_clips_status'} and (debugfs['status'] in ('parsed', 'unknown')) and (debugfs['damage_clips_status'] == 'unknown') and (type(debugfs['framebuffers']) is list) and (len(debugfs['framebuffers']) <= 64))
        debug_ids = set()
        for fb in debugfs['framebuffers']:
            drm_require(type(fb) is dict and set(fb) == {'id', 'width', 'height', 'pitch', 'format', 'modifier'} and (type(fb['id']) is int) and (0 < fb['id'] <= 4294967295) and (fb['id'] not in debug_ids))
            debug_ids.add(fb['id'])
            integers([fb['width'], fb['height']], 16384)
            drm_require(fb['width'] > 0 and fb['height'] > 0)
            integers([fb['pitch']], 1024 * 1024)
            drm_require(fb['pitch'] > 0)
            integers([fb['format']])
            integers([fb['modifier']], 18446744073709551615)
        drm_require(debugfs['status'] == ('parsed' if debugfs['framebuffers'] else 'unknown'))
        if device['status'] == 'unknown':
            drm_require(set(device) == base | {'reason'} and device['reason'] in ('permission', 'unavailable'))
            continue
        drm_require(device['status'] == 'partial' and set(device) == base | {'driver', 'driver_version', 'crtcs', 'planes', 'framebuffers', 'property_visibility', 'inventory_atomic', 'ioctl_calls'} and (device['driver'] in drm_DRIVERS) and (type(device['driver_version']) is list) and (len(device['driver_version']) == 3) and (device['property_visibility'] == 'client-default-no-atomic-or-universal-cap-request') and (device['inventory_atomic'] is False))
        integers(device['driver_version'], 65535)
        integers([device['ioctl_calls']], 4096)
        for role, bound in [('crtcs', 16), ('planes', 64), ('framebuffers', 64)]:
            drm_require(type(device[role]) is list and len(device[role]) <= bound)
            seen = set()
            for item in device[role]:
                drm_require(type(item) is dict and type(item.get('id')) is int and (0 < item['id'] <= 4294967295) and (item['id'] not in seen))
                seen.add(item['id'])
                if role == 'crtcs':
                    drm_require(type(item.get('mode_valid')) is bool and set(item) == {'id', 'framebuffer_id', 'mode_valid', 'x', 'y', 'properties'} | ({'width', 'height'} if item['mode_valid'] else set()))
                    integers([item['framebuffer_id']])
                    integers([item['x'], item['y']], 32768)
                    if item['mode_valid']:
                        integers([item['width'], item['height']], 16384)
                        drm_require(item['width'] > 0 and item['height'] > 0)
                    props(item['properties'])
                elif role == 'planes':
                    drm_require(set(item) == {'id', 'crtc_id', 'framebuffer_id', 'properties'})
                    integers([item['crtc_id'], item['framebuffer_id']])
                    props(item['properties'])
                else:
                    drm_require(set(item) == {'id', 'width', 'height', 'format', 'modifier_status', 'pitches', 'offsets', 'modifiers'} and item['modifier_status'] in ('explicit', 'unspecified'))
                    integers([item['width'], item['height']], 16384)
                    drm_require(item['width'] > 0 and item['height'] > 0)
                    integers([item['format']])
                    drm_require(type(item['pitches']) is list and 1 <= len(item['pitches']) <= 4 and (type(item['offsets']) is list) and (len(item['offsets']) == len(item['pitches'])) and (type(item['modifiers']) is list) and (len(item['modifiers']) == (len(item['pitches']) if item['modifier_status'] == 'explicit' else 0)))
                    integers(item['pitches'], 1024 * 1024)
                    drm_require(all((value > 0 for value in item['pitches'])))
                    integers(item['offsets'], 1024 ** 3)
                    integers(item['modifiers'], 18446744073709551615)
        drm_require(debug_ids <= {item['id'] for item in device['framebuffers']})
    drm_require(report['status'] == ('observed' if report['devices'] else 'unknown'))
    return report

class drm_ProcessIdentity:
    """Minimal read-only native identity adapter for the isolated worker."""

    def identity(self, pid, uid):
        process = drm_Path('/proc') / str(pid)
        drm_require(process.stat().st_uid == uid)
        content = (process / 'stat').read_text()
        drm_require(len(content) <= 65536)
        values = content.rsplit(')', 1)[1].split()
        drm_require(values[0] not in ('Z', 'X'))
        return dict(pid=pid, start_ticks=int(values[19]), executable=drm_os.readlink(process / 'exe'))

def drm_child_entry():
    """Internal fixed-mode entry; input identity only, no paths or commands."""
    try:
        data = drm_sys.stdin.buffer.read(1025)
        drm_require(len(data) <= 1024)
        identity = drm_strict_json(data)
        drm_require(type(identity) is dict and set(identity) == {'pid', 'start_ticks', 'executable'})
        report = drm_validate_snapshot(drm_observe_drm(drm_ProcessIdentity(), identity), identity)
        raw = (drm_json.dumps(report, sort_keys=True, allow_nan=False) + '\n').encode()
        drm_require(len(raw) <= 65536)
        drm_sys.stdout.buffer.write(raw)
    except Exception:
        return 1
    return 0

def drm_bounded_observe_drm(native, identity, worker_path, run=drm_subprocess.run):
    """Existing guest path may expose child_entry in a fixed internal mode.

    Deadline is subprocess.run(timeout=20), with normal kill/reap semantics. A
    kernel task stuck in uninterruptible sleep can delay reaping; no stronger
    real-time guarantee is claimed. No actual local ioctl is needed to test it.
    """
    expected = {key: identity[key] for key in ('pid', 'start_ticks', 'executable')}
    drm_require(type(expected['pid']) is type(expected['start_ticks']) is int and expected['pid'] > 0 and (expected['start_ticks'] > 0) and (expected['executable'] == '/usr/bin/mango'))
    drm_require(native.identity(identity['pid'], 1000) == expected)
    raw = drm_json.dumps(expected, sort_keys=True, allow_nan=False).encode()
    drm_require(len(raw) <= 1024)
    report = dict(schema='arctic-safe-readonly-drm-v1', pid=identity['pid'], start_ticks=identity['start_ticks'], status='unknown', devices=[])
    try:
        result = run([drm_sys.executable, '-I', str(worker_path), '--safe-readonly-drm-child'], input=raw, stdout=drm_subprocess.PIPE, stderr=drm_subprocess.DEVNULL, timeout=20, check=False)
        if result.returncode == 0:
            drm_require(type(result.returncode) is int and type(result.stdout) is bytes and (len(result.stdout) <= 65536))
            report = drm_validate_snapshot(drm_strict_json(result.stdout), identity)
    except (OSError, drm_subprocess.TimeoutExpired):
        pass
    drm_require(native.identity(identity['pid'], 1000) == expected)
    return report
# END FIXED READONLY DRM COMPONENT
