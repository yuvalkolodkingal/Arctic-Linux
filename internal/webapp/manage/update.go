package manage

import (
	"context"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"net"
	"os"
	"strings"
	"syscall"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/discover"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/icon"
)

// Update re-discovers apps' names, manifests and icons. Fields you set yourself (user_set) are
// never overwritten; they are reported as kept.
func (m *Manager) Update(ctx context.Context, ids []string, all bool) (api.UpdateResult, error) {
	res := api.UpdateResult{Updated: []api.Updated{}}
	if all {
		apps, _, err := m.Paths.List()
		if err != nil {
			return res, err
		}
		ids = nil
		for _, a := range apps {
			ids = append(ids, a.ID)
		}
	}
	if len(ids) == 0 && !all {
		return res, webapp.Errorf(webapp.CodeBadRequest, "Say which web app to update.")
	}
	for _, id := range ids {
		a, err := m.Paths.Load(id)
		if err != nil {
			return res, err
		}
		found, err := discover.Discover(ctx, a.StartURL, discover.Options{PSL: m.psl(), Fetcher: NewFetcher(), Progress: m.Progress})
		if err != nil {
			return res, err
		}
		up := api.Updated{ID: id, Changed: []string{}, Kept: []string{}}
		err = m.exclusive(func() error {
			cur, err := m.Paths.Load(id)
			if err != nil {
				return err
			}
			change := func(field string, apply func() bool) {
				if cur.IsUserSet(field) {
					up.Kept = append(up.Kept, field)
					return
				}
				if apply() {
					up.Changed = append(up.Changed, field)
				}
			}
			change("name", func() bool {
				if found.Name != "" && found.Name != cur.Name && found.NameSource != "host" {
					cur.Name, cur.NameSource = found.Name, found.NameSource
					return true
				}
				return false
			})
			change("category", func() bool {
				if found.Category != "Network" && found.Category != cur.Category {
					cur.Category = found.Category
					return true
				}
				return false
			})
			change("icon", func() bool {
				if len(found.Icons) == 0 || found.Icons[0].SHA256 == cur.Icon.SHA256 {
					return false
				}
				best := found.Icons[0]
				if best.Size < icon.MinSource && cur.Icon.Source != "monogram" {
					return false // never trade an icon for a smaller favicon
				}
				if err := icon.SaveSource(m.Paths, id, best.Image, best.Purpose); err != nil {
					return false
				}
				cur.Icon = webapp.Icon{Rev: cur.Icon.Rev + 1, Source: best.Source, URL: best.URL, SHA256: best.SHA256, Purpose: best.Purpose}
				return true
			})
			if found.ManifestURL != "" && found.ManifestURL != cur.ManifestURL {
				cur.ManifestURL = found.ManifestURL
				up.Changed = append(up.Changed, "manifest")
			}
			if found.ThemeColor != cur.ThemeColor {
				cur.ThemeColor = found.ThemeColor
			}
			if len(up.Changed) == 0 && cur.Render >= webapp.RenderVersion {
				return nil
			}
			cur.Render = webapp.RenderVersion
			cur.Updated = m.Now()
			cur.Icon.Name = cur.IconName()
			if err := m.Paths.Save(cur); err != nil {
				return err
			}
			return m.render(cur)
		})
		if err != nil {
			return res, err
		}
		res.Updated = append(res.Updated, up)
	}
	return res, nil
}

// IconFromFile is the host's favicon upgrade: an app still wearing a letter icon (or a tiny
// favicon) gets the icon the page showed, decoded with the same bounded decoders, when it is at
// least 64 px and you haven't picked an icon yourself. It reports whether the icon changed.
func (m *Manager) IconFromFile(id, path, source string) (bool, error) {
	if source != "host-favicon" {
		return false, webapp.Errorf(webapp.CodeBadRequest, "Only host-favicon icons come from a file here.")
	}
	img, msg := decodeFile(path)
	if msg != "" {
		return false, webapp.Errorf(webapp.CodeInvalid, "%s", msg)
	}
	b := img.Bounds()
	if b.Dx() < icon.MinSource && b.Dy() < icon.MinSource {
		return false, nil
	}
	data, _ := os.ReadFile(path)
	sum := sha256.Sum256(data)
	changed := false
	err := m.exclusive(func() error {
		a, err := m.Paths.Load(id)
		if err != nil {
			return err
		}
		if a.IsUserSet("icon") || (a.Icon.Source != "monogram" && a.Icon.Source != "favicon-ico") {
			return nil
		}
		if err := icon.SaveSource(m.Paths, id, img, "any"); err != nil {
			return err
		}
		a.Icon = webapp.Icon{Rev: a.Icon.Rev + 1, Source: "host-favicon", SHA256: hex.EncodeToString(sum[:]), Purpose: "any"}
		a.Icon.Name = a.IconName()
		a.Updated = m.Now()
		if err := m.Paths.Save(a); err != nil {
			return err
		}
		changed = true
		return m.render(a)
	})
	return changed, err
}

// LookupHost resolves names for the private-host check; tests replace it.
var LookupHost = func(host string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return net.DefaultResolver.LookupHost(ctx, host)
}

// privateHost: an IP literal in a private range, localhost, or a .local/.lan/.home.arpa/
// .internal name whose every address is private.
func privateHost(hostport string) bool {
	if !webapp.PrivateHostLiteral(hostport) {
		return false
	}
	host := hostport
	if h, _, err := net.SplitHostPort(hostport); err == nil {
		host = h
	}
	if net.ParseIP(host) != nil || host == "localhost" {
		return true
	}
	addrs, err := LookupHost(host)
	if err != nil || len(addrs) == 0 {
		return false
	}
	for _, a := range addrs {
		ip := net.ParseIP(a)
		if ip == nil || !webapp.PrivateIP(ip) {
			return false
		}
	}
	return true
}

// TrustCertificate stores a certificate you confirmed for a private-network host (a Home
// Assistant or NAS with a self-signed certificate), then tells the running app (SIGHUP). Public
// hosts never get an exception.
func (m *Manager) TrustCertificate(id, host, pemPath string) error {
	host = strings.ToLower(strings.TrimSpace(host))
	if !privateHost(host) {
		return webapp.Errorf(webapp.CodeInvalid, "Only sites on your own network can have a trusted certificate.")
	}
	data, err := os.ReadFile(pemPath)
	if err != nil || len(data) > 64<<10 {
		return webapp.Errorf(webapp.CodeInvalid, "The certificate file can’t be read.")
	}
	block, _ := pem.Decode(data)
	if block == nil || block.Type != "CERTIFICATE" {
		return webapp.Errorf(webapp.CodeInvalid, "That isn’t a certificate.")
	}
	if _, err := x509.ParseCertificate(block.Bytes); err != nil {
		return webapp.Errorf(webapp.CodeInvalid, "That isn’t a certificate.")
	}
	sum := sha256.Sum256(block.Bytes)
	fp := hex.EncodeToString(sum[:])
	err = m.exclusive(func() error {
		a, err := m.Paths.Load(id)
		if err != nil {
			return err
		}
		var keep []webapp.TLSException
		for _, e := range a.TLSExceptions {
			if e.Host != host {
				keep = append(keep, e)
			}
		}
		a.TLSExceptions = append(keep, webapp.TLSException{Host: host, SHA256: fp, PEM: string(pem.EncodeToMemory(block))})
		a.Updated = m.Now()
		return m.Paths.Save(a)
	})
	if err == nil {
		m.Paths.Signal(id, syscall.SIGHUP)
	}
	return err
}
