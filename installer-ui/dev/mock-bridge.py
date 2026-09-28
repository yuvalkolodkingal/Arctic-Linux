#!/usr/bin/env python3
"""Mock installer engine for developing the Arctic installer UI.

Speaks the engine <-> UI protocol of docs/BUILD-SPEC.md §4 on stdin/stdout
(newline-delimited JSON), exactly like `arctic-install bridge --mock`, so the
Quickshell UI can run with no daemon, no root and no Go toolchain:

    ARCTIC_INSTALLER_BRIDGE="python3 installer-ui/dev/mock-bridge.py" quickshell -p installer-ui

It never touches the system. Knobs (environment):
    ARCTIC_MOCK_ONLINE=1      start online on Wi-Fi (Tundra-5G), default: offline
    ARCTIC_MOCK_WIRED=1       start on a wired connection (network step auto-skipped)
    ARCTIC_MOCK_FAIL=<id>     optional app that fails to download (default: steam if
                              selected, else the last selected optional or video app)
    ARCTIC_MOCK_CATALOG=<dir> catalog directory (default: the repo's modules/)
    ARCTIC_MOCK_FAIL_TWICE=1  the failing app also fails its retry
    ARCTIC_MOCK_FATAL=<n>     a core step fails the first n installs (1 = once; shows the
                              "Something went wrong" view)
    ARCTIC_MOCK_SPEED=<f>     install speed multiplier (default 1.0 = about 40 s)
    ARCTIC_MOCK_LOG=<path>    append every request/response to this file
    ARCTIC_MOCK_HW=none       no drivers found (default: an NVIDIA hybrid laptop, so the
                              Apps step offers the NVIDIA and Intel drivers)
    ARCTIC_MOCK_SECUREBOOT=0  Secure Boot off (default on: the Done step shows the key steps)
    ARCTIC_MOCK_DROP=1        the connection drops when the install starts, so the drivers are
                              put off to first boot (with Secure Boot: the "once your driver is
                              installed" key steps)
"""

import json
import os
import random
import re
import sys
import threading
import time
import tomllib
from pathlib import Path

VERSION = "0.3.0-mock"
ENV = os.environ


def env_on(name):
    return ENV.get(name, "") not in ("", "0", "false", "no")


# ---------------------------------------------------------------- mock data

LANGUAGES = [
    ("en_US.UTF-8", "English (US)", "English"),
    ("he_IL.UTF-8", "עברית", "Hebrew"),
    ("de_DE.UTF-8", "Deutsch", "German"),
    ("es_ES.UTF-8", "Español", "Spanish"),
    ("fr_FR.UTF-8", "Français", "French"),
    ("ja_JP.UTF-8", "日本語", "Japanese"),
    ("en_GB.UTF-8", "English (UK)", "English"),
    ("it_IT.UTF-8", "Italiano", "Italian"),
    ("nl_NL.UTF-8", "Nederlands", "Dutch"),
    ("pl_PL.UTF-8", "Polski", "Polish"),
    ("pt_BR.UTF-8", "Português (Brasil)", "Portuguese"),
    ("ru_RU.UTF-8", "Русский", "Russian"),
    ("sv_SE.UTF-8", "Svenska", "Swedish"),
    ("tr_TR.UTF-8", "Türkçe", "Turkish"),
    ("uk_UA.UTF-8", "Українська", "Ukrainian"),
    ("ar_EG.UTF-8", "العربية", "Arabic"),
]

# (layout, variant, name, description, languages it is suggested for)
LAYOUTS = [
    ("us", "", "English (US)", "", ["en_US"]),
    ("us", "intl", "English (US, international)", "Dead keys for accents", []),
    ("il", "", "Hebrew", "Standard", ["he_IL"]),
    ("gb", "", "English (UK)", "", ["en_GB"]),
    ("de", "", "German", "", ["de_DE"]),
    ("de", "nodeadkeys", "German (no dead keys)", "", []),
    ("es", "", "Spanish", "", ["es_ES"]),
    ("fr", "", "French", "AZERTY", ["fr_FR"]),
    ("jp", "", "Japanese", "", ["ja_JP"]),
    ("it", "", "Italian", "", ["it_IT"]),
    ("nl", "", "Dutch", "", ["nl_NL"]),
    ("pl", "", "Polish", "Programmer", ["pl_PL"]),
    ("br", "", "Portuguese (Brazil)", "ABNT2", ["pt_BR"]),
    ("ru", "", "Russian", "", ["ru_RU"]),
    ("se", "", "Swedish", "", ["sv_SE"]),
    ("tr", "", "Turkish", "Q layout", ["tr_TR"]),
    ("ua", "", "Ukrainian", "", ["uk_UA"]),
    ("ara", "", "Arabic", "", ["ar_EG"]),
    ("gr", "", "Greek", "", []),
    ("us", "dvorak", "English (Dvorak)", "", []),
    ("us", "colemak", "English (Colemak)", "", []),
]

# Like the engine (wizard.KeyboardConfig): layouts that can't type Latin letters get "us"
# first, Alt+Shift to switch, and a console keymap whose base layer is Latin.
NON_LATIN_KEYMAPS = {"il": "us", "ara": "us", "gr": "gr", "ru": "ru", "ua": "ua-utf"}


def keyboard_xkb(kb):
    layout, variant = kb["layout"], kb.get("variant") or ""
    if layout in NON_LATIN_KEYMAPS:
        return {"layout": f"us,{layout}", "variant": f",{variant}" if variant else "", "options": "grp:alt_shift_toggle",
                "keymap": NON_LATIN_KEYMAPS[layout], "latin": False}
    return {"layout": layout, "variant": variant, "options": "", "keymap": layout + (f"-{variant}" if variant else ""), "latin": True}


REGIONS = {
    "Africa": [("Cairo", "Africa/Cairo"), ("Johannesburg", "Africa/Johannesburg"), ("Lagos", "Africa/Lagos"), ("Nairobi", "Africa/Nairobi")],
    "America": [("Chicago", "America/Chicago"), ("Denver", "America/Denver"), ("Los Angeles", "America/Los_Angeles"), ("Mexico City", "America/Mexico_City"),
                ("New York", "America/New_York"), ("São Paulo", "America/Sao_Paulo"), ("Toronto", "America/Toronto"), ("Vancouver", "America/Vancouver")],
    "Asia": [("Bangkok", "Asia/Bangkok"), ("Dubai", "Asia/Dubai"), ("Jerusalem", "Asia/Jerusalem"), ("Kolkata", "Asia/Kolkata"), ("Seoul", "Asia/Seoul"),
             ("Shanghai", "Asia/Shanghai"), ("Singapore", "Asia/Singapore"), ("Tokyo", "Asia/Tokyo")],
    "Australia": [("Adelaide", "Australia/Adelaide"), ("Brisbane", "Australia/Brisbane"), ("Perth", "Australia/Perth"), ("Sydney", "Australia/Sydney")],
    "Europe": [("Amsterdam", "Europe/Amsterdam"), ("Berlin", "Europe/Berlin"), ("Kyiv", "Europe/Kyiv"), ("Lisbon", "Europe/Lisbon"), ("London", "Europe/London"),
               ("Madrid", "Europe/Madrid"), ("Oslo", "Europe/Oslo"), ("Paris", "Europe/Paris"), ("Reykjavik", "Atlantic/Reykjavik"), ("Rome", "Europe/Rome"),
               ("Stockholm", "Europe/Stockholm"), ("Warsaw", "Europe/Warsaw")],
    "Pacific": [("Auckland", "Pacific/Auckland"), ("Honolulu", "Pacific/Honolulu")],
}

GB = 1000 ** 3
DISKS = [
    {"path": "/dev/nvme0n1", "model": "Samsung SSD 980", "size_bytes": 512 * GB, "size_label": "512 GB", "removable": False,
     "install_media": False, "existing_os": ["Windows 11"], "alongside_possible": True, "alongside_label": "Uses 128 GB of free space"},
    {"path": "/dev/sda", "model": "Kingston A400", "size_bytes": 240 * GB, "size_label": "240 GB", "removable": False,
     "install_media": False, "existing_os": [], "alongside_possible": False, "alongside_label": ""},
    {"path": "/dev/sdb", "model": "SanDisk Ultra USB", "size_bytes": 32 * GB, "size_label": "32 GB", "removable": True,
     "install_media": True, "existing_os": [], "alongside_possible": False, "alongside_label": ""},
    # virtio-blk (the QEMU test VM): no model, so the label falls back to the path
    {"path": "/dev/vda", "model": "", "size_bytes": 64 * GB, "size_label": "64 GB", "removable": False,
     "install_media": False, "existing_os": [], "alongside_possible": False, "alongside_label": ""},
]
# Like the Go engine (hw.Disk.Label, wizard.diskOptions): label, and the alongside card's wording.
for _d in DISKS:
    _d["label"] = f"{_d['model'] or _d['path']} · {_d['size_label']}"
    if _d["alongside_possible"]:
        _os = _d["existing_os"][0] if _d["existing_os"] else "the other system"
        _d["alongside_title"] = f"Install alongside {_os}"
        _d["alongside_description"] = f"Keeps {_os}. You choose which one to start each time. {_d['alongside_label']}."

WIFI = [
    {"ssid": "Tundra-5G", "signal": 86, "secure": True},
    {"ssid": "Snowfield", "signal": 62, "secure": True},
    {"ssid": "Cafe Polar", "signal": 41, "secure": False},
    {"ssid": "Aurora Guest", "signal": 23, "secure": True},
]
WIFI_PASSWORDS = {"Tundra-5G": "polarnight", "Snowfield": "snowfield", "Aurora Guest": "guest1234"}
# A weak disk passphrase or password is a warning, never refused (wizard.CopyWeak*).
WEAK_PASSPHRASE = "This passphrase is easy to guess: someone who has your computer could read your files. You can still use it."
WEAK_PASSWORD = "This password is easy to guess: someone at your computer could log in as you. You can still use it."
WEAK_PASSWORD_DISK = "This password is easy to guess: someone who has your computer could read your files. You can still use it."
WEAK_PASSPHRASE_ROW = "easy-to-guess passphrase"   # this mock has no Encryption row: after the Disk row's ", encrypted"
WEAK_PASSWORD_ROW = "easy-to-guess password"       # after the Account row's value

# Categories and apps come from the real catalog (modules/catalog.toml and every
# modules/<category>/<id>/module.toml), so the UI sees exactly what the engine offers:
# names, order, defaults, first install method and download sizes. ARCTIC_MOCK_CATALOG
# points at another catalog directory.
CATALOG_DIR = Path(ENV.get("ARCTIC_MOCK_CATALOG") or Path(__file__).resolve().parents[2] / "modules")
SOURCES = {"flatpak": "Flathub", "copr": "COPR", "nix": "Nix"}


def load_catalog(root):
    with open(root / "catalog.toml", "rb") as f:
        cat = tomllib.load(f)
    categories, modules, system = [], [], []
    links = {}   # id -> (requires, conflicts), as the engine's catalog.Validate checks them
    for c in cat["category"]:
        # id, name, choice ("one" | "any"), note, required, collapsed, role, hardware
        categories.append((c["id"], c["name"], c["choice"], c.get("note", ""), bool(c.get("required")),
                           bool(c.get("collapsed")), c.get("role", "app"), bool(c.get("hardware"))))
        for mid in c["modules"]:
            with open(root / c["id"] / mid / "module.toml", "rb") as f:
                m = tomllib.load(f)
            first = (m.get("install") or [{}])[0]
            method = first.get("method", "")
            source = SOURCES.get(method, "Fedora")
            if method == "dnf" and any(r.startswith("rpmfusion") for r in first.get("repos", [])):
                source = "RPM Fusion"
            # id, name, category, summary, default, download_mb, method, in_live_image, role,
            # source, tile, icon, runtime, verified, proprietary, always
            modules.append((m["id"], m["name"], m["category"], m["summary"], bool(m.get("default")),
                            first.get("download_mb", 0), method, bool(m.get("in_live_image")),
                            m.get("role") or c.get("role", "app"), source, m.get("tile") or m["id"], m.get("icon", ""),
                            first.get("runtime", ""), bool(first.get("verified")), bool(m.get("proprietary")),
                            bool(m.get("always"))))
            links[m["id"]] = (list(m.get("requires") or []), list(m.get("conflicts") or []))
    for f in sorted(root.glob("_system/*/module.toml")):
        with open(f, "rb") as fh:
            m = tomllib.load(fh)
        first = (m.get("install") or [{}])[0]
        if m.get("always") and not m.get("in_live_image"):
            system.append((m["id"], first.get("download_mb", 0), first.get("runtime", "")))
    return categories, modules, system, cat.get("runtimes", {}), links


CATEGORIES, MODULES, SYSTEM, RUNTIMES, LINKS = load_catalog(CATALOG_DIR)

# The mock machine is an NVIDIA hybrid laptop (like the engine's mock, hw.DefaultFixture):
# Intel Iris Xe draws the screen, an RTX 4060 renders on demand, Secure Boot is on.
# ARCTIC_MOCK_HW=none: no drivers found; ARCTIC_MOCK_SECUREBOOT=0: Secure Boot off.
HAS_DRIVERS = ENV.get("ARCTIC_MOCK_HW", "") != "none"
SECURE_BOOT = ENV.get("ARCTIC_MOCK_SECUREBOOT", "") != "0"
# The drivers "detected" on it: id -> (tile, device, builds a kernel module)
DRIVERS = {
    "nvidia": ("driver-gpu", "NVIDIA GeForce RTX 4060 Max-Q / Mobile", True),
    "intel-media": ("driver-media", "Intel Iris Xe Graphics", False),
} if HAS_DRIVERS else {}
# Hardware categories (drivers) offer only what was detected, with the device in the summary;
# with nothing detected the section is left out, as the engine's catalog.MarkDetected does.
HARDWARE = {c[0] for c in CATEGORIES if c[7]}
MODULES = [m[:3] + (m[3].replace("{device}", DRIVERS[m[0]][1]),) + m[4:] if m[2] in HARDWARE else m
           for m in MODULES if m[2] not in HARDWARE or m[0] in DRIVERS]
CATEGORIES = [c for c in CATEGORIES if not c[7] or any(m[2] == c[0] for m in MODULES)]
SUMMARY_APPS = 12   # like the engine's wizard.appList: the Summary doesn't scroll


def app_list(names):
    if len(names) <= SUMMARY_APPS:
        return ", ".join(names)
    return f"{', '.join(names[:SUMMARY_APPS])} and {len(names) - SUMMARY_APPS} more"

MOD = {m[0]: m for m in MODULES}
OPTIONAL_GROUPS = {c[0] for c in CATEGORIES if c[5]}   # the collapsed "More apps" sections


def is_driver(mid):
    return mid in MOD and MOD[mid][2] == "drivers"


def driver_text(mid, status, mok):
    name, dev = MOD[mid][1], DRIVERS[mid][1]
    if status == "deferred":
        return f"The {name} for your {dev} is installed the first time Arctic Linux is online. Restart once more after that."
    if mok and DRIVERS[mid][2]:
        return f"The {name} for your {dev} starts once you’ve confirmed its key (below)."
    return f"The {name} for your {dev} starts after you restart."


def secure_boot_info(code, later=False):
    # internal/wizard SecureBootSteps(code, later): later = the driver was put off to first boot
    # (offline), and the engine keeps the code's hash for arctic-firstboot.
    title = "One more step when the computer restarts"
    intro = "Secure Boot is on, so this computer only starts drivers it trusts. The first time it restarts, confirm the key Arctic Linux signed your driver with:"
    first = "Restart. A blue screen, “Perform MOK management”, appears — press any key within 10 seconds."
    if later:
        title = "One more step once your driver is installed"
        intro = "Secure Boot is on, so this computer only starts drivers it trusts. Your driver is installed the first time Arctic Linux is online; keep this code for the restart after that:"
        first = "Restart once the driver is installed. A blue screen, “Perform MOK management”, appears — press any key within 10 seconds."
    return {
        "code": code,
        "title": title,
        "intro": intro,
        "steps": [
            first,
            "Choose “Enroll MOK”, then “Continue”, then “Yes”.",
            f"Type the one-time code {code} with the number keys above the letters, then press Enter.",
            "Choose “Reboot”. Your driver starts from now on.",
        ],
        "note": "Missed the blue screen? Arctic Linux still starts, only without the driver. Run “sudo mokutil --import /etc/pki/akmods/certs/public_key.der” in a terminal, pick any password, restart and type it there.",
    }

STEPS = [
    ("welcome", "Welcome to Arctic Linux", "This takes about 10 minutes. First, pick the language you'd like to use."),
    ("keyboard", "Choose your keyboard layout", "This is how the keys on your keyboard will type. You can add more layouts later."),
    ("network", "Connect to the internet", "Pick a Wi-Fi network or plug in a cable."),
    ("timezone", "Where are you?", "We use this to set your clock and time zone."),
    ("disk", "How should we install?", ""),
    ("encryption", "Create an encryption passphrase", "You'll type this each time the computer starts, before logging in."),
    ("account", "Create your account", ""),
    ("apps", "Choose your apps", "We've ticked our favourites. Change anything — you can add or remove apps later."),
    ("summary", "Ready to install", "Check everything below. Nothing has been written to your disk yet."),
    ("install", "Installing Arctic Linux", "You can leave this running. Keep the computer plugged in."),
    ("done", "Arctic Linux is ready", ""),
]
STEP_IDS = [s[0] for s in STEPS]

WORDS = ("acorn amber arctic aurora badger basin birch blizzard boulder breeze canyon cedar cloud comet "
         "copper coral crystal dawn delta drift ember fjord flint forest frost galaxy glacier granite "
         "harbor hazel heron husky icicle island juniper kayak lantern lichen lynx maple meadow meteor "
         "moss nimbus north ocean orbit otter owl pebble pepper pine planet polar puffin quartz raven "
         "reef ridge river robin sable salmon shore sierra snowy spruce summit tundra valley walrus "
         "willow winter").split()

USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED = {"root", "bin", "daemon", "adm", "lp", "sync", "shutdown", "halt", "mail", "operator", "games", "ftp", "nobody", "liveuser"}


class InvalidError(Exception):
    def __init__(self, message, fields=None, code="invalid"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or {}


# ---------------------------------------------------------------- engine

class MockEngine:
    def __init__(self, emit):
        self.emit_raw = emit
        self.lock = threading.RLock()
        self.subscribed = False
        self.current = 0
        self.visited = {0}
        self.done = set()          # steps passed with Next
        self.return_to = False     # Next goes back to Summary (after a Change link), like the engine
        self.return_lang = ""      # language when Change left Summary (a new one also shows Keyboard)
        self.wired = env_on("ARCTIC_MOCK_WIRED")
        self.ssid = "Tundra-5G" if env_on("ARCTIC_MOCK_ONLINE") and not self.wired else ""
        self.secrets = {}
        self.keyboard_set = False  # the person picked a layout (a new language then keeps it)
        self.install_thread = None
        self.install_state = "idle"  # idle | running | attention | failed | done
        self.retry_event = threading.Event()
        self.retry_action = None
        self.fail_attempts = {}
        self.done_drivers = []
        self.done_secure_boot = None
        fatal = ENV.get("ARCTIC_MOCK_FATAL", "")
        self.fatal_left = int(fatal) if fatal.isdigit() else int(env_on("ARCTIC_MOCK_FATAL"))  # core failures to come
        self.speed = max(0.05, float(ENV.get("ARCTIC_MOCK_SPEED", "1") or 1))
        self.data = {
            "welcome": {"language": "en_US.UTF-8"},
            "keyboard": {"layout": "us", "variant": ""},
            "network": {},
            "timezone": {"timezone": "Asia/Jerusalem", "auto_time": True},
            "disk": {"disk": "/dev/nvme0n1", "mode": "erase"},
            "encryption": {"enabled": True},
            "account": {"full_name": "", "username": "", "hostname": "", "autologin": False},
            "apps": {"selection": self.default_selection()},
        }
        self.module_status = {}

    # ---- helpers
    def emit(self, obj):
        if self.subscribed:
            self.emit_raw(obj)

    @staticmethod
    def default_selection():
        sel = {c[0]: [] for c in CATEGORIES}
        for m in MODULES:
            if m[4]:
                sel[m[2]].append(m[0])
        return sel

    def online(self):
        return self.wired or bool(self.ssid)

    def step_id(self):
        return STEP_IDS[self.current]

    def wizard(self):
        steps = []
        for i, (sid, title, _help) in enumerate(STEPS):
            if i < self.current:
                state = "done"
            elif i == self.current:
                state = "error" if self.install_state in ("attention", "failed") and sid == "install" else "current"
            else:
                state = "todo"
            if sid == "network" and self.wired and i < self.current:
                state = "done"
            steps.append({"id": sid, "title": title, "state": state})
        return {"steps": steps, "current": self.step_id()}

    def selected_ids(self):
        """The ticked apps (not drivers: they aren't counted as apps)."""
        out = []
        for c in CATEGORIES:
            out.extend(i for i in self.data["apps"]["selection"].get(c[0], []) if not is_driver(i))
        return out

    def selected_drivers(self):
        return [i for i in self.data["apps"]["selection"].get("drivers", []) if is_driver(i)]

    def estimate(self, selection):
        # Like catalog.EstimateDownload: the ticked apps' first methods, the always-installed
        # system modules, and every shared Flatpak runtime once; live-image apps cost nothing.
        ids = []
        for c in CATEGORIES:
            ids.extend(i for i in selection.get(c[0], []) if i in MOD and MOD[i][2] == c[0])
        mb, runtimes = 0.0, set()
        paid = [(MOD[i][5], MOD[i][12]) for i in ids if not MOD[i][7]]
        for mod_mb, runtime in paid + [(s[1], s[2]) for s in SYSTEM]:
            mb += mod_mb
            if runtime and runtime not in runtimes:
                runtimes.add(runtime)
                mb += RUNTIMES.get(runtime, 0)
        b = int(mb * 1000 * 1000)
        if b >= 1000 ** 3:
            size = f"{b / 1000 ** 3:.1f}".rstrip("0").rstrip(".") + " GB"
        else:
            size = f"{(b + 500_000) // 1_000_000} MB"
        n = sum(1 for i in ids if not is_driver(i))
        drivers = len(ids) - n
        count = f"{n} app{'s' if n != 1 else ''}"
        if drivers:
            count += f" + {drivers} driver{'s' if drivers != 1 else ''}"
        label = f"{count} · {size} download" if b else f"{count} · nothing to download"
        out = {"apps": n, "bytes": b, "label": label}
        if drivers:   # omitempty, as the engine's Estimate
            out["drivers"] = drivers
        return out

    def disk(self, path=None):
        path = path or self.data["disk"]["disk"]
        for d in DISKS:
            if d["path"] == path and not d["install_media"]:
                return d
        return None

    def lang_name(self, lid):
        for l in LANGUAGES:
            if l[0] == lid:
                return l[1]
        return lid

    def layout_name(self, layout, variant):
        for l in LAYOUTS:
            if l[0] == layout and l[1] == variant:
                return l[2]
        return layout + (f" ({variant})" if variant else "")

    def city_of(self, tz):
        for region, cities in REGIONS.items():
            for city, zone in cities:
                if zone == tz:
                    return city, region
        return tz.split("/")[-1].replace("_", " "), tz.split("/")[0]

    # ---- passphrase
    @staticmethod
    def check_passphrase(text):
        text = text or ""
        words = [w for w in re.split(r"[\s\-_.,]+", text) if w]
        n = len(words)
        classes = sum(bool(re.search(p, text)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9\s]"))
        if len(text) < 8:
            score = 0
        elif n >= 4 and len(text) >= 16:
            score = 4
        elif n >= 3 or len(text) >= 18:
            score = 3
        elif len(text) >= 12 or classes >= 3:
            score = 2
        else:
            score = 1
        if text.lower() in ("password", "password1", "12345678", "qwertyui", "arcticlinux"):
            score = min(score, 1)
        labels = ["Too short", "Weak", "Fair", "Good", "Strong"]
        return {"score": score, "label": labels[score], "words": n, "ok": score >= 2}

    # ---- steps
    def get_step(self, sid):
        if sid not in STEP_IDS:
            raise InvalidError(f"Unknown step {sid}.", code="not_found")
        title, help_ = STEPS[STEP_IDS.index(sid)][1:]
        data = json.loads(json.dumps(self.data.get(sid, {})))
        options = {}
        if sid == "welcome":
            options = {"languages": [{"id": l[0], "name": l[1], "english": l[2]} for l in LANGUAGES], "suggested": "en_US.UTF-8"}
        elif sid == "keyboard":
            data["xkb"] = keyboard_xkb(data)
            lang = self.data["welcome"]["language"].split(".")[0]
            layouts = []
            for l in LAYOUTS:
                layouts.append({"layout": l[0], "variant": l[1], "name": l[2], "description": l[3], "suggested": lang in l[4]})
            layouts.sort(key=lambda x: (not x["suggested"],))
            options = {"layouts": layouts}
        elif sid == "network":
            options = {"online": self.online(), "wired": self.wired, "ssid": self.ssid}
        elif sid == "timezone":
            options = {"detected": {"city": "Jerusalem, Israel", "timezone": "Asia/Jerusalem", "source": "network" if self.online() else "default"},
                       "regions": {r: [{"city": c, "timezone": z} for c, z in cities] for r, cities in REGIONS.items()}}
        elif sid == "disk":
            options = {"disks": [d for d in DISKS if not d["install_media"]]}
        elif sid == "encryption":
            # min_score: below it the step warns (WEAK_PASSPHRASE); any passphrase is accepted.
            options = {"min_score": 2, "passphrase_set": "luks_passphrase" in self.secrets, "weak_warning": WEAK_PASSPHRASE}
            if "luks_passphrase" in self.secrets:
                options["strength"] = self.check_passphrase(self.secrets["luks_passphrase"])
        elif sid == "account":
            options = {"hostname_hint": "Suggested from your name and computer", "password_set": "user_password" in self.secrets,
                       "encryption": self.data["encryption"].get("enabled", True),
                       "min_score": 1, "weak_warning": WEAK_PASSWORD, "weak_disk_warning": WEAK_PASSWORD_DISK}
            if "user_password" in self.secrets:
                options["strength"] = self.check_passphrase(self.secrets["user_password"])
        elif sid == "apps":
            options = {"categories": [{"id": c[0], "name": c[1], "choice": c[2], "note": c[3], "required": c[4],
                                       "rule": "Pick one" if c[2] == "one" else "Pick any", "collapsed": c[5],
                                       **({"hardware": True} if c[7] else {})}
                                      for c in CATEGORIES],
                       "modules": [{"id": m[0], "name": m[1], "summary": m[3], "category": m[2], "default": m[4],
                                    "always": m[15], "tile": m[10], "icon": m[11], "download_mb": 0 if m[7] else m[5],
                                    "source": m[9], "method": m[6], "verified": m[13], "in_live_image": m[7],
                                    "proprietary": m[14],
                                    **({"device": DRIVERS[m[0]][1]} if is_driver(m[0]) else {})} for m in MODULES]}
        elif sid == "done":
            first = (self.data["account"]["full_name"] or "").split(" ")[0]
            data = {"apps_installed": sum(1 for s in self.module_status.values() if s == "installed"), "first_name": first}
            if self.done_drivers:
                options["drivers"] = self.done_drivers
            if self.done_secure_boot:
                options["secure_boot"] = self.done_secure_boot
        return {"id": sid, "title": title, "help": help_, "data": data, "options": options}

    def validate(self, sid, data):
        fields = {}
        if sid == "welcome":
            if data.get("language") not in [l[0] for l in LANGUAGES]:
                fields["language"] = "Pick a language from the list."
        elif sid == "keyboard":
            if not any(l[0] == data.get("layout") and l[1] == (data.get("variant") or "") for l in LAYOUTS):
                fields["layout"] = "Pick a layout from the list."
        elif sid == "timezone":
            zones = [z for cities in REGIONS.values() for _c, z in cities]
            if data.get("timezone") not in zones:
                fields["timezone"] = "Pick a city from the list."
        elif sid == "disk":
            d = self.disk(data.get("disk"))
            if not d:
                fields["disk"] = "Pick a disk to install on."
            elif d["size_bytes"] < 40 * GB:
                fields["disk"] = "This disk is too small. Arctic Linux needs at least 40 GB."
            if data.get("mode") not in ("erase", "alongside"):
                fields["mode"] = "Choose how to install."
            elif data.get("mode") == "alongside" and d and not d["alongside_possible"]:
                fields["mode"] = "There isn't enough free space to install alongside."
        elif sid == "account":
            name = (data.get("full_name") or "").strip()
            user = data.get("username") or ""
            host = data.get("hostname") or ""
            if not name:
                fields["full_name"] = "Enter your name."
            if not user:
                fields["username"] = "Choose a username."
            elif not USERNAME_RE.match(user):
                fields["username"] = "Use lowercase letters, numbers, - and _."
            elif user in RESERVED:
                fields["username"] = "This name is used by the system. Pick another one."
            if not host:
                fields["hostname"] = "Choose a computer name."
            elif not HOSTNAME_RE.match(host):
                fields["hostname"] = "Use lowercase letters, numbers and -."
        elif sid == "apps":
            sel = data.get("selection") or {}
            for c in CATEGORIES:
                chosen = [i for i in sel.get(c[0], []) if i in MOD and MOD[i][2] == c[0]]
                if c[2] == "one" and len(chosen) > 1:
                    fields[c[0]] = f"Pick one {c[1].lower()}."
                elif c[4] and not chosen:
                    fields[c[0]] = f"Pick a {c[1].lower()}."
            if not fields:
                # Like catalog.Validate: conflicts, then requires, per ticked app in catalog
                # order; the first message for a group wins.
                have = {m[0] for m in MODULES if m[15] or any(m[0] in sel.get(k, []) for k in sel)}
                for m in MODULES:
                    if m[0] not in have:
                        continue
                    requires, conflicts = LINKS.get(m[0], ([], []))
                    for x in conflicts:
                        if x in have:
                            fields.setdefault(m[2], f"{m[1]} and {MOD[x][1]} can't be installed together.")
                    for r in requires:
                        if r not in have:
                            fields.setdefault(m[2], f"{m[1]} needs {MOD[r][1]}. Tick it too.")
        if fields:
            raise InvalidError("Some fields need attention.", fields)

    def set_step(self, sid, data):
        if self.install_state != "idle":
            raise InvalidError("The installer is already running.", code="state")
        if sid not in self.data:
            raise InvalidError(f"Step {sid} has no settings.", code="not_found")
        merged = dict(self.data[sid])
        merged.update(data or {})
        if sid == "keyboard":
            merged.pop("xkb", None)  # read-only
            if "layout" in (data or {}) and "variant" not in data:
                merged["variant"] = ""
            merged["variant"] = merged.get("variant") or ""
        self.validate(sid, merged)
        if sid == "welcome" and merged["language"] != self.data["welcome"]["language"] and not self.keyboard_set:
            # Like the engine: a new language suggests its layout until one is picked.
            lang = merged["language"].split(".")[0]
            for l in LAYOUTS:
                if lang in l[4]:
                    self.data["keyboard"] = {"layout": l[0], "variant": l[1]}
                    break
        self.data[sid] = merged
        if sid == "keyboard":
            self.keyboard_set = True
            return {"ok": True, "data": dict(merged, xkb=keyboard_xkb(merged))}
        return {"ok": True, "data": merged}

    def check_can_leave(self, sid):
        if sid == "network" and not self.online():
            raise InvalidError("Connect to the internet to continue.", {"network": "Connect to the internet to continue."}, code="offline")
        if sid == "encryption" and self.data["encryption"].get("enabled", True):
            p = self.secrets.get("luks_passphrase")
            if not p:
                raise InvalidError("Choose a passphrase.", {"passphrase": "Choose a passphrase."})
            # A weak passphrase is only a warning (the step, the Summary), as in the engine.
        if sid == "account":
            self.validate("account", self.data["account"])
            if not self.secrets.get("user_password"):
                raise InvalidError("Choose a password.", {"password": "Choose a password."})
        if sid in self.data and sid not in ("network", "encryption", "account"):
            self.validate(sid, self.data[sid])

    def next(self):
        sid = self.step_id()
        if sid in ("install", "done"):
            raise InvalidError("The install can't be skipped.", code="state")
        if sid == "summary":
            # ReadyToInstall: every answer again (a passphrase set through the account
            # step's "use it for the disk too" is only checked here).
            for prev in STEP_IDS[:STEP_IDS.index("summary")]:
                if prev != "network":
                    self.check_can_leave(prev)
        self.check_can_leave(sid)
        self.done.add(sid)
        target = self.current + 1
        summary = STEP_IDS.index("summary")
        if self.return_to and sid == "welcome" and self.data["welcome"]["language"] != self.return_lang:
            self.return_lang = self.data["welcome"]["language"]   # show Keyboard first
        elif self.return_to:
            self.return_to = False
            if all(STEP_IDS[k] in self.done or (STEP_IDS[k] == "network" and self.wired) for k in range(target, summary)):
                target = summary
        self.current = target
        if self.step_id() == "network" and self.wired:
            self.current += 1  # wired and online: skip the network step
        self.visited.add(self.current)
        return self.wizard()

    def leave_failed(self):
        """After a core failure, Back / Goto return to the wizard (answers and secrets kept)."""
        if self.step_id() == "install" and self.install_state == "failed":
            self.install_state = "idle"
            self.current = STEP_IDS.index("summary")
            self.return_to = False
            return True
        return False

    def back(self):
        if self.leave_failed():
            return self.wizard()
        if self.step_id() == "done" or self.install_state != "idle":
            raise InvalidError("You can't go back while installing.", code="state")
        self.return_to = False
        if self.current > 0:
            self.current -= 1
            if self.step_id() == "network" and self.wired:
                self.current -= 1
        return self.wizard()

    def goto(self, sid):
        if sid not in STEP_IDS:
            raise InvalidError(f"Unknown step {sid}.", code="not_found")
        i = STEP_IDS.index(sid)
        if self.step_id() == "install" and self.install_state == "failed" and i <= STEP_IDS.index("summary"):
            self.leave_failed()
        if self.step_id() == "done" or self.install_state != "idle":
            raise InvalidError("You can't change answers while installing.", code="state")
        if i > self.current or i >= STEP_IDS.index("summary") and self.step_id() != "install":
            raise InvalidError("You can only go back to a finished step.", code="state")
        if i != self.current:
            self.return_to = self.step_id() == "summary"
            self.return_lang = self.data["welcome"]["language"]
        self.current = i
        return self.wizard()

    # ---- summary
    def summary(self):
        d = self.disk()
        mode = self.data["disk"]["mode"]
        enc = self.data["encryption"].get("enabled", True)
        acct = self.data["account"]
        city, _region = self.city_of(self.data["timezone"]["timezone"])
        offset = {"Asia/Jerusalem": "UTC+2"}.get(self.data["timezone"]["timezone"], "")
        apps = [MOD[i][1].replace(" Browser", "").replace(" Office", "") for i in self.selected_ids() if i in MOD]
        os_name = (d["existing_os"] or ["the other system"])[0] if d else ""
        name = (d["model"] or d["path"]) if d else ""
        if mode == "alongside":
            disk_value = f"Alongside {os_name} on {name} · {d['alongside_label'].replace('Uses ', 'uses ')}"
            primary = f"Install alongside {os_name}"
            warning = f"Installing will use free space on {name}. {os_name} and its files stay as they are."
        else:
            disk_value = f"Erase {d['label']}"
            primary = "Erase disk and install"
            warning = f"Installing will **erase everything on {name}**. This can't be undone."
        disk_value += ", encrypted" if enc else ", not encrypted"
        # As the engine: a secret that is easy to guess is noted in its row (the warning
        # stays one sentence).
        if enc and self.secrets.get("luks_passphrase") and self.check_passphrase(self.secrets["luks_passphrase"])["score"] < 2:
            disk_value += ", " + WEAK_PASSPHRASE_ROW
        account = f"{acct['full_name']} ({acct['username']}) on {acct['hostname']}"
        if self.secrets.get("user_password") and self.check_passphrase(self.secrets["user_password"])["score"] < 1:
            account += ", " + WEAK_PASSWORD_ROW
        rows = [
            {"step": "welcome", "label": "Language and keyboard",
             "value": f"{self.lang_name(self.data['welcome']['language'])} · {self.layout_name(self.data['keyboard']['layout'], self.data['keyboard']['variant'])} layout"},
            {"step": "timezone", "label": "Time zone", "value": f"{city} ({offset})" if offset else city},
            {"step": "disk", "label": "Disk", "value": disk_value},
            {"step": "account", "label": "Account", "value": account},
            {"step": "apps", "label": "Apps", "value": app_list(apps) if apps else "No extra apps"},
        ]
        if HAS_DRIVERS:
            drivers = self.selected_drivers()
            value = "; ".join(f"{MOD[i][1]} for your {DRIVERS[i][1]}" for i in drivers) or "None — your hardware keeps its open-source drivers"
            if SECURE_BOOT and any(DRIVERS[i][2] for i in drivers):
                value += ". Secure Boot is on: you’ll confirm the driver’s key once after restarting"
            rows.append({"step": "apps", "icon": "cpu", "label": "Drivers", "value": value})
        return {"rows": rows, "warning": warning, "primary_label": primary}

    # ---- install simulation
    def start(self):
        if self.step_id() != "install":
            if self.step_id() == "summary":
                self.current = STEP_IDS.index("install")
            else:
                raise InvalidError("Finish the steps before installing.", code="state")
        if self.install_state in ("running", "attention"):
            raise InvalidError("The install is already running.", code="state")
        if self.install_state == "done":
            raise InvalidError("Arctic Linux is already installed.", code="state")
        self.install_state = "running"
        self.module_status = {}
        self.install_thread = threading.Thread(target=self.run_install, daemon=True)
        self.install_thread.start()
        return {"ok": True}

    def sleep(self, s):
        time.sleep(s / self.speed)

    def substeps(self, active):
        order = [("disk", "Preparing the disk"), ("system", "Copying Arctic Linux"), ("apps", "Installing your apps"), ("finish", "Setting up your account")]
        idx = [o[0] for o in order].index(active) if active else len(order)
        out = [{"id": k, "label": lbl, "state": "done" if i < idx else ("active" if i == idx else "todo")} for i, (k, lbl) in enumerate(order)]
        # Like the engine (backend/progress.go): the active apps sub-step counts, "· 3 of 9".
        total = len(self.module_status)
        if active == "apps" and total:
            done = sum(1 for st in self.module_status.values() if st in ("installed", "skipped", "deferred"))
            out[2]["label"] += f" · {min(done + 1, total)} of {total}"
        return out

    def progress(self, percent, phase, status, sub, eta):
        self.emit({"event": "progress", "percent": round(percent, 1), "phase": phase, "status": status,
                   "eta_seconds": int(max(0, eta)), "substeps": self.substeps(sub)})

    def run_install(self):
        try:
            self._run_install()
        except Exception as e:  # pragma: no cover - debugging aid
            self.install_state = "failed"
            self.emit({"event": "failed", "message": f"Mock engine crashed: {e}", "fatal": True})

    def _run_install(self):
        total_eta = 540  # seconds, as a real install would report

        def eta(p):
            return total_eta * (100 - p) / 100

        # disk + system copy (core)
        for i in range(10):
            p = i * 0.8
            self.progress(p, "disk", "Preparing the disk…", "disk", eta(p))
            self.sleep(0.2)
        for i in range(30):
            p = 8 + i * 1.3
            self.progress(p, "copy", "Copying Arctic Linux…", "system", eta(p))
            self.sleep(0.2)
            if self.fatal_left > 0 and i == 12:
                self.fatal_left -= 1
                self.install_state = "failed"
                self.emit({"event": "failed", "title": "Something went wrong while installing",
                           "message": "Copying the system failed: the disk stopped responding (I/O error on /dev/nvme0n1p3).",
                           "details": "copy: rsync -aAXH /run/rootfsbase/ /mnt/: exit status 23\nrsync: write failed on \"/mnt/usr/lib64/libLLVM.so.19\": Input/output error (5)",
                           "fatal": True, "can_change": True})
                return
        for i in range(4):
            p = 47 + i * 1.5
            self.progress(p, "configure", "Copying Arctic Linux…", "system", eta(p))
            self.sleep(0.2)
        for i in range(4):
            p = 53 + i * 1.2
            self.progress(p, "bootloader", "Copying Arctic Linux…", "system", eta(p))
            self.sleep(0.2)

        # apps (optional): one may fail
        ids = [i for i in self.selected_ids() if i in MOD]
        for i in ids:
            self.module_status[i] = "queued"
            self.emit({"event": "module", "id": i, "name": MOD[i][1], "status": "queued", "percent": 0})
        fail_id = ENV.get("ARCTIC_MOCK_FAIL") or ("steam" if "steam" in ids else next(
            (i for i in reversed(ids) if MOD[i][2] == "video" or MOD[i][2] in OPTIONAL_GROUPS), None))
        n = len(ids)
        for k, i in enumerate(ids):
            name, cat, role = MOD[i][1], MOD[i][2], MOD[i][8]
            base = 58 + 37 * k / max(1, n)
            span = 37 / max(1, n)
            while True:
                self.module_status[i] = "downloading"
                attempt = self.fail_attempts.get(i, 0)
                failed = False
                for s in range(6):
                    pc = (s + 1) * 100 / 6
                    self.emit({"event": "module", "id": i, "name": name, "status": "downloading", "percent": round(pc)})
                    self.progress(base + span * pc / 100, "apps", f"Installing {name}, your {role}…", "apps", eta(base + span * pc / 100))
                    self.sleep(0.12)
                    if i == fail_id and s == 3 and (attempt == 0 or env_on("ARCTIC_MOCK_FAIL_TWICE")):
                        failed = True
                        break
                if not failed:
                    self.module_status[i] = "installed"
                    self.emit({"event": "module", "id": i, "name": name, "status": "installed", "percent": 100})
                    break
                self.fail_attempts[i] = attempt + 1
                self.module_status[i] = "failed"
                self.install_state = "attention"
                self.emit({"event": "module", "id": i, "name": name, "status": "failed", "percent": 50})
                self.emit({"event": "attention", "module": {"id": i, "name": name}, "title": f"{name} couldn’t be downloaded",
                           "message": "The download server didn't answer.",
                           "help": f"Everything else is fine — {name} is optional and you can add it later from the Software app.",
                           "details": (f"flatpak install --system -y flathub {i}\nerror: Unable to connect to dl.flathub.org: Could not resolve hostname"
                                       if MOD[i][6] == "flatpak" else
                                       f"dnf install -y {i}\nCurl error (6): Could not resolve host: mirrors.fedoraproject.org"),
                           "optional": True, "retry_label": "Try again", "skip_label": f"Skip {name}"})
                self.retry_event.clear()
                self.retry_event.wait()
                self.install_state = "running"
                if self.retry_action == "skip":
                    self.module_status[i] = "skipped"
                    self.emit({"event": "module", "id": i, "name": name, "status": "skipped", "percent": 0})
                    break
                # retry: loop again

        # drivers: installed with the apps, then built for the kernel (akmods)
        drivers = self.selected_drivers()
        offline = not self.online()
        # As the engine: with Secure Boot and an akmod driver there is a code either way;
        # offline, the driver (and so the key) waits for first boot.
        mok = SECURE_BOOT and any(DRIVERS[i][2] for i in drivers)
        results = []
        for i in drivers:
            name, dev = MOD[i][1], DRIVERS[i][1]
            status = "deferred" if offline else "installed"
            if not offline:
                self.progress(95, "apps", f"Installing the {name} for your {dev}…", "apps", eta(95))
                self.sleep(0.6)
                if DRIVERS[i][2]:
                    self.progress(95, "apps", f"Building the {name} for this computer — this takes a few minutes…", "apps", eta(95))
                    self.sleep(1.2)
            results.append({"id": i, "name": name, "device": dev, "status": status, "text": driver_text(i, status, mok)})
        self.done_drivers = results
        self.done_secure_boot = secure_boot_info("".join(random.choice("0123456789") for _ in range(8)), later=offline) if mok else None

        for i in range(6):
            p = 95 + i
            self.progress(min(p, 100), "finalize", "Setting up your account…" if i < 3 else "Almost there — tidying up…", "finish", eta(p))
            self.sleep(0.2)
        self.progress(100, "finalize", "Almost there — tidying up…", None, 0)
        self.install_state = "done"
        self.current = STEP_IDS.index("done")
        first = (self.data["account"]["full_name"] or "").split(" ")[0]
        installed = sum(1 for s in self.module_status.values() if s == "installed")
        done = {"event": "done", "apps_installed": installed, "first_name": first}
        if self.done_drivers:
            done["drivers"] = self.done_drivers
        if self.done_secure_boot:
            done["secure_boot"] = self.done_secure_boot
        self.emit(done)

    def resume(self, action, mid):
        if self.install_state != "attention":
            raise InvalidError("Nothing is waiting for an answer.", code="state")
        self.retry_action = action
        self.retry_event.set()
        return {"ok": True}

    # ---- dispatch
    def handle(self, method, params):
        p = params or {}
        with self.lock:
            if method == "Hello":
                phase = {"idle": "wizard", "running": "installing"}.get(self.install_state, self.install_state)
                return {"engine_version": VERSION, "mock": True, "live": True, "firmware": "uefi", "state": phase}
            if method == "Subscribe":
                self.subscribed = True
                return {"ok": True}
            if method == "GetWizard":
                return self.wizard()
            if method == "GetStep":
                return self.get_step(p.get("id") or self.step_id())
            if method == "SetStep":
                return self.set_step(p.get("id"), p.get("data") or {})
            if method == "Next":
                return self.next()
            if method == "Back":
                return self.back()
            if method == "Goto":
                return self.goto(p.get("id"))
            if method == "ScanWifi":
                nets = []
                for n in WIFI:
                    s = max(5, min(100, n["signal"] + random.randint(-4, 4)))
                    nets.append({"ssid": n["ssid"], "signal": s, "secure": n["secure"], "connected": n["ssid"] == self.ssid})
                return {"networks": nets}
            if method == "ConnectWifi":
                ssid, pw = p.get("ssid"), p.get("password") or ""
                net = next((n for n in WIFI if n["ssid"] == ssid), None)
                if not net:
                    raise InvalidError("That network is out of range.", code="timeout")
            if method == "NetworkState":
                return {"online": self.online(), "wired": self.wired, "ssid": self.ssid or None}
            if method == "CheckPassphrase":
                return self.check_passphrase(p.get("text"))
            if method == "SuggestPassphrase":
                rng = random.SystemRandom()
                return {"text": " ".join(rng.choice(WORDS) for _ in range(4))}
            if method == "SuggestAccount":
                full = (p.get("full_name") or "").strip()
                first = full.split(" ")[0] if full else ""
                user = re.sub(r"[^a-z0-9_-]", "", first.lower())
                if user and not re.match(r"[a-z_]", user[0]):
                    user = "u" + user
                user = user[:32]
                return {"username": user, "hostname": f"{user}-thinkpad" if user else "arctic-thinkpad"}
            if method == "SetSecrets":
                for k in ("luks_passphrase", "user_password"):
                    if k in p:
                        if p[k]:
                            self.secrets[k] = p[k]
                        else:
                            self.secrets.pop(k, None)
                return {"ok": True}
            if method == "EstimateDownload":
                return self.estimate(p.get("selection") or {})
            if method == "GetSummary":
                return self.summary()
            if method == "Start":
                if env_on("ARCTIC_MOCK_DROP"):
                    self.wired, self.ssid = False, ""
                return self.start()
            if method == "RetryModule":
                return self.resume("retry", p.get("id"))
            if method == "SkipModule":
                return self.resume("skip", p.get("id"))
            if method == "SaveLog":
                return {"path": "/run/initramfs/live/arctic-install.log", "on_usb": True,
                        "message": "Saved the log to the USB stick (arctic-install.log)."}
            if method == "Reboot":
                return {"ok": True}
        if method == "ConnectWifi":
            # outside the lock: connecting takes a moment
            time.sleep(1.2 / self.speed if self.speed < 5 else 0.1)
            with self.lock:
                if net["secure"] and pw != WIFI_PASSWORDS.get(ssid):
                    raise InvalidError("Wrong password. Check it and try again.", {"password": "Wrong password. Check it and try again."}, code="auth")
                self.ssid = ssid
                return {"ok": True}
        raise InvalidError(f"Unknown method {method}.", code="not_found")


# ---------------------------------------------------------------- main loop

def main():
    out_lock = threading.Lock()
    log_path = ENV.get("ARCTIC_MOCK_LOG")

    def log(direction, obj):
        if not log_path:
            return
        safe = json.loads(json.dumps(obj))
        if isinstance(safe, dict) and safe.get("method") == "SetSecrets":
            safe["params"] = {k: "***" for k in (safe.get("params") or {})}
        if isinstance(safe, dict) and safe.get("method") in ("CheckPassphrase", "ConnectWifi"):
            safe["params"] = {k: ("***" if k in ("text", "password") else v) for k, v in (safe.get("params") or {}).items()}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {direction} {json.dumps(safe, ensure_ascii=False)}\n")

    def emit(obj):
        line = json.dumps(obj, ensure_ascii=False)
        with out_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        log(">", obj)

    engine = MockEngine(emit)

    def serve(req):
        rid = req.get("id")
        try:
            result = engine.handle(req.get("method"), req.get("params"))
            emit({"id": rid, "result": result})
        except InvalidError as e:
            err = {"code": e.code, "message": e.message}
            if e.fields:
                err["fields"] = e.fields
            emit({"id": rid, "error": err})
        except Exception as e:  # pragma: no cover
            emit({"id": rid, "error": {"code": "internal", "message": str(e)}})

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except ValueError:
            emit({"id": None, "error": {"code": "parse", "message": "Could not read the request."}})
            continue
        log("<", req)
        if req.get("method") in ("ConnectWifi",):
            threading.Thread(target=serve, args=(req,), daemon=True).start()
        else:
            serve(req)


if __name__ == "__main__":
    main()
