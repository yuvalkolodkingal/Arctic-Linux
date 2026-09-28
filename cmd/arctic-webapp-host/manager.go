//go:build cgo && webkit

package main

import (
	"context"
	"crypto/sha256"
	"encoding/pem"
	"fmt"
	"net"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webkit"
)

// The host never writes app.json or icons itself: for a trusted certificate or a favicon it
// runs the manager with an argv (no shell), which validates, stores and tells the running app.

// managerPath is arctic-webapp: next to a development host first, then on PATH.
func managerPath() string {
	if self, err := os.Executable(); err == nil {
		sib := filepath.Join(filepath.Dir(self), "arctic-webapp")
		if _, err := os.Stat(sib); err == nil && filepath.Dir(self) != "/usr/libexec/arctic" {
			return sib
		}
	}
	if p, err := exec.LookPath("arctic-webapp"); err == nil {
		return p
	}
	return "/usr/bin/arctic-webapp"
}

func (c *controller) runManager(timeout time.Duration, args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	out, err := exec.CommandContext(ctx, managerPath(), args...).CombinedOutput()
	if err != nil {
		c.log.Printf("arctic-webapp %s: %v: %s", args[0], err, strings.TrimSpace(string(out)))
	}
	return err
}

// CertificateQuestion offers to trust a certificate only for private-network hosts (the
// manager checks again, including every resolved address).
func (c *controller) CertificateQuestion(uri, certPEM string) string {
	u, err := url.Parse(uri)
	if err != nil || u.Host == "" || !webapp.PrivateHostLiteral(u.Host) {
		return ""
	}
	block, _ := pem.Decode([]byte(certPEM))
	if block == nil || block.Type != "CERTIFICATE" {
		return ""
	}
	sum := sha256.Sum256(block.Bytes)
	var fp []string
	for _, b := range sum[:8] {
		fp = append(fp, fmt.Sprintf("%02X", b))
	}
	c.pendingCert = &pendingCert{host: strings.ToLower(u.Host), pem: certPEM}
	return fmt.Sprintf("%s isn’t using a certificate your computer trusts (SHA-256 %s…). If this is your own device, you can trust this certificate for %s.",
		u.Host, strings.Join(fp, ":"), u.Host)
}

type pendingCert struct{ host, pem string }

// TrustCertificate stores the certificate through the manager and allows it now.
func (c *controller) TrustCertificate() bool {
	pc := c.pendingCert
	c.pendingCert = nil
	if pc == nil {
		return false
	}
	if err := c.paths.EnsureRuntimeDir(); err != nil {
		return false
	}
	file := filepath.Join(c.paths.RuntimeDir, c.app.ID+"-cert.pem")
	if err := webapp.WriteFileAtomic(file, []byte(pc.pem), 0o600); err != nil {
		return false
	}
	defer os.Remove(file)
	if c.runManager(10*time.Second, "trust-certificate", c.app.ID, "--host", pc.host, "--pem", file) != nil {
		webkit.Banner("Arctic couldn’t trust this certificate. Only sites on your own network can be trusted.", "")
		return false
	}
	host := pc.host
	if h, _, err := net.SplitHostPort(host); err == nil {
		host = h
	}
	webkit.AllowCertificate(host, pc.pem)
	c.log.Printf("trusted a certificate for %s", pc.host)
	return true
}

// WantFavicon: only while the app wears a letter icon (or a bare favicon.ico) you didn't pick,
// and only an icon of at least 64 px.
func (c *controller) WantFavicon(width, height int) bool {
	if c.faviconSent || c.app.IsUserSet("icon") {
		return false
	}
	if c.app.Icon.Source != "monogram" && c.app.Icon.Source != "favicon-ico" {
		return false
	}
	return width >= 64 || height >= 64
}

// Favicon hands WebKit's decoded favicon to the manager, which decodes it again with its own
// bounded decoders, renders the icon sizes and bumps the icon revision.
func (c *controller) Favicon(png []byte) bool {
	if c.faviconSent {
		return false
	}
	if err := c.paths.EnsureRuntimeDir(); err != nil {
		return false
	}
	file := filepath.Join(c.paths.RuntimeDir, c.app.ID+"-favicon.png")
	if err := webapp.WriteFileAtomic(file, png, 0o600); err != nil {
		return false
	}
	c.faviconSent = true
	go func() {
		defer os.Remove(file)
		c.runManager(20*time.Second, "icon", c.app.ID, "--from-file", file, "--source", "host-favicon")
	}()
	return true
}
