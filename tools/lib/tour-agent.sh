#!/bin/bash
# tools/screenshot-tour.sh: the guest agent. Runs in the live session as liveuser, started once
# from a terminal (`curl … /agent` then `setsid -f bash`), so it has the session's environment
# (WAYLAND_DISPLAY, XDG_RUNTIME_DIR, D-Bus). It long-polls the tour's HTTP server on the host
# (10.0.2.2 is QEMU user networking's address for the host) for shell commands, runs each one
# and posts back "<exit code>\n<output>". The tour uses it to start the demo installer and to
# read its state over Quickshell IPC instead of guessing with sleeps.
# @HOST@ is filled in by tools/lib/tour.py when it serves this file.
H="http://@HOST@"
curl -fsS --max-time 20 -X POST --data-binary "$(id -un) ${WAYLAND_DISPLAY:-no-wayland}" "$H/hello" >/dev/null 2>&1
while :; do
  if ! curl -fsS --max-time 75 -o /tmp/tour-cmd "$H/next" 2>/dev/null; then
    sleep 2
    continue
  fi
  [ -s /tmp/tour-cmd ] || continue
  id=$(head -n 1 /tmp/tour-cmd)
  tail -n +2 /tmp/tour-cmd > /tmp/tour-cmd.sh
  out=$(timeout 600 bash /tmp/tour-cmd.sh </dev/null 2>&1)
  rc=$?
  printf '%s\n%s' "$rc" "$out" | curl -fsS --max-time 30 -X POST --data-binary @- "$H/result/$id" >/dev/null 2>&1
done
