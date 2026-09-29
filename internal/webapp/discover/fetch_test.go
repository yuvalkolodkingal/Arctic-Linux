package discover

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/psl"
)

func errCode(err error) string {
	var pe *protocol.Error
	if errors.As(err, &pe) {
		return pe.Code
	}
	return fmt.Sprintf("not a protocol error: %v", err)
}

func mustURL(s string) *url.URL {
	u, err := url.Parse(s)
	if err != nil {
		panic(err)
	}
	return u
}

func pngBytes(size int, c color.NRGBA) []byte {
	img := image.NewNRGBA(image.Rect(0, 0, size, size))
	for i := 0; i < len(img.Pix); i += 4 {
		img.Pix[i], img.Pix[i+1], img.Pix[i+2], img.Pix[i+3] = c.R, c.G, c.B, c.A
	}
	var b bytes.Buffer
	png.Encode(&b, img)
	return b.Bytes()
}

func TestFetchRedirectLimits(t *testing.T) {
	mux := http.NewServeMux()
	for i := 0; i < 8; i++ {
		i := i
		mux.HandleFunc(fmt.Sprintf("/r%d", i), func(w http.ResponseWriter, r *http.Request) {
			http.Redirect(w, r, fmt.Sprintf("/r%d", i+1), http.StatusFound)
		})
	}
	mux.HandleFunc("/loop", func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, "/loop", http.StatusFound) })
	mux.HandleFunc("/r5ok", func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, "/r3", http.StatusFound) })
	mux.HandleFunc("/r8", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("<title>end</title>")) })
	srv := httptest.NewServer(mux)
	defer srv.Close()
	f := NewFetcher(nil)
	ctx := context.Background()
	if _, err := f.Get(ctx, mustURL(srv.URL+"/r0"), "text/html", MaxHTML, true); errCode(err) != webapp.CodeFetch {
		t.Fatalf("8 redirects: %v", err)
	}
	if _, err := f.Get(ctx, mustURL(srv.URL+"/loop"), "text/html", MaxHTML, true); errCode(err) != webapp.CodeFetch {
		t.Fatalf("loop: %v", err)
	}
	if r, err := f.Get(ctx, mustURL(srv.URL+"/r3"), "text/html", MaxHTML, true); err != nil || !strings.Contains(string(r.Body), "end") {
		t.Fatalf("5 redirects must work: %v", err)
	}
}

func TestFetchHTTPSDowngradeRefused(t *testing.T) {
	plain := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("plain")) }))
	defer plain.Close()
	tlsSrv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, plain.URL+"/", http.StatusFound)
	}))
	tlsSrv.Config.ErrorLog = log.New(io.Discard, "", 0) // the untrusted-certificate case logs a handshake error
	tlsSrv.StartTLS()
	defer tlsSrv.Close()
	f := NewFetcher(tlsSrv.Client().Transport.(*http.Transport).TLSClientConfig.RootCAs)
	if _, err := f.Get(context.Background(), mustURL(tlsSrv.URL), "text/html", MaxHTML, true); errCode(err) != webapp.CodeFetch {
		t.Fatalf("https → http: %v", err)
	}
	// An untrusted certificate is a tls error, never skipped.
	f2 := NewFetcher(nil)
	if _, err := f2.Get(context.Background(), mustURL(tlsSrv.URL), "text/html", MaxHTML, true); errCode(err) != webapp.CodeTLS {
		t.Fatalf("self-signed: %v", err)
	}
}

func TestFetchSizesStatusAndHeaders(t *testing.T) {
	var gotUA, gotAccept string
	mux := http.NewServeMux()
	mux.HandleFunc("/big", func(w http.ResponseWriter, r *http.Request) {
		gotUA, gotAccept = r.UserAgent(), r.Header.Get("Accept")
		w.Header().Set("Content-Type", "text/html")
		w.Write(bytes.Repeat([]byte("a"), 3<<20))
	})
	mux.HandleFunc("/404", func(w http.ResponseWriter, r *http.Request) { http.NotFound(w, r) })
	mux.HandleFunc("/slow", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("<title>"))
		w.(http.Flusher).Flush()
		time.Sleep(2 * time.Second)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()
	f := NewFetcher(nil)
	r, err := f.Get(context.Background(), mustURL(srv.URL+"/big"), "text/html,application/xhtml+xml", MaxHTML, true)
	if err != nil || len(r.Body) != MaxHTML || !r.Truncated {
		t.Fatalf("3 MiB HTML: %v %d", err, len(r.Body))
	}
	if gotUA != webapp.FetchUserAgent || gotAccept != "text/html,application/xhtml+xml" {
		t.Fatalf("headers: %q %q", gotUA, gotAccept)
	}
	if _, err := f.Get(context.Background(), mustURL(srv.URL+"/big"), "image/*", MaxImage, false); errCode(err) != webapp.CodeTooLarge {
		t.Fatalf("image over its limit: %v", err)
	}
	if _, err := f.Get(context.Background(), mustURL(srv.URL+"/404"), "text/html", MaxHTML, true); errCode(err) != webapp.CodeHTTP {
		t.Fatalf("404: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	if _, err := f.Get(ctx, mustURL(srv.URL+"/slow"), "text/html", MaxHTML, true); errCode(err) != webapp.CodeTimeout {
		t.Fatalf("slow body: %v", err)
	}
}

// A public page may not pull its manifest or icons from a private address; a page on your own
// network may.
func TestPrivateAddressGuard(t *testing.T) {
	icon := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(pngBytes(64, color.NRGBA{1, 2, 3, 255}))
	}))
	defer icon.Close()
	page := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("<title>x</title>"))
	}))
	defer page.Close()
	pageAddr := strings.TrimPrefix(page.URL, "http://")

	for _, pagePublic := range []bool{true, false} {
		f := NewFetcher(nil)
		f.private = func(address string, ip net.IP) bool {
			if address == pageAddr && pagePublic {
				return false
			}
			return webapp.PrivateIP(ip)
		}
		r, err := f.Get(context.Background(), mustURL(page.URL), "text/html", MaxHTML, true)
		if err != nil {
			t.Fatal(err)
		}
		// A dial to a private address that lost the race (a Happy Eyeballs fallback) comes
		// after the page's own and must not count: the page's connection does.
		if err := f.control("tcp", "[fd00::1]:80", nil); err != nil {
			t.Fatal(err)
		}
		f.pageFrom(r)
		_, err = f.Get(context.Background(), mustURL(icon.URL+"/i.png"), "image/*", MaxImage, false)
		if pagePublic && errCode(err) != webapp.CodeFetch {
			t.Fatalf("public page → private icon: %v", err)
		}
		if !pagePublic && err != nil {
			t.Fatalf("private page → private icon refused: %v", err)
		}
	}
}

// A public page's refresh to a private address that isn't a page leaves the page public: its
// icons still may not come from your network.
func TestPrivateAddressGuardAfterRefresh(t *testing.T) {
	var iconHits atomic.Int32
	priv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/i.png" {
			iconHits.Add(1)
		}
		w.Header().Set("Content-Type", "image/png")
		w.Write(pngBytes(64, color.NRGBA{1, 2, 3, 255}))
	}))
	defer priv.Close()
	page := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		fmt.Fprintf(w, `<title>Pub</title><meta http-equiv=refresh content="0; url=%s/x.png"><link rel=icon href="%s/i.png" sizes=64x64>`, priv.URL, priv.URL)
	}))
	defer page.Close()
	pageAddr := strings.TrimPrefix(page.URL, "http://")
	f := NewFetcher(nil)
	f.private = func(address string, ip net.IP) bool { return address != pageAddr && webapp.PrivateIP(ip) }
	res, err := Discover(context.Background(), page.URL, Options{PSL: testPSL(t), Fetcher: f})
	if err != nil {
		t.Fatal(err)
	}
	if iconHits.Load() != 0 || len(res.Icons) != 0 {
		t.Fatalf("a public page's icon came from a private address: %+v", res.Icons)
	}
}

// A .local page is dialled at the address glibc finds for it (Go's resolver can't do mDNS).
func TestFetchMDNSName(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("<title>" + r.Host + "</title>"))
	}))
	defer srv.Close()
	_, port, _ := net.SplitHostPort(strings.TrimPrefix(srv.URL, "http://"))
	getent := filepath.Join(t.TempDir(), "getent")
	os.WriteFile(getent, []byte("#!/bin/sh\n[ \"$2\" = printer.local ] || exit 2\necho '127.0.0.1       STREAM printer.local'\n"), 0o755)
	old := webapp.Getent
	webapp.Getent = getent
	defer func() { webapp.Getent = old }()

	f := NewFetcher(nil)
	f.client.Transport.(*http.Transport).Proxy = nil // whatever proxy the test's environment names
	r, err := f.Get(context.Background(), mustURL("http://printer.local:"+port+"/"), "text/html", MaxHTML, true)
	if err != nil || string(r.Body) != "<title>printer.local:"+port+"</title>" {
		t.Fatalf("%v %+v", err, r)
	}
	f.pageFrom(r)
	if !f.allowPrivate {
		t.Fatal("a page on your own network may load its icons from it")
	}
}

// ---- whole-site fixtures ----

type site struct {
	files map[string]string // path → body; a "->" prefix means redirect
	types map[string]string
}

func (s site) serve(t *testing.T) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.URL.Path
		if r.URL.RawQuery != "" {
			key += "?" + r.URL.RawQuery
		}
		body, ok := s.files[key]
		if !ok {
			http.NotFound(w, r)
			return
		}
		if to, isRedirect := strings.CutPrefix(body, "->"); isRedirect {
			http.Redirect(w, r, to, http.StatusFound)
			return
		}
		if ct, ok := s.types[key]; ok {
			w.Header().Set("Content-Type", ct)
		}
		w.Write([]byte(body))
	}))
}

func testPSL(t *testing.T) *psl.List {
	l, err := psl.Load("../psl/testdata/public_suffix_list.dat")
	if err != nil {
		t.Fatal(err)
	}
	return l
}

func TestDiscoverManifestSite(t *testing.T) {
	big := string(pngBytes(512, color.NRGBA{200, 0, 0, 255}))
	small := string(pngBytes(32, color.NRGBA{0, 0, 200, 255}))
	s := site{files: map[string]string{
		"/":                     `<html><head><title>Music - Home</title><link rel=manifest href=/manifest.webmanifest><link rel=icon href=/fav.png sizes=32x32></head></html>`,
		"/manifest.webmanifest": `{"name":"Tunes","start_url":"/?source=pwa","categories":["music"],"theme_color":"#123456","icons":[{"src":"/512.png","sizes":"512x512","type":"image/png"}]}`,
		"/512.png":              big,
		"/fav.png":              small,
	}, types: map[string]string{"/": "text/html; charset=utf-8"}}
	srv := s.serve(t)
	defer srv.Close()
	var stages []string
	res, err := Discover(context.Background(), srv.URL, Options{PSL: testPSL(t), Progress: func(stage, _ string) { stages = append(stages, stage) }})
	if err != nil {
		t.Fatal(err)
	}
	if res.Name != "Tunes" || res.NameSource != "manifest" || res.Category != "AudioVideo" || res.ThemeColor != "#123456" {
		t.Fatalf("%+v", res)
	}
	if res.StartURL != srv.URL+"/?source=pwa" || res.ManifestURL != srv.URL+"/manifest.webmanifest" || !res.Insecure {
		t.Fatalf("urls: %+v", res)
	}
	if len(res.Icons) != 2 || res.Icons[0].Size != 512 || res.Icons[0].Source != "manifest" || res.Icons[1].Size != 32 {
		t.Fatalf("icons: %+v", res.Icons)
	}
	if strings.Join(stages, ",") != "page,manifest,icons,icons,icons" {
		t.Fatalf("stages %v", stages)
	}
}

func TestDiscoverDeepURLAndNonHTML(t *testing.T) {
	s := site{files: map[string]string{
		"/mail/u/1/": `<title>Mail</title><link rel=manifest href=/m.json>`,
		"/m.json":    `{"name":"Mail","start_url":"/mail/","scope":"/mail/"}`,
		"/file.pdf":  "%PDF-1.4",
		"/refresh":   `<title>r</title><meta http-equiv=refresh content="0; url=/mail/u/1/">`,
	}, types: map[string]string{"/file.pdf": "application/pdf"}}
	srv := s.serve(t)
	defer srv.Close()
	res, err := Discover(context.Background(), srv.URL+"/mail/u/1/", Options{PSL: testPSL(t)})
	if err != nil {
		t.Fatal(err)
	}
	if res.StartURL != srv.URL+"/mail/u/1/" {
		t.Fatalf("typed deep URL must be kept: %s", res.StartURL)
	}
	if _, err := Discover(context.Background(), srv.URL+"/file.pdf", Options{PSL: testPSL(t)}); errCode(err) != webapp.CodeNotHTML {
		t.Fatalf("pdf: %v", err)
	}
	res, err = Discover(context.Background(), srv.URL+"/refresh", Options{PSL: testPSL(t)})
	if err != nil || res.Name != "Mail" {
		t.Fatalf("meta refresh: %v %+v", err, res)
	}
	if _, err := Discover(context.Background(), srv.URL+"/missing", Options{PSL: testPSL(t)}); errCode(err) != webapp.CodeHTTP {
		t.Fatalf("404: %v", err)
	}
}

// A redirect to a sign-in page on another site: its name and icons are ignored and the typed
// origin is probed instead; the typed URL stays the start URL.
func TestDiscoverLoginWall(t *testing.T) {
	// The fixture PSL treats 127.0.0.1:port and localhost:port as different sites.
	login := site{files: map[string]string{
		"/signin": `<title>Sign in - Accounts</title><link rel=icon href=/accounts.png>`,
	}}
	lsrv := login.serve(t)
	defer lsrv.Close()
	loginURL := strings.Replace(lsrv.URL, "127.0.0.1", "localhost", 1) + "/signin"
	app := site{files: map[string]string{
		"/mail/":                "->" + loginURL,
		"/manifest.webmanifest": `{"name":"Mailer","icons":[{"src":"/icon.png","sizes":"256x256"}]}`,
		"/icon.png":             string(pngBytes(256, color.NRGBA{9, 9, 9, 255})),
	}}
	asrv := app.serve(t)
	defer asrv.Close()
	res, err := Discover(context.Background(), asrv.URL+"/mail/", Options{PSL: testPSL(t)})
	if err != nil {
		t.Fatal(err)
	}
	if !res.LoginWall || res.Name != "Mailer" || res.StartURL != asrv.URL+"/mail/" {
		t.Fatalf("%+v", res)
	}
	if len(res.Icons) == 0 || !strings.HasPrefix(res.Icons[0].URL, asrv.URL) {
		t.Fatalf("icons from the sign-in page: %+v", res.Icons)
	}
}
