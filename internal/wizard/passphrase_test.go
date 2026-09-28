package wizard

import (
	"strings"
	"testing"
)

func TestWordList(t *testing.T) {
	if len(Words) != 1296 {
		t.Fatalf("EFF short list should have 1296 words, got %d", len(Words))
	}
	if Words[0] != "acid" || Words[len(Words)-1] != "zoom" {
		t.Errorf("first/last word %q %q", Words[0], Words[len(Words)-1])
	}
}

func TestCheckPassphrase(t *testing.T) {
	cases := []struct {
		text  string
		score int
		label string
		words int
	}{
		{"", 0, "Too short", 0},
		{"abc", 0, "Too short", 1},
		{"Tr0ub4!", 0, "Too short", 2},
		{"password", 1, "Weak", 1},
		{"Password123!", 1, "Weak", 1},
		{"12345678", 1, "Weak", 0},
		{"aaaaaaaaaaaa", 1, "Weak", 1},
		{"abcdefghij", 1, "Weak", 1},
		{"acid acorn", 1, "Weak", 2},
		{"acid acorn acre", 3, "Good", 3},
		{"acid acorn acre aged", 4, "Strong", 4},
		{"Xk9#mP2$qL7!", 4, "Strong", 3},
	}
	for _, c := range cases {
		got := CheckPassphrase(c.text)
		if got.Score != c.score || got.Label != c.label || got.Words != c.words {
			t.Errorf("%q: got score %d %q words %d (%.1f bits), want %d %q %d", c.text, got.Score, got.Label, got.Words, got.Bits, c.score, c.label, c.words)
		}
		if got.OK != (c.score >= 2) {
			t.Errorf("%q: ok=%v", c.text, got.OK)
		}
		// The warnings (never a refusal): the passphrase below Fair, the password below Weak.
		if got.WeakPassphrase() != (c.score < 2) || got.WeakPassword() != (c.score < 1) {
			t.Errorf("%q: weak passphrase %v, weak password %v", c.text, got.WeakPassphrase(), got.WeakPassword())
		}
	}
	if l := CheckPassphrase("acid acorn acre aged").MeterLabel(); l != "Strong · 4 words" {
		t.Errorf("meter label %q", l)
	}
}

func TestSuggestPassphrase(t *testing.T) {
	seen := map[string]bool{}
	for i := 0; i < 50; i++ {
		p, err := SuggestPassphrase()
		if err != nil {
			t.Fatal(err)
		}
		f := strings.Fields(p)
		if len(f) != 4 {
			t.Fatalf("want four words, got %q", p)
		}
		for _, w := range f {
			if !wordSet[w] {
				t.Fatalf("%q not from the list", w)
			}
		}
		if s := CheckPassphrase(p); s.Score != 4 || !s.OK {
			t.Errorf("suggestion %q scored %d (%.1f bits)", p, s.Score, s.Bits)
		}
		seen[p] = true
	}
	if len(seen) < 45 {
		t.Errorf("suggestions repeat too often: %d distinct of 50", len(seen))
	}
}

func TestSuggestAccount(t *testing.T) {
	cases := []struct{ name, user string }{
		{"Noa Levi", "noa"},
		{"  Zoë  Müller ", "zoe"},
		{"Łukasz", "lukasz"},
		{"נועה לוי", "user"},
		{"O'Brien", "obrien"},
		{"Root", "root1"},
		{"42 Douglas", "douglas"},
		{"", "user"},
	}
	for _, c := range cases {
		if got := SuggestUsername(c.name); got != c.user {
			t.Errorf("SuggestUsername(%q) = %q, want %q", c.name, got, c.user)
		}
	}
	if h := SuggestHostname("noa", "thinkpad"); h != "noa-thinkpad" {
		t.Errorf("hostname %q", h)
	}
	if h := SuggestHostname(strings.Repeat("a", 60), "thinkpad"); len(h) > 63 || strings.HasSuffix(h, "-") {
		t.Errorf("long hostname %q", h)
	}
}

func TestModelName(t *testing.T) {
	cases := []struct {
		d    DMI
		want string
	}{
		{DMI{"LENOVO", "ThinkPad X1 Carbon Gen 11", "21HMCTO1WW"}, "thinkpad"},
		{DMI{"HP", "103C_5336AN HP EliteBook", "HP EliteBook 840 G8 Notebook PC"}, "elitebook"},
		{DMI{"Dell Inc.", "XPS", "XPS 13 9310"}, "xps"},
		{DMI{"Apple Inc.", "MacBook Pro", "MacBookPro14,1"}, "macbook"},
		{DMI{"Framework", "Laptop", "Laptop (13th Gen Intel Core)"}, "framework"},
		{DMI{"QEMU", "", "Standard PC (Q35 + ICH9, 2009)"}, "vm"},
		{DMI{"innotek GmbH", "Virtual Machine", "VirtualBox"}, "vm"},
		{DMI{"To be filled by O.E.M.", "To be filled by O.E.M.", "System Product Name"}, "pc"},
		{DMI{"ASUSTeK COMPUTER INC.", "Zenbook", "ZenBook UX425EA_UX425EA"}, "zenbook"},
		{DMI{}, "pc"},
	}
	for _, c := range cases {
		if got := ModelName(c.d); got != c.want {
			t.Errorf("ModelName(%+v) = %q, want %q", c.d, got, c.want)
		}
	}
}

func TestLocaleHelpers(t *testing.T) {
	if GuessLanguage("de_AT.UTF-8") != "de_DE.UTF-8" || GuessLanguage("C.UTF-8") != "en_US.UTF-8" || GuessLanguage("he_IL.utf8") != "he_IL.UTF-8" {
		t.Error("GuessLanguage")
	}
	if l, v := SuggestedLayout("de_DE.UTF-8"); l != "de" || v != "" {
		t.Errorf("de layout %s %s", l, v)
	}
	if !ValidTimezone("Asia/Jerusalem") || ValidTimezone("Mars/Olympus") || ValidTimezone("../etc/passwd") {
		t.Error("ValidTimezone")
	}
	if c := LookupCity("America/Argentina/Buenos_Aires"); c.City != "Buenos Aires" {
		t.Errorf("city %+v", c)
	}
	if c := LookupCity("Europe/Tiraspol"); c.City != "Tiraspol" {
		t.Errorf("fallback city %+v", c)
	}
	for region, cities := range Regions {
		for _, c := range cities {
			if !ValidTimezone(c.Timezone) {
				t.Errorf("%s: invalid zone %s", region, c.Timezone)
			}
		}
	}
	for _, l := range Languages {
		for _, k := range l.Keyboards {
			lay, variant, _ := strings.Cut(k, ":")
			if _, ok := FindLayout(lay, variant); !ok {
				t.Errorf("%s suggests unknown layout %s", l.ID, k)
			}
		}
	}
}
