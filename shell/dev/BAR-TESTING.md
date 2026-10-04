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
and JSON results. It resets preview state even if an assertion fails. Fractional-scale and
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
