package webapp

import (
	"strings"
	"testing"
)

func TestValidIDs(t *testing.T) {
	cases := []struct {
		id   string
		want bool
	}{
		{"org.arcticlinux.WebApp.YouTubeMusic_4c1a9e", true},
		{"org.arcticlinux.WebApp.App_4c1a9e12", true},
		{"org.arcticlinux.WebApp.A_000000", true},
		{"org.arcticlinux.WebApp.YouTube-Music_4c1a9e", false}, // no '-'
		{"org.arcticlinux.WebApp.1Password_4c1a9e", false},     // leading digit
		{"org.arcticlinux.WebApp.X_4C1A9E", false},             // uppercase hash
		{"org.arcticlinux.WebApp.X_4c1a9", false},              // 5 digits
		{"org.arcticlinux.WebApp.X_4c1a9e123", false},          // 9 digits
		{"org.arcticlinux.WebApp.X_4c1a9e/../../x", false},
		{"org.arcticlinux.WebApp.X_4c1a9e\n", false},
		{"org.arcticlinux.WebApp." + strings.Repeat("A", 33) + "_4c1a9e", false},
		{"org.arcticlinux.Installer", false},
		{"", false},
	}
	for _, c := range cases {
		if got := Valid(c.id); got != c.want {
			t.Errorf("Valid(%q) = %v, want %v", c.id, got, c.want)
		}
	}
}

func TestGApplicationIDRules(t *testing.T) {
	for id, want := range map[string]bool{
		"org.gnome.Foo": true, "a.b": true, "a": false, ".a.b": false, "a..b": false, "a.1b": false,
		"a.b-c": true, "a.b c": false, strings.Repeat("a.", 128) + "b": false,
	} {
		if got := ValidGApplicationID(id); got != want {
			t.Errorf("ValidGApplicationID(%q) = %v, want %v", id, got, want)
		}
	}
}

func TestSlug(t *testing.T) {
	cases := []struct{ name, site, want string }{
		{"YouTube Music", "youtube.com", "YouTubeMusic"},
		{"gmail", "google.com", "Gmail"},
		{"וואלה", "walla.co.il", "Walla"}, // Hebrew name: the site label
		{"🎵", "", "App"},                  // nothing usable
		{"1Password", "1password.com", "App1Password"},
		{"Home Assistant (ha.lan)", "ha.lan", "HomeAssistantHaLan"},
		{"a-b_c", "x.org", "ABC"},
		{strings.Repeat("Long", 20), "x.org", strings.Repeat("Long", 8)},
	}
	for _, c := range cases {
		if got := Slug(c.name, c.site); got != c.want {
			t.Errorf("Slug(%q, %q) = %q, want %q", c.name, c.site, got, c.want)
		}
	}
}

// The hash is deterministic (a reinstall after remove --keep-data finds the same profile), a
// second copy gets its own, and a different identity on the same 6 digits gets 8.
func TestNewID(t *testing.T) {
	free := func(string) string { return "" }
	id1 := NewID("YouTube Music", "youtube.com", "https://music.youtube.com/?source=pwa", free)
	id2 := NewID("YouTube Music", "youtube.com", "https://music.youtube.com/?source=pwa", free)
	if id1 != id2 || !Valid(id1) || !strings.HasPrefix(id1, IDPrefix+"YouTubeMusic_") || len(HashOf(id1)) != 6 {
		t.Fatalf("NewID not deterministic or invalid: %q %q", id1, id2)
	}
	copy2 := NewID("YouTube Music", "youtube.com", Identity("", "https://music.youtube.com/?source=pwa", 2), free)
	if copy2 == id1 {
		t.Fatal("a second copy must get its own id")
	}
	same := func(id string) string {
		if id == id1 {
			return "https://music.youtube.com/?source=pwa"
		}
		return ""
	}
	if got := NewID("YouTube Music", "youtube.com", "https://music.youtube.com/?source=pwa", same); got != id1 {
		t.Fatalf("the owner's own identity must keep its id, got %q", got)
	}
	other := func(id string) string {
		if id == id1 {
			return "https://someone.else/"
		}
		return ""
	}
	got := NewID("YouTube Music", "youtube.com", "https://music.youtube.com/?source=pwa", other)
	if len(HashOf(got)) != 8 || !Valid(got) || !strings.HasPrefix(HashOf(got), HashOf(id1)) {
		t.Fatalf("collision should give 8 digits, got %q", got)
	}
	taken := func(string) string { return "x" }
	if got := NewID("A", "a.org", "https://a.org/", taken); got != "" {
		t.Fatalf("both taken should give \"\", got %q", got)
	}
}

func TestIdentity(t *testing.T) {
	if got := Identity("", "https://a.org/x#frag", 1); got != "https://a.org/x" {
		t.Errorf("fragment kept: %q", got)
	}
	if got := Identity("https://a.org/?id=1", "https://a.org/x", 3); got != "https://a.org/?id=1#3" {
		t.Errorf("manifest id / copy: %q", got)
	}
}
