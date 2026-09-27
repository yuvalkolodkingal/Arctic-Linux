"""The template language: placeholders, filters, scalars and errors.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from themegen import palette, render, template  # noqa: E402
from themegen.template import TemplateError  # noqa: E402

COLORS = {"frost": "#1a212ad1", "ground": "#12171E", "half": "#10203080", "clear": "#10203000"}
SCALARS = {"name": "polar-night", "label": "Polar night", "mode": "dark", "scheme": "prefer-dark",
           "is_dark": "true", "wallpaper": "aurora-polar-night", "lock_wallpaper": "fox-polar-night",
           "font.sans": "Figtree", "font.mono": "JetBrains Mono"}


def r(text):
    return template.render(text, COLORS, SCALARS, where="t.tmpl")


class FilterTests(unittest.TestCase):
    def test_filters(self):
        self.assertEqual(r("{{frost}}"), "#1a212ad1")
        self.assertEqual(r("{{ground}}"), "#12171E")               # as written
        self.assertEqual(r("{{ground|hex}}"), "#12171e")
        self.assertEqual(r("{{frost|hex}}"), "#1a212a")
        self.assertEqual(r("{{ground|hexa}}"), "#12171eff")
        self.assertEqual(r("{{frost|hexa}}"), "#1a212ad1")
        self.assertEqual(r("{{frost|nohash}}"), "1a212a")
        self.assertEqual(r("{{ground|nohasha}}"), "12171eff")
        self.assertEqual(r("{{frost|nohasha}}"), "1a212ad1")
        self.assertEqual(r("{{frost|rgb}}"), "26, 33, 42")
        self.assertEqual(r("{{frost|rgba}}"), "rgba(26, 33, 42, 0.82)")
        self.assertEqual(r("{{ground|rgba}}"), "rgba(18, 23, 30, 1)")
        self.assertEqual(r("{{half|rgba}}"), "rgba(16, 32, 48, 0.502)")
        self.assertEqual(r("{{clear|rgba}}"), "rgba(16, 32, 48, 0)")
        self.assertEqual(r("{{ground|alpha:0.35}}"), "rgba(18, 23, 30, 0.35)")
        self.assertEqual(r("{{frost|alpha:1}}"), "rgba(26, 33, 42, 1)")
        self.assertEqual(r("{{frost|argb}}"), "#d11a212a")
        self.assertEqual(r("{{ground|argb}}"), "#ff12171e")

    def test_scalars_and_plain_text(self):
        self.assertEqual(r("{{name}} {{label}} {{mode}} {{scheme}} {{is_dark}}"),
                         "polar-night Polar night dark prefer-dark true")
        self.assertEqual(r("{{wallpaper}}/{{lock_wallpaper}}: {{font.sans}}, {{font.mono}}"),
                         "aurora-polar-night/fox-polar-night: Figtree, JetBrains Mono")
        text = "a { b } c }} {x} ${HOME}\n#{ground}\n"
        self.assertEqual(r(text), text)
        self.assertEqual(r("x{{ground|hex}}y{{frost|nohash}}z\n\n"), "x#12171ey1a212az\n\n")

    def test_errors(self):
        bad = {
            "{{nope}}": "unknown placeholder",
            "{{ground|nope}}": "unknown filter",
            "{{ ground }}": "whitespace",
            "{{ground |hex}}": "whitespace",
            "{{}}": "whitespace",
            "{{name|hex}}": "not a colour",
            "{{ground|alpha}}": "alpha needs",
            "{{ground|alpha:1.5}}": "alpha needs",
            "{{ground|alpha:x}}": "alpha needs",
            "{{ground|hex:2}}": "takes no argument",
            "{{Ground}}": "malformed",
            "{{ground|hex|rgb}}": "malformed",
            "ok\n{{ground": "unterminated",
        }
        for text, message in bad.items():
            with self.assertRaises(TemplateError, msg=text) as cm:
                r(text)
            self.assertIn(message, str(cm.exception), text)
            self.assertIn("t.tmpl:", str(cm.exception))
        with self.assertRaises(TemplateError) as cm:
            r("line one\nline two {{nope}}\n")
        self.assertIn("t.tmpl:2", str(cm.exception))


class TemplatePathTests(unittest.TestCase):
    def test_output_paths_and_overrides(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            os.makedirs(os.path.join(a, "qt6ct", "colors"))
            with open(os.path.join(a, "qt6ct", "colors", "arctic.conf.tmpl"), "w") as f:
                f.write("x")
            with open(os.path.join(a, "kitty.conf.tmpl"), "w") as f:
                f.write("a")
            with open(os.path.join(b, "kitty.conf.tmpl"), "w") as f:
                f.write("b")
            with open(os.path.join(a, "README"), "w") as f:
                f.write("not a template")
            found = render.template_files([a, b])
            self.assertEqual(sorted(found), ["kitty.conf", "qt6ct/colors/arctic.conf"])
            self.assertTrue(found["kitty.conf"].startswith(b))

    def test_engine_outputs_cannot_be_templates(self):
        for rel in ("theme.json.tmpl", "gtk.css.tmpl", os.path.join("icons", "x.svg.tmpl")):
            with tempfile.TemporaryDirectory() as d:
                os.makedirs(os.path.join(d, "icons"))
                with open(os.path.join(d, rel), "w") as f:
                    f.write("x")
                with self.assertRaises(palette.ThemegenError):
                    render.template_files([d])

    def test_shipped_templates_only_use_known_placeholders(self):
        p = palette.builtin("polar-night")
        colors, scalars = template.context(p, palette.tokens()["font"])
        for rel, path in render.template_files([render.TEMPLATES_DIR]).items():
            with open(path, encoding="utf-8") as f:
                template.render(f.read(), colors, scalars, where=path)   # raises on any mistake


if __name__ == "__main__":
    unittest.main()
