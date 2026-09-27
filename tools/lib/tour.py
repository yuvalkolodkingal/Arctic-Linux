"""Screenshot tour of Arctic Linux for the wiki (driver for tools/screenshot-tour.sh).

Runs in the Fedora test container next to vmtest.py (QMP screendump, key presses). Two boots:

  live       the ISO, "Try Arctic Linux" (UEFI): the boot menu, the splash, the live desktop and
             the shell's surfaces driven with real key presses over QMP (Super = meta_l), a
             terminal, tiled windows, the Winter theme, Zen, then the installer UI against the
             engine's demo mode (`arctic-install bridge --mock`, ARCTIC_INSTALLER_MOCK=1),
             walked step by step through its IPC target (`quickshell ipc … call installer`).
  installed  a copy of a disk tools/test-install.sh installed: the disk passphrase prompt,
             the login screen, the desktop and the lock screen.

Final PNGs (1280 px wide, optimised to < 400 KB) go to $IMAGES; raw screendumps, test.log and
manifest.json to $OUT.

Guest control: in the live session the tour opens a terminal once and starts tour-agent.sh
(fetched from this driver's HTTP server at 10.0.2.2, QEMU user networking's address for the
host), then closes the terminal. The agent long-polls for shell commands and posts their
output back, so the tour can seed caches, start apps and the demo installer and read the
installer's state without guessing with sleeps. Screenshots are always of the real screen.

Development: with HOLD=<seconds> the VM stays up at the end of a phase (or after a failure)
and takes commands from the host:
    python3 tools/lib/tour.py ctl out/tour shot NAME | keys meta_l-spc … | type TEXT |
                                 click X Y | park | agent 'shell command' | save RAW NAME |
                                 settle TAG | release
"""
import http.server
import json
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vmtest  # noqa: E402
from vmtest import log  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

E = os.environ
OUT = vmtest.OUT
MAX_BYTES = 400 * 1024
W, H = 1280, 800          # the guest's desktop mode (virtio-gpu default)

LIVE_STEPS = ["boot-menu", "boot-splash", "live-welcome", "live-desktop", "osd-volume",
              "launcher", "launcher-calculator", "wallpapers", "get-apps", "power-menu", "keys",
              "terminal-fetch", "tiling", "theme-winter", "zen-browser", "installer"]
INSTALLER_SHOTS = ["installer-01-welcome", "installer-02-keyboard", "installer-03-network",
                   "installer-04-timezone", "installer-05-disk", "installer-06-encryption",
                   "installer-07-account", "installer-08-apps", "installer-09-summary",
                   "installer-10-installing", "installer-11-attention", "installer-12-done"]
INSTALLED_STEPS = ["luks-prompt", "sddm-login", "installed-desktop", "lock-screen"]


class TourError(Exception):
    pass


# ---- image helpers -------------------------------------------------------------------------

def _amber_mask(im):
    r, g, b = im.split()
    mr = r.point(lambda v: 255 if abs(v - 246) < 30 else 0)
    mg = g.point(lambda v: 255 if abs(v - 189) < 38 else 0)
    mb = b.point(lambda v: 255 if abs(v - 85) < 45 else 0)
    return ImageChops.multiply(ImageChops.multiply(mr, mg), mb)


def amber_box(path, box):
    """(count, bbox in screen coordinates or None) of amber (#f6bd55) pixels inside box."""
    try:
        im = Image.open(path).convert("RGB")
    except OSError:
        return 0, None
    if box:
        im = im.crop(box)
    m = _amber_mask(im)
    bb = m.getbbox()
    if bb and box:
        bb = (bb[0] + box[0], bb[1] + box[1], bb[2] + box[0], bb[3] + box[1])
    return m.histogram()[255], bb


def mean(path):
    im = Image.open(path).convert("L").resize((64, 40))
    return sum(im.histogram()[i] * i for i in range(256)) / (64 * 40)


def size(path):
    return Image.open(path).size


def busy(path, box):
    """Standard deviation of the luminance in box: ~0 for an empty panel, high for pictures."""
    from PIL import ImageStat
    return ImageStat.Stat(Image.open(path).convert("L").crop(box)).stddev[0]


def region_diff(a, b, box):
    ia = Image.open(a).convert("L").crop(box)
    ib = Image.open(b).convert("L").crop(box)
    d = ImageChops.difference(ia, ib).point(lambda v: 255 if v > 24 else 0)
    return d.histogram()[255] / max(1, ia.width * ia.height)


def fox(path):
    """The Plymouth splash: a compact, mostly filled white fox mark on a dark screen.
    Returns {"count", "centered", "w", "cx"} or None."""
    im = Image.open(path).convert("L")
    w, h = im.size
    m = im.point(lambda v: 255 if v > 225 else 0)
    bb = m.getbbox()
    cnt = m.histogram()[255]
    if not bb or cnt < 0.004 * w * h:
        return None
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    if bw > 0.3 * w or bh > 0.4 * h or cnt < 0.3 * bw * bh:
        return None          # text, a menu or a desktop, not the mark
    cx = (bb[0] + bb[2]) / 2
    return {"count": cnt, "centered": abs(cx - w / 2) < 0.04 * w, "w": w, "cx": cx}


def amber_block(path, box, min_row=100):
    """Bounding box (screen coordinates) of a solid amber block inside box: the rows with at
    least min_row amber pixels, and the columns amber in at least a third of those rows (so
    anti-aliased text and small marks around it don't count). None when there is none."""
    try:
        im = Image.open(path).convert("RGB").crop(box)
    except OSError:
        return None
    m = _amber_mask(im)
    wd, ht = m.size
    data = m.tobytes()
    rows = [y for y in range(ht) if data[y * wd:(y + 1) * wd].count(255) >= min_row]
    if len(rows) < 8:
        return None
    y0, y1 = rows[0], rows[-1]
    cols = [x for x in range(wd) if sum(1 for y in rows if data[y * wd + x] == 255) >= len(rows) / 3]
    if not cols:
        return None
    return (cols[0] + box[0], y0 + box[1], cols[-1] + 1 + box[0], y1 + 1 + box[1])


def bar_up(path):
    """The shell's top bar is drawn: the amber pill of workspace 1 at the top left (dark theme)."""
    if size(path) != (W, H):
        return False
    n, _ = amber_box(path, (36, 2, 90, 32))
    return n > 120


def welcome_card(path):
    """The live welcome card: the bounding box of its amber "Install Arctic Linux" button."""
    if size(path) != (W, H):
        return None
    return amber_block(path, (380, 300, 900, 620), min_row=100)


def save_png(src, dst, resize=None):
    im = Image.open(src).convert("RGB")
    if resize and im.size != resize:
        im = im.resize(resize, Image.LANCZOS)
    tmp = dst + ".tmp.png"
    im.save(tmp, optimize=True)
    if os.path.getsize(tmp) > MAX_BYTES:
        for colors in (256, 192, 128):
            im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                        dither=Image.Dither.FLOYDSTEINBERG).save(tmp, optimize=True)
            if os.path.getsize(tmp) <= MAX_BYTES:
                break
    os.replace(tmp, dst)
    return os.path.getsize(dst)


# ---- the guest agent's HTTP server ----------------------------------------------------------

class Agent:
    """HTTP server for tour-agent.sh in the guest: GET /agent (the script), GET /next (long
    poll: "<id>\\n<shell command>"), POST /result/<id> ("<rc>\\n<output>"), POST /hello,
    GET /file/<name> (files the tour hands to the guest)."""

    def __init__(self, port, files):
        self.port = port
        self.files = files
        self.q = queue.Queue()
        self.results = {}
        self.cv = threading.Condition()
        self.hello = threading.Event()
        self.hello_info = ""
        self.n = 0
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "tour-agent.sh")) as f:
            self.script = f.read().replace("@HOST@", f"10.0.2.2:{port}")
        agent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, body, code=200):
                if isinstance(body, str):
                    body = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/agent":
                    self.reply(agent.script)
                elif self.path == "/next":
                    try:
                        i, cmd = agent.q.get(timeout=45)
                    except queue.Empty:
                        self.reply("")
                        return
                    try:
                        self.reply(f"{i}\n{cmd}\n")
                    except OSError:
                        agent.q.put((i, cmd))
                elif self.path.startswith("/file/"):
                    p = agent.files.get(os.path.basename(self.path[6:]))
                    if not p or not os.path.exists(p):
                        self.reply("not found", 404)
                        return
                    with open(p, "rb") as f:
                        self.reply(f.read())
                else:
                    self.reply("not found", 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode("utf-8", "replace")
                if self.path == "/hello":
                    agent.hello_info = body
                    agent.hello.set()
                    self.reply("ok")
                elif self.path.startswith("/result/"):
                    rc, _, out = body.partition("\n")
                    rc = rc.strip()
                    with agent.cv:
                        agent.results[int(self.path[8:])] = (int(rc) if rc.lstrip("-").isdigit() else -1, out)
                        agent.cv.notify_all()
                    self.reply("ok")
                else:
                    self.reply("not found", 404)

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def run(self, cmd, timeout=180, check=False):
        if not self.hello.is_set():
            raise TourError("the guest agent isn't running")
        self.n += 1
        i = self.n
        self.q.put((i, cmd))
        deadline = time.time() + timeout
        with self.cv:
            while i not in self.results:
                left = deadline - time.time()
                if left <= 0:
                    raise TourError(f"agent: no answer to {cmd[:80]!r} within {timeout}s")
                self.cv.wait(left)
            rc, out = self.results.pop(i)
        if check and rc != 0:
            raise TourError(f"agent: {cmd[:80]!r} failed ({rc}): {out[-400:]}")
        return rc, out

    def close(self):
        self.srv.shutdown()


# ---- the tour --------------------------------------------------------------------------------

class Tour:
    def __init__(self):
        self.images = E["IMAGES"]
        self.only = set(filter(None, E.get("ONLY", "").split(",")))
        self.skip = set(filter(None, E.get("SKIP", "").split(",")))
        self.hold_secs = int(E.get("HOLD", "0") or 0)
        self.memory, self.smp, self.accel = E.get("MEMORY", "6144"), E.get("SMP", "4"), E.get("ACCEL", "tcg,thread=multi")
        self.port = int(E.get("PORT", "18765"))
        self.launcher_query = E.get("LAUNCHER_QUERY", "te")
        self.vm = None
        self.agent = None
        self.n = 0
        self.flip = 0
        self.manifest = {}
        self.skipped = {}
        os.makedirs(f"{OUT}/raw", exist_ok=True)
        os.makedirs(self.images, exist_ok=True)
        mf = f"{OUT}/manifest.json"
        if os.path.exists(mf):
            try:
                with open(mf) as f:
                    old = json.load(f)
                self.manifest, self.skipped = old.get("images", {}), old.get("skipped", {})
            except (OSError, ValueError):
                pass

    # -- selection
    def want(self, name):
        group = "installer" if name.startswith("installer-") else name
        if name in self.skip or group in self.skip:
            return False
        return not self.only or name in self.only or group in self.only

    def want_any(self, names):
        return any(self.want(n) for n in names)

    # -- VM
    def qemu_argv(self, name, iso=None, disk=None, vars_path=None):
        a = ["qemu-system-x86_64", "-machine", "q35", "-accel", self.accel, "-cpu", "max",
             "-smp", self.smp, "-m", self.memory, "-display", "none", "-vga", "virtio",
             "-qmp", f"unix:{OUT}/qmp-{name}.sock,server=on,wait=off",
             "-serial", f"file:{OUT}/serial-{name}.log", "-monitor", "none", "-no-reboot",
             "-netdev", "user,id=net0", "-device", "virtio-net-pci,netdev=net0",
             "-device", "qemu-xhci", "-device", "usb-tablet", "-rtc", "base=utc"]
        if E.get("AUDIO") == "1":
            # A sound card, so PipeWire has a sink: the volume keys and their OSD work.
            a += ["-audiodev", "none,id=snd0", "-device", "ich9-intel-hda",
                  "-device", "hda-output,audiodev=snd0"]
        if iso:
            a += ["-drive", f"file={iso},media=cdrom,readonly=on,if=none,id=cd",
                  "-device", "ide-cd,drive=cd,bootindex=0"]
        if disk:
            a += ["-drive", f"file={disk},if=none,id=disk,discard=unmap",
                  "-device", "virtio-blk-pci,drive=disk,bootindex=1"]
        if vars_path is None:
            vars_path = f"{OUT}/OVMF_VARS-{name}.fd"
            shutil.copy("/usr/share/edk2/ovmf/OVMF_VARS.fd", vars_path)
        a += ["-drive", "if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
              "-drive", f"if=pflash,format=raw,unit=1,file={vars_path}"]
        return a

    # -- screen
    def probe(self):
        """A screendump that is overwritten by the next-but-one probe."""
        self.flip ^= 1
        p = self.vm.shot(f"probe-{self.flip}")
        if p is None:
            raise TourError("screendump failed (is the VM still running?)")
        return p

    def keep(self, path, tag):
        self.n += 1
        dst = f"{OUT}/raw/{self.n:04d}-{tag}.png"
        shutil.copy(path, dst)
        return dst

    def grab(self, tag):
        return self.keep(self.probe(), tag)

    def settle(self, tag, timeout=90, interval=2.0, thresh=0.002, need=2):
        """Screendumps until `need` consecutive ones barely differ; keeps and returns the last."""
        t = time.time()
        prev = self.probe()
        stable = 0
        cur = prev
        while time.time() - t < timeout:
            time.sleep(interval)
            cur = self.probe()
            if vmtest.changed_fraction(prev, cur) < thresh:
                stable += 1
                if stable >= need:
                    return self.keep(cur, tag)
            else:
                stable = 0
            prev = cur
        log(f"{tag}: the screen did not settle within {timeout}s; using the last frame")
        return self.keep(cur, tag)

    def wait_for(self, pred, what, timeout, every=2.0):
        t = time.time()
        while time.time() - t < timeout:
            if not self.vm.alive():
                raise TourError(f"the VM stopped while waiting for {what}")
            p = self.probe()
            try:
                ok = pred(p)
            except OSError:
                ok = False
            if ok:
                log(f"{what}: on screen after {time.time() - t:.0f}s")
                return p
            time.sleep(every)
        return None

    def wait_change(self, base, what, timeout=60, thresh=0.01, every=1.0):
        return self.wait_for(lambda p: vmtest.changed_fraction(base, p) >= thresh, what, timeout, every)

    def save(self, raw, name, resize=None, note=""):
        if not self.want(name):
            return
        dst = f"{self.images}/{name}.png"
        n = save_png(raw, dst, resize)
        self.manifest[name] = {"raw": os.path.basename(raw), "bytes": n, "note": note,
                               "size": list(Image.open(dst).size),
                               "taken": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.skipped.pop(name, None)
        log(f"saved {name}.png ({n // 1024} KB){' - ' + note if note else ''}")
        self.write_manifest()

    def skipped_because(self, name, why):
        if self.want(name):
            self.skipped[name] = why
            log(f"skipped {name}: {why}")
            self.write_manifest()

    def write_manifest(self):
        with open(f"{OUT}/manifest.json", "w") as f:
            json.dump({"images": self.manifest, "skipped": self.skipped}, f, indent=2, sort_keys=True)

    # -- input
    def pointer(self, x, y):
        self.vm.cmd("input-send-event", events=[
            {"type": "abs", "data": {"axis": "x", "value": int(x * 0x7FFF / (W - 1))}},
            {"type": "abs", "data": {"axis": "y", "value": int(y * 0x7FFF / (H - 1))}}])

    def click(self, x, y):
        self.pointer(x, y)
        time.sleep(0.4)
        self.vm.cmd("input-send-event", events=[{"type": "btn", "data": {"down": True, "button": "left"}}])
        time.sleep(0.15)
        self.vm.cmd("input-send-event", events=[{"type": "btn", "data": {"down": False, "button": "left"}}])

    def park(self):
        """The pointer to the bottom-right corner, where it hides (the bottom-left one is
        Mango's hot corner for the overview)."""
        self.pointer(W - 1, H - 1)

    def dismiss(self, base, what, key="esc", tries=4):
        """Press Esc until the screen is back to `base` (the desktop before a popup)."""
        for _ in range(tries):
            self.vm.keys(key)
            if self.wait_for(lambda p: vmtest.changed_fraction(base, p) < 0.01, f"{what} closed", 12, 1.0):
                return True
        log(f"warning: {what} did not close")
        return False

    # -- guest agent
    def start_agent(self):
        if self.agent and self.agent.hello.is_set():
            return
        files = {n: f"{OUT}/{n}" for n in ("packages.txt", "flathub.txt") if os.path.exists(f"{OUT}/{n}")}
        if not self.agent:
            self.agent = Agent(self.port, files)
        cmd = (f"curl -fsSo /tmp/tour-agent.sh 10.0.2.2:{self.port}/agent && "
               "setsid -f bash /tmp/tour-agent.sh >/tmp/tour-agent.log 2>&1 </dev/null; exit")
        for attempt in (1, 2, 3):
            base = self.settle("before-agent", timeout=30, need=1)
            self.vm.keys("meta_l-ret")
            if not self.wait_change(base, "a terminal", 90):
                log(f"agent: no terminal opened (attempt {attempt})")
                continue
            self.settle("agent-terminal", timeout=60, need=2)
            self.vm.type_text(cmd, gap=0.12)
            self.vm.keys("ret")
            if self.agent.hello.wait(90):
                log(f"agent: running in the guest ({self.agent.hello_info})")
                self.wait_for(lambda p: vmtest.changed_fraction(base, p) < 0.01, "the terminal closed", 30)
                return
            log(f"agent: no hello from the guest (attempt {attempt})")
            self.vm.keys("meta_l-q")
            time.sleep(5)
        raise TourError("could not start the guest agent")

    def sh(self, cmd, timeout=180, check=True):
        rc, out = self.agent.run(cmd, timeout=timeout, check=check)
        return out

    # -- development: take commands from the host while holding the VM
    def hold(self, why):
        if self.hold_secs <= 0 or not self.vm or not self.vm.alive():
            return
        ctl = f"{OUT}/ctl"
        os.makedirs(ctl, exist_ok=True)
        log(f"holding the VM ({why}) for {self.hold_secs}s: python3 tools/lib/tour.py ctl {OUT} <op> …")
        end = time.time() + self.hold_secs
        while time.time() < end and self.vm.alive():
            for f in sorted(os.listdir(ctl)):
                if not f.endswith(".req"):
                    continue
                with open(f"{ctl}/{f}") as fh:
                    req = json.load(fh)
                os.remove(f"{ctl}/{f}")
                try:
                    res = self.ctl_op(req)
                except Exception as e:  # noqa: BLE001 - report anything back to the caller
                    res = {"error": f"{type(e).__name__}: {e}"}
                if res.get("release"):
                    end = 0
                with open(f"{ctl}/{f[:-4]}.res.tmp", "w") as fh:
                    json.dump(res, fh)
                os.replace(f"{ctl}/{f[:-4]}.res.tmp", f"{ctl}/{f[:-4]}.res")
            time.sleep(0.3)

    def ctl_op(self, req):
        op, args = req["op"], req.get("args", [])
        if op == "shot":
            return {"path": self.grab(args[0] if args else "ctl")}
        if op == "keys":
            self.vm.keys(*args)
            return {"ok": True}
        if op == "type":
            self.vm.type_text(" ".join(args))
            return {"ok": True}
        if op == "click":
            self.click(int(args[0]), int(args[1]))
            return {"ok": True}
        if op == "park":
            self.park()
            return {"ok": True}
        if op == "agent":
            rc, out = self.agent.run(" ".join(args), timeout=300)
            return {"rc": rc, "out": out}
        if op == "settle":
            return {"path": self.settle(args[0] if args else "ctl")}
        if op == "save":
            self.save(args[0], args[1], note="(ctl)")
            return {"ok": True}
        if op == "release":
            return {"release": True}
        if op == "eval":
            return {"out": repr(eval(" ".join(args), {"tour": self, "vmtest": vmtest}))}  # noqa: S307 - dev only
        return {"error": f"unknown op {op}"}

    # ================================================================ live phase
    def phase_live(self):
        iso = E["ISO"]
        self.vm = vmtest.VM(self.qemu_argv("live", iso=iso), f"{OUT}/qmp-live.sock", "live",
                            qemu_log=f"{OUT}/qemu-live.log")
        try:
            self.live_boot()
            self.live_desktop()
            for name, fn in (("osd-volume", self.osd_volume), ("launcher", self.launcher),
                             ("launcher-calculator", self.launcher_calc), ("wallpapers", self.wallpapers),
                             ("get-apps", self.get_apps), ("power-menu", self.power_menu), ("keys", self.keys_sheet)):
                if self.want(name):
                    self.run_step(name, fn)
            if self.want_any(["terminal-fetch", "tiling", "theme-winter"]):
                self.run_step("terminal-fetch", self.windows)
            if self.want("zen-browser"):
                self.run_step("zen-browser", self.zen)
            if self.want("installer"):
                self.run_step("installer", self.installer_demo)
            self.hold("end of the live phase")
        except Exception:
            log("live phase failed")
            self.grab("failure")
            self.hold("failure")
            raise
        finally:
            if self.agent:
                self.agent.close()
                self.agent = None
            self.vm.quit()

    def run_step(self, name, fn):
        """A failed optional step is logged (and its screenshot left out); the tour goes on."""
        try:
            fn()
        except TourError as e:
            log(f"step {name} failed: {e}")
            self.grab(f"{name}-failed")
            self.skipped.setdefault(name, f"failed: {e}")
            self.write_manifest()

    def live_boot(self):
        # 1. The boot menu (drawn at the firmware's 1920x1080 mode; scaled to 1280x720).
        p = self.wait_for(vmtest.looks_like_boot_menu, "the boot menu", 300, 1.0)
        if not p:
            raise TourError("no boot menu")
        time.sleep(1.5)
        p = self.grab("boot-menu")
        w, h = size(p)
        self.save(p, "boot-menu", resize=(1280, round(1280 * h / w)))
        self.vm.keys("ret")
        log("booting 'Try Arctic Linux'")
        # 2. The splash, until the desktop's bar is up. The fox is looked for in every frame;
        #    a centred one is preferred (see the notes in the manifest).
        t = time.time()
        found = []
        while time.time() - t < 1200:
            if not self.vm.alive():
                raise TourError("the VM stopped while booting")
            p = self.probe()
            f = None if vmtest.looks_like_boot_menu(p) else fox(p)
            if f and sum(1 for x in found if x[1]["w"] == f["w"] and x[1]["centered"] == f["centered"]) < 4:
                found.append((self.keep(p, f"splash-{f['w']}-{'c' if f['centered'] else 'off'}"), f))
            if bar_up(p):
                log(f"desktop bar up after {time.time() - t:.0f}s")
                break
            time.sleep(1.5)
        else:
            raise TourError("the live desktop did not come up in 20 min")
        if found:
            def rank(item):
                f = item[1]
                return (f["centered"], f["w"] == W, f["count"])
            best, f = max(found, key=rank)
            note = "" if f["centered"] else f"fox drawn off-centre (x={f['cx']:.0f} of {f['w']})"
            bw, bh = size(best)
            self.save(best, "boot-splash", resize=(1280, round(1280 * bh / bw)), note=note)
            log("splash frames: " + ", ".join(f"{os.path.basename(p)} centred={x['centered']}" for p, x in found))
        else:
            self.skipped_because("boot-splash", "no splash frame with the fox was seen")

    def live_desktop(self):
        # 3. The welcome card ("You're trying Arctic Linux") on the settled desktop.
        p = self.wait_for(welcome_card, "the welcome card", 240, 3.0)
        self.park()
        if not p:
            log("warning: no welcome card seen")
        p = self.settle("live-welcome", timeout=120, interval=3, need=2)
        card = welcome_card(p)
        if card:
            self.save(p, "live-welcome")
            # 4. Keep trying: the text button right of the amber Install button.
            x, y = card[2] + 68, (card[1] + card[3]) // 2
            for attempt in (1, 2):
                self.click(x, y)
                self.park()
                if self.wait_for(lambda q: not welcome_card(q), "the card closed", 90, 2.0):
                    break
                log(f"the welcome card is still open after clicking Keep trying (attempt {attempt})")
        else:
            self.skipped_because("live-welcome", "the welcome card was not on screen")
        time.sleep(3)
        p = self.settle("live-desktop", timeout=60, need=2)
        self.save(p, "live-desktop")
        self.desktop = p

    def osd_volume(self):
        base = self.settle("osd-base", timeout=30, need=1)
        box = (440, 640, 840, 790)          # the OSD pill: bottom centre, 44 px above the edge
        best, best_d = None, 0.0
        for attempt in (1, 2, 3):
            self.vm.keys("volumeup")
            t = time.time()
            frames = []
            while time.time() - t < 20:
                p = self.grab("osd")
                d = region_diff(base, p, box)
                frames.append((p, d))
                if d > best_d:
                    best, best_d = p, d
                # Seen, and it has had time to finish its entrance: stop.
                if best_d > 0.05 and d < best_d * 0.5:
                    break
                time.sleep(0.1)
            for p, _ in frames:
                if p != best:
                    os.remove(p)
            if best_d > 0.05:
                break
            log(f"osd: nothing seen after the volume key (attempt {attempt})")
            time.sleep(3)
        if best_d > 0.05:
            self.save(best, "osd-volume")
        else:
            raise TourError("the volume OSD did not appear")

    def type_checked(self, text, region, what, tries=3):
        """Type into the focused field and check that the region changed (under TCG a surface
        that has just opened can miss the first keys); clears the field and types again if not."""
        before = self.probe()
        before = shutil.copy(before, f"{OUT}/type-before.png")
        for attempt in range(1, tries + 1):
            self.vm.type_text(text, gap=0.2)
            if self.wait_for(lambda p: region_diff(before, p, region) > 0.02, f"{what}: typed text", 30, 1.0):
                return True
            log(f"{what}: the typed text didn't show (attempt {attempt}); typing again")
            self.vm.keys(*(["ctrl-a", "backspace"]))
            time.sleep(2)
        return False

    def popup(self, name, chord, what, typed=None, field=None, ready=None, timeout=120, settle_timeout=90):
        """Open a shell surface with its shortcut (optionally type into its field), wait until it
        shows what it should (ready(path)), screenshot it and close it again with Esc."""
        base = self.settle(f"{name}-base", timeout=30, need=1)
        self.vm.keys(chord)
        if not self.wait_change(base, what, timeout):
            raise TourError(f"{what} did not open ({chord})")
        self.settle(f"{name}-open", timeout=30, interval=1.5, need=2)
        time.sleep(2)
        if typed:
            if not self.type_checked(typed, field or (0, 0, W, H), what):
                raise TourError(f"{what}: typing {typed!r} had no effect")
        if ready and not self.wait_for(ready, f"{what} ready", settle_timeout, 3.0):
            log(f"warning: {what} never looked ready")
        p = self.settle(name, timeout=settle_timeout, interval=2, need=2)
        self.save(p, name)
        self.dismiss(base, what)

    # The launcher's search field, just under the bar (it hangs from the bar's left end).
    LAUNCHER_FIELD = (30, 50, 530, 100)

    def launcher(self):
        self.popup("launcher", "meta_l-spc", "the launcher", typed=self.launcher_query, field=self.LAUNCHER_FIELD)

    def launcher_calc(self):
        self.popup("launcher-calculator", "meta_l-spc", "the launcher", typed="=12*4", field=self.LAUNCHER_FIELD)

    def wallpapers(self):
        # Thumbnails are made on first open (Pillow, slow under TCG): wait until the grid below
        # the search field has pictures in it (it reads "Loading your wallpapers…" until then).
        def grid_filled(p):
            return busy(p, (42, 190, 874, 600)) > 12
        self.popup("wallpapers", "meta_l-shift-w", "the wallpaper picker", ready=grid_filled, settle_timeout=400)

    def get_apps(self):
        # The VM has no internet: the console's package index (normally `dnf5 repoquery` and
        # `flatpak remote-ls flathub`, cached in ~/.cache/arctic) is seeded with the real
        # Fedora 44 / Flathub name lists fetched by screenshot-tour.sh on the host.
        self.start_agent()
        seeded = []
        for n in ("packages.txt", "flathub.txt"):
            if os.path.exists(f"{OUT}/{n}"):
                self.sh(f"mkdir -p ~/.cache/arctic && curl -fsS -o ~/.cache/arctic/{n} 10.0.2.2:{self.port}/file/{n} && touch ~/.cache/arctic/{n}")
                seeded.append(n)
        log(f"get-apps: seeded {seeded or 'nothing'}")
        self.popup("get-apps", "meta_l-shift-a", "Get apps", typed=E.get("GETAPPS_QUERY", "gimp"), settle_timeout=120)

    def power_menu(self):
        self.popup("power-menu", "meta_l-esc", "the power menu")

    def keys_sheet(self):
        self.popup("keys", "meta_l-slash", "the shortcut sheet")

    def windows(self):
        """terminal-fetch, tiling and theme-winter: kitty with the fox greeting, a second kitty
        and Thunar tiled, then the same desktop in the Winter theme."""
        base = self.settle("term-base", timeout=30, need=1)
        self.vm.keys("meta_l-ret")
        if not self.wait_change(base, "a terminal", 90):
            raise TourError("no terminal opened")
        self.settle("term-open", timeout=60, need=2)
        # The live user's shell is bash (no greeting); the greeting is `arctic-fetch`.
        self.vm.type_text("clear; arctic-fetch", gap=0.15)
        self.vm.keys("ret")
        time.sleep(8)
        p = self.settle("terminal-fetch", timeout=120, interval=2, need=3)
        self.save(p, "terminal-fetch")
        if not self.want_any(["tiling", "theme-winter"]):
            self.vm.keys("meta_l-q")
            return
        self.start_agent_if_needed_quietly()
        cur = self.probe()
        self.vm.keys("meta_l-ret")
        self.wait_change(cur, "a second terminal", 90, thresh=0.05)
        self.settle("term2-open", timeout=60, need=2)
        self.vm.type_text("cat /etc/os-release", gap=0.15)
        self.vm.keys("ret")
        time.sleep(3)
        cur = self.settle("term2", timeout=30, need=1)
        if self.agent and self.agent.hello.is_set():
            self.sh("setsid -f arctic-open files >/dev/null 2>&1 </dev/null; echo ok")
        else:
            self.vm.keys("meta_l-spc")
            time.sleep(3)
            self.vm.type_text("files", gap=0.2)
            time.sleep(2)
            self.vm.keys("ret")
        self.wait_change(cur, "the file manager", 120, thresh=0.05)
        time.sleep(5)
        p = self.settle("tiling", timeout=120, interval=2, need=3)
        self.save(p, "tiling")
        if self.want("theme-winter"):
            cur = p
            self.vm.keys("meta_l-shift-t")
            self.wait_change(cur, "the Winter theme", 60, thresh=0.2)
            time.sleep(5)
            p = self.settle("theme-winter", timeout=120, interval=2, need=3)
            self.save(p, "theme-winter")
            self.vm.keys("meta_l-shift-t")
            self.wait_change(p, "Polar night again", 60, thresh=0.2)
            time.sleep(5)
            self.settle("theme-back", timeout=90, need=2)
        # Close the three windows.
        for _ in range(3):
            cur = self.probe()
            self.vm.keys("meta_l-q")
            self.wait_change(cur, "a window closed", 30, thresh=0.02)
            time.sleep(2)
        self.settle("windows-closed", timeout=60, need=2)

    def start_agent_if_needed_quietly(self):
        if self.agent and self.agent.hello.is_set():
            return
        # The agent starts from a terminal of its own; keep the fetch terminal where it is by
        # doing it on workspace 5 and coming back.
        self.vm.keys("meta_l-5")
        time.sleep(3)
        try:
            self.start_agent()
        finally:
            self.vm.keys("meta_l-1")
            time.sleep(3)

    def zen(self):
        self.start_agent()
        rc, out = self.agent.run("flatpak info app.zen_browser.zen >/dev/null 2>&1 && echo yes || echo no")
        if out.strip() != "yes":
            self.skipped_because("zen-browser", "Zen Browser is not preinstalled in this ISO")
            return
        base = self.settle("zen-base", timeout=30, need=1)
        # Through the launcher, as a person would.
        self.vm.keys("meta_l-spc")
        if not self.wait_change(base, "the launcher", 60):
            raise TourError("the launcher did not open")
        time.sleep(2)
        self.vm.type_text("zen", gap=0.2)
        time.sleep(3)
        self.vm.keys("ret")
        if not self.wait_change(base, "Zen", 300, thresh=0.3, every=5):
            raise TourError("Zen did not open")
        time.sleep(20)
        p = self.settle("zen-browser", timeout=300, interval=4, need=3)
        self.save(p, "zen-browser")
        self.vm.keys("meta_l-q")
        self.wait_for(lambda q: vmtest.changed_fraction(base, q) < 0.02, "Zen closed", 60)

    # -- the installer against the engine's demo mode
    def inst(self, *args, timeout=120):
        cmd = ("pid=$(pgrep -n -f 'quickshell.*installer-ui'); [ -n \"$pid\" ] || { echo no-installer; exit 3; }; "
               "quickshell ipc --pid \"$pid\" call installer " + " ".join(shlex.quote(a) for a in args) + " 2>/dev/null")
        rc, out = self.agent.run(cmd, timeout=timeout)
        return out.strip().splitlines()[-1] if out.strip() else ""

    def state(self):
        r = self.inst("state")
        try:
            return json.loads(r)
        except ValueError:
            return {}

    def wait_state(self, pred, what, timeout=180):
        t = time.time()
        d = {}
        while time.time() - t < timeout:
            d = self.state()
            if d and pred(d):
                return d
            time.sleep(1.5)
        raise TourError(f"installer: timed out waiting for {what} (state {d})")

    def fill(self, values):
        r = self.inst("fill", json.dumps(values))
        if r != "ok":
            raise TourError(f"installer: fill {values} → {r}")

    def next(self, expect):
        for _ in range(40):
            r = self.inst("next")
            if r == "ok":
                break
            if r in ("not ready",):
                time.sleep(1.5)
                continue
            raise TourError(f"installer: next → {r} (state {self.state()})")
        self.wait_state(lambda d: d.get("page") == expect and d.get("ready"), f"page {expect}")

    def ishot(self, name, **kw):
        kw.setdefault("timeout", 60)
        kw.setdefault("interval", 1.5)
        p = self.settle(name, **kw)
        self.save(p, name, note="installer demo mode (ARCTIC_INSTALLER_MOCK=1)")

    def installer_demo(self):
        self.start_agent()
        speed = E.get("MOCK_SPEED", "0.5")
        self.sh("pkill -f 'quickshell.*installer-ui' || true", check=False)
        self.sh(f"ARCTIC_INSTALLER_MOCK=1 ARCTIC_MOCK_SPEED={speed} setsid -f arctic-installer "
                ">/tmp/tour-installer.log 2>&1 </dev/null; echo started")
        self.wait_state(lambda d: d.get("connected") and d.get("page") == "welcome" and d.get("ready"),
                        "the Welcome step", 300)
        self.park()
        self.ishot("installer-01-welcome")
        self.next("keyboard")
        self.fill({"try": "The quick arctic fox"})
        self.ishot("installer-02-keyboard")
        self.next("network")
        self.fill({"ssid": "Tundra-5G", "password": "polarnight"})
        self.wait_state(lambda d: d.get("valid") and not d.get("busy"), "the Wi-Fi connection", 90)
        time.sleep(2)
        self.ishot("installer-03-network")
        self.next("timezone")
        self.ishot("installer-04-timezone")
        self.next("disk")
        self.ishot("installer-05-disk")
        self.next("encryption")
        self.fill({"passphrase": "correct horse battery staple", "confirm": "correct horse battery staple",
                   "focus": "confirm"})
        self.wait_state(lambda d: d.get("valid"), "a valid passphrase", 60)
        self.ishot("installer-06-encryption")
        self.next("account")
        self.fill({"full_name": "Noa Levi", "password": "snowy-owl-42", "confirm": "snowy-owl-42"})
        self.wait_state(lambda d: d.get("valid"), "a valid account", 60)
        time.sleep(3)
        self.ishot("installer-07-account")
        self.next("apps")
        self.fill({"select": ["steam"]})
        self.ishot("installer-08-apps")
        self.next("summary")
        self.ishot("installer-09-summary")
        # The Summary's primary action ("Erase disk and install"): the demo engine only pretends.
        for _ in range(40):
            r = self.inst("next")
            if r == "ok":
                break
            time.sleep(1.5)
        self.wait_state(lambda d: d.get("page") == "install" and "Installing " in d.get("status", "")
                        and int((d.get("apps") or "0/0").split("/")[0] or 0) >= 2,
                        "the apps phase of the install", 400)
        p = self.grab("installer-10-installing")
        self.save(p, "installer-10-installing", note="installer demo mode (ARCTIC_INSTALLER_MOCK=1)")
        self.wait_state(lambda d: d.get("page") == "attention", "the attention view", 400)
        time.sleep(2)
        self.ishot("installer-11-attention")
        self.inst("retry")
        self.wait_state(lambda d: d.get("page") == "done" and d.get("ready"), "the Done step", 400)
        time.sleep(2)
        self.ishot("installer-12-done")

    # ================================================================ installed phase
    def phase_installed(self):
        disk, vars_path = E["DISK_COPY"], E["VARS_COPY"]
        luks, password = E["LUKS_PASSPHRASE"], E["USER_PASSWORD"]
        argv = self.qemu_argv("installed", disk=disk, vars_path=vars_path)
        argv[argv.index("virtio-blk-pci,drive=disk,bootindex=1")] = "virtio-blk-pci,drive=disk,bootindex=0"
        self.vm = vmtest.VM(argv, f"{OUT}/qmp-installed.sock", "installed", qemu_log=f"{OUT}/qemu-installed.log")
        try:
            if self.wait_for(vmtest.looks_like_boot_menu, "the installed system's boot menu", 300, 1.0):
                time.sleep(1)
                self.grab("installed-grub")
                self.vm.keys("ret")
            # The passphrase prompt: the Plymouth theme's entry (amber edge) or, failing that, a
            # screen that stays still (text prompt) once the splash is gone.
            t = time.time()
            prev, still, p = None, 0, None
            while time.time() - t < 1200:
                cur = self.probe()
                kind = vmtest.classify(cur)
                if kind == "prompt":
                    p = cur
                    break
                if prev and kind not in ("dark", "grub") and vmtest.changed_fraction(prev, cur) < 0.002:
                    still += 1
                    if still >= 4 and time.time() - t > 45:
                        p = cur
                        log("passphrase prompt: taking the still screen (no Plymouth entry seen)")
                        break
                else:
                    still = 0
                prev = shutil.copy(cur, f"{OUT}/luks-prev.png")
                time.sleep(4)
            if not p:
                raise TourError("no passphrase prompt")
            time.sleep(3)
            self.vm.type_text(luks[:9], gap=0.3)
            time.sleep(2)
            p = self.grab("luks-prompt")
            self.save(p, "luks-prompt", note=f"classify={vmtest.classify(p)}")
            self.vm.type_text(luks[9:], gap=0.3)
            self.vm.keys("ret")
            p = self.wait_for(lambda q: vmtest.classify(q) == "login", "the login screen", 1500, 10)
            if not p:
                raise TourError("no login screen")
            self.park()
            time.sleep(20)
            p = self.settle("sddm-login", timeout=120, interval=3, need=2)
            self.save(p, "sddm-login")
            self.vm.type_text(password, gap=0.25)
            self.vm.keys("ret")
            p = self.wait_for(bar_up, "the desktop", 900, 10)
            if not p:
                raise TourError("no desktop after logging in")
            self.park()
            time.sleep(30)
            p = self.settle("installed-desktop", timeout=240, interval=5, need=3)
            self.save(p, "installed-desktop")
            base = p
            self.vm.keys("meta_l-l")
            if not self.wait_change(base, "the lock screen", 120, thresh=0.2):
                raise TourError("the lock screen did not appear")
            time.sleep(5)
            self.settle("lock-open", timeout=90, interval=2, need=2)
            self.vm.type_text(password[:6], gap=0.3)
            time.sleep(1.5)
            p = self.grab("lock-screen")
            self.save(p, "lock-screen")
            self.hold("end of the installed phase")
        except Exception:
            log("installed phase failed")
            self.grab("failure")
            self.hold("failure")
            raise
        finally:
            self.vm.quit()


def ctl_main(argv):
    """Host side of HOLD: python3 tour.py ctl <work dir> <op> [args…]."""
    work, op, args = argv[0], argv[1], argv[2:]
    ctl = os.path.join(work, "ctl")
    rid = f"{time.time():.6f}"
    tmp = os.path.join(ctl, rid + ".tmp")
    with open(tmp, "w") as f:
        json.dump({"op": op, "args": args}, f)
    os.replace(tmp, os.path.join(ctl, rid + ".req"))
    res = os.path.join(ctl, rid + ".res")
    for _ in range(3600):
        if os.path.exists(res):
            with open(res) as f:
                print(json.dumps(json.load(f), indent=1))
            os.remove(res)
            return 0
        time.sleep(0.25)
    print("no answer (is the tour holding the VM?)", file=sys.stderr)
    return 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "ctl":
        sys.exit(ctl_main(sys.argv[2:]))
    tour = Tour()
    phases = E.get("PHASES", "live,installed").split(",")
    rc = 0
    if "live" in phases and tour.want_any(LIVE_STEPS + INSTALLER_SHOTS):
        try:
            tour.phase_live()
        except (TourError, vmtest.QMPError, SystemExit) as e:
            log(f"live phase: {e}")
            rc = 1
    if "installed" in phases and tour.want_any(INSTALLED_STEPS):
        if E.get("DISK_COPY"):
            try:
                tour.phase_installed()
            except (TourError, vmtest.QMPError, SystemExit) as e:
                log(f"installed phase: {e}")
                rc = 1
        else:
            for n in INSTALLED_STEPS:
                tour.skipped_because(n, E.get("NO_DISK_REASON", "no installed disk"))
    tour.write_manifest()
    for f in ("probe-0.png", "probe-1.png", "luks-prev.png"):
        if os.path.exists(f"{OUT}/{f}"):
            os.remove(f"{OUT}/{f}")
    log("images: " + ", ".join(sorted(tour.manifest)))
    if tour.skipped:
        log("skipped: " + "; ".join(f"{k}: {v}" for k, v in sorted(tour.skipped.items())))
    sys.exit(rc)


if __name__ == "__main__":
    main()
