#!/usr/bin/env python3
"""Test-CD only: leave the owned initiating Foot before native GUI checks.

No process is signalled or killed. The unchanged GUI checker still rejects all
pre-existing native apps. Importing this module has no execution side effects.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import time

LOCATION = Path('/run/t/native-launcher.py')
SHELLS = {'bash', 'fish', 'zsh', 'dash', 'sh'}


def require(value, message):
    if not value: raise RuntimeError(message)


def identity(pid):
    path = Path('/proc')/str(pid)
    fields = (path/'stat').read_text().rsplit(')', 1)[1].split()
    executable = (path/'exe').resolve(strict=True)
    uid = path.stat().st_uid
    with executable.open('rb') as stream: magic = stream.read(4)
    require(magic == b'\x7fELF', 'Launcher ancestor is not a native ELF process')
    return dict(pid=int(pid), ppid=int(fields[1]), start_ticks=int(fields[19]),
                uid=uid, executable=str(executable),
                executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())


def same_process(proof, read=identity):
    try: current = read(proof['pid'])
    except FileNotFoundError: return False
    return current['start_ticks'] == proof['start_ticks']


def identify_launcher(shell_pid=None, read=identity):
    require(shell_pid is None or (type(shell_pid) is int and shell_pid > 1), 'Invalid initiating shell PID')
    chain = []
    pid = os.getpid()
    for _ in range(32):
        item = read(pid); chain.append(item)
        if item['executable'] == '/usr/bin/foot': break
        require(item['ppid'] > 1 and item['ppid'] != pid, 'No bounded Foot ancestor')
        pid = item['ppid']
    else: raise RuntimeError('Foot ancestry exceeds bound')
    if shell_pid is None:
        shells = [item for item in chain[:-1] if item['uid'] > 0 and Path(item['executable']).name in SHELLS][:1]
    else:
        shells = [item for item in chain[:-1] if item['pid'] == shell_pid]
    require(len(shells) == 1, 'Supplied initiating shell is not an actual ancestor')
    shell, foot = shells[0], chain[-1]
    require(Path(shell['executable']).name in SHELLS and shell['uid'] > 0
            and foot['uid'] == shell['uid'] and foot['executable'] == '/usr/bin/foot',
            'Initiating shell/Foot UID or ELF identity differs')
    return dict(shell=shell, foot=foot, ancestry=chain)


def wait_disappeared(proof, descriptors, timeout=30, read=identity):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select(descriptors, [], [], 0)
        if len(ready) == len(descriptors) and all(not same_process(proof[name],read) for name in ('shell','foot')):
            return
        time.sleep(.02)
    raise RuntimeError('Owned initiating shell/Foot did not disappear within 30 seconds')


def barrier_path(stage):
    require(stage in ('live','installed'), 'Invalid native launcher stage')
    return Path('/run/arctic-native-launcher-'+stage+'.json')


def verify_barrier(stage, expected_sha):
    path = barrier_path(stage)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
            'Native launcher proof is not an owned root-only regular file')
    proof = json.loads(path.read_text())
    require(proof['schema'] == 'arctic-native-launcher-v1' and proof['stage'] == stage
            and proof['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and proof['launcher_sha256'] == expected_sha and proof['owned_launcher_gone'] is True,
            'Native launcher same-boot/helper identity differs')
    require(proof['foot']['executable'] == '/usr/bin/foot' and proof['foot']['uid'] > 0
            and proof['shell']['uid'] == proof['foot']['uid']
            and Path(proof['shell']['executable']).name in SHELLS,
            'Native launcher saved ownership differs')
    require(not same_process(proof['shell']) and not same_process(proof['foot']),
            'Owned native launcher identity remains alive')
    pid = os.getpid()
    for _ in range(32):
        current = identity(pid)
        if current['pid'] == proof['probe']['pid']:
            require(current['start_ticks'] == proof['probe']['start_ticks'] and current['uid'] == 0,
                    'Native probe ancestor changed')
            break
        require(current['ppid'] > 1, 'Native checker is outside its owned root probe')
        pid = current['ppid']
    else: raise RuntimeError('Native probe ancestry exceeds bound')
    return proof


def main():
    descriptors = []
    try:
        require(LOCATION.resolve() == Path(__file__).resolve() and os.geteuid() == 0,
                'Requires the root-owned test-CD launcher location')
        require(len(sys.argv) == 1, 'No launcher arguments are allowed; actual ancestors determine ownership')
        require(subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm'),
                'Requires explicitly disposable QEMU/KVM guest')
        require(subprocess.check_output(['getenforce'],text=True).strip() == 'Enforcing',
                'Requires enforcing guest SELinux')
        stage = 'live' if 'rd.live.image' in Path('/proc/cmdline').read_text().split() else 'installed'
        path = barrier_path(stage); require(not path.exists(), 'Native launcher stage already started')
        proof = identify_launcher()
        for name in ('shell','foot'):
            descriptors.append(os.pidfd_open(proof[name]['pid']))
            require(identity(proof[name]['pid']) == proof[name], 'Launcher changed while opening pidfd')
        ready_r, ready_w = os.pipe()
        child = os.fork()
        if child:
            os.close(ready_w)
            try:
                require(bool(select.select([ready_r],[],[],10)[0]) and os.read(ready_r,32) == b'READY\n',
                        'Detached root probe did not acknowledge readiness')
            finally:
                os.close(ready_r); os.waitpid(child,0)
            return 0
        os.close(ready_r)
        os.setsid()
        if os.fork(): os._exit(0)
        null = os.open('/dev/null',os.O_RDONLY)
        serial = os.open('/dev/ttyS0',os.O_WRONLY|os.O_NOCTTY)
        os.dup2(null,0); os.dup2(serial,1); os.dup2(serial,2)
        os.close(null); os.close(serial)
        proof.update(schema='arctic-native-launcher-v1',stage=stage,
                     boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                     launcher_sha256=hashlib.sha256(LOCATION.read_bytes()).hexdigest(),probe=identity(os.getpid()))
        print('ARCTIC-NATIVE-LAUNCHER-READY '+json.dumps(proof,sort_keys=True),flush=True)
        os.write(ready_w,b'READY\n'); os.close(ready_w)
        wait_disappeared(proof,descriptors)
        proof['owned_launcher_gone'] = True
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(proof,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        print('ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(proof,sort_keys=True),flush=True)
        for fd in descriptors: os.close(fd)
        descriptors.clear()
        os.execv('/usr/bin/bash',['bash','/run/t/run.sh' if stage=='live' else '/run/t/collect.sh'])
    except BaseException as error:
        message = 'ARCTIC-NATIVE-LAUNCHER-FAILED '+type(error).__name__+': '+str(error)+'\n'
        try:
            with open('/dev/ttyS0','w') as serial: serial.write(message);serial.flush()
        except OSError: sys.stderr.write(message)
        return 1
    finally:
        for fd in descriptors: os.close(fd)


if __name__ == '__main__':
    sys.exit(main())
