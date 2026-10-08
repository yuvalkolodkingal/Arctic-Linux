# Native taskbar checks

`BarHarness.qml` exercises the checkout's real `Bar`, `VerticalBar` and `BarMenu` on the current
Mango/Wayland desktop. It uses real tray, sound, battery, weather and workspace services, and
an in-memory recording indicator fixture. Its separate popup is a test card. It does not
replace the installed shell, write taskbar preferences or restart applications.

Run in a disposable copy of `shell/`, so `Session.scripts` still resolves correctly:

```sh
cp -a shell /tmp/arctic-bar-preview
cp shell/dev/BarHarness.qml /tmp/arctic-bar-preview/bar-test.qml
gcc -Wall shell/dev/virtual-pointer.c -l:libwayland-client.so.0 -o /tmp/arctic-test-pointer
quickshell -p /tmp/arctic-bar-preview/bar-test.qml
```

In another terminal, record the answer from `arctic-shell-ipc bar hidden`. If it is `false`,
use `arctic-shell-ipc bar toggleHidden` to hide the installed bar for the comparison. This keeps
the installed shell and applications running. Check the monitor names with `mmsg get all-monitors`.
The checks move a virtual pointer and use a virtual keyboard; avoid other pointer/keyboard
activity during the run. They must be the sole input automation running against the preview.

```sh
python3 shell/dev/test-bar.py \
  --preview /tmp/arctic-bar-preview/bar-test.qml \
  --pointer /tmp/arctic-test-pointer --out /tmp/arctic-bar-results \
  --monitor eDP-1 --other-monitor HDMI-A-5
```

The runner checks left/right controls at 28/32/56 logical pixels, native Home/End navigation,
all four physical edge triggers, intermediate animation values, hide delay, repeated entry,
actual calendar clicks, separate-popup pinning, dragging/releasing outside, the hidden input
region, independent monitor activation, keyboard reveal and reduced motion. It saves screenshots
and JSON results. It resets and stops the owned preview even if an assertion fails or the
runner receives SIGTERM/SIGHUP. Fractional-scale and
small-display checks can use the same harness after a reversible display change; restore the
original monitor configuration afterward.

When finished, stop only the preview:

```sh
quickshell kill -p /tmp/arctic-bar-preview/bar-test.qml
```

If the installed bar was visible before testing and is still hidden, use `arctic-shell-ipc bar
toggleHidden` to restore it. Keep the user's original hidden state when it was already hidden.
Native checks require two connected outputs, Quickshell, Mango's `mmsg`, `grim`, `wtype`, a C
compiler and the Wayland client library. A successful native preview check is distinct from
verification of an installed package or after a session restart.

## Dodge windows

The same isolated entry point supports `testbar mode dodge`. `test-dodge.py` launches and
stops its own preview (do not start it separately) and exercises the real
Mango event bridge using a disposable Kitty window, empty workspaces on two outputs, and a
reversible 150% scale change on the primary output. It manages and restores the installed
bar's hidden state, output/workspace configuration and its own windows. It refuses to run
while a native polkit password prompt is open. Do not use either output or run another input
automation during the check.

```sh
python3 shell/dev/test-dodge.py \
  --preview /tmp/arctic-bar-preview/bar-test.qml \
  --pointer /tmp/arctic-test-pointer --out /tmp/arctic-dodge-results \
  --monitor eDP-1 --other-monitor HDMI-A-5
```

Checks cover clear versus overlapped space on all four edges at 100% and 150% scale, the hide
delay, physical-edge reveal, calendar popup bounds/pinning, thickness changes, inactive
workspaces, minimized windows, separate popups, press/drag/release, keyboard navigation,
fullscreen and independent outputs. Always visible and Auto-hide remain separate modes.
The bridge uses two persistent subscriptions with 60ms burst coalescing and geometry
deduplication. The companion Mango 0.17.3 package patch supplies missing floating-move/resize
events, coalesces subscriber-only notifications for 60ms, and advertises the capability.
Old Mango packages, other compositors or a disconnected bridge safely leave Dodge bars
visible; this feature targets Arctic's Mango session. Long verification runs can use
`--isolated` against a separate headless Mango with HEADLESS-* output names, so they never
contact the production shell. This is distinct from real-display verification.
Isolated runs also measure idle and movement event volume/CPU/RSS, verify the shared bridge
has exactly two subscriptions, and kill one subscription to check fail-visible recovery.
Entering a hiding mode while fullscreen remaps the bar onto the Overlay layer once; later
reveals/hides animate only content and retain the input mask throughout.
