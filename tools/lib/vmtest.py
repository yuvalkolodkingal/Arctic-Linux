"""QEMU/QMP helpers shared by the VM test harnesses (tools/test-install.sh).

Runs inside the Fedora test container (python3-pillow). A VM is one QEMU process with a QMP
socket; screenshots are PNG files written by QMP screendump; keys go in with QMP send-key
(qcodes, US layout). Every harness logs to <out>/test.log with seconds since the start.
"""
import json
import os
import socket
import subprocess
import time

from PIL import Image, ImageChops

T0 = time.time()
OUT = os.environ.get("OUT", "/out")


def log(msg):
    line = f"[{time.time() - T0:6.0f}s] {msg}"
    print(line, flush=True)
    with open(f"{OUT}/test.log", "a") as f:
        f.write(line + "\n")


class QMPError(Exception):
    pass


class VM:
    """One QEMU process. argv is the full qemu command line; it must contain
    -qmp unix:<qmp>,server=on,wait=off."""

    def __init__(self, argv, qmp_path, name):
        self.name = name
        self.qmp_path = qmp_path
        if os.path.exists(qmp_path):
            os.remove(qmp_path)
        self.proc = subprocess.Popen(argv, stdout=open(f"{OUT}/qemu-{name}.log", "w"), stderr=subprocess.STDOUT)
        log(f"[{name}] qemu started: {' '.join(argv)}")
        self.s = None
        for _ in range(300):
            try:
                s = socket.socket(socket.AF_UNIX)
                s.connect(qmp_path)
                self.s = s
                break
            except OSError:
                if self.proc.poll() is not None:
                    raise SystemExit(f"qemu exited: see qemu-{name}.log")
                time.sleep(0.2)
        if self.s is None:
            raise SystemExit("no QMP socket")
        self.f = self.s.makefile("rw")
        json.loads(self.f.readline())
        self.cmd("qmp_capabilities")

    def alive(self):
        return self.proc.poll() is None

    def cmd(self, name, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        try:
            self.f.write(json.dumps(msg) + "\n")
            self.f.flush()
            while True:
                line = self.f.readline()
                if not line:
                    raise QMPError("QMP closed")
                reply = json.loads(line)
                if "return" in reply or "error" in reply:
                    return reply
        except (OSError, ValueError) as e:
            raise QMPError(str(e))

    def shot(self, name):
        """Screendump to <out>/<name>.png; returns the path or None."""
        path = f"{OUT}/{name}.png"
        if not self.alive():
            return None
        try:
            r = self.cmd("screendump", filename=path, format="png")
        except QMPError as e:
            log(f"screendump failed: {e}")
            return None
        if "error" in r:
            log(f"screendump failed: {r['error']}")
            return None
        return path

    def keys(self, *names, gap=0.3):
        """Press keys one after the other; "ctrl-x" style names press a chord."""
        for k in names:
            chord = k.split("-") if len(k) > 1 and "-" in k else [k]
            self.cmd("send-key", keys=[{"type": "qcode", "data": c} for c in chord])
            time.sleep(gap)

    def type_text(self, text, gap=0.15):
        for ch in text:
            self.cmd("send-key", keys=[{"type": "qcode", "data": c} for c in chord_for(ch)], **{"hold-time": 40})
            time.sleep(gap)

    def quit(self):
        if self.alive():
            try:
                self.cmd("quit")
            except QMPError:
                pass
        try:
            self.proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    def wait_exit(self, timeout):
        try:
            self.proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False


QCODE = {" ": "spc", "=": "equal", ",": "comma", ".": "dot", "-": "minus", "/": "slash",
         ";": "semicolon", "'": "apostrophe", "\\": "backslash", "`": "grave_accent",
         "[": "bracket_left", "]": "bracket_right", "\n": "ret"}
SHIFTED = {"_": "minus", ":": "semicolon", "+": "equal", '"': "apostrophe", ">": "dot",
           "<": "comma", "|": "backslash", "&": "7", "*": "8", "(": "9", ")": "0", "$": "4",
           "~": "grave_accent", "!": "1", "@": "2", "#": "3", "%": "5", "^": "6",
           "{": "bracket_left", "}": "bracket_right", "?": "slash"}


def chord_for(ch):
    if ch.isalnum() and ch.isascii():
        return ["shift", ch.lower()] if ch.isupper() else [ch]
    if ch in QCODE:
        return [QCODE[ch]]
    if ch in SHIFTED:
        return ["shift", SHIFTED[ch]]
    raise SystemExit(f"cannot type {ch!r}")


# ---- serial log ----------------------------------------------------------------------------

def serial_has(path, marker):
    """True when the (binary-safe) serial log contains marker."""
    try:
        with open(path, "rb") as f:
            return marker.encode() in f.read()
    except OSError:
        return False


def serial_value(path, prefix):
    """The rest of the last line starting with prefix (e.g. "ARCTIC-INSTALL-EXIT=")."""
    try:
        with open(path, "rb") as f:
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    val = None
    for line in data.replace("\r", "\n").split("\n"):
        i = line.find(prefix)
        if i >= 0:
            val = line[i + len(prefix):].strip()
    return val


# ---- screen heuristics ---------------------------------------------------------------------

AMBER = (246, 189, 85)   # the Arctic accent (#f6bd55): GRUB selection, Plymouth entry, SDDM


def _is_amber(p):
    r, g, b = p
    return abs(r - AMBER[0]) < 30 and abs(g - AMBER[1]) < 38 and abs(b - AMBER[2]) < 45


def amber_runs(path, scale=2):
    """Per row (every `scale`-th row and column): the longest run of amber pixels, in
    full-resolution pixels."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    small = im.resize((max(1, w // scale), max(1, h // scale)), Image.NEAREST)
    px = small.load()
    sw, sh = small.size
    runs = []
    for y in range(sh):
        best = cur = 0
        for x in range(sw):
            if _is_amber(px[x, y]):
                cur += 1
                if cur > best:
                    best = cur
            else:
                cur = 0
        runs.append(best * scale)
    return runs, scale


def classify(path):
    """A rough guess of what is on screen (sizes as drawn at 1920x1080, the virtio-vga mode):
    "grub"   the arctic GRUB theme: a filled amber selection bar (~420x40 px);
    "login"  the SDDM card: a filled amber button (44x44 px) next to the focused, amber-edged
             password field;
    "prompt" the Plymouth passphrase prompt: a thin amber-edged entry box (~400 px), no button;
    "dark"   almost black; else "other"."""
    try:
        im = Image.open(path).convert("L")
    except OSError:
        return "none"
    small = im.resize((64, 36))
    mean = sum(small.getdata()) / (64 * 36)
    runs, scale = amber_runs(path)
    long_rows = sum(scale for r in runs if r >= 200)      # rows (full-res) with a long amber line
    button_rows = sum(scale for r in runs if 36 <= r <= 80)
    if long_rows >= 24:
        return "grub"
    if button_rows >= 24:
        return "login"
    if 1 <= long_rows <= 16:
        return "prompt"
    if mean < 6:
        return "dark"
    return "other"


def looks_like_boot_menu(path):
    """The arctic GRUB theme (an amber selection bar) or GRUB's text menu (a light bar)."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w < 320:
        return False
    small = im.resize((w // 4, h // 4))
    px = small.load()
    sw, sh = small.size
    amber = 0
    bar_rows = 0
    for y in range(sh):
        bright = 0
        for x in range(sw):
            r, g, b = px[x, y]
            if abs(r - 246) < 30 and abs(g - 189) < 35 and abs(b - 85) < 40:
                amber += 1
            if r > 150 and g > 150 and b > 150:
                bright += 1
        if bright > sw * 0.6:
            bar_rows += 1
    return amber > 400 or 2 <= bar_rows <= sh // 6


def changed_fraction(a, b):
    """Fraction of pixels that differ noticeably between two screenshots (0..1)."""
    try:
        ia = Image.open(a).convert("L")
        ib = Image.open(b).convert("L")
    except OSError:
        return 1.0
    if ia.size != ib.size:
        return 1.0
    ia = ia.resize((ia.width // 4, ia.height // 4))
    ib = ib.resize((ib.width // 4, ib.height // 4))
    diff = ImageChops.difference(ia, ib).point(lambda v: 255 if v > 24 else 0)
    hist = diff.histogram()
    return hist[255] / (ia.width * ia.height)
