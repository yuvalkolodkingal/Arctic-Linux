//go:build cgo && webkit

package webkit

import (
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp/psl"
)

// The pure-Go Public Suffix List (what the manager stores as an app's scope) agrees with
// libsoup's, which WebKit itself uses.
func TestPSLMatchesLibsoup(t *testing.T) {
	list, err := psl.Load(psl.SystemPath)
	if err != nil {
		t.Skipf("no system Public Suffix List: %v", err)
	}
	for _, host := range []string{
		"mail.google.com", "music.youtube.com", "foo.bar.co.uk", "user.github.io", "a.b.user.github.io",
		"www.walla.co.il", "app.slack.com", "outlook.office.com", "www.bbc.co.uk", "x.y.kawasaki.jp",
		"city.kawasaki.jp", "a.city.kawasaki.jp", "www.ck", "example.pages.dev", "discord.com",
	} {
		want := BaseDomain(host)
		if got := list.Site(host); got != want {
			t.Errorf("%s: psl %q, libsoup %q", host, got, want)
		}
	}
}

// The host runs against a WebKitGTK at least as new as the 2.50 floor (D-4), and reports its
// version without a display.
func TestVersion(t *testing.T) {
	v := Version()
	parts := strings.Split(v, ".")
	if len(parts) != 3 {
		t.Fatalf("version %q", v)
	}
	major, _ := strconv.Atoi(parts[0])
	minor, _ := strconv.Atoi(parts[1])
	if major != 2 || minor < 50 {
		t.Fatalf("WebKitGTK %s is older than 2.50", v)
	}
	if os.Getenv("WAYLAND_DISPLAY") == "" && os.Getenv("DISPLAY") == "" {
		t.Logf("WebKitGTK %s (no display, as intended)", v)
	}
}
