"""App theme templates and theme hooks (docs/BUILD-SPEC.md "App theming").

The theme engine (design/themegen, arctic-themegen) is built separately, so these tests carry
their own small renderer that implements exactly the placeholder syntax of the shared interface:

    {{role}}                  the palette value as written
    {{role|hex}}              #rrggbb (alpha dropped)       {{role|hexa}}     #rrggbbaa
    {{role|nohash}}           rrggbb                        {{role|nohasha}}  rrggbbaa
    {{role|rgb}}              "r, g, b"                     {{role|argb}}     #aarrggbb (Qt)
    {{role|rgba}}             "rgba(r, g, b, a)" (a from the palette, 1 if none, <= 3 decimals)
    {{role|alpha:0.35}}       "rgba(r, g, b, 0.35)"
    {{name}} {{label}} {{mode}} {{scheme}} {{is_dark}} {{wallpaper}} {{lock_wallpaper}}
    {{font.sans}} {{font.mono}}

Unknown placeholders or filters and whitespace inside the braces are errors. Both built-in
palettes (Winter, Polar night) are built from design/exports/arctic-tokens.json. Every template
is rendered with both; the app templates are then parsed the way their app reads them (JSON,
TOML, INI, btop's theme lines, zsh, fzf) and checked against what the app accepts. The hooks in
packaging/theme-hooks.d run against a temporary home directory.

Run: python3 -m unittest discover -s design/themegen/tests -p 'test_*.py' -v
"""
import configparser
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOKENS = ROOT / "design" / "exports" / "arctic-tokens.json"
TEMPLATES = ROOT / "design" / "themegen" / "templates"
HOOKS = ROOT / "packaging" / "theme-hooks.d"
DOTFILES = ROOT / "dotfiles"

# The colour roles every palette has (the shared interface).
ROLES = (
    "ground surface surface-raised surface-sunken frost scrim line line-strong ink ink-muted "
    "ink-subtle ink-disabled ink-inverse accent accent-hover accent-pressed on-accent accent-text "
    "accent-soft accent-edge focus selection warm warm-soft success success-soft warning "
    "warning-soft error error-soft on-error error-hover info info-soft aurora-1 aurora-2 aurora-3 "
    "term-background term-foreground term-cursor term-cursor-text-color term-selection-background "
    "term-selection-foreground"
).split() + ["ansi-%d" % i for i in range(16)]
SCALARS = ("name", "label", "mode", "scheme", "is_dark", "wallpaper", "lock_wallpaper",
           "font.sans", "font.mono")
PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}")
HEX = re.compile(r"^#[0-9a-f]{6}([0-9a-f]{2})?$")

# The templates this change adds (the engine's own templates are only checked for syntax).
APP_TEMPLATES = (
    "qt6ct/colors/arctic.conf", "qt5ct/colors/arctic.conf", "zed/themes/arctic.json",
    "yazi/theme.toml", "btop/arctic.theme", "zsh/colors.zsh", "fzf/fzfrc", "zen/user.js",
    "foot/colors.ini", "alacritty/colors.toml",
)


class TemplateError(ValueError):
    pass


def builtin_palettes():
    """Winter and Polar night as interface palettes, from the flat token export."""
    tok = json.loads(TOKENS.read_text(encoding="utf-8"))
    names = tok["themeNames"]
    return {
        "winter": {"name": "winter", "label": names["light"], "mode": "light", "base": "winter",
                   "colors": dict(tok["themes"]["light"]),
                   "wallpaper": "snowfield-winter", "lock_wallpaper": "fox-winter"},
        "polar-night": {"name": "polar-night", "label": names["dark"], "mode": "dark",
                        "base": "polar-night", "colors": dict(tok["themes"]["dark"]),
                        "wallpaper": "aurora-polar-night", "lock_wallpaper": "fox-polar-night"},
    }, dict(tok["font"])


def _rgba(value):
    if not HEX.match(value.lower()):
        raise TemplateError("not a #rrggbb[aa] colour: %r" % value)
    v = value.lower()[1:]
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    a = int(v[6:8], 16) if len(v) == 8 else 255
    return r, g, b, a


def _num(x):
    return ("%.3f" % x).rstrip("0").rstrip(".") or "0"


def apply_filter(value, filt):
    r, g, b, a = _rgba(value)
    if filt == "hex":
        return "#%02x%02x%02x" % (r, g, b)
    if filt == "hexa":
        return "#%02x%02x%02x%02x" % (r, g, b, a)
    if filt == "nohash":
        return "%02x%02x%02x" % (r, g, b)
    if filt == "nohasha":
        return "%02x%02x%02x%02x" % (r, g, b, a)
    if filt == "rgb":
        return "%d, %d, %d" % (r, g, b)
    if filt == "rgba":
        return "rgba(%d, %d, %d, %s)" % (r, g, b, _num(a / 255))
    if filt == "argb":
        return "#%02x%02x%02x%02x" % (a, r, g, b)
    if filt.startswith("alpha:"):
        arg = filt[len("alpha:"):]
        if not re.fullmatch(r"(0|1)(\.\d+)?|\.\d+", arg) or not 0 <= float(arg) <= 1:
            raise TemplateError("bad alpha %r" % arg)
        return "rgba(%d, %d, %d, %s)" % (r, g, b, arg)
    raise TemplateError("unknown filter %r" % filt)


def render(text, palette, fonts):
    scalars = {
        "name": palette["name"], "label": palette["label"], "mode": palette["mode"],
        "scheme": "prefer-dark" if palette["mode"] == "dark" else "prefer-light",
        "is_dark": "true" if palette["mode"] == "dark" else "false",
        "wallpaper": palette["wallpaper"], "lock_wallpaper": palette["lock_wallpaper"],
        "font.sans": fonts["sans"], "font.mono": fonts["mono"],
    }

    def one(m):
        inner = m.group(1)
        if not inner or re.search(r"\s", inner) or "{" in inner:
            raise TemplateError("bad placeholder %r" % m.group(0))
        name, _, filt = inner.partition("|")
        if name in scalars:
            if filt:
                raise TemplateError("filters only apply to colour roles: %r" % m.group(0))
            return scalars[name]
        if name not in ROLES:
            raise TemplateError("unknown placeholder %r" % m.group(0))
        value = palette["colors"][name]
        return apply_filter(value, filt) if filt else value

    out = PLACEHOLDER.sub(one, text)
    if "{{" in out or "}}" in out:
        raise TemplateError("unresolved braces left in the output")
    return out


def render_all(palette, fonts, dest, only=None):
    """Render templates/**/<file>.tmpl into dest/<file> (the engine's layout)."""
    for tmpl in sorted(TEMPLATES.rglob("*.tmpl")):
        rel = tmpl.relative_to(TEMPLATES).as_posix()[:-len(".tmpl")]
        if only is not None and rel not in only:
            continue
        out = Path(dest) / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(tmpl.read_text(encoding="utf-8"), palette, fonts), encoding="utf-8")
    return Path(dest)


class RendererTest(unittest.TestCase):
    """The test renderer itself follows the interface."""

    def setUp(self):
        self.pal = {"name": "t", "label": "T", "mode": "dark", "wallpaper": "w", "lock_wallpaper": "l",
                    "colors": {r: "#102030" for r in ROLES}}
        self.pal["colors"]["frost"] = "#1a212ad1"
        self.fonts = {"sans": "Figtree", "mono": "JetBrains Mono"}

    def r(self, text):
        return render(text, self.pal, self.fonts)

    def test_filters(self):
        self.assertEqual(self.r("{{frost}}"), "#1a212ad1")
        self.assertEqual(self.r("{{frost|hex}}"), "#1a212a")
        self.assertEqual(self.r("{{ink|hexa}}"), "#102030ff")
        self.assertEqual(self.r("{{frost|nohash}}"), "1a212a")
        self.assertEqual(self.r("{{frost|nohasha}}"), "1a212ad1")
        self.assertEqual(self.r("{{frost|rgb}}"), "26, 33, 42")
        self.assertEqual(self.r("{{frost|rgba}}"), "rgba(26, 33, 42, 0.82)")
        self.assertEqual(self.r("{{ink|rgba}}"), "rgba(16, 32, 48, 1)")
        self.assertEqual(self.r("{{ink|alpha:0.35}}"), "rgba(16, 32, 48, 0.35)")
        self.assertEqual(self.r("{{frost|argb}}"), "#d11a212a")
        self.assertEqual(self.r("{{mode}} {{scheme}} {{is_dark}} {{font.mono}}"),
                         "dark prefer-dark true JetBrains Mono")

    def test_errors(self):
        for bad in ("{{nope}}", "{{ink|nope}}", "{{ ink }}", "{{ink| hex}}", "{{mode|hex}}",
                    "{{ink|alpha:2}}", "{{}}", "{{{ink}}}"):
            with self.subTest(bad=bad), self.assertRaises(TemplateError):
                self.r(bad)

    def test_single_braces_pass_through(self):
        self.assertEqual(self.r('{ fg = "{{ink|hex}}" }'), '{ fg = "#102030" }')


class TemplatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palettes, cls.fonts = builtin_palettes()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = {}
        for name, pal in cls.palettes.items():
            cls.out[name] = render_all(pal, cls.fonts, Path(cls.tmp.name) / name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def each(self, rel):
        for name in self.palettes:
            with self.subTest(theme=name, file=rel):
                yield name, self.palettes[name], (self.out[name] / rel).read_text(encoding="utf-8")

    def test_builtin_palettes_have_every_role(self):
        for name, pal in self.palettes.items():
            missing = [r for r in ROLES if r not in pal["colors"]]
            self.assertEqual(missing, [], name)
            for role, value in pal["colors"].items():
                self.assertRegex(value.lower(), HEX, "%s %s" % (name, role))

    def test_every_template_follows_the_interface(self):
        # render_all already raised on anything the interface doesn't allow; all app templates exist.
        for rel in APP_TEMPLATES:
            self.assertTrue((TEMPLATES / (rel + ".tmpl")).is_file(), rel)
        for tmpl in TEMPLATES.rglob("*.tmpl"):
            self.assertNotIn("{{ ", tmpl.read_text(encoding="utf-8"), tmpl)

    def test_qt_colour_schemes(self):
        for rel, count in (("qt6ct/colors/arctic.conf", 22), ("qt5ct/colors/arctic.conf", 21)):
            for name, pal, text in self.each(rel):
                ini = configparser.ConfigParser(interpolation=None, comment_prefixes=(";",))
                ini.read_string(text)
                self.assertEqual(sorted(ini["ColorScheme"]), ["active_colors", "disabled_colors", "inactive_colors"])
                for key, value in ini["ColorScheme"].items():
                    colours = [c.strip() for c in value.split(",")]
                    self.assertEqual(len(colours), count, key)
                    for c in colours:
                        self.assertRegex(c, r"^#[0-9a-f]{8}$", key)
                active = [c.strip() for c in ini["ColorScheme"]["active_colors"].split(",")]
                self.assertEqual(active[0], "#ff" + pal["colors"]["ink"][1:])          # WindowText
                self.assertEqual(active[10], "#ff" + pal["colors"]["surface"][1:])     # Window
                self.assertEqual(active[12], "#ff" + pal["colors"]["selection"][1:])   # Highlight

    def test_zed_theme(self):
        for name, pal, text in self.each("zed/themes/arctic.json"):
            family = json.loads(text)
            self.assertEqual(family["name"], "Arctic")
            self.assertTrue(family["author"])
            self.assertEqual(len(family["themes"]), 1)
            theme = family["themes"][0]
            self.assertEqual(theme["name"], "Arctic")                    # settings.json "theme"
            self.assertEqual(theme["appearance"], pal["mode"])
            style = theme["style"]
            unknown = set(style) - ZED_STYLE_KEYS
            self.assertEqual(unknown, set(), "keys not in Zed's theme schema v0.2.0")
            self.assertIn(style["background.appearance"], ("opaque", "transparent", "blurred"))
            for key, value in style.items():
                if key in ("accents",):
                    for c in value:
                        self.assertRegex(c, HEX, key)
                elif key == "players":
                    self.assertGreaterEqual(len(value), 1)
                    for p in value:
                        self.assertEqual(set(p), {"cursor", "background", "selection"})
                        for c in p.values():
                            self.assertRegex(c, HEX, key)
                elif key == "syntax":
                    for scope, hl in value.items():
                        self.assertLessEqual(set(hl), {"color", "background_color", "font_style", "font_weight"}, scope)
                        self.assertRegex(hl["color"], HEX, scope)
                        if "font_style" in hl:
                            self.assertIn(hl["font_style"], ("normal", "italic", "oblique"))
                        if "font_weight" in hl:
                            self.assertIn(hl["font_weight"], range(100, 1000, 100))
                elif key != "background.appearance":
                    self.assertRegex(value, HEX, key)
            self.assertEqual(style["editor.background"], pal["colors"]["surface"])
            self.assertEqual(style["terminal.ansi.red"], pal["colors"]["ansi-1"])

    def test_yazi_theme(self):
        for name, pal, text in self.each("yazi/theme.toml"):
            theme = tomllib.loads(text)
            for section, keys in theme.items():
                self.assertIn(section, YAZI_KEYS, "section not in yazi's preset theme")
                self.assertLessEqual(set(keys), YAZI_KEYS[section], section)
            styles = [v for s, keys in theme.items() if s != "filetype" for v in keys.values()]
            styles += theme["filetype"]["rules"]
            for style in styles:
                if not isinstance(style, dict):
                    continue
                for attr in ("fg", "bg"):
                    if attr in style:
                        self.assertTrue(style[attr] == "reset" or HEX.match(style[attr]), style)
            for rule in theme["filetype"]["rules"]:
                self.assertTrue(("mime" in rule) != ("url" in rule), rule)
            self.assertEqual(theme["mgr"]["cwd"]["fg"], pal["colors"]["accent-text"])

    def test_btop_theme(self):
        for name, pal, text in self.each("btop/arctic.theme"):
            seen = set()
            for line in text.splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                m = re.fullmatch(r'theme\[([a-z_]+)\]="(#[0-9a-f]{6})"', line)
                self.assertIsNotNone(m, line)
                self.assertIn(m.group(1), BTOP_KEYS, line)
                seen.add(m.group(1))
            self.assertEqual(seen, BTOP_KEYS)

    def test_zsh_colors(self):
        for name, pal, text in self.each("zsh/colors.zsh"):
            self.assertIn("typeset -g ARCTIC_THEME_MODE=%s" % pal["mode"], text)
            if not shutil.which("zsh"):
                continue
            f = self.out[name] / "zsh/colors.zsh"
            subprocess.run(["zsh", "-n", str(f)], check=True)
            out = subprocess.run(
                ["zsh", "-fc", 'source "$1"; print -r -- "${ARCTIC_PROMPT_COLORS[arrow]} $ARCTIC_MENU_SELECTION '
                               '$ZSH_HIGHLIGHT_STYLES[comment]"', "zsh", str(f)],
                check=True, capture_output=True, text=True).stdout.split()
            self.assertEqual(out[0], pal["colors"]["accent-text"])
            self.assertRegex(out[1], r"^48;2;\d+;\d+;\d+;38;2;\d+;\d+;\d+$")
            self.assertEqual(out[2], "fg=" + pal["colors"]["ink-subtle"])

    def test_fzf_options(self):
        allowed = {"fg", "bg", "hl", "fg+", "bg+", "hl+", "gutter", "info", "prompt", "pointer",
                   "marker", "spinner", "header", "border", "query"}
        for name, pal, text in self.each("fzf/fzfrc"):
            for line in text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                self.assertTrue(line.startswith("--color="), line)
                for pair in line[len("--color="):].split(","):
                    key, value = pair.split(":")
                    self.assertIn(key, allowed)
                    self.assertTrue(value == "-1" or HEX.match(value), pair)
            if shutil.which("fzf"):
                env = dict(os.environ, FZF_DEFAULT_OPTS_FILE=str(self.out[name] / "fzf/fzfrc"))
                env.pop("FZF_DEFAULT_OPTS", None)
                r = subprocess.run(["fzf", "--filter", "a"], input="abc\n", env=env,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_zen_user_js(self):
        for name, pal, text in self.each("zen/user.js"):
            prefs = [l for l in text.splitlines() if l.strip() and not l.startswith("//")]
            self.assertEqual(prefs, ['user_pref("zen.theme.accent-color", "%s");' % pal["colors"]["accent"]])

    def test_foot_colors(self):
        for name, pal, text in self.each("foot/colors.ini"):
            ini = configparser.ConfigParser(interpolation=None)
            ini.read_string(text)
            self.assertEqual(ini["main"]["initial-color-theme"], pal["mode"])
            colors = ini["colors-" + pal["mode"]]
            for key, value in colors.items():
                for c in value.split():
                    self.assertRegex(c, r"^[0-9a-f]{6}$", key)
            if shutil.which("foot"):
                r = subprocess.run(["foot", "--config", str(self.out[name] / "foot/colors.ini"),
                                    "--check-config"], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_alacritty_colors(self):
        for name, pal, text in self.each("alacritty/colors.toml"):
            conf = tomllib.loads(text)
            self.assertEqual(set(conf), {"colors"})

            def walk(d, path=""):
                for k, v in d.items():
                    if isinstance(v, dict):
                        walk(v, path + k + ".")
                    else:
                        self.assertRegex(v, HEX, path + k)
            walk(conf)
            self.assertEqual(conf["colors"]["normal"]["red"], pal["colors"]["ansi-1"])


class DotfilesTest(unittest.TestCase):
    """The home directory defaults point the apps at the active theme."""

    def link(self, rel):
        p = DOTFILES / rel
        self.assertTrue(p.is_symlink(), rel)
        return os.readlink(p)

    def test_links_into_the_active_theme(self):
        self.assertEqual(self.link(".config/yazi/theme.toml"), "../arctic/current/yazi/theme.toml")
        self.assertEqual(self.link(".config/btop/themes/arctic.theme"), "../../arctic/current/btop/arctic.theme")
        self.assertEqual(self.link(".config/gtk-3.0/arctic-colors.css"), "../arctic/current/gtk.css")
        self.assertEqual(self.link(".config/gtk-4.0/arctic-colors.css"), "../arctic/current/gtk.css")

    def test_qtct_configs(self):
        for tool in ("qt5ct", "qt6ct"):
            ini = configparser.ConfigParser(interpolation=None)
            ini.read(DOTFILES / ".config" / tool / (tool + ".conf"))
            app = ini["Appearance"]
            self.assertEqual(app["color_scheme_path"], "~/.config/arctic/current/%s/colors/arctic.conf" % tool)
            self.assertEqual(app["custom_palette"], "true")
            self.assertEqual(app["style"], "Fusion")
            # Quoted, or QSettings reads "family,size" as a list and the font is dropped.
            self.assertRegex(ini["Fonts"]["general"], r'^"[^",]+,\d+"$')
            self.assertRegex(ini["Fonts"]["fixed"], r'^"[^",]+,\d+"$')

    def test_gtk_imports_the_theme_colours(self):
        for gtk in ("gtk-3.0", "gtk-4.0"):
            css = (DOTFILES / ".config" / gtk / "gtk.css").read_text(encoding="utf-8")
            self.assertIn('@import url("arctic-colors.css");', css)

    def test_btop_and_zed_defaults(self):
        conf = (DOTFILES / ".config/btop/btop.conf").read_text(encoding="utf-8")
        self.assertIn('color_theme = "arctic"', conf)
        zed = json.loads((DOTFILES / ".config/zed/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(zed["theme"], "Arctic")

    def test_qt_platform_theme_everywhere(self):
        envd = (DOTFILES / ".config/environment.d/10-arctic.conf").read_text(encoding="utf-8")
        self.assertIn("QT_QPA_PLATFORMTHEME=qt6ct", envd.splitlines())
        look = (DOTFILES / ".config/mango/arctic/look.conf").read_text(encoding="utf-8")
        self.assertIn("env=QT_QPA_PLATFORMTHEME,qt6ct", look.splitlines())
        self.assertIn("cursor_theme=Adwaita", look.splitlines())


class HooksTest(unittest.TestCase):
    """packaging/theme-hooks.d against a throwaway home directory."""

    @classmethod
    def setUpClass(cls):
        cls.palettes, cls.fonts = builtin_palettes()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.themes = {}
        for name, pal in self.palettes.items():
            d = render_all(pal, self.fonts, Path(self.tmp.name) / "themes" / name, only=APP_TEMPLATES)
            (d / "gtk.css").write_text("/* gtk %s */\n" % name, encoding="utf-8")
            self.themes[name] = d
        # No gsettings, flatpak or running apps: only what the hooks do on disk is tested.
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        for tool in ("bash", "python3", "sed", "cp", "mv", "mkdir", "cat", "cmp", "rm", "grep", "mktemp",
                     "chmod", "readlink", "dirname", "basename", "ln", "head", "touch", "stat", "env"):
            path = shutil.which(tool)
            if path:
                (self.bin / tool).symlink_to(path)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, hook, theme="polar-night"):
        env = {"HOME": str(self.home), "PATH": str(self.bin), "ARCTIC_THEME_DIR": str(self.themes[theme]),
               "ARCTIC_THEME_MODE": self.palettes[theme]["mode"], "LANG": "C.UTF-8"}
        r = subprocess.run([str(HOOKS / hook)], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_hooks_are_executable_scripts(self):
        hooks = sorted(p.name for p in HOOKS.iterdir())
        self.assertEqual(hooks, ["10-gtk", "20-qt", "30-zed", "40-zen"])
        for p in HOOKS.iterdir():
            self.assertTrue(os.access(p, os.X_OK), p)

    def test_gtk_copies_the_colours_for_flatpak_apps(self):
        for gtk in ("gtk-3.0", "gtk-4.0"):
            d = self.home / ".config" / gtk
            d.mkdir(parents=True)
            (d / "arctic-colors.css").symlink_to("../arctic/current/gtk.css")
        ini = self.home / ".config/gtk-3.0/settings.ini"
        ini.write_text("[Settings]\ngtk-theme-name=adw-gtk3\ngtk-application-prefer-dark-theme=0\n")
        self.run_hook("10-gtk", "polar-night")
        for gtk in ("gtk-3.0", "gtk-4.0"):
            f = self.home / ".config" / gtk / "arctic-colors.css"
            self.assertFalse(f.is_symlink())
            self.assertIn("gtk polar-night", f.read_text())
        self.assertIn("gtk-application-prefer-dark-theme=1", ini.read_text())
        self.run_hook("10-gtk", "winter")
        self.assertIn("gtk winter", (self.home / ".config/gtk-4.0/arctic-colors.css").read_text())
        self.assertIn("gtk-application-prefer-dark-theme=0", ini.read_text())
        # A file of your own is left alone.
        own = self.home / ".config/gtk-3.0/arctic-colors.css"
        own.write_text("/* mine */\n")
        self.run_hook("10-gtk", "polar-night")
        self.assertEqual(own.read_text(), "/* mine */\n")

    def test_qt_touches_the_config_directory(self):
        d = self.home / ".config/qt6ct"
        d.mkdir(parents=True)
        conf = d / "qt6ct.conf"
        conf.write_text("[Appearance]\nstyle=Fusion\n")
        before = conf.stat().st_ino
        self.run_hook("20-qt")
        self.assertEqual(conf.read_text(), "[Appearance]\nstyle=Fusion\n")
        self.assertNotEqual(conf.stat().st_ino, before)      # replaced: qt6ct's watcher fires
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["qt6ct.conf"])
        self.run_hook("20-qt")                                 # no qt5ct directory: nothing to do

    def test_zed_theme_copied_and_settings_created_once(self):
        (self.home / ".config/zed").mkdir(parents=True)
        (self.home / ".var/app/dev.zed.Zed").mkdir(parents=True)
        self.run_hook("30-zed", "winter")
        for cfg in (self.home / ".config/zed", self.home / ".var/app/dev.zed.Zed/config/zed"):
            theme = cfg / "themes/arctic.json"
            self.assertFalse(theme.is_symlink())
            self.assertEqual(json.loads(theme.read_text())["themes"][0]["appearance"], "light")
            self.assertEqual(json.loads((cfg / "settings.json").read_text())["theme"], "Arctic")
        own = self.home / ".config/zed/settings.json"
        own.write_text('{"theme": "One Dark"}\n')
        self.run_hook("30-zed", "polar-night")
        self.assertEqual(own.read_text(), '{"theme": "One Dark"}\n')
        self.assertEqual(json.loads((self.home / ".config/zed/themes/arctic.json").read_text())
                         ["themes"][0]["appearance"], "dark")

    def test_zed_nothing_without_zed(self):
        self.run_hook("30-zed")
        self.assertFalse((self.home / ".config/zed").exists())
        self.assertFalse((self.home / ".var").exists())

    def zen_profile(self):
        base = self.home / ".var/app/app.zen_browser.zen/.zen"
        (base / "abc.Default").mkdir(parents=True)
        (base / "profiles.ini").write_text("[Profile0]\nName=Default\nIsRelative=1\nPath=abc.Default\n")
        return base / "abc.Default/user.js"

    def test_zen_only_when_asked(self):
        user_js = self.zen_profile()
        self.run_hook("40-zen")
        self.assertFalse(user_js.exists())
        settings = self.home / ".config/arctic/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"auto_colors": false, "zen_theme": true}')
        user_js.write_text('user_pref("browser.startup.page", 3);\n')
        self.run_hook("40-zen", "polar-night")
        self.run_hook("40-zen", "winter")                       # replaced, not appended
        text = user_js.read_text()
        self.assertTrue(text.startswith('user_pref("browser.startup.page", 3);\n'))
        self.assertEqual(text.count("zen.theme.accent-color"), 1)
        self.assertIn(self.palettes["winter"]["colors"]["accent"], text)
        settings.write_text('{"zen_theme": false}')
        self.run_hook("40-zen")
        self.assertEqual(user_js.read_text(), 'user_pref("browser.startup.page", 3);\n')


# Zed theme schema v0.2.0 (https://zed.dev/schema/themes/v0.2.0.json): ThemeStyleContent keys.
ZED_STYLE_KEYS = set("""
accents background background.appearance border border.disabled border.focused border.selected
border.transparent border.variant conflict conflict.background conflict.border created
created.background created.border deleted deleted.background deleted.border
drop_target.background editor.active_line.background editor.active_line_number
editor.active_wrap_guide editor.background editor.document_highlight.bracket_background
editor.document_highlight.read_background editor.document_highlight.write_background
editor.foreground editor.gutter.background editor.highlighted_line.background
editor.indent_guide editor.indent_guide_active editor.invisible editor.line_number
editor.subheader.background editor.wrap_guide element.active element.background element.disabled
element.hover element.selected elevated_surface.background error error.background error.border
ghost_element.active ghost_element.background ghost_element.disabled ghost_element.hover
ghost_element.selected hidden hidden.background hidden.border hint hint.background hint.border
icon icon.accent icon.disabled icon.muted icon.placeholder ignored ignored.background
ignored.border info info.background info.border link_text.hover modified modified.background
modified.border pane.focused_border pane_group.border panel.background panel.focused_border
panel.indent_guide panel.indent_guide_active panel.indent_guide_hover players predictive
predictive.background predictive.border renamed renamed.background renamed.border
scrollbar.thumb.background scrollbar.thumb.border scrollbar.thumb.hover_background
scrollbar.track.background scrollbar.track.border search.match_background status_bar.background
success success.background success.border surface.background syntax tab.active_background
tab.inactive_background tab_bar.background terminal.ansi.background terminal.ansi.black
terminal.ansi.blue terminal.ansi.bright_black terminal.ansi.bright_blue
terminal.ansi.bright_cyan terminal.ansi.bright_green terminal.ansi.bright_magenta
terminal.ansi.bright_red terminal.ansi.bright_white terminal.ansi.bright_yellow
terminal.ansi.cyan terminal.ansi.dim_black terminal.ansi.dim_blue terminal.ansi.dim_cyan
terminal.ansi.dim_green terminal.ansi.dim_magenta terminal.ansi.dim_red terminal.ansi.dim_white
terminal.ansi.dim_yellow terminal.ansi.green terminal.ansi.magenta terminal.ansi.red
terminal.ansi.white terminal.ansi.yellow terminal.background terminal.bright_foreground
terminal.dim_foreground terminal.foreground text text.accent text.disabled text.muted
text.placeholder title_bar.background title_bar.inactive_background toolbar.background
unreachable unreachable.background unreachable.border warning warning.background warning.border
""".split())

# yazi 26.9.1 preset theme (yazi-config/preset/theme-dark.toml): the keys of each section.
YAZI_KEYS = {k: set(v.split()) for k, v in {
    "flavor": "dark light",
    "app": "overall",
    "mgr": "border_style border_symbol count_copied count_cut count_selected cwd find_keyword "
           "find_position marker_copied marker_cut marker_marked marker_selected marker_symbol "
           "symlink_target syntect_theme",
    "tabs": "active inactive sep_inner sep_outer",
    "mode": "normal_alt normal_main select_alt select_main unset_alt unset_main",
    "indicator": "current padding parent preview",
    "status": "overall perm_exec perm_read perm_sep perm_type perm_write progress_error "
              "progress_label progress_normal sep_left sep_right",
    "which": "border cand cols desc mask rest separator separator_style",
    "confirm": "body border btn_labels btn_no btn_yes list title",
    "spot": "border tbl_cell tbl_col title",
    "notify": "icon_error icon_info icon_warn title_error title_info title_warn",
    "pick": "active border inactive",
    "input": "border selected title value",
    "cmp": "active border icon_command icon_file icon_folder inactive",
    "tasks": "border hovered title",
    "help": "action border chord hovered",
    "filetype": "rules",
    "icon": "conds dirs exts files globs",
}.items()}

# btop 1.4.7 theme keys (the ones it looks up when loading a theme file).
BTOP_KEYS = set("""
main_bg main_fg title hi_fg selected_bg selected_fg inactive_fg graph_text meter_bg proc_misc
proc_banner_bg proc_banner_fg proc_pause_bg proc_follow_bg followed_bg followed_fg
cpu_box mem_box net_box proc_box div_line temp_start temp_mid temp_end cpu_start cpu_mid cpu_end
free_start free_mid free_end cached_start cached_mid cached_end available_start available_mid
available_end used_start used_mid used_end download_start download_mid download_end
upload_start upload_mid upload_end process_start process_mid process_end
""".split())


if __name__ == "__main__":
    unittest.main()
