package webapp

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeGetent puts a stand-in getent in place: it logs its arguments and knows ha.local.
func fakeGetent(t *testing.T) string {
	dir := t.TempDir()
	log := filepath.Join(dir, "argv")
	script := "#!/bin/sh\necho \"$*\" >> " + log + "\n" +
		"[ \"$1 $2\" = \"ahosts ha.local\" ] || exit 2\n" +
		"printf '192.168.1.20    STREAM ha.local\\n192.168.1.20    DGRAM  \\n192.168.1.20    RAW    \\nfd00::20        STREAM \\n'\n"
	path := filepath.Join(dir, "getent")
	if err := os.WriteFile(path, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	old := Getent
	Getent = path
	t.Cleanup(func() { Getent = old })
	return log
}

// A .local name is resolved by glibc (nss-mdns), which Go's resolver without cgo can't reach.
func TestLookupHostMDNS(t *testing.T) {
	log := fakeGetent(t)
	ctx := context.Background()
	addrs, err := LookupHost(ctx, "HA.local.")
	if err != nil || strings.Join(addrs, " ") != "192.168.1.20 fd00::20" {
		t.Fatalf("ha.local: %v %v", addrs, err)
	}
	// Other names go to Go's resolver (localhost from /etc/hosts), never to getent.
	if addrs, err := LookupHost(ctx, "localhost"); err != nil || len(addrs) == 0 {
		t.Fatalf("localhost: %v %v", addrs, err)
	}
	// A name getent could read as an option never reaches it.
	if addrs := lookupNSS(ctx, "-s.local"); addrs != nil {
		t.Fatalf("-s.local: %v", addrs)
	}
	data, _ := os.ReadFile(log)
	if strings.TrimSpace(string(data)) != "ahosts ha.local" {
		t.Fatalf("getent ran with %q", data)
	}
	for host, want := range map[string]bool{"ha.local": true, "HA.LOCAL.": true, "local": false, ".local": false, "ha.local.example.com": false, "ha.lan": false} {
		if MDNSName(host) != want {
			t.Errorf("MDNSName(%q) != %v", host, want)
		}
	}
}
