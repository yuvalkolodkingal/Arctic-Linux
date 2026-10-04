"""fastfetch, neofetch and the arctic-fetch greeting (docs/BUILD-SPEC.md §3.1 "Apps").

design/themegen/templates/fastfetch/{config,neofetch}.jsonc.tmpl render into every theme
folder: ~/.config/fastfetch/config.jsonc links to the active theme's config.jsonc, and the
`neofetch` wrapper (dotfiles/.local/bin/neofetch) reads neofetch.jsonc. arctic-fetch draws its
info column with dotfiles/.local/share/arctic/fastfetch/greeting.jsonc and answers
`arctic-fetch --info os|base|wm|shell|theme|updates` for the lines fastfetch can't word the
Arctic way. The layouts are checked against fastfetch's JSON schema (the modules and options
that fastfetch 2.60, Fedora 44's release version, and 2.68, its update, both have); with
fastfetch installed they are also run.

Run: python3 -m unittest discover -s design/themegen/tests -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "design"))

from themegen import color, palette, render  # noqa: E402

import test_app_templates as apps  # noqa: E402  (a module import: its test classes stay there)

DOTFILES = ROOT / "dotfiles"
BIN = DOTFILES / ".local" / "bin"
FETCH = BIN / "arctic-fetch"
NEOFETCH = BIN / "neofetch"
DATA = DOTFILES / ".local" / "share" / "arctic" / "fastfetch"
LOGO = DATA / "logo.txt"
GREETING = DATA / "greeting.jsonc"
OS_RELEASE = ROOT / "packaging" / "release" / "os-release"
SPEC = ROOT / "packaging" / "arctic-linux.spec"
LAYOUTS = ("fastfetch/config.jsonc", "fastfetch/neofetch.jsonc")
INFO_NAMES = ("os", "base", "wm", "shell", "theme", "updates")
BASH = shutil.which("bash") or "/bin/bash"
FASTFETCH = shutil.which("fastfetch")

# fastfetch's modules and the options of the ones the layouts use: doc/json_schema.json of
# fastfetch 2.60.0 and 2.68.1 (what both accept). fastfetch itself ignores unknown modules and
# options without a word, so this is the only place a typo shows.
MODULES = {
    "battery", "bios", "bluetooth", "bluetoothradio", "board", "bootmgr", "break", "brightness",
    "btrfs", "camera", "chassis", "colors", "command", "cpu", "cpucache", "cpuusage", "cursor",
    "custom", "datetime", "de", "disk", "diskio", "display", "dns", "editor", "font", "gamepad",
    "gpu", "host", "icons", "initsystem", "kernel", "keyboard", "lm", "loadavg", "locale",
    "localip", "logo", "media", "memory", "monitor", "mouse", "netio", "opencl", "opengl", "os",
    "packages", "physicaldisk", "physicalmemory", "player", "poweradapter", "processes",
    "publicip", "separator", "shell", "sound", "swap", "terminal", "terminalfont",
    "terminalsize", "terminaltheme", "theme", "title", "tpm", "uptime", "users", "version",
    "vulkan", "wallpaper", "weather", "wifi", "wm", "wmtheme", "zpool",
}
COMMON = {"type", "key", "keyColor", "keyIcon", "keyWidth", "outputColor", "format", "condition"}
OPTIONS = {
    "title": COMMON | {"color", "fqdn"},
    "separator": {"type", "condition", "outputColor", "string", "times"},
    "break": {"type", "condition"},
    "colors": {"type", "condition", "key", "keyColor", "keyIcon", "keyWidth", "block", "paddingLeft", "symbol"},
    "command": COMMON | {"parallel", "param", "shell", "splitLines", "text", "useStdErr"},
    "packages": COMMON | {"combined", "disabled"},
    "wm": COMMON | {"detectPlugin"},
    "cpu": COMMON | {"showPeCoreCount", "temp", "tempSensor"},
    "gpu": COMMON | {"detectionMethod", "driverSpecific", "hideType", "percent", "temp"},
    "memory": COMMON | {"percent"},
    "disk": COMMON | {"folders", "hideFS", "hideFolders", "percent", "showExternal", "showHidden",
                      "showReadOnly", "showRegular", "showSubvolumes", "showUnknown", "useAvailable"},
    "display": COMMON | {"compactType", "order", "preciseRefreshRate"},
}
for _m in ("os", "kernel", "uptime", "shell", "terminal", "host", "board", "de", "wmtheme", "theme",
           "icons", "terminalfont"):
    OPTIONS[_m] = COMMON
TOP_LEVEL = {"$schema", "logo", "display", "general", "modules"}
DISPLAY = {"bar", "brightColor", "color", "constants", "disableLinewrap", "duration", "fraction", "freq",
           "hideCursor", "key", "noBuffer", "percent", "pipe", "separator", "showErrors", "size", "stat",
           "temp"}
LOGO_OPTIONS = {"chafa", "color", "height", "padding", "position", "preserveAspectRatio", "printRemaining",
                "recache", "source", "type", "width"}
CONDITIONS = {"system", "!system", "arch", "!arch", "succeeded"}
# fastfetch's colour syntax (wiki: Color-Format-Specification): named colours with prefixes,
# #rrggbb (2.42+), or raw SGR parameters.
_NAMES = "black|red|green|yellow|blue|magenta|cyan|white|default"
COLOUR = re.compile(r"^((reset|bold|bright|dim|italic|underline|blink|inverse|hidden|strike)_)*"
                    r"((light_)?(%s)|#[0-9a-f]{6})$|^\d+(;\d+)*$" % _NAMES)

TEXT, GLYPH = 4.5, 3.0


def jsonc(text):
    """fastfetch's JSONC: // and /* */ comments outside strings, then JSON."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 2
        else:
            out.append(c)
            i += 1
    return json.loads("".join(out))


def modules(conf):
    """[(type, options)] of a layout's modules (a plain string is a module without options)."""
    return [(m, {"type": m}) if isinstance(m, str) else (m["type"], m) for m in conf["modules"]]


def colours(conf):
    """[(where, colour value)] of every colour a layout sets."""
    found = []
    logo = conf.get("logo") or {}
    for k, v in (logo.get("color") or {}).items():
        found.append(("logo " + k, v))
    display = conf.get("display", {})
    c = display.get("color", {})
    for k, v in (c.items() if isinstance(c, dict) else [("all", c)]):
        found.append(("display.color." + k, v))
    for k, v in display.get("percent", {}).get("color", {}).items():
        found.append(("percent " + k, v))
    for kind, m in modules(conf):
        for k, v in (m.get("color") or {}).items():
            found.append(("%s.color.%s" % (kind, k), v))
        for k in ("outputColor", "keyColor"):
            if k in m:
                found.append(("%s.%s" % (kind, k), m[k]))
    return found


def hex_of(value):
    """The #rrggbb in a colour value, or None for a palette slot / name."""
    m = re.search(r"#[0-9a-f]{6}", value)
    return m.group(0) if m else None


def run_fetch(*args, env=None, home=None, path=None):
    e = {"PATH": path or (str(BIN) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")),
         "HOME": str(home or tempfile.gettempdir()), "LANG": "C.UTF-8", "TERM": "dumb"}
    e.update(env or {})
    r = subprocess.run([BASH, str(FETCH)] + list(args), env=e, capture_output=True, text=True, timeout=30,
                       stdin=subprocess.DEVNULL)
    return r


class Rendered(unittest.TestCase):
    """The two layouts as the engine renders them for Winter and Polar night."""

    @classmethod
    def setUpClass(cls):
        cls.palettes = apps.builtin_palettes()
        cls.files = {name: render.outputs(p) for name, p in cls.palettes.items()}

    def each(self):
        for name, files in self.files.items():
            for rel in LAYOUTS:
                with self.subTest(theme=name, file=rel):
                    yield name, rel, jsonc(files[rel])


class LayoutTest(Rendered):
    def test_templates_render_into_every_theme(self):
        for rel in LAYOUTS:
            self.assertTrue((apps.TEMPLATES / (rel + ".tmpl")).is_file(), rel)
            for name in self.palettes:
                committed = DOTFILES / ".config/arctic/themes" / name / rel
                self.assertTrue(committed.is_file(), committed)

    def test_valid_jsonc_with_known_options(self):
        layouts = [(name + " " + rel, conf) for name, rel, conf in self.each()]
        layouts.append(("greeting", jsonc(GREETING.read_text(encoding="utf-8"))))
        for where, conf in layouts:
            with self.subTest(layout=where):
                self.assertLessEqual(set(conf), TOP_LEVEL)
                self.assertLessEqual(set(conf.get("display", {})), DISPLAY)
                if conf.get("logo") is not None:
                    self.assertLessEqual(set(conf["logo"]), LOGO_OPTIONS)
                self.assertGreater(len(conf["modules"]), 5)
                for kind, m in modules(conf):
                    self.assertIn(kind, MODULES, "not a fastfetch module")
                    self.assertIn(kind, OPTIONS, "add its options (fastfetch's schema) to OPTIONS")
                    self.assertLessEqual(set(m), OPTIONS[kind], kind)
                    self.assertLessEqual(set(m.get("condition", {})), CONDITIONS, kind)
                for what, value in colours(conf):
                    self.assertRegex(value, COLOUR, what)

    def test_the_theme_colours(self):
        for name, rel, conf in self.each():
            c = self.palettes[name]["colors"]
            logo = conf["logo"]
            self.assertEqual(logo["type"], "data")
            self.assertEqual(logo["color"], {"1": c["term-foreground"][:7], "2": c["ansi-3"][:7]})
            display = conf["display"]
            self.assertEqual(display["percent"]["color"],
                             {"green": c["success"][:7], "yellow": c["warning"][:7], "red": c["error"][:7]})
            keys = c["ansi-6"] if rel.endswith("config.jsonc") else c["accent-text"]
            self.assertEqual(display["color"]["keys"], keys[:7])

    def test_contrast_on_the_terminal_background(self):
        """Keys, title, values' percentages and the fox read on the terminal's background, for
        the built-in palettes and those made from solid-colour wallpapers."""
        with tempfile.TemporaryDirectory() as tmp:
            pals = dict(apps.builtin_palettes())
            pals.update(apps.derived_palettes(tmp))
        failures = []
        for name, pal in pals.items():
            files = render.outputs(pal)
            bg = pal["colors"]["term-background"][:7]
            for rel in LAYOUTS:
                for what, value in colours(jsonc(files[rel])):
                    fg = hex_of(value)
                    if fg is None:
                        continue
                    need = GLYPH if ("separator" in what or ".at" in what or "outputColor" in what) else TEXT
                    r = color.contrast(fg, bg)
                    if r < need:
                        failures.append("%s %s %s: %s on %s = %.2f < %s" % (name, rel, what, fg, bg, r, need))
        self.assertEqual(failures, [], "\n" + "\n".join(failures))

    def test_keys_are_padded_not_positioned(self):
        """display.key.width makes fastfetch move the cursor to a column (also into pipes and,
        for the greeting, into the fox): the Arctic layouts pad their keys instead."""
        for name, rel, conf in self.each():
            self.assertNotIn("width", conf["display"].get("key", {}))
        for name, rel, conf in self.each():
            if not rel.endswith("config.jsonc"):
                continue
            for kind, m in modules(conf):
                key = m.get("key")
                if key and "{" not in key:
                    self.assertEqual(len(key), 10, key)
        greeting = jsonc(GREETING.read_text(encoding="utf-8"))
        self.assertIsNone(greeting["logo"])
        for kind, m in modules(greeting):
            if "key" in m:
                self.assertEqual(len(m["key"]), 7, m["key"])     # arctic-fetch's %-7s

    def test_rules_have_a_length(self):
        """fastfetch 2.60 sizes a rule to user@host in bytes and cuts a multi-byte "─" in two:
        such rules say how many."""
        layouts = [conf for _, _, conf in self.each()] + [jsonc(GREETING.read_text(encoding="utf-8"))]
        for conf in layouts:
            for kind, m in modules(conf):
                if kind == "separator" and not m.get("string", "-").isascii():
                    self.assertGreater(m.get("times", 0), 0, m)

    def test_arctic_lines_have_fallbacks(self):
        """A line from arctic-fetch --info names an existing fact; where fastfetch has its own
        module for it, that module follows with succeeded: false (arctic-fetch missing or
        silent, e.g. not in Mango)."""
        layouts = [conf for _, rel, conf in self.each() if rel.endswith("config.jsonc")]
        layouts.append(jsonc(GREETING.read_text(encoding="utf-8")))
        for conf in layouts:
            mods = modules(conf)
            for i, (kind, m) in enumerate(mods):
                if kind != "command":
                    continue
                cmd = re.fullmatch(r"arctic-fetch --info ([a-z]+)", m["text"])
                self.assertIsNotNone(cmd, m["text"])
                self.assertIn(cmd.group(1), INFO_NAMES)
                if cmd.group(1) in ("os", "wm") and conf.get("logo") is not None:
                    self.assertEqual(mods[i + 1][0], cmd.group(1))
                    self.assertEqual(mods[i + 1][1]["condition"], {"succeeded": False})

    def test_config_modules(self):
        """The Arctic layout: os, kernel, uptime, packages, shell, wm, terminal, theme, cpu, gpu,
        memory, disk and updates, in that order."""
        for name, rel, conf in self.each():
            if not rel.endswith("config.jsonc"):
                continue
            lines = []
            for kind, m in modules(conf):
                if kind == "command":
                    kind = m["text"].split()[-1]
                if "condition" in m or kind in lines:
                    continue
                lines.append(kind)
            self.assertEqual(lines, ["title", "separator", "os", "kernel", "uptime", "packages", "shell", "wm",
                                     "terminal", "theme", "cpu", "gpu", "memory", "disk", "updates", "break",
                                     "colors"])
            packages = dict(modules(conf))["packages"]
            self.assertTrue(packages["combined"])            # rpm, flatpak, nix (system + user) counts

    def test_neofetch_layout(self):
        """Classic neofetch: its module order and key names, "Key: value", title + rule."""
        for name, rel, conf in self.each():
            if not rel.endswith("neofetch.jsonc"):
                continue
            self.assertEqual(conf["display"]["separator"], ": ")
            mods = modules(conf)
            self.assertEqual([k for k, _ in mods[:2]], ["title", "separator"])
            keys = [m.get("key") for k, m in mods if "condition" not in m and k not in ("title", "separator", "break", "colors")]
            self.assertEqual(keys, ["OS", "Host", "Kernel", "Uptime", "Packages", "Shell", "Resolution", "DE", "WM",
                                    "WM Theme", "Theme", "Icons", "Terminal", "Terminal Font", "CPU", "GPU", "Memory"])
            self.assertEqual(mods[-1][0], "colors")


class LogoTest(Rendered):
    def test_logo_file(self):
        text = LOGO.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        rows = text.rstrip("\n").split("\n")
        self.assertTrue(12 <= len(rows) <= 16, len(rows))
        for row in rows:
            self.assertTrue(row.startswith("$1"), row)
            self.assertEqual(set(re.findall(r"\$(.)", row)) - {"1", "2"}, set(), row)
            plain = re.sub(r"\$[12]", "", row)
            self.assertLessEqual(len(plain), 32, row)
            self.assertEqual(plain, plain.rstrip())
            self.assertLessEqual(set(plain), set(" ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"), row)
        self.assertEqual(sum(row.count("$2") for row in rows), 2, "two amber eyes")

    def test_layouts_carry_the_logo_file(self):
        logo = LOGO.read_text(encoding="utf-8").rstrip("\n")
        for name, rel, conf in self.each():
            self.assertEqual(conf["logo"]["source"], logo)

    @unittest.skipUnless(shutil.which("rsvg-convert") and apps.Image is not None, "needs rsvg-convert and Pillow")
    def test_logo_is_the_mark(self):
        """The committed logo is what branding/tools/fastfetch_logo.py draws from the mark."""
        sys.path.insert(0, str(ROOT / "branding" / "tools"))
        try:
            import fastfetch_logo
        finally:
            sys.path.pop(0)
        self.assertEqual(fastfetch_logo.logo(), LOGO.read_text(encoding="utf-8"))


class InfoTest(unittest.TestCase):
    """arctic-fetch --info NAME: one line, or nothing where it doesn't apply; always exit 0."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def info(self, name, **env):
        r = run_fetch("--info", name, env=env, home=self.dir / "home")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        return r.stdout

    def os_release(self, text):
        f = self.dir / "os-release"
        f.write_text(text, encoding="utf-8")
        return str(f)

    def test_os_and_base(self):
        self.assertEqual(self.info("os", ARCTIC_OS_RELEASE=str(OS_RELEASE)), "Arctic Linux 1.2 (Fedora 44)\n")
        self.assertEqual(self.info("base", ARCTIC_OS_RELEASE=str(OS_RELEASE)), "Fedora 44\n")
        fedora = self.os_release('NAME="Fedora Linux"\nVERSION="44 (Workstation Edition)"\nID=fedora\n'
                                 'VERSION_ID=44\nPRETTY_NAME="Fedora Linux 44 (Workstation Edition)"\n')
        self.assertEqual(self.info("os", ARCTIC_OS_RELEASE=fedora), "Fedora Linux 44 (Workstation Edition)\n")
        self.assertEqual(self.info("base", ARCTIC_OS_RELEASE=fedora), "Fedora 44\n")
        ubuntu = self.os_release("NAME='Ubuntu'\nID=ubuntu\nID_LIKE=debian\nVERSION_ID=\"24.04\"\n"
                                 "PRETTY_NAME=\"Ubuntu 24.04.1 LTS\"\n")
        self.assertEqual(self.info("os", ARCTIC_OS_RELEASE=ubuntu), "Ubuntu 24.04.1 LTS\n")
        self.assertEqual(self.info("os", ARCTIC_OS_RELEASE=str(self.dir / "missing")), "")

    def test_wm_only_in_mango(self):
        self.assertEqual(self.info("wm", XDG_CURRENT_DESKTOP="mango"), "Mango\n")
        self.assertEqual(self.info("wm", MANGO_INSTANCE_SIGNATURE="x"), "Mango\n")
        self.assertEqual(self.info("wm", XDG_CURRENT_DESKTOP="sway"), "")

    def test_shell_is_the_login_shell(self):
        self.assertRegex(self.info("shell", SHELL=BASH), r"^bash \d+(\.\d+)+\n$")
        self.assertEqual(self.info("shell", SHELL="/usr/bin/nu"), "nu\n")
        self.assertEqual(self.info("shell", SHELL=""), "")

    def test_theme(self):
        self.assertEqual(self.info("theme"), "")
        arctic = self.dir / "home/.config/arctic"
        arctic.mkdir(parents=True)
        (arctic / "current").symlink_to(DOTFILES / ".config/arctic/themes/polar-night")
        self.assertEqual(self.info("theme"), "Polar night\n")
        (arctic / "current").unlink()
        own = self.dir / "wallpaper"
        own.mkdir()
        (own / "theme.env").write_text('ARCTIC_THEME=wallpaper\nARCTIC_THEME_NAME="Wall \\"paper\\""\n'
                                       "ARCTIC_THEME_MODE=light\n", encoding="utf-8")
        (arctic / "current").symlink_to(own)
        self.assertEqual(self.info("theme"), 'Wall "paper" · light\n')

    def updates(self, status=None, linked=False, live=False, with_update=True):
        root = self.dir / "root"
        shutil.rmtree(root, ignore_errors=True)
        (root / "var/lib/arctic").mkdir(parents=True)
        (root / "proc").mkdir()
        (root / "proc/cmdline").write_text("BOOT_IMAGE=/vmlinuz rhgb%s quiet\n" % (" rd.live.image" if live else ""))
        if status is not None:
            (root / "var/lib/arctic/update-status.json").write_text(json.dumps(status, indent=2, sort_keys=True))
        if linked:
            (root / "system-update").symlink_to("/usr/lib/sysimage/libdnf5/offline")
        tools = self.dir / "tools"
        shutil.rmtree(tools, ignore_errors=True)
        tools.mkdir()
        for t in ("date", "bash"):
            (tools / t).symlink_to(shutil.which(t))
        if with_update:
            (tools / "arctic-update").symlink_to(BIN / "arctic-update")
        r = run_fetch("--info", "updates", env={"ARCTIC_UPDATE_TEST_ROOT": str(root)}, path=str(tools))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.rstrip("\n")

    def test_updates(self):
        now = subprocess.run(["date", "-Iseconds"], capture_output=True, text=True).stdout.strip()
        ready = {"state": "ready", "packages": 12, "download_mb": 84.3, "armed": True, "checked_at": now,
                 "auto": "download-and-install-on-reboot", "boot_failures": 0}
        self.assertEqual(self.updates(ready, linked=True), "12 updates ready (84 MB) · restart to install")
        self.assertEqual(self.updates(dict(ready, packages=1, download_mb=0.4), linked=True),
                         "1 update ready (0.4 MB) · restart to install")
        self.assertEqual(self.updates(dict(ready, armed=False, auto="download-only", download_mb=1536)),
                         "12 updates downloaded (1.5 GB) · arctic-update apply")
        idle = {"state": "idle", "packages": 0, "download_mb": 0.0, "checked_at": now, "armed": False,
                "auto": "download-and-install-on-reboot"}
        self.assertEqual(self.updates(idle), "up to date · checked today")
        self.assertEqual(self.updates(dict(idle, checked_at="2020-01-01T03:00:00+00:00")),
                         self.updates(dict(idle, checked_at="2020-01-01T03:00:00+00:00")))
        self.assertRegex(self.updates(dict(idle, checked_at="2020-01-01T03:00:00+00:00")),
                         r"^up to date · checked \d+ days ago$")
        self.assertEqual(self.updates(dict(idle, checked_at=None)), "not checked yet")
        self.assertEqual(self.updates(dict(idle, auto="off")), "automatic updates off · checked today")
        self.assertEqual(self.updates({"state": "checking"}), "checking now…")
        self.assertEqual(self.updates({"state": "failed", "boot_failures": 2}),
                         "paused after failed installs · arctic-update now")
        self.assertEqual(self.updates({"state": "failed"}), "the last check failed · arctic-update")
        # Nothing: no status file yet, the live USB, arctic-update not installed.
        self.assertEqual(self.updates(None), "")
        self.assertEqual(self.updates(ready, linked=True, live=True), "")
        self.assertEqual(self.updates(ready, linked=True, with_update=False), "")

    def test_unknown_name(self):
        r = run_fetch("--info", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)


class NeofetchWrapperTest(unittest.TestCase):
    """dotfiles/.local/bin/neofetch: fastfetch with the neofetch layout, unless a real neofetch
    is on PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "home"
        self.home.mkdir()
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        # A fastfetch that shows how it was called.
        self.script(self.bin / "fastfetch", 'printf "fastfetch %s\\n" "$*"')
        for t in ("sh", "readlink", "grep", "sed"):
            (self.bin / t).symlink_to(shutil.which(t))

    def tearDown(self):
        self.tmp.cleanup()

    def script(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        path.chmod(0o755)

    def run_wrapper(self, *args, path=None, env=None, wrapper=NEOFETCH):
        e = {"PATH": path or str(self.bin), "HOME": str(self.home)}
        e.update(env or {})
        return subprocess.run(["sh", str(wrapper)] + list(args), env=e, capture_output=True, text=True,
                              timeout=30, executable=shutil.which("sh"))

    def test_syntax(self):
        subprocess.run(["sh", "-n", str(NEOFETCH)], check=True)
        self.assertTrue(os.access(NEOFETCH, os.X_OK))

    def test_layout_order(self):
        r = self.run_wrapper()
        self.assertEqual(r.stdout, "fastfetch --config neofetch\n")        # fastfetch's own preset
        current = self.home / ".config/arctic/current/fastfetch/neofetch.jsonc"
        current.parent.mkdir(parents=True)
        current.write_text("{}")
        self.assertEqual(self.run_wrapper("--logo", "none").stdout, "fastfetch --config %s --logo none\n" % current)
        own = self.home / ".config/fastfetch/neofetch.jsonc"
        own.parent.mkdir(parents=True)
        own.write_text("{}")
        self.assertEqual(self.run_wrapper().stdout, "fastfetch --config %s\n" % own)

    def test_neofetch_switches(self):
        self.assertEqual(self.run_wrapper("--stdout").stdout, "fastfetch --config neofetch --logo none --pipe true\n")
        self.assertEqual(self.run_wrapper("--off", "--pipe").stdout, "fastfetch --config neofetch --logo none --pipe\n")
        self.assertIn("neofetch", self.run_wrapper("--help").stdout)
        self.assertIn("fastfetch", self.run_wrapper("--version").stdout)

    def test_a_real_neofetch_wins(self):
        real = self.dir / "later"
        self.script(real / "neofetch", 'echo "real neofetch $*"')
        # A copy of this wrapper (dotfiles in ~/.local/bin and the package's) is not "real".
        copy = self.dir / "copy"
        copy.mkdir()
        shutil.copy(NEOFETCH, copy / "neofetch")
        path = os.pathsep.join([str(copy), str(self.bin), str(real)])
        self.assertEqual(self.run_wrapper("-x", path=path).stdout, "real neofetch -x\n")
        self.assertEqual(self.run_wrapper("-x", path=path, env={"NEOFETCH_ARCTIC": "1"}).stdout,
                         "fastfetch --config neofetch -x\n")
        path = os.pathsep.join([str(copy), str(self.bin)])
        self.assertEqual(self.run_wrapper(path=path).stdout, "fastfetch --config neofetch\n")

    def test_without_fastfetch(self):
        (self.bin / "fastfetch").unlink()
        r = self.run_wrapper()
        self.assertEqual(r.returncode, 127)
        self.assertIn("dnf install fastfetch", r.stderr)


class PackagingTest(unittest.TestCase):
    def test_home_directory_link(self):
        link = DOTFILES / ".config/fastfetch/config.jsonc"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../arctic/current/fastfetch/config.jsonc")

    def test_spec(self):
        spec = SPEC.read_text(encoding="utf-8")
        self.assertIn("Provides:       neofetch = %{version}-%{release}", spec)
        self.assertIn("%ghost %{_bindir}/neofetch\n", spec)
        self.assertIn("%{_libexecdir}/arctic/neofetch\n", spec)
        self.assertIn("%triggerpostun -n arctic-desktop-config -- neofetch", spec)
        self.assertIn("%{_datadir}/arctic/fastfetch/greeting.jsonc\n", spec)
        self.assertIn("%{_datadir}/arctic/fastfetch/logo.txt\n", spec)
        self.assertEqual(sorted(p.name for p in DATA.iterdir()), ["greeting.jsonc", "logo.txt"])
        kiwi = (ROOT / "iso/kiwi/config.kiwi").read_text(encoding="utf-8")
        self.assertIn('<package name="fastfetch"/>', kiwi)

    def test_os_release_logo(self):
        text = OS_RELEASE.read_text(encoding="utf-8")
        logo = re.search(r"^LOGO=(\S+)$", text, re.M).group(1)
        pixmaps = ROOT / "branding/logos/usr/share/pixmaps"
        self.assertTrue((pixmaps / (logo + ".png")).is_file())
        self.assertTrue((pixmaps / (logo + ".svg")).is_file())
        self.assertTrue((ROOT / "branding/logos/usr/share/icons/hicolor/scalable/apps" / (logo + ".svg")).is_file())


@unittest.skipUnless(FASTFETCH, "fastfetch is not installed")
class FastfetchRunTest(unittest.TestCase):
    """The layouts in fastfetch itself, with arctic-fetch --info from this checkout."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name) / "home"
        cls.themes = Path(cls.tmp.name) / "themes"
        for name, pal in apps.builtin_palettes().items():
            apps.render_all(pal, cls.themes / name)
        arctic = cls.home / ".config/arctic"
        arctic.mkdir(parents=True)
        (arctic / "current").symlink_to(cls.themes / "polar-night")
        cls.status = Path(cls.tmp.name) / "update-status.json"
        cls.status.write_text(json.dumps({"state": "idle", "checked_at": None}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def env(self):
        return {"PATH": str(BIN) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(self.home), "LANG": "C.UTF-8", "TERM": "xterm-256color",
                "ARCTIC_OS_RELEASE": str(OS_RELEASE), "ARCTIC_UPDATE_STATUS": str(self.status),
                "XDG_CURRENT_DESKTOP": "mango", "SHELL": BASH}

    def fastfetch(self, *args):
        r = subprocess.run([FASTFETCH] + list(args), env=self.env(), capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Error:", r.stdout + r.stderr)     # e.g. a colour fastfetch can't read
        return r.stdout

    def test_config(self):
        for name in ("polar-night", "winter"):
            out = self.fastfetch("--config", str(self.themes / name / "fastfetch/config.jsonc"), "--pipe")
            self.assertIn("Arctic Linux", out)
            self.assertRegex(out, r"os {8}Arctic Linux 1\.1 \(Fedora 44\)\n")
            self.assertRegex(out, r"wm {8}Mango · Wayland\n")
            self.assertRegex(out, r"theme {5}Polar night\n")
            self.assertRegex(out, r"updates {3}not checked yet\n")
            self.assertIn("▗██▙▖        ▗▟██▖", out)
            self.assertIn("─" * 20 + "\n", out)
            coloured = self.fastfetch("--config", str(self.themes / name / "fastfetch/config.jsonc"), "--pipe", "false")
            c = apps.builtin_palettes()[name]["colors"]
            r, g, b = color.parse_hex(c["ansi-6"])[0]
            self.assertIn("\x1b[38;2;%d;%d;%dmos" % (r, g, b), coloured)

    def test_neofetch(self):
        out = subprocess.run(["sh", str(NEOFETCH), "--pipe"], env=self.env(), capture_output=True, text=True,
                             timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(out.returncode, 0, out.stderr)
        # fastfetch 2.60 prints the logo first and moves the cursor back up for the text.
        plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out.stdout)
        self.assertRegex(plain, r"(?m)-{3,}$")                     # the rule under user@host
        self.assertRegex(plain, r"OS: .+\n")
        self.assertRegex(plain, r"Kernel: .+\n")
        self.assertIn("▗██▙▖        ▗▟██▖", plain)

    def test_greeting(self):
        r = subprocess.run([BASH, str(FETCH), "--static"], env=dict(self.env(), XDG_DATA_HOME=str(DATA.parents[1])),
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", r.stdout)
        self.assertIn("▗█▖         ▗█▖", plain)
        self.assertRegex(plain, r"base   Fedora 44\n")
        self.assertRegex(plain, r"wm     Mango · Wayland\n")
        self.assertRegex(plain, r"theme  Polar night\n")
        self.assertRegex(plain, r"shell  bash \d")
        self.assertNotIn("\x1b[?25l", r.stdout)                  # static: the cursor stays


if __name__ == "__main__":
    unittest.main()
