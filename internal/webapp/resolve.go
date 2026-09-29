package webapp

import (
	"context"
	"net"
	"os/exec"
	"strings"
	"time"
)

// LookupHost resolves a host name to its addresses. Arctic's Go tools are built without cgo,
// so Go's own resolver answers, and it can't do multicast DNS: a .local name (a Home Assistant
// or a printer that Avahi announces) is asked of glibc instead, through getent and nss-mdns,
// which also gives the addresses WebKit will connect to. When that finds nothing, Go's
// resolver answers, and its error is the one a caller sees.
func LookupHost(ctx context.Context, host string) ([]string, error) {
	if MDNSName(host) {
		if addrs := lookupNSS(ctx, host); len(addrs) > 0 {
			return addrs, nil
		}
	}
	return net.DefaultResolver.LookupHost(ctx, host)
}

// MDNSName reports a name under .local, the domain RFC 6762 gives to multicast DNS.
func MDNSName(host string) bool {
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	return strings.HasSuffix(host, ".local") && len(host) > len(".local")
}

// Getent is glibc's getent; tests put a stand-in in its place.
var Getent = "getent"

// lookupNSS runs `getent ahosts NAME` (getaddrinfo, as WebKit resolves) for at most 3 s. Only a
// plain DNS name gets that far, never anything getent could read as an option.
func lookupNSS(ctx context.Context, host string) []string {
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	if !ValidDomain(host) || strings.Contains(host, ":") {
		return nil
	}
	path, err := exec.LookPath(Getent)
	if err != nil {
		return nil
	}
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, path, "ahosts", host).Output()
	if err != nil {
		return nil
	}
	return parseAhosts(out)
}

// parseAhosts collects the addresses in getent ahosts output ("192.168.1.20  STREAM ha.local"
// and a line per socket type), each once, in order.
func parseAhosts(out []byte) []string {
	var addrs []string
	seen := map[string]bool{}
	for _, line := range strings.Split(string(out), "\n") {
		f := strings.Fields(line)
		if len(f) == 0 || seen[f[0]] || net.ParseIP(f[0]) == nil {
			continue
		}
		seen[f[0]] = true
		addrs = append(addrs, f[0])
	}
	return addrs
}
