"""App theme templates and theme hooks (docs/BUILD-SPEC.md "App theming").

The app templates (Qt, Zed, yazi, btop, zsh, fzf, Zen, foot, Alacritty) are rendered with the
theme engine itself (design/themegen: render.outputs) for both built-in palettes (Winter, Polar
night), then parsed the way their app reads them (JSON, TOML, INI, btop's theme lines, zsh, fzf)
and checked against what the app accepts. The placeholder syntax is the engine's and is tested
in test_template.py. ContrastTest checks the foreground/background pairs each template actually
draws, for the built-ins and for palettes derived from solid-colour wallpapers. The hooks in
packaging/theme-hooks.d run against a temporary home directory.

Run: python3 -m unittest discover -s design/themegen/tests -v
"""
import colorsys
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "design"))

from themegen import color, palette, render  # noqa: E402

try:
    from themegen import derive
    from PIL import Image
except ImportError:          # Pillow missing: derived palettes are skipped
    derive = Image = None

TEMPLATES = ROOT / "design" / "themegen" / "templates"
HOOKS = ROOT / "packaging" / "theme-hooks.d"
DOTFILES = ROOT / "dotfiles"

# The colour roles every palette has, plus the ones the engine fills in.
ROLES = palette.ROLES + palette.OPTIONAL_ROLES
HEX = re.compile(r"^#[0-9a-f]{6}([0-9a-f]{2})?$")

# The templates this change adds (the engine's own templates are tested by the engine).
APP_TEMPLATES = (
    "qt6ct/colors/arctic.conf", "qt5ct/colors/arctic.conf", "zed/themes/arctic.json",
    "yazi/theme.toml", "btop/arctic.theme", "zsh/colors.zsh", "fzf/fzfrc", "zen/user.js",
    "foot/colors.ini", "alacritty/colors.toml",
)


def builtin_palettes():
    """Winter and Polar night, as the engine builds them from the design tokens."""
    return {name: palette.builtin(name) for name in palette.BUILTINS}


def render_all(pal, dest, only=None):
    """Write the engine's output for `pal` into dest (only the files in `only`, if given)."""
    dest = Path(dest)
    for rel, text in render.outputs(pal).items():
        if only is not None and rel not in only:
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            out.write_bytes(text)
        else:
            out.write_text(text, encoding="utf-8")
    return dest


class TemplatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palettes = builtin_palettes()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = {}
        for name, pal in cls.palettes.items():
            cls.out[name] = render_all(pal, Path(cls.tmp.name) / name)

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
        # render.outputs already raised on anything the interface doesn't allow; all app templates exist.
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


# ---- contrast of what the templates draw ---------------------------------------------------

TEXT = 4.5      # WCAG AA for text
GLYPH = 3.0     # non-text marks that must be seen (fzf pointer, prompt arrows are text anyway)


def _qt(value):
    cols = [c.strip() for c in value.split(",")]
    return ["#" + c[3:] for c in cols]           # #aarrggbb -> #rrggbb


def used_pairs(files, pal):
    """[(where, fg, bg, ratio)] for the text each app template draws on a background."""
    c = pal["colors"]
    term_bg = c["term-background"]
    pairs = []

    def add(where, fg, bg, ratio=TEXT):
        pairs.append((where, fg.lower()[:7], bg.lower()[:7], ratio))

    # Alacritty / foot: terminal text, cursor, selection, hints and search matches.
    a = tomllib.loads(files["alacritty/colors.toml"])["colors"]
    bg = a["primary"]["background"]
    add("alacritty primary", a["primary"]["foreground"], bg)
    add("alacritty cursor", a["cursor"]["text"], a["cursor"]["cursor"])
    add("alacritty selection", a["selection"]["text"], a["selection"]["background"])
    for k in ("hints.start", "hints.end", "search.matches", "search.focused_match"):
        d = a
        for part in k.split("."):
            d = d[part]
        add("alacritty " + k, d["foreground"], d["background"])
    for group in ("normal", "bright"):
        for name, v in a[group].items():
            if name not in ("black", "white"):
                add("alacritty %s.%s" % (group, name), v, bg)
    foot = configparser.ConfigParser(interpolation=None)
    foot.read_string(files["foot/colors.ini"])
    f = foot["colors-" + pal["mode"]]
    fbg = "#" + f["background"]
    add("foot foreground", "#" + f["foreground"], fbg)
    cur_text, cur = f["cursor"].split()
    add("foot cursor", "#" + cur_text, "#" + cur)
    add("foot selection", "#" + f["selection-foreground"], "#" + f["selection-background"])
    add("foot urls", "#" + f["urls"], fbg)

    # fzf: "-1" is the terminal's background.
    fz = {}
    for line in files["fzf/fzfrc"].splitlines():
        if line.startswith("--color="):
            for pair in line[len("--color="):].split(","):
                k, v = pair.split(":")
                fz[k] = term_bg if v == "-1" else v
    for k in ("fg", "hl", "info", "prompt", "header", "query", "marker"):
        add("fzf " + k, fz[k], fz["bg"])
    for k in ("pointer", "spinner"):
        add("fzf " + k, fz[k], fz["bg"], GLYPH)
    for k in ("fg+", "hl+"):
        add("fzf " + k, fz[k], fz["bg+"])

    # Qt: text roles on the roles they are drawn on (active group).
    for tool in ("qt5ct", "qt6ct"):
        ini = configparser.ConfigParser(interpolation=None, comment_prefixes=(";",))
        ini.read_string(files[tool + "/colors/arctic.conf"])
        q = _qt(ini["ColorScheme"]["active_colors"])
        for fg, bg, what in ((0, 10, "WindowText/Window"), (6, 9, "Text/Base"),
                             (6, 16, "Text/AlternateBase"), (8, 1, "ButtonText/Button"),
                             (13, 12, "HighlightedText/Highlight"), (19, 18, "ToolTipText/ToolTipBase"),
                             (14, 9, "Link/Base"), (15, 9, "LinkVisited/Base"),
                             (20, 9, "PlaceholderText/Base")):
            add("%s %s" % (tool, what), q[fg], q[bg])

    # yazi: styles with a text colour, on their own background or the terminal's.
    y = tomllib.loads(files["yazi/theme.toml"])
    skip = re.compile(r"border|sep|marker_|progress_normal|progress_error|symbol")
    for section, keys in y.items():
        if section in ("filetype", "flavor", "icon"):
            continue
        for key, style in keys.items():
            if not isinstance(style, dict) or "fg" not in style or skip.search(key):
                continue
            sbg = style.get("bg", "reset")
            add("yazi %s.%s" % (section, key), style["fg"], term_bg if sbg == "reset" else sbg)
    for rule in y["filetype"]["rules"]:
        add("yazi filetype %s" % (rule.get("mime") or rule.get("is") or rule.get("url")),
            rule.get("fg", c["term-foreground"]), rule.get("bg", term_bg))

    # btop.
    bt = dict(re.findall(r'^theme\[([a-z_]+)\]="(#[0-9a-f]{6})"', files["btop/arctic.theme"], re.M))
    for k in ("main_fg", "title", "hi_fg", "graph_text", "proc_misc"):
        add("btop " + k, bt[k], bt["main_bg"])
    for fg, bg in (("selected_fg", "selected_bg"), ("proc_banner_fg", "proc_banner_bg"),
                   ("followed_fg", "followed_bg"), ("main_fg", "proc_pause_bg"),
                   ("main_fg", "proc_follow_bg")):
        add("btop %s/%s" % (fg, bg), bt[fg], bt[bg])

    # zsh: prompt and highlighting on the terminal background, the completion menu selection.
    z = files["zsh/colors.zsh"]
    for k, v in re.findall(r"^\s+(dir|arrow|error|git)\s+'(#[0-9a-f]{6})'", z, re.M):
        add("zsh prompt " + k, v, term_bg)
    for k, v in re.findall(r"^(?:ZSH_HIGHLIGHT_STYLES\[([a-z-]+)\]|(?:typeset -g )?ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE)='fg=(#[0-9a-f]{6})", z, re.M):
        add("zsh highlight " + (k or "autosuggest"), v, term_bg)
    m = re.search(r'ARCTIC_MENU_SELECTION="48;2;([\d, ]+);38;2;([\d, ]+)"', z)
    rgb = [tuple(int(x) for x in g.split(",")) for g in m.groups()]
    add("zsh menu selection", color.to_hex(rgb[1]), color.to_hex(rgb[0]))

    # Zed: UI text on the surfaces, code on the editor, the terminal.
    st = json.loads(files["zed/themes/arctic.json"])["themes"][0]["style"]
    for fg in ("text", "text.muted", "text.accent", "text.placeholder"):
        for bg in ("background", "surface.background", "elevated_surface.background",
                   "editor.background", "panel.background", "tab.active_background"):
            add("zed %s on %s" % (fg, bg), st[fg], st[bg])
    for k in ("error", "warning", "success", "info", "modified", "created", "deleted", "hint"):
        add("zed " + k, st[k], st["editor.background"])
    add("zed editor", st["editor.foreground"], st["editor.background"])
    add("zed active line number", st["editor.active_line_number"], st["editor.background"])
    add("zed terminal", st["terminal.foreground"], st["terminal.background"])
    for scope, hl in st["syntax"].items():
        add("zed syntax " + scope, hl["color"], hl.get("background_color", st["editor.background"]))
    return pairs


def derived_palettes(folder):
    """Palettes from solid black, white and pure-hue pictures, in dark and light."""
    if derive is None:
        return {}
    pics = {"black": (0, 0, 0), "white": (255, 255, 255)}
    for h in range(0, 360, 45):
        r, g, b = colorsys.hsv_to_rgb(h / 360, 1, 1)
        pics["hue%03d" % h] = (round(r * 255), round(g * 255), round(b * 255))
    out = {}
    for name, rgb in pics.items():
        path = os.path.join(folder, name + ".png")
        Image.new("RGB", (32, 32), rgb).save(path)
        for mode in ("dark", "light"):
            out["%s-%s" % (name, mode)] = derive.from_wallpaper(path, mode)
    return out


class ContrastTest(unittest.TestCase):
    """What each app template draws is readable, for every palette the engine can make."""

    def test_pairs_the_templates_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            pals = dict(builtin_palettes())
            pals.update(derived_palettes(tmp))
        self.assertGreater(len(pals), 2 if derive is None else 20)
        failures = []
        for name, pal in pals.items():
            files = render.outputs(pal)
            pairs = used_pairs(files, pal)
            self.assertGreater(len(pairs), 100)
            for where, fg, bg, ratio in pairs:
                r = color.contrast(fg, bg)
                if r < ratio:
                    failures.append("%s: %s: %s on %s = %.2f < %s" % (name, where, fg, bg, r, ratio))
        self.assertEqual(failures, [], "\n" + "\n".join(failures))

    def test_alacritty_search_matches_use_ink_on_accent_soft(self):
        for name, pal in builtin_palettes().items():
            a = tomllib.loads(render.outputs(pal)["alacritty/colors.toml"])["colors"]
            self.assertEqual(a["search"]["matches"], {"foreground": pal["colors"]["ink"].lower()[:7],
                                                      "background": pal["colors"]["accent-soft"].lower()[:7]})


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


class ShellFzfTest(unittest.TestCase):
    """bash and zsh set FZF_DEFAULT_OPTS_FILE only while the theme has fzf/fzfrc (fzf exits
    when it names a missing file) and never replace your own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.arctic = self.home / ".config/arctic"
        self.empty = Path(self.tmp.name) / "empty-theme"
        self.empty.mkdir()
        self.full = render_all(builtin_palettes()["polar-night"], Path(self.tmp.name) / "polar-night",
                               only=("fzf/fzfrc",))
        self.arctic.mkdir(parents=True)
        (self.arctic / "current").symlink_to(self.empty)
        self.rc = self.full / "fzf/fzfrc"
        self.ours = str(self.arctic / "current/fzf/fzfrc")

    def tearDown(self):
        self.tmp.cleanup()

    def switch(self):
        return 'ln -sfn "%s" "%s"' % (self.full, self.arctic / "current")

    def run_shell(self, argv, script, **env):
        e = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
             "TERM": "dumb", "ARCTIC_FETCH": "0", "LANG": "C.UTF-8"}
        e.update(env)
        r = subprocess.run(argv + [script], env=e, capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split()

    def check(self, argv, prelude, prompt):
        show = 'echo "${FZF_DEFAULT_OPTS_FILE-unset}"; '
        # No fzf/fzfrc in the theme: not set; after a switch to a theme with one, the next prompt sets it.
        out = self.run_shell(argv, prelude + show + self.switch() + "; " + prompt + "; " + show)
        self.assertEqual(out, ["unset", self.ours])
        # Back to a theme without it: unset again.
        (self.arctic / "current").unlink()
        (self.arctic / "current").symlink_to(self.full)
        out = self.run_shell(argv, prelude + show + 'ln -sfn "%s" "%s"; ' % (self.empty, self.arctic / "current")
                             + prompt + "; " + show)
        self.assertEqual(out, [self.ours, "unset"])
        # Your own value stays.
        out = self.run_shell(argv, prelude + prompt + "; " + show, FZF_DEFAULT_OPTS_FILE="/my/fzfrc")
        self.assertEqual(out, ["/my/fzfrc"])
        if shutil.which("fzf"):
            (self.arctic / "current").unlink()
            (self.arctic / "current").symlink_to(self.empty)
            self.run_shell(argv, prelude + "printf 'abc\\n' | fzf --filter a >/dev/null")
            (self.arctic / "current").unlink()
            (self.arctic / "current").symlink_to(self.full)
            self.run_shell(argv, prelude + "printf 'abc\\n' | fzf --filter a >/dev/null")

    def test_bash(self):
        rc = DOTFILES / ".bashrc.d/arctic.sh"
        self.check(["bash", "--norc", "--noprofile", "-ic"], 'source "%s"; ' % rc, 'eval "$PROMPT_COMMAND"')

    @unittest.skipIf(shutil.which("zsh") is None, "zsh is not installed")
    def test_zsh(self):
        shutil.copy(DOTFILES / ".zshrc", self.home / ".zshrc")
        self.check(["zsh", "-ic"], "", "precmd")


class HooksTest(unittest.TestCase):
    """packaging/theme-hooks.d against a throwaway home directory."""

    @classmethod
    def setUpClass(cls):
        cls.palettes = builtin_palettes()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.themes = {}
        for name, pal in self.palettes.items():
            d = render_all(pal, Path(self.tmp.name) / "themes" / name, only=APP_TEMPLATES)
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
        # settings.ini and gtk-theme belong to arctic-theme (ArcticThemeReloadTest).
        self.assertIn("gtk-application-prefer-dark-theme=0", ini.read_text())
        copy = self.home / ".config/gtk-4.0/arctic-colors.css"
        inode = copy.stat().st_ino
        self.run_hook("10-gtk", "polar-night")                 # unchanged: left alone
        self.assertEqual(copy.stat().st_ino, inode)
        self.run_hook("10-gtk", "winter")
        self.assertIn("gtk winter", copy.read_text())
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


ARCTIC_THEME = DOTFILES / ".local/bin/arctic-theme"
# gsettings that keeps its values in a file and logs every set; when gtk-theme is set it also
# saves the arctic-colors.css GTK would read at that moment.
FAKE_GSETTINGS = r"""#!/bin/sh
state="$ARCTIC_TEST_DIR/gsettings"
case "$1" in
  get) v=$(sed -n "s/^$2 $3=//p" "$state" 2>/dev/null); echo "'${v:-adw-gtk3-dark}'" ;;
  set) echo "set $3 $4" >> "$ARCTIC_TEST_DIR/log"
       grep -v "^$2 $3=" "$state" > "$state.new" 2>/dev/null; echo "$2 $3=$4" >> "$state.new"
       mv "$state.new" "$state"
       if [ "$3" = gtk-theme ] && [ -n "$4" ]; then
         n=$(ls "$ARCTIC_TEST_DIR" | grep -c '^css-'); cp "$HOME/.config/gtk-3.0/arctic-colors.css" "$ARCTIC_TEST_DIR/css-$n"
       fi ;;
esac
exit 0
"""


@unittest.skipIf(shutil.which("bash") is None, "bash is needed")
class ArcticThemeReloadTest(unittest.TestCase):
    """The real `arctic-theme reload` with the real hooks, a stub gsettings and a new account."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        share = root / "share/arctic"
        for name, pal in builtin_palettes().items():
            render_all(pal, share / "themes" / name)
        (share / "theme-hooks.d").symlink_to(HOOKS)
        self.share = share
        self.home = root / "home"
        cfg = self.home / ".config"
        for gtk in ("gtk-3.0", "gtk-4.0"):
            (cfg / gtk).mkdir(parents=True)
            (cfg / gtk / "arctic-colors.css").symlink_to("../arctic/current/gtk.css")
        (cfg / "gtk-3.0/settings.ini").write_text(
            "[Settings]\ngtk-theme-name=adw-gtk3-dark\ngtk-application-prefer-dark-theme=1\n")
        (cfg / "arctic").mkdir()
        (cfg / "arctic/current").symlink_to(share / "themes/polar-night")
        (cfg / "arctic/theme").write_text("polar-night\n")
        # A user hook that records what hooks are given.
        (cfg / "arctic/theme-hooks.d").mkdir()
        rec = cfg / "arctic/theme-hooks.d/90-record"
        rec.write_text('#!/bin/sh\necho "$ARCTIC_THEME_NAME $ARCTIC_THEME_MODE $ARCTIC_THEME_DIR" >> "$ARCTIC_TEST_DIR/hooks"\n')
        rec.chmod(0o755)
        self.test_dir = root / "t"
        self.test_dir.mkdir()
        fakes = root / "fakes"
        fakes.mkdir()
        (fakes / "gsettings").write_text(FAKE_GSETTINGS)
        (fakes / "gsettings").chmod(0o755)
        for name in ("adw-gtk3", "adw-gtk3-dark"):          # installed, as in the image
            (root / "sysdata/themes" / name / "gtk-3.0").mkdir(parents=True)
        self.env = {
            "HOME": str(self.home), "LANG": "C.UTF-8", "ARCTIC_TEST_DIR": str(self.test_dir),
            "XDG_DATA_DIRS": str(root / "sysdata"), "XDG_DATA_HOME": str(root / "data"),
            "XDG_CACHE_HOME": str(root / "cache"), "ARCTIC_DATA_DIR": str(share),
            "ARCTIC_BACKGROUNDS_DIR": str(root / "backgrounds"),
            "ARCTIC_THEMEGEN_DIR": str(ROOT / "design/themegen"), "ARCTIC_THEME_HOOK_TIMEOUT": "2",
            "PATH": os.pathsep.join([str(fakes), "/usr/bin", "/bin"]),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def arctic_theme(self, *args):
        r = subprocess.run([str(ARCTIC_THEME), *args], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("hook", r.stderr)           # no hook failed or timed out
        return r

    def lines(self, name):
        p = self.test_dir / name
        return p.read_text().splitlines() if p.exists() else []

    def test_reload_runs_the_hooks_then_sets_gtk_once(self):
        self.arctic_theme("reload")
        current = os.path.realpath(self.home / ".config/arctic/current")
        self.assertEqual(self.lines("hooks"), ["polar-night dark " + current])
        self.arctic_theme("set", "winter")
        current = os.path.realpath(self.home / ".config/arctic/current")
        self.assertEqual(current, os.path.realpath(self.share / "themes/winter"))
        self.assertEqual(self.lines("hooks")[-1], "winter light " + current)
        themes = [l.split(" ", 2)[2] if l.count(" ") >= 2 else "" for l in self.lines("log")
                  if l.startswith("set gtk-theme")]
        self.assertTrue(themes, self.lines("log"))
        self.assertFalse([t for t in themes if t.startswith("Adwaita")], themes)
        self.assertEqual(themes[-1], "adw-gtk3")
        self.assertIn("set color-scheme prefer-light", self.lines("log"))
        # GTK was told after 10-gtk had copied the new colours.
        css = sorted(self.test_dir.glob("css-*"), key=lambda p: int(p.name[4:]))[-1].read_text()
        self.assertIn((self.share / "themes/winter/gtk.css").read_text(), css)
        ini = (self.home / ".config/gtk-3.0/settings.ini").read_text()
        self.assertIn("gtk-application-prefer-dark-theme=0", ini)


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
