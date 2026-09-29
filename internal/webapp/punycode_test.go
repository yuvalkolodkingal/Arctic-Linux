package webapp

import "testing"

// Hosts are stored as WebKit reports them: internationalised labels in Punycode.
func TestASCIIHost(t *testing.T) {
	for in, want := range map[string]string{
		"bücher.de":             "xn--bcher-kva.de",
		"münchen.example":       "xn--mnchen-3ya.example",
		"MÜNCHEN.de":            "xn--mnchen-3ya.de",
		"münchen.de:8443":       "xn--mnchen-3ya.de:8443",
		"пример.рф":             "xn--e1afmkfd.xn--p1ai",
		"例え。テスト":                "xn--r8jz45g.xn--zckzah",
		"ｅｘａｍｐｌｅ．com":           "example.com",
		"example.com":           "example.com",
		"Example.COM":           "Example.COM", // ASCII is left to the caller
		"xn--mnchen-3ya.de":     "xn--mnchen-3ya.de",
		"[::1]:8080":            "[::1]:8080",
		"192.168.1.10":          "192.168.1.10",
		"mail.bücher.de.":       "mail.xn--bcher-kva.de.",
		"3年b組金八先生.jp":           "xn--3b-ww4c5e180e575a65lsy2b.jp",
		"他们为什么不说中文.example.com": "xn--ihqwcrb4cv8a8dqg056pqjye.example.com",
	} {
		if got := ASCIIHost(in); got != want {
			t.Errorf("ASCIIHost(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestUnicodeHost(t *testing.T) {
	for in, want := range map[string]string{
		"xn--mnchen-3ya.de":      "münchen.de",
		"XN--MNCHEN-3YA.de:8443": "münchen.de:8443",
		"xn--e1afmkfd.xn--p1ai":  "пример.рф",
		"example.com":            "example.com",
		"xn--.de":                "xn--.de",               // empty
		"xn--99999999999999.de":  "xn--99999999999999.de", // overflows
		"xn--a-.de":              "xn--a-.de",             // plain ASCII
		"xn--a.de":               "xn--a.de",              // a control character
	} {
		if got := UnicodeHost(in); got != want {
			t.Errorf("UnicodeHost(%q) = %q, want %q", in, got, want)
		}
	}
}

// RFC 3492's samples and a few edges both ways.
func TestPunycodeRoundTrip(t *testing.T) {
	for in, want := range map[string]string{
		"münchen":                  "mnchen-3ya",
		"ü":                        "tda",
		"üx":                       "x-dha",
		"a-ü":                      "a--yka",
		"3年B組金八先生":                 "3B-ww4c5e180e575a65lsy2b",
		"他们为什么不说中文":                "ihqwcrb4cv8a8dqg056pqjye",
		"安室奈美恵-with-SUPER-MONKEYS": "-with-SUPER-MONKEYS-pc58ag80a8qai00g7n9n",
	} {
		if got := punycode(in); got != want {
			t.Errorf("punycode(%q) = %q, want %q", in, got, want)
		}
		if got, ok := unpunycode(want); !ok || got != in {
			t.Errorf("unpunycode(%q) = %q %v, want %q", want, got, ok, in)
		}
	}
}
