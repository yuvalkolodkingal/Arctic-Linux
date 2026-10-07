"""Nonsecret SMBIOS credentials. Build-time generation only, never VM dispatch."""
import base64,hashlib,json,re,sys
from pathlib import Path
NAME='arctic-mango-trace-collector.service'
DROP='systemd.unit-dropin.sddm.service~90-arctic-mango-trace'
EXTRA='systemd.extra-unit.'+NAME

def require(v,m):
    if not v:raise RuntimeError(m)

def values(cdsha,cdbytes):
    require(type(cdsha) is str and re.fullmatch('[0-9a-f]{64}',cdsha) is not None and type(cdbytes) is int and 0<cdbytes<=16777216 and cdbytes%2048==0,'Invalid exact diagnostic CD identity')
    # The Bash command is fixed, nonsecret, and uses only exact validated SHA,
    # integer size and kernel-reported block/stat data. No eval or user argv.
    command=("set -euo pipefail; "
             "mount_node=''; mounted=0; trace_device=''; "
             "cleanup_trace_mount() { "
             "test -n \"$mount_node\" || return 1; "
             "if test \"$mounted\" -eq 1; then "
             "read -r mt ms mo mf < <(/usr/bin/findmnt -n -o TARGET,SOURCE,OPTIONS,FSTYPE --mountpoint /run/arctic-mango-trace-cd); "
             "test \"$mt\" = /run/arctic-mango-trace-cd && test \"$ms\" = \"$trace_device\" && test \"$mf\" = iso9660 || return 1; "
             "case ,$mo, in *,ro,*) ;; *) return 1;; esac; "
             "umount /run/arctic-mango-trace-cd || return 1; fi; "
             "test \"$(stat -c '%d:%i:%u:%g:%a' /run/arctic-mango-trace-cd)\" = \"$mount_node\" || return 1; "
             "rmdir /run/arctic-mango-trace-cd; }; "
             "trap 'trace_rc=$?; if test \"$trace_rc\" -ne 0 && test -n \"$mount_node\"; then cleanup_trace_mount || printf \"Owned trace mount cleanup failed\\n\" >&2; fi; exit \"$trace_rc\"' EXIT; "
             "test ! -e /run/arctic-mango-trace-cd; test ! -L /run/arctic-mango-trace-cd; "
             "mkdir -m 700 /run/arctic-mango-trace-cd; "
             "mount_node=$(stat -c '%d:%i:%u:%g:%a' /run/arctic-mango-trace-cd); "
             "mapfile -t trace_devices < <(/usr/sbin/blkid -t LABEL=ARCTICSAFE -o device); "
             "test ${#trace_devices[@]} -eq 1; trace_device=${trace_devices[0]}; test -b \"$trace_device\"; "
             f"test $(/usr/sbin/blockdev --getsize64 \"$trace_device\") -eq {cdbytes}; "
             f"test $(/usr/bin/sha256sum \"$trace_device\" | cut -d' ' -f1) = {cdsha}; "
             "mount -o ro,nosuid,nodev,noexec \"$trace_device\" /run/arctic-mango-trace-cd; mounted=1; "
             f"/usr/bin/python3.14 -I -S /run/arctic-mango-trace-cd/prepare.py {cdsha} {cdbytes} \"$mount_node\" > /dev/ttyS0")
    # systemd first handles $ and % specifiers. The resulting Bash argv must
    # recover the literal command exactly; no command substitution by manager.
    escaped=command.replace('$','$$').replace('%','%%').replace('\\','\\\\').replace('"','\\"')
    drop=("[Unit]\nWants="+NAME+"\n[Service]\nExecStartPre=/usr/bin/timeout --kill-after=2 30 /usr/bin/bash --noprofile --norc -ec \""+escaped+"\"\n")
    extra=("[Unit]\nDescription=Owned one-target renderer trace (startup perturbation)\nAfter=sddm.service\nConditionPathExists=!/etc/initrd-release\n[Service]\nType=simple\nExecStart=/usr/bin/bash --noprofile --norc -ec \"exec /usr/bin/python3.14 -I -S /run/arctic-mango-trace/controller.py > /dev/ttyS0\"\nRuntimeMaxSec=1300\nTimeoutStopSec=5\n")
    return {DROP:drop,EXTRA:extra}

def qemu_args(cdsha,cdbytes):
    result=[]
    for name,value in values(cdsha,cdbytes).items():
        result+=['-smbios','type=11,value=io.systemd.credential.binary:'+name+'='+base64.b64encode(value.encode()).decode('ascii')]
    return result
if __name__=='__main__':
    require(len(sys.argv)==2,'Exact existing generated diagnostic CD required')
    p=Path(sys.argv[1]);require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=16777216,'Unsafe CD input')
    print(json.dumps(qemu_args(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_size)))
