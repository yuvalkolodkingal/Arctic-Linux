package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp/manage"
)

func init() { manage.PSLPath = "../../internal/webapp/psl/testdata/public_suffix_list.dat" }

func fixturePNG(size int, c color.NRGBA) []byte {
	img := image.NewNRGBA(image.Rect(0, 0, size, size))
	for i := 0; i < len(img.Pix); i += 4 {
		img.Pix[i], img.Pix[i+1], img.Pix[i+2], img.Pix[i+3] = c.R, c.G, c.B, c.A
	}
	var b bytes.Buffer
	png.Encode(&b, img)
	return b.Bytes()
}

// fixtureSite serves a small web app: a page, a manifest and a 256 px icon.
func fixtureSite(t *testing.T) *httptest.Server {
	icon := fixturePNG(256, color.NRGBA{20, 120, 200, 255})
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		io.WriteString(w, `<!doctype html><html><head><title>Notes – Home</title><link rel="manifest" href="/app.webmanifest"></head><body>hi</body></html>`)
	})
	mux.HandleFunc("/app.webmanifest", func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"name":"Fixture Notes","start_url":"/?pwa","categories":["productivity"],"icons":[{"src":"/icon.png","sizes":"256x256","type":"image/png"}]}`)
	})
	mux.HandleFunc("/icon.png", func(w http.ResponseWriter, r *http.Request) { w.Write(icon) })
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// Inspect → install → list → set icon (revision .r1) → update → remove --keep-data → kept →
// reinstall (same id and profile) → forget, checking which files appear and disappear.
func TestLifecycleCLI(t *testing.T) {
	tc := newTestCLI(t)
	srv := fixtureSite(t)
	p := tc.m.Paths

	code, m := tc.runJSON("inspect", srv.URL)
	if code != 0 {
		t.Fatalf("inspect: %v", m)
	}
	pr := m["preview"].(map[string]any)
	if pr["name"] != "Fixture Notes" || pr["category"] != "Office" || pr["start_url"] != srv.URL+"/?pwa" {
		t.Fatalf("preview %v", pr)
	}
	icons := pr["icons"].([]any)
	if len(icons) != 2 || icons[1].(map[string]any)["source"] != "monogram" {
		t.Fatalf("icons %v", icons)
	}
	for _, ic := range icons {
		if path := ic.(map[string]any)["path"].(string); !exists(path) {
			t.Fatalf("preview icon %s missing", path)
		}
	}
	warnings := pr["warnings"].([]any)
	if len(warnings) != 1 || warnings[0].(map[string]any)["code"] != "insecure" {
		t.Fatalf("warnings %v", warnings)
	}

	code, m = tc.runJSON("install", "--preview", pr["token"].(string), "--name", "My Notes")
	if code != 0 {
		t.Fatalf("install: %v", m)
	}
	app := m["app"].(map[string]any)
	id := app["id"].(string)
	if app["name"] != "My Notes" || !strings.HasPrefix(id, "org.arcticlinux.WebApp.MyNotes_") || !exists(m["desktop_file"].(string)) {
		t.Fatalf("install result %v", m)
	}
	for _, f := range []string{p.AppFile(id), p.SourceIcon(id), p.IconFile(id, 48), p.IconFile(id, 512)} {
		if !exists(f) {
			t.Fatalf("%s missing after install", f)
		}
	}
	if code, m = tc.runJSON("install", srv.URL); code != 1 || m["code"] != "exists" {
		t.Fatalf("second install: %d %v", code, m)
	}

	iconFile := filepath.Join(tc.home, "mine.png")
	os.WriteFile(iconFile, fixturePNG(128, color.NRGBA{200, 10, 10, 255}), 0o644)
	code, m = tc.runJSON("set", id, "--icon", iconFile, "--links", "app", "--add-domain", "accounts.example.org")
	if code != 0 || m["applied"] != "saved" {
		t.Fatalf("set: %v", m)
	}
	if exists(p.IconFile(id, 48)) || !exists(p.IconFile(id+".r1", 48)) {
		t.Fatal("icon revision not bumped")
	}
	desk, _ := os.ReadFile(p.DesktopFile(id))
	if !strings.Contains(string(desk), "Icon="+id+".r1\n") {
		t.Fatalf("desktop Icon not updated:\n%s", desk)
	}
	code, m = tc.runJSON("set", id, "--runtime", "chromium:brave")
	if code != 1 || m["code"] != "invalid" || m["fields"].(map[string]any)["runtime"] != "Brave isn’t installed." {
		t.Fatalf("set runtime: %v", m)
	}

	code, m = tc.runJSON("update", id)
	up := m["updated"].([]any)[0].(map[string]any)
	if code != 0 || !strings.Contains(strings.Join(toStrings(up["kept"]), ","), "icon") || !strings.Contains(strings.Join(toStrings(up["kept"]), ","), "name") {
		t.Fatalf("update must keep your name and icon: %v", m)
	}

	os.MkdirAll(p.Profile(id), 0o700)
	os.WriteFile(filepath.Join(p.Profile(id), "cookies.sqlite"), []byte("signed in"), 0o600)
	if code, m = tc.runJSON("remove", id, "--keep-data"); code != 0 {
		t.Fatalf("remove: %v", m)
	}
	if exists(p.DesktopFile(id)) || exists(p.IconFile(id+".r1", 48)) || !exists(filepath.Join(p.Profile(id), "cookies.sqlite")) {
		t.Fatal("remove --keep-data: wrong files")
	}
	code, m = tc.runJSON("install", srv.URL)
	if code != 0 || m["app"].(map[string]any)["id"] != id {
		t.Fatalf("reinstall must reuse the id: %v", m)
	}
	if !exists(filepath.Join(p.Profile(id), "cookies.sqlite")) {
		t.Fatal("reinstall lost the sign-in")
	}
	code, m = tc.runJSON("install", srv.URL, "--new-copy")
	if code != 0 || m["app"].(map[string]any)["id"] == id {
		t.Fatalf("second copy: %v", m)
	}
	copyID := m["app"].(map[string]any)["id"].(string)
	if code, _ = tc.runJSON("remove", id, copyID); code != 0 {
		t.Fatal("remove both")
	}
	if exists(p.AppDir(id)) || exists(p.AppDir(copyID)) {
		t.Fatal("remove without --keep-data left data")
	}
}

func toStrings(v any) []string {
	var out []string
	for _, x := range v.([]any) {
		out = append(out, x.(string))
	}
	return out
}

// serve: responses by id, events told apart by "event", progress only here, changed after
// writes, unknown methods and bad JSON answered.
func TestServeTranscript(t *testing.T) {
	tc := newTestCLI(t)
	srv := fixtureSite(t)
	inR, inW := io.Pipe()
	outR, outW := io.Pipe()
	c := &cli{stdin: inR, stdout: outW, stderr: io.Discard, newManager: func() (*manage.Manager, error) { return tc.m, nil }, euid: func() int { return 1000 }}
	done := make(chan int)
	go func() { done <- c.main([]string{"serve"}); outW.Close() }()
	lines := make(chan map[string]any, 100)
	go func() {
		sc := bufio.NewScanner(outR)
		sc.Buffer(make([]byte, 1<<20), 1<<20)
		for sc.Scan() {
			var m map[string]any
			if err := json.Unmarshal(sc.Bytes(), &m); err != nil {
				t.Errorf("not JSON: %s", sc.Text())
			}
			lines <- m
		}
		close(lines)
	}()
	send := func(s string) { io.WriteString(inW, s+"\n") }
	wait := func(id float64) (map[string]any, []map[string]any) {
		var events []map[string]any
		timeout := time.After(20 * time.Second)
		for {
			select {
			case m, ok := <-lines:
				if !ok {
					t.Fatal("serve exited")
				}
				if _, isEvent := m["event"]; isEvent {
					events = append(events, m)
					continue
				}
				if m["id"] == id {
					return m, events
				}
			case <-timeout:
				t.Fatalf("no response to %v", id)
			}
		}
	}
	send(`{"id":0,"method":"Hello"}`)
	r, _ := wait(0)
	res := r["result"].(map[string]any)
	if res["protocol_version"] != float64(1) || len(res["runtimes"].([]any)) != 6 {
		t.Fatalf("hello %v", r)
	}
	send(`{"id":1,"method":"Inspect","params":{"url":"` + srv.URL + `"}}`)
	r, events := wait(1)
	if r["error"] != nil || len(events) == 0 || events[0]["event"] != "progress" || events[0]["request"] != float64(1) || events[0]["stage"] != "page" {
		t.Fatalf("inspect %v %v", r, events)
	}
	token := r["result"].(map[string]any)["token"].(string)
	send(`{"id":2,"method":"Install","params":{"token":"` + token + `","icon":"monogram","category":"Calendar","launch":false}}`)
	r, _ = wait(2)
	if r["error"] != nil {
		t.Fatalf("install %v", r)
	}
	id := r["result"].(map[string]any)["app"].(map[string]any)["id"].(string)
	// The changed event follows the response.
	ev := <-lines
	if ev["event"] != "changed" || ev["ids"].([]any)[0] != id {
		t.Fatalf("changed %v", ev)
	}
	send(`{"id":3,"method":"List","params":{"kept":true}}`)
	r, _ = wait(3)
	if apps := r["result"].(map[string]any)["apps"].([]any); len(apps) != 1 || apps[0].(map[string]any)["category"] != "Calendar" {
		t.Fatalf("list %v", r)
	}
	send(`{"id":4,"method":"Get","params":{"id":"` + id + `","sizes":true}}`)
	r, _ = wait(4)
	if app := r["result"].(map[string]any)["app"].(map[string]any); app["data_bytes"] == nil {
		t.Fatalf("get with sizes %v", r)
	}
	send(`{"id":5,"method":"Frobnicate"}`)
	if r, _ = wait(5); r["error"].(map[string]any)["code"] != "unknown_method" {
		t.Fatalf("unknown method %v", r)
	}
	send(`{"id":6,"method":"Set","params":{"id":"` + id + `","runtime":"chromium:vivaldi"}}`)
	r, _ = wait(6)
	if e := r["error"].(map[string]any); e["code"] != "invalid" || e["fields"].(map[string]any)["runtime"] != "Vivaldi isn’t installed." {
		t.Fatalf("set invalid %v", r)
	}
	send(`{"id":7,"method":"Cancel","params":{"request":99}}`)
	if r, _ = wait(7); r["result"] == nil {
		t.Fatalf("cancel %v", r)
	}
	send(`{"id":8,"method":"Remove","params":{"ids":["` + id + `"],"keep_data":true}}`)
	r, _ = wait(8)
	if rm := r["result"].(map[string]any)["removed"].([]any); rm[0].(map[string]any)["kept_data"] != true {
		t.Fatalf("remove %v", r)
	}
	<-lines // changed
	send(`{"id":9,"method":"Forget","params":{"ids":["` + id + `"]}}`)
	if r, _ = wait(9); r["error"] != nil {
		t.Fatalf("forget %v", r)
	}
	<-lines // changed
	send(`not json`)
	if m := <-lines; m["error"].(map[string]any)["code"] != "bad_request" {
		t.Fatalf("bad json %v", m)
	}
	inW.Close()
	if code := <-done; code != 0 {
		t.Fatalf("serve exit %d", code)
	}
	if exists(filepath.Join(tc.m.Paths.RuntimeDir, "inspect-"+token)) {
		t.Fatal("serve left its preview directory")
	}
}
