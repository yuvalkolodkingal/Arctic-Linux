#!/usr/bin/python3
"""Linux parent-death guard for the session broker's trusted children."""
import ctypes
import os
import resource
import signal
import sys

def main():
    parent = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise SystemExit(1)
    if os.getppid() != parent:
        raise SystemExit(1)
    os.execv(sys.argv[2], sys.argv[2:])

if __name__ == "__main__":
    main()
