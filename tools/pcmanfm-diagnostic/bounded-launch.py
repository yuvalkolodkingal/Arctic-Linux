#!/usr/bin/env python3
"""Drain one owned diagnostic child's raw streams, failing above combined 2 MiB."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import stat
import selectors
import signal
import subprocess
import sys
import time

HELPER_SHA = 'e44586b3b3d738888a6e12f58c6cf7cc6bbf980412d80c79d7cecaff539b1b75'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process_identity(pid):
    root = Path('/proc') / str(pid)
    raw = (root / 'stat').read_text()
    start = int(raw[raw.rindex(')') + 2:].split()[19])
    uid = root.stat().st_uid
    executable = os.readlink(root / 'exe')
    return dict(pid=pid, start_ticks=start, uid=uid, executable=executable,
                executable_sha256=digest(executable))


def role_configuration(paths):
    configured = None
    records = []
    for path in paths:
        try: info=path.lstat()
        except FileNotFoundError:
            records.append(dict(path=str(path), present=False)); continue
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise RuntimeError('role configuration is not a bounded regular file')
        data = path.read_bytes()
        # The pinned helper's grep/tail separates LF records. Preserve CR and
        # other control separators literally; never normalize a different argv.
        matches = [line[6:] for line in data.decode('utf-8', errors='strict').split('\n') if line.startswith('files=')]
        if matches:
            configured = matches[-1]
        records.append(dict(path=str(path), present=True, sha256=hashlib.sha256(data).hexdigest(),
                            last_files_value=matches[-1] if matches else None))
    if configured != 'pcmanfm':
        raise RuntimeError('exact resolved role/argv is not pcmanfm without arguments')
    return configured, records


def resolved_role():
    helper = Path('/usr/bin/arctic-open')
    if helper.is_symlink() or not helper.is_file() or stat.S_IMODE(helper.stat().st_mode)!=0o755 or digest(helper) != HELPER_SHA:
        raise RuntimeError('candidate generated role helper differs')
    helper_owner = subprocess.run(['rpm','-qf','--qf','%{NAME}|%{VERSION}|%{RELEASE}|%{ARCH}|%{EPOCHNUM}\n',str(helper)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
    expected_owner='arctic-desktop-config|1.2.0|1.preview.37507582946.1.gitfe4742c.fc44|noarch|0'
    if helper_owner.returncode!=0 or helper_owner.stderr or len(helper_owner.stdout)>65536 or helper_owner.stdout.decode().strip()!=expected_owner:
        raise RuntimeError('candidate generated helper RPM ownership differs')
    paths = [Path('/etc/arctic/default-apps'),
             Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'arctic/default-apps']
    configured, records = role_configuration(paths)
    if records[0]['present'] is not True:
        raise RuntimeError('mandatory system default role proof absent')
    actual = shutil.which('pcmanfm')
    binary = Path('/usr/bin/pcmanfm')
    if actual is None or Path(actual).resolve(strict=True) != binary.resolve(strict=True):
        raise RuntimeError('role PATH points to another native binary')
    verification = subprocess.run(['rpm', '-Vf', str(binary)], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=15, check=False)
    owner = subprocess.run(['rpm', '-qf', str(binary)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=15, check=False)
    if any(len(x) > 65536 for x in (verification.stdout, verification.stderr, owner.stdout, owner.stderr)):
        raise RuntimeError('role RPM proof exceeds bound')
    if verification.returncode != 0 or verification.stdout or verification.stderr or owner.returncode != 0 or owner.stderr:
        raise RuntimeError('native role RPM verification failed')
    return dict(configured=configured, helper_sha256=HELPER_SHA, helper_rpm_owner=expected_owner,configurations=records,
                direct_argv=[str(binary)], helper_exec_args=[], helper_id_args=[], helper_app_args=[],
                executable_sha256=digest(binary), rpm_owner=owner.stdout.decode().strip(),
                rpm_verification=dict(exit_status=verification.returncode,
                                      stdout=verification.stdout.decode(), stderr=verification.stderr.decode()),
                launch_difference='observed arm only: direct owned native process, preserving stderr/stdout; no role detach/redirection')


def run_owned(root, argv, *, limit=2*1024*1024, deadline=180, role=None):
    outputs = {'stdout':root/'pcmanfm-stdout.log','stderr':root/'pcmanfm-wayland-stderr.log'}
    error = root/'pcmanfm-wayland-error.json'
    if any(p.exists() for p in (*outputs.values(),error,root/'pcmanfm-owned-launch.json',root/'pcmanfm-owned-completion.json')):
        raise RuntimeError('Wayland evidence must be unused')
    child = None; descriptor = None; sel = None; failed = None; count = 0; result = 74
    saved_handlers = {}; targets = {}; caught = None
    def send(sig):
        if child is None or child.poll() is not None:
            return
        try:
            if descriptor is not None:
                signal.pidfd_send_signal(descriptor,sig)
            else:
                # Only our direct unreaped child is signalled, never a searched PID.
                child.send_signal(sig)
        except ProcessLookupError:
            pass
    try:
        child = subprocess.Popen(argv, env=dict(os.environ, WAYLAND_DEBUG='client'),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        descriptor = os.pidfd_open(child.pid)
        if role is not None:
            identity = process_identity(child.pid)
            if identity['uid'] != os.getuid() or identity['executable'] != argv[0] or identity['executable_sha256'] != role['executable_sha256']:
                raise RuntimeError('direct owned native launch identity differs')
            (root/'pcmanfm-owned-launch.json').write_text(json.dumps(dict(role=role, process=identity,
                environment_change=dict(WAYLAND_DEBUG='client'), monotonic_ns=time.monotonic_ns()), indent=2)+'\n')
        sel = selectors.DefaultSelector()
        for name,stream in (('stdout',child.stdout),('stderr',child.stderr)):
            targets[name] = outputs[name].open('xb')
            os.set_blocking(stream.fileno(),False); sel.register(stream,selectors.EVENT_READ,data=name)
        started = time.monotonic()
        def interrupted(signum, _):
            nonlocal failed
            failed = 'owned wrapper interrupted by signal '+str(signum)
            send(signal.SIGTERM)
        for sig in (signal.SIGTERM, signal.SIGINT):
            saved_handlers[sig] = signal.getsignal(sig); signal.signal(sig, interrupted)
        while sel.get_map():
            if time.monotonic()-started > deadline:
                failed = 'owned Wayland child exceeded deadline'
            if failed:
                break
            for key,_ in sel.select(.2):
                data = os.read(key.fd,65536)
                if not data:
                    sel.unregister(key.fileobj);continue
                count += len(data)
                if count > limit:
                    failed = 'combined Wayland/stdout log exceeded 2 MiB; required evidence incomplete'
                    break
                targets[key.data].write(data)
        if failed:
            send(signal.SIGTERM)
        try: result = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            failed = failed or 'owned child failed to retire after stream completion'
            send(signal.SIGKILL);result=child.wait(timeout=3)
    except BaseException as exc:
        failed = type(exc).__name__+': '+str(exc); caught = exc
    finally:
        # Setup and preservation failures must still reap only the direct owned child.
        try:
            send(signal.SIGTERM)
            if child is not None:
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    send(signal.SIGKILL);child.wait(timeout=3)
        except BaseException as exc:
            failed = (failed+'; ' if failed else '')+'owned cleanup: '+str(exc)
            caught = caught or exc
        finally:
            for stream in ((child.stdout,child.stderr) if child is not None else ()):
                if stream is not None: stream.close()
            if sel is not None: sel.close()
            if descriptor is not None: os.close(descriptor)
            for stream in targets.values(): stream.close()
            for sig, handler in saved_handlers.items(): signal.signal(sig,handler)
        if failed:
            error.write_text(json.dumps(dict(error=failed, bytes_observed=count, preservation_complete=False,
                streams={name:path.name for name,path in outputs.items()},combined_limit_bytes=limit)))
        if role is not None:
            streams={name:dict(bytes=path.stat().st_size,sha256=digest(path))
                     for name,path in outputs.items() if path.is_file()}
            (root/'pcmanfm-owned-completion.json').write_text(json.dumps(dict(
                complete=failed is None and len(streams)==2 and sum(v['bytes'] for v in streams.values())==count,
                error=failed, bytes_observed=count, combined_limit_bytes=limit,
                child_exit_status=child.returncode if child is not None else None,
                only_owned_direct_child_reaped=child is not None and child.poll() is not None,
                streams=streams, role=role),indent=2)+'\n')
    if caught is not None:
        raise caught
    return 74 if failed else result


def main():
    if len(sys.argv) != 2 or os.geteuid() == 0:
        raise RuntimeError('requires owned evidence directory as desktop UID')
    root = Path(sys.argv[1])
    if not root.is_dir() or root.is_symlink() or root.stat().st_uid != os.getuid():
        raise RuntimeError('unproved diagnostic evidence directory')
    role = resolved_role()
    return run_owned(root, role['direct_argv'], role=role)


if __name__ == '__main__':
    raise SystemExit(main())
