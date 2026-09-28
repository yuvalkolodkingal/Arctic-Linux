package manage

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"image"
	"image/png"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

func str(s string) *string { return &s }
func yes() *bool           { t := true; return &t }

func TestSetAppliedAndUserSet(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	res, err := m.Set(context.Background(), api.SetParams{ID: a.ID, Name: str("  My   Notes "), Category: str("Office")})
	if err != nil {
		t.Fatal(err)
	}
	if res.Applied != "saved" || res.App.Name != "My Notes" {
		t.Fatalf("%+v", res)
	}
	got, _ := m.Paths.Load(a.ID)
	if !got.IsUserSet("name") || !got.IsUserSet("category") || got.NameSource != "user" {
		t.Fatalf("user_set %v", got.UserSet)
	}
	// Live options on a running WebKit app: SIGHUP, applied live. The "host" is a sleep child
	// (SIGHUP ends it); a fake /proc gives it the host's command line.
	proc := t.TempDir()
	old := webapp.ProcRoot
	webapp.ProcRoot = proc
	defer func() { webapp.ProcRoot = old }()
	child := exec.Command("sleep", "30")
	if err := child.Start(); err != nil {
		t.Skip("no sleep binary")
	}
	defer child.Process.Kill()
	pid := child.Process.Pid
	m.Paths.WritePid(a.ID, pid)
	os.MkdirAll(filepath.Join(proc, strconv.Itoa(pid)), 0o755)
	os.WriteFile(filepath.Join(proc, strconv.Itoa(pid), "cmdline"), []byte("arctic-webapp-host\x00--app-id\x00"+a.ID+"\x00"), 0o644)
	// Rendering applies at the next start; nothing is signalled.
	res, err = m.Set(context.Background(), api.SetParams{ID: a.ID, Rendering: str("software")})
	if err != nil || res.Applied != "next_start" {
		t.Fatalf("rendering: %+v %v", res, err)
	}
	res, err = m.Set(context.Background(), api.SetParams{ID: a.ID, AddDomain: "Accounts.Example.org", Devtools: yes(), ExtraDomains: nil})
	if err != nil {
		t.Fatal(err)
	}
	if res.Applied != "live" || len(res.App.ExtraDomains) != 1 || res.App.ExtraDomains[0] != "accounts.example.org" || !res.App.Devtools {
		t.Fatalf("live: %+v", res)
	}
	_, err = m.Set(context.Background(), api.SetParams{ID: a.ID, AddDomain: "bad domain/x"})
	if code(err) != webapp.CodeInvalid {
		t.Fatalf("bad domain: %v", err)
	}
	_, err = m.Set(context.Background(), api.SetParams{ID: a.ID, MailLinks: yes()})
	if code(err) != webapp.CodeInvalid {
		t.Fatalf("mail links on a non-mail site: %v", err)
	}
}

func selfSigned(t *testing.T, host string) string {
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: host}, NotBefore: time.Now(), NotAfter: time.Now().Add(time.Hour), DNSNames: []string{host}}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "cert.pem")
	os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o600)
	return path
}

func TestTrustCertificatePrivateOnly(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Home", "https://ha.lan:8123/")
	put(t, m, a)
	old := LookupHost
	defer func() { LookupHost = old }()
	LookupHost = func(h string) ([]string, error) {
		if h == "ha.lan" {
			return []string{"192.168.1.20"}, nil
		}
		return []string{"93.184.216.34"}, nil // rebinding: a .lan name pointing at a public address
	}
	pemPath := selfSigned(t, "ha.lan")
	if err := m.TrustCertificate(a.ID, "ha.lan:8123", pemPath); err != nil {
		t.Fatal(err)
	}
	got, _ := m.Paths.Load(a.ID)
	if len(got.TLSExceptions) != 1 || got.TLSExceptions[0].Host != "ha.lan:8123" || len(got.TLSExceptions[0].SHA256) != 64 {
		t.Fatalf("%+v", got.TLSExceptions)
	}
	for _, host := range []string{"example.com", "evil.lan", "8.8.8.8"} {
		if err := m.TrustCertificate(a.ID, host, pemPath); code(err) != webapp.CodeInvalid {
			t.Errorf("%s: %v", host, err)
		}
	}
	notPEM := filepath.Join(t.TempDir(), "x")
	os.WriteFile(notPEM, []byte("hello"), 0o600)
	if err := m.TrustCertificate(a.ID, "192.168.1.20", notPEM); code(err) != webapp.CodeInvalid {
		t.Fatalf("not a certificate: %v", err)
	}
	info := m.Info(got, false)
	if len(info.TLSExceptions) != 1 || info.TLSExceptions[0].SHA256 == "" {
		t.Fatal("info shows the exception without its PEM")
	}
	if _, err := m.Set(context.Background(), api.SetParams{ID: a.ID, ForgetCertificate: "ha.lan:8123"}); err != nil {
		t.Fatal(err)
	}
	got, _ = m.Paths.Load(a.ID)
	if len(got.TLSExceptions) != 0 {
		t.Fatal("forget-certificate kept it")
	}
}

func TestIconFromFileUpgradesLetterIcons(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	a.Icon.Source = "monogram"
	put(t, m, a)
	write := func(size int) string {
		var b bytes.Buffer
		png.Encode(&b, image.NewNRGBA(image.Rect(0, 0, size, size)))
		p := filepath.Join(t.TempDir(), "fav.png")
		os.WriteFile(p, b.Bytes(), 0o600)
		return p
	}
	if changed, err := m.IconFromFile(a.ID, write(32), "host-favicon"); err != nil || changed {
		t.Fatalf("32 px must not replace the icon: %v %v", changed, err)
	}
	changed, err := m.IconFromFile(a.ID, write(128), "host-favicon")
	if err != nil || !changed {
		t.Fatalf("upgrade: %v %v", changed, err)
	}
	got, _ := m.Paths.Load(a.ID)
	if got.Icon.Rev != 1 || got.Icon.Source != "host-favicon" || !fileExists(m.Paths.IconFile(a.ID+".r1", 64)) {
		t.Fatalf("%+v", got.Icon)
	}
	// Not again: it has a real icon now.
	if changed, _ := m.IconFromFile(a.ID, write(256), "host-favicon"); changed {
		t.Fatal("upgraded twice")
	}
}

func TestPunycode(t *testing.T) {
	for in, want := range map[string]string{"bücher.de": "xn--bcher-kva.de", "münchen.example": "xn--mnchen-3ya.example", "example.com": "example.com", "пример.рф": "xn--e1afmkfd.xn--p1ai"} {
		if got := asciiHost(in); got != want {
			t.Errorf("asciiHost(%q) = %q, want %q", in, got, want)
		}
	}
}

// "Add with a letter icon" works when the site can't be reached; other icons still need it.
func TestInstallOfflineWithLetterIcon(t *testing.T) {
	m := testManager(t)
	srv := httptest.NewServer(http.NotFoundHandler())
	addr := srv.URL
	srv.Close() // nothing listens there now
	_, err := m.Install(context.Background(), api.InstallParams{URL: addr})
	if code(err) != webapp.CodeFetch {
		t.Fatalf("without a letter icon: %v", err)
	}
	res, err := m.Install(context.Background(), api.InstallParams{URL: addr + "/app", Icon: json.RawMessage(`"monogram"`)})
	if err != nil {
		t.Fatal(err)
	}
	a, err := m.Paths.Load(res.App.ID)
	if err != nil || a.Icon.Source != "monogram" || a.StartURL != addr+"/app" || a.Scope.Scheme != "http" {
		t.Fatalf("%+v %v", a, err)
	}
}
