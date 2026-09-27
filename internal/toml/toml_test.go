package toml

import (
	"math"
	"reflect"
	"strings"
	"testing"
)

func TestParseScalarsAndTables(t *testing.T) {
	doc := `
# a comment
id = "zen"            # trailing comment
name = 'Zen Browser'
default = true
off = false
count = 1_000
neg = -42
hex = 0xff
ratio = 0.5
exp = 1e3
"quoted key" = "x"
dotted.key = "y"
empty = ""
esc = "tab\there \"q\" é \\"

[defaults]
desktop_id = "app.zen_browser.zen.desktop"
mime = [
  "x-scheme-handler/http",   # http
  "x-scheme-handler/https",
]

[a.b]
c = 1

[[install]]
method = "flatpak"
ref = "app.zen_browser.zen"

[[install]]
method = "dnf"
packages = ["firefox"]
inline = { x = 1, y = "two" }
nested = [[1, 2], ["a"]]
`
	got, err := Parse([]byte(doc))
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]any{
		"id": "zen", "name": "Zen Browser", "default": true, "off": false,
		"count": int64(1000), "neg": int64(-42), "hex": int64(255), "ratio": 0.5, "exp": 1000.0,
		"quoted key": "x", "dotted": map[string]any{"key": "y"}, "empty": "",
		"esc": "tab\there \"q\" é \\",
		"defaults": map[string]any{
			"desktop_id": "app.zen_browser.zen.desktop",
			"mime":       []any{"x-scheme-handler/http", "x-scheme-handler/https"},
		},
		"a": map[string]any{"b": map[string]any{"c": int64(1)}},
		"install": []any{
			map[string]any{"method": "flatpak", "ref": "app.zen_browser.zen"},
			map[string]any{"method": "dnf", "packages": []any{"firefox"},
				"inline": map[string]any{"x": int64(1), "y": "two"},
				"nested": []any{[]any{int64(1), int64(2)}, []any{"a"}}},
		},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestMultilineStrings(t *testing.T) {
	doc := "a = \"\"\"\nline one\nline two\\\n   continued\"\"\"\nb = '''\nraw \\n text'''\nc = \"\"\"quote\"\"\"\"\"\n"
	got, err := Parse([]byte(doc))
	if err != nil {
		t.Fatal(err)
	}
	if got["a"] != "line one\nline twocontinued" {
		t.Errorf("a = %q", got["a"])
	}
	if got["b"] != `raw \n text` {
		t.Errorf("b = %q", got["b"])
	}
	if got["c"] != `quote""` {
		t.Errorf("c = %q", got["c"])
	}
}

func TestSpecialFloats(t *testing.T) {
	got, err := Parse([]byte("a = inf\nb = -inf\nc = nan\n"))
	if err != nil {
		t.Fatal(err)
	}
	if !math.IsInf(got["a"].(float64), 1) || !math.IsInf(got["b"].(float64), -1) || !math.IsNaN(got["c"].(float64)) {
		t.Fatalf("got %#v", got)
	}
}

func TestParseErrors(t *testing.T) {
	cases := map[string]string{
		"dup key":        "a = 1\na = 2\n",
		"dup table":      "[x]\n[x]\n",
		"unterminated":   "a = \"abc\n",
		"no value":       "a = \n",
		"garbage after":  "a = 1 b\n",
		"bad escape":     `a = "\q"` + "\n",
		"leading zero":   "a = 012\n",
		"date":           "a = 1979-05-27\n",
		"bad underscore": "a = 1__0\n",
		"array unclosed": "a = [1, 2\n",
		"table over val": "a = 1\n[a]\n",
		"no equals":      "a 1\n",
		"bad float":      "a = 1.\n",
		"aot over table": "[a]\n[[a]]\n",
	}
	for name, doc := range cases {
		if _, err := Parse([]byte(doc)); err == nil {
			t.Errorf("%s: expected an error", name)
		}
	}
}

func TestErrorHasLine(t *testing.T) {
	_, err := Parse([]byte("a = 1\n\nb = @\n"))
	if err == nil || !strings.Contains(err.Error(), "line 3") {
		t.Fatalf("want line 3 in error, got %v", err)
	}
}

type testInstall struct {
	Method     string   `toml:"method"`
	Packages   []string `toml:"packages"`
	Ref        string   `toml:"ref"`
	DownloadMB float64  `toml:"download_mb"`
}

type testModule struct {
	ID       string        `toml:"id"`
	Default  bool          `toml:"default"`
	Size     int           `toml:"size"`
	Install  []testInstall `toml:"install"`
	Defaults struct{ Mime []string }
	Extra    map[string]string `toml:"extra"`
	Any      any               `toml:"any"`
	Ptr      *testInstall      `toml:"ptr"`
	Skip     string            `toml:"-"`
}

func TestUnmarshal(t *testing.T) {
	doc := `
id = "zen"
default = true
size = 3
any = [1, "x"]
[[install]]
method = "flatpak"
ref = "app.zen_browser.zen"
download_mb = 160
[[install]]
method = "dnf"
packages = ["a", "b"]
download_mb = 1.5
[defaults]
mime = ["text/html"]
[extra]
k = "v"
[ptr]
method = "nix"
`
	var m testModule
	if err := Unmarshal([]byte(doc), &m); err != nil {
		t.Fatal(err)
	}
	if m.ID != "zen" || !m.Default || m.Size != 3 || len(m.Install) != 2 {
		t.Fatalf("got %+v", m)
	}
	if m.Install[0].DownloadMB != 160 || m.Install[1].Packages[1] != "b" || m.Install[1].DownloadMB != 1.5 {
		t.Fatalf("install = %+v", m.Install)
	}
	if m.Defaults.Mime[0] != "text/html" || m.Extra["k"] != "v" || m.Ptr.Method != "nix" {
		t.Fatalf("got %+v", m)
	}
	if !reflect.DeepEqual(m.Any, []any{int64(1), "x"}) {
		t.Fatalf("any = %#v", m.Any)
	}
}

func TestUnmarshalStrictAndTypes(t *testing.T) {
	var m testModule
	if err := Unmarshal([]byte("idd = \"x\"\n"), &m); err == nil || !strings.Contains(err.Error(), `unknown key "idd"`) {
		t.Fatalf("want unknown key error, got %v", err)
	}
	if err := Unmarshal([]byte("default = \"yes\"\n"), &m); err == nil || !strings.Contains(err.Error(), "expected true or false") {
		t.Fatalf("want type error, got %v", err)
	}
	if err := Unmarshal([]byte("[[install]]\nmethodd = 1\n"), &m); err == nil || !strings.Contains(err.Error(), "install[0].methodd") {
		t.Fatalf("want nested path in error, got %v", err)
	}
	if err := Unmarshal([]byte("id = 1\n"), m); err == nil {
		t.Fatal("want error for non-pointer")
	}
}
