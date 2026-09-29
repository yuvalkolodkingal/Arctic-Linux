package webapp

import (
	"bufio"
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode"
)

// DesktopEntry renders the app's launcher entry with exactly these keys, in this order. Exec
// holds only the validated id (plus %u for a mail-link app): never a URL, never another field
// code. No WebBrowser category (Settings' browser role picks by it), no NoDisplay, no MimeType
// but the mailto opt-in.
func DesktopEntry(a *App) []byte {
	var b bytes.Buffer
	kv := func(k, v string) { b.WriteString(k + "=" + v + "\n") }
	host := a.Host()
	b.WriteString("[Desktop Entry]\n")
	kv("Type", "Application")
	kv("Version", "1.5")
	kv("Name", escapeValue(clean(a.Name, 64)))
	kv("Comment", escapeValue(clean("Web app · "+host, 160)))
	exec := "arctic-webapp run " + a.ID
	if a.HasHandler("mailto") {
		exec += " %u"
	}
	kv("Exec", exec)
	kv("TryExec", "arctic-webapp")
	kv("Icon", a.IconName())
	kv("Terminal", "false")
	kv("StartupNotify", "true")
	kv("StartupWMClass", escapeValue(clean(a.WMClass, 255)))
	kv("SingleMainWindow", "true")
	kv("Categories", categories(a.Category))
	kv("Keywords", "web;app;"+escapeList(strings.ToLower(host))+";")
	if a.HasHandler("mailto") {
		kv("MimeType", "x-scheme-handler/mailto;")
	}
	kv("X-Arctic-WebApp-Id", a.ID)
	kv("X-Arctic-WebApp-URL", escapeValue(clean(a.StartURL, 2048)))
	kv("X-Arctic-WebApp-Runtime", a.Runtime)
	kv("X-Arctic-WebApp-Schema", "1")
	return b.Bytes()
}

// categories maps the app's category to one main category plus X-Arctic-WebApp; Calendar is
// Office;Calendar (the Calendar default-app role looks for it).
func categories(c string) string {
	if c == "Calendar" {
		return "Office;Calendar;X-Arctic-WebApp;"
	}
	return c + ";X-Arctic-WebApp;"
}

// clean strips control and bidi-override characters, collapses whitespace and cuts the value
// to max runes.
func clean(s string, max int) string {
	var b strings.Builder
	space := false
	n := 0
	for _, r := range s {
		if unicode.IsSpace(r) {
			space = true
			continue
		}
		if unicode.IsControl(r) || isBidi(r) || r == unicode.ReplacementChar {
			continue
		}
		if space && b.Len() > 0 {
			if n >= max {
				break
			}
			b.WriteByte(' ')
			n++
		}
		space = false
		if n >= max {
			break
		}
		b.WriteRune(r)
		n++
	}
	return strings.TrimSpace(b.String())
}

func isBidi(r rune) bool {
	return r >= 0x202A && r <= 0x202E || r >= 0x2066 && r <= 0x2069 || r == 0x200E || r == 0x200F || r == 0x061C
}

// CleanName is the stored form of a display name (same rules as the .desktop Name).
func CleanName(s string) string { return clean(s, 64) }

// escapeValue escapes a string value for a desktop entry (\\ first, then the others).
func escapeValue(s string) string {
	r := strings.NewReplacer(`\`, `\\`, "\n", `\n`, "\t", `\t`, "\r", `\r`)
	return r.Replace(s)
}

// escapeList escapes one element of a list value (;-separated).
func escapeList(s string) string {
	return strings.ReplaceAll(escapeValue(s), ";", `\;`)
}

// ParseEntry reads the [Desktop Entry] group of a .desktop file into a map (unescaped only
// where the manager needs it: it compares ids and paths, never runs anything from it).
func ParseEntry(data []byte) map[string]string {
	m := map[string]string{}
	in := false
	sc := bufio.NewScanner(bytes.NewReader(data))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") {
			in = line == "[Desktop Entry]"
			continue
		}
		if !in {
			continue
		}
		if k, v, ok := strings.Cut(line, "="); ok {
			m[strings.TrimSpace(k)] = strings.TrimSpace(v)
		}
	}
	return m
}

// DesktopIDs lists the web-app launcher entries in the applications directory: file name
// org.arcticlinux.WebApp.*.desktop or an X-Arctic-WebApp-Id key, with a valid id.
func (p Paths) DesktopIDs() []string {
	entries, err := os.ReadDir(p.Applications())
	if err != nil {
		return nil
	}
	var ids []string
	for _, e := range entries {
		name := e.Name()
		if !strings.HasSuffix(name, ".desktop") || !strings.HasPrefix(name, IDPrefix) {
			continue
		}
		id := strings.TrimSuffix(name, ".desktop")
		if !Valid(id) {
			continue
		}
		data, err := os.ReadFile(filepath.Join(p.Applications(), name))
		if err != nil {
			continue
		}
		if ParseEntry(data)["X-Arctic-WebApp-Id"] == id {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	return ids
}

// WriteDesktop writes the app's launcher entry (0644, atomic).
func (p Paths) WriteDesktop(a *App) error {
	if !Valid(a.ID) {
		return errors.New("bad id")
	}
	if err := os.MkdirAll(p.Applications(), 0o755); err != nil {
		return err
	}
	return WriteFileAtomic(p.DesktopFile(a.ID), DesktopEntry(a), 0o644)
}
