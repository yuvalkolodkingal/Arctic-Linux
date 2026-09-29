package webapp

import "testing"

// Certificate exceptions are only for hosts on your own network.
func TestPrivateHostLiteral(t *testing.T) {
	for host, want := range map[string]bool{
		"192.168.1.5": true, "10.0.0.1:8443": true, "172.16.3.4": true, "127.0.0.1:8123": true, "[::1]:8080": true,
		"fd00::1": true, "169.254.10.1": true, "localhost": true, "ha.lan:8123": true, "nas.local": true,
		"router.home.arpa": true, "grafana.internal": true,
		"8.8.8.8": false, "example.com": false, "lan": false, ".lan": false, "evil.lan.example.com": false,
		"2001:4860:4860::8888": false, "local": false,
		// RFC 6598 shared space (carrier-grade NAT, Tailscale): 100.64.0.0 to 100.127.255.255.
		"100.64.0.1": true, "100.101.102.103:8123": true, "100.127.255.255": true, "::ffff:100.64.0.1": true,
		"100.63.255.255": false, "100.128.0.1": false,
	} {
		if got := PrivateHostLiteral(host); got != want {
			t.Errorf("PrivateHostLiteral(%q) = %v, want %v", host, got, want)
		}
	}
}

func TestValidDomain(t *testing.T) {
	for d, want := range map[string]bool{
		"accounts.google.com": true, "sso.example.org:8443": true, "192.168.1.5": true, "a-b.c": true,
		"UPPER.com": false, "a..b": false, "-a.com": false, "a.com/": false, "a com": false, "": false, "a.com:": false,
		"a.com:x": false,
	} {
		if got := ValidDomain(d); got != want {
			t.Errorf("ValidDomain(%q) = %v, want %v", d, got, want)
		}
	}
}
