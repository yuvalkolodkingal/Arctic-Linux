package installer

import (
	"os/exec"
	"strings"
	"testing"
)

func TestSHA512CryptVectors(t *testing.T) {
	// Test vectors from Drepper's "Unix crypt using SHA-256 and SHA-512" specification.
	cases := []struct{ setting, key, want string }{
		{"$6$saltstring", "Hello world!",
			"$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1"},
		{"$6$rounds=10000$saltstringsaltstring", "Hello world!",
			"$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v."},
		{"$6$rounds=5000$toolongsaltstring", "This is just a test",
			"$6$rounds=5000$toolongsaltstrin$lQ8jolhgVRVhY4b5pZKaysCLi0QBxGoNeKQzQ3glMhwllF7oGDZxUhx1yxdYcz/e1JSbq3y6JMxxl8audkUEm0"},
		{"$6$rounds=1400$anotherlongsaltstring", "a very much longer text to encrypt.  This one even stretches over morethan one line.",
			"$6$rounds=1400$anotherlongsalts$POfYwTEok97VWcjxIiSOjiykti.o/pQs.wPvMxQ6Fm7I6IoYN3CmLs66x9t0oSwbtEW7o7UmJEiDwGqd8p4ur1"},
		{"$6$rounds=77777$short", "we have a short salt string but not a short password",
			"$6$rounds=77777$short$WuQyW2YR.hBNpjjRhpYD/ifIw05xdfeEyQoMxIXbkvr0gge1a1x3yRULJ5CCaUeOxFmtlcGZelFl5CxtgfiAc0"},
		{"$6$rounds=10$roundstoolow", "the minimum number is still observed",
			"$6$rounds=1000$roundstoolow$kUMsbe306n21p9R.FRkW3IGn.S9NPN0x50YhH1xhLsPuWGsUSklZt58jaTfF4ZEQpyUNGc0dqbpBYYBaHHrsX."},
	}
	for _, c := range cases {
		got, err := SHA512Crypt([]byte(c.key), c.setting)
		if err != nil {
			t.Fatal(err)
		}
		if got != c.want {
			t.Errorf("%s:\n got %s\nwant %s", c.setting, got, c.want)
		}
	}
}

func TestHashPasswordRoundTrip(t *testing.T) {
	h, err := HashPassword([]byte("winter fox 2026"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(h, "$6$") || len(strings.Split(h, "$")) != 4 {
		t.Fatalf("hash %q", h)
	}
	again, _ := SHA512Crypt([]byte("winter fox 2026"), h)
	if again != h {
		t.Fatalf("re-hash with the same salt differs: %s vs %s", again, h)
	}
	// Cross-check with openssl when it is installed.
	if _, err := exec.LookPath("openssl"); err == nil {
		salt := strings.Split(h, "$")[2]
		cmd := exec.Command("openssl", "passwd", "-6", "-salt", salt, "-stdin")
		cmd.Stdin = strings.NewReader("winter fox 2026\n")
		out, err := cmd.Output()
		if err != nil {
			t.Fatalf("openssl: %v", err)
		}
		if strings.TrimSpace(string(out)) != h {
			t.Errorf("openssl says %s, we say %s", strings.TrimSpace(string(out)), h)
		}
	}
}
