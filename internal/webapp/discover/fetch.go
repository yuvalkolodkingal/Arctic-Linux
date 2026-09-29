package discover

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

// Size limits (docs/BUILD-SPEC.md §11).
const (
	MaxHTML     = 1 << 20
	MaxManifest = 256 << 10
	MaxImage    = 2 << 20
	MaxICO      = 1 << 20
	MaxSVG      = 1 << 20
	MaxTotal    = 8 << 20
	MaxRedirect = 5
)

// Fetcher does the GETs of one inspect: no cookie jar, TLS 1.2+, strict timeouts, at most 5
// redirects (never https → http), an overall byte budget, and the private-address guard.
type Fetcher struct {
	client         *http.Client
	UserAgent      string
	AcceptLanguage string

	mu           sync.Mutex
	pagePhase    bool            // the page itself is being fetched
	allowPrivate bool            // sub-resources may reach private addresses (the page is private)
	proxied      map[string]bool // remote addresses of connections to a proxy
	budget       int64
	// private classifies a dialled address; tests make one loopback server count as public.
	private func(address string, ip net.IP) bool
}

// NewFetcher builds a fetcher. rootCAs is nil for the system pool (tests pass their own).
func NewFetcher(rootCAs *x509.CertPool) *Fetcher {
	f := &Fetcher{UserAgent: webapp.FetchUserAgent, AcceptLanguage: acceptLanguage(), budget: MaxTotal, pagePhase: true,
		proxied: map[string]bool{}, private: func(_ string, ip net.IP) bool { return webapp.PrivateIP(ip) }}
	guarded := &net.Dialer{Timeout: 5 * time.Second, Control: f.control}
	plain := &net.Dialer{Timeout: 5 * time.Second}
	proxies := proxyAddrs()
	tr := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			if proxies[addr] {
				// A proxy's own address says nothing about the destination; the proxy decides.
				c, err := plain.DialContext(ctx, network, addr)
				if err == nil {
					f.mu.Lock()
					f.proxied[c.RemoteAddr().String()] = true
					f.mu.Unlock()
				}
				return c, err
			}
			if host, port, err := net.SplitHostPort(addr); err == nil && webapp.MDNSName(host) {
				return dialMDNS(ctx, guarded, network, host, port)
			}
			return guarded.DialContext(ctx, network, addr)
		},
		TLSHandshakeTimeout:    5 * time.Second,
		ResponseHeaderTimeout:  10 * time.Second,
		MaxResponseHeaderBytes: 64 << 10,
		TLSClientConfig:        &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: rootCAs},
		ForceAttemptHTTP2:      true,
		MaxIdleConnsPerHost:    3,
		IdleConnTimeout:        30 * time.Second,
	}
	f.client = &http.Client{Transport: tr, CheckRedirect: checkRedirect}
	return f
}

// dialMDNS dials a .local name at the addresses glibc finds for it (Go's resolver can't do
// mDNS), one after another; the guard still checks each address as it connects.
func dialMDNS(ctx context.Context, d *net.Dialer, network, host, port string) (net.Conn, error) {
	addrs, err := webapp.LookupHost(ctx, host)
	if err != nil {
		return nil, err
	}
	if len(addrs) == 0 {
		return nil, &net.DNSError{Err: "no such host", Name: host, IsNotFound: true}
	}
	var first error
	for _, a := range addrs {
		c, err := d.DialContext(ctx, network, net.JoinHostPort(a, port))
		if err == nil {
			return c, nil
		}
		if first == nil {
			first = err
		}
	}
	return nil, first
}

func proxyAddrs() map[string]bool {
	m := map[string]bool{}
	for _, k := range []string{"HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"} {
		v := os.Getenv(k)
		if v == "" {
			continue
		}
		if !strings.Contains(v, "://") {
			v = "http://" + v
		}
		if u, err := url.Parse(v); err == nil && u.Host != "" {
			host, port := u.Hostname(), u.Port()
			if port == "" {
				port = map[string]string{"https": "443", "socks5": "1080"}[u.Scheme]
				if port == "" {
					port = "80"
				}
			}
			m[net.JoinHostPort(host, port)] = true
		}
	}
	return m
}

func acceptLanguage() string {
	for _, k := range []string{"LANGUAGE", "LC_ALL", "LANG"} {
		v := os.Getenv(k)
		if v == "" || v == "C" || strings.HasPrefix(v, "C.") || v == "POSIX" {
			continue
		}
		v = strings.Split(v, ":")[0]
		v, _, _ = strings.Cut(v, ".")
		v = strings.ReplaceAll(v, "_", "-")
		if v != "" && !strings.HasPrefix(v, "en") {
			return v + ", en;q=0.5"
		}
		return v
	}
	return "en"
}

// control runs at connect time with the resolved address, so DNS rebinding can't get around
// it: once the page has come from a public address, its manifest and icons may not come from
// loopback, private, link-local or unspecified addresses. The page itself may come from
// anywhere; where it came from is read from the connection it used (connPrivate), not from
// the dials, since a Happy Eyeballs fallback dial may lose the race.
func (f *Fetcher) control(network, address string, _ syscall.RawConn) error {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return err
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return fmt.Errorf("unresolved address %s", address)
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.pagePhase || f.allowPrivate || !f.private(address, ip) {
		return nil
	}
	return errPrivate
}

var errPrivate = errors.New("a public page may not load from a private address")

// connPrivate classifies the address a connection went to. A proxy's says nothing about the
// destination (the proxy chose it), so it counts as public.
func (f *Fetcher) connPrivate(c net.Conn) bool {
	ta, ok := c.RemoteAddr().(*net.TCPAddr)
	if !ok {
		return false
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	return !f.proxied[ta.String()] && f.private(ta.String(), ta.IP)
}

// PageDone ends the page phase without a page (an icon address you gave): public addresses
// only.
func (f *Fetcher) PageDone() { f.pageFrom(&Response{}) }

// pageFrom ends the page phase with the page discovery kept: sub-resources may use private
// addresses only if it came from one.
func (f *Fetcher) pageFrom(page *Response) {
	f.mu.Lock()
	f.pagePhase = false
	f.allowPrivate = page.private
	f.mu.Unlock()
	if !page.private {
		// Connections kept from the page's hops (a redirect or refresh to your network) never
		// met the guard; sub-resources dial afresh, through control.
		f.client.CloseIdleConnections()
	}
}

func checkRedirect(req *http.Request, via []*http.Request) error {
	if len(via) > MaxRedirect {
		return webapp.Errorf(webapp.CodeFetch, "The site redirected too many times.")
	}
	u := req.URL
	if (u.Scheme != "https" && u.Scheme != "http") || u.User != nil {
		return webapp.Errorf(webapp.CodeFetch, "The site redirected to an address Arctic won’t follow.")
	}
	if via[len(via)-1].URL.Scheme == "https" && u.Scheme == "http" {
		return webapp.Errorf(webapp.CodeFetch, "The site redirected from a secure to an insecure address.")
	}
	return nil
}

// Response is a fetched body.
type Response struct {
	URL         *url.URL // after redirects
	ContentType string
	Body        []byte
	Truncated   bool
	private     bool // (page phase) the last hop came over a connection to a private address
}

// Get fetches u with an Accept header, reading at most limit bytes. With truncate the body is
// cut at the limit; otherwise going over it is a too_large error.
func (f *Fetcher) Get(ctx context.Context, u *url.URL, accept string, limit int64, truncate bool) (*Response, error) {
	f.mu.Lock()
	page := f.pagePhase
	f.mu.Unlock()
	var private atomic.Bool
	if page {
		// GotConn fires for every hop with the connection it really used; the last is the page's.
		ctx = httptrace.WithClientTrace(ctx, &httptrace.ClientTrace{GotConn: func(ci httptrace.GotConnInfo) {
			private.Store(f.connPrivate(ci.Conn))
		}})
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, webapp.Errorf(webapp.CodeInvalid, "That isn’t a web address.")
	}
	req.Header.Set("User-Agent", f.UserAgent)
	req.Header.Set("Accept", accept)
	req.Header.Set("Accept-Language", f.AcceptLanguage)
	resp, err := f.client.Do(req)
	if err != nil {
		return nil, classify(err, u.Host)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, webapp.Errorf(webapp.CodeHTTP, "%s answered with error %d.", u.Host, resp.StatusCode)
	}
	f.mu.Lock()
	budget := f.budget
	f.mu.Unlock()
	if budget <= 0 {
		return nil, webapp.Errorf(webapp.CodeTooLarge, "The site sent too much data.")
	}
	read := limit
	if read > budget {
		read = budget
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, read+1))
	if err != nil {
		return nil, classify(err, u.Host)
	}
	final := *resp.Request.URL
	final.Host = webapp.ASCIIHost(final.Host) // a redirect to a Unicode name, as WebKit would see it
	r := &Response{URL: &final, ContentType: resp.Header.Get("Content-Type"), private: private.Load()}
	if int64(len(body)) > read {
		if !truncate {
			return nil, webapp.Errorf(webapp.CodeTooLarge, "%s sent a file that is too large.", u.Host)
		}
		body = body[:read]
		r.Truncated = true
	}
	f.mu.Lock()
	f.budget -= int64(len(body))
	f.mu.Unlock()
	r.Body = body
	return r, nil
}

// classify turns a transport error into an engine error with a sentence.
func classify(err error, host string) error {
	switch {
	case errors.Is(err, context.Canceled):
		return webapp.Errorf(webapp.CodeTimeout, "Stopped.")
	case errors.Is(err, context.DeadlineExceeded):
		return webapp.Errorf(webapp.CodeTimeout, "%s took too long to answer.", host)
	case errors.Is(err, errPrivate):
		return webapp.Errorf(webapp.CodeFetch, "%s pointed at an address on your own network, which Arctic won’t load for a public site.", host)
	}
	var pe *protocol.Error
	if errors.As(err, &pe) {
		return pe // from checkRedirect
	}
	var dnsErr *net.DNSError
	if errors.As(err, &dnsErr) {
		if dnsErr.IsNotFound {
			return webapp.Errorf(webapp.CodeFetch, "There’s no site at %s. Check the address.", host)
		}
		return webapp.Errorf(webapp.CodeOffline, "You’re offline. You can still add the app with a letter icon.")
	}
	if errors.Is(err, syscall.ENETUNREACH) || errors.Is(err, syscall.EHOSTUNREACH) {
		return webapp.Errorf(webapp.CodeOffline, "You’re offline. You can still add the app with a letter icon.")
	}
	var certErr *tls.CertificateVerificationError
	var unknownAuth x509.UnknownAuthorityError
	var hostErr x509.HostnameError
	var invalid x509.CertificateInvalidError
	if errors.As(err, &certErr) || errors.As(err, &unknownAuth) || errors.As(err, &hostErr) || errors.As(err, &invalid) {
		return webapp.Errorf(webapp.CodeTLS, "The connection to %s isn’t private: its certificate isn’t trusted.", host)
	}
	var netErr net.Error
	if errors.As(err, &netErr) && netErr.Timeout() {
		return webapp.Errorf(webapp.CodeTimeout, "%s took too long to answer.", host)
	}
	return webapp.Errorf(webapp.CodeFetch, "Couldn’t reach %s.", host)
}
