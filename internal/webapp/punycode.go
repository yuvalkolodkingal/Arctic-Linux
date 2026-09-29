package webapp

import (
	"net"
	"strings"
	"unicode"
	"unicode/utf8"
)

// ASCIIHost is a host (or host:port) the way WebKit and DNS see it: a label with letters beyond
// ASCII becomes "xn--" + Punycode (RFC 3492), after the lowercasing and width folding of IDNA's
// mapping (full-width letters and the ideographic full stops). An ASCII host comes back as it
// is. The standard library has no IDNA encoder; this one leaves out IDNA's NFC step (typed text
// is already composed) and its validity checks (WebKit refuses an invalid name anyway). Hosts
// are stored in this form, so an app's scope matches the pages WebKit reports.
func ASCIIHost(hostport string) string {
	if isASCII(hostport) {
		return hostport
	}
	host, port, err := net.SplitHostPort(hostport)
	if err != nil {
		host, port = hostport, ""
	}
	host = strings.ToLower(strings.Map(func(r rune) rune {
		switch {
		case r == 0x3002 || r == 0xFF61: // 。 ｡
			return '.'
		case r >= 0xFF01 && r <= 0xFF5E: // full-width ASCII, ． included
			return r - 0xFEE0
		}
		return r
	}, host))
	labels := strings.Split(host, ".")
	for i, l := range labels {
		if !isASCII(l) {
			labels[i] = "xn--" + punycode(l)
		}
	}
	host = strings.Join(labels, ".")
	if port != "" {
		return net.JoinHostPort(host, port)
	}
	return host
}

// UnicodeHost decodes the "xn--" labels of a host (or host:port) for display, such as a name
// made from the site label. A label stays as it is unless it decodes to printable text beyond
// ASCII that encodes back to the same label (so "xn--a-" never shows as "a").
func UnicodeHost(hostport string) string {
	if !strings.Contains(strings.ToLower(hostport), "xn--") {
		return hostport
	}
	host, port, err := net.SplitHostPort(hostport)
	if err != nil {
		host, port = hostport, ""
	}
	labels := strings.Split(host, ".")
	for i, l := range labels {
		if len(l) > 4 && strings.EqualFold(l[:4], "xn--") {
			code := strings.ToLower(l[4:])
			if u, ok := unpunycode(code); ok && !isASCII(u) && punycode(u) == code && printable(u) {
				labels[i] = u
			}
		}
	}
	host = strings.Join(labels, ".")
	if port != "" {
		return net.JoinHostPort(host, port)
	}
	return host
}

func printable(s string) bool {
	for _, r := range s {
		if !unicode.IsGraphic(r) || unicode.IsSpace(r) {
			return false
		}
	}
	return true
}

func isASCII(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] >= utf8.RuneSelf {
			return false
		}
	}
	return true
}

// Punycode's parameters (RFC 3492 section 5).
const (
	pcBase, pcTmin, pcTmax, pcSkew, pcDamp = 36, 1, 26, 38, 700
	pcInitialBias, pcInitialN              = 72, 128
)

func pcAdapt(delta, numPoints int, first bool) int {
	if first {
		delta /= pcDamp
	} else {
		delta /= 2
	}
	delta += delta / numPoints
	k := 0
	for delta > ((pcBase-pcTmin)*pcTmax)/2 {
		delta /= pcBase - pcTmin
		k += pcBase
	}
	return k + (pcBase-pcTmin+1)*delta/(delta+pcSkew)
}

func pcThreshold(k, bias int) int {
	t := k - bias
	if t < pcTmin {
		return pcTmin
	}
	if t > pcTmax {
		return pcTmax
	}
	return t
}

// punycode encodes one label (RFC 3492 section 6.3).
func punycode(s string) string {
	digit := func(d int) byte {
		if d < 26 {
			return byte('a' + d)
		}
		return byte('0' + d - 26)
	}
	runes := []rune(s)
	var out []byte
	for _, r := range runes {
		if r < 128 {
			out = append(out, byte(r))
		}
	}
	b := len(out)
	h := b
	if b > 0 {
		out = append(out, '-')
	}
	n, delta, bias := pcInitialN, 0, pcInitialBias
	for h < len(runes) {
		m := rune(0x10FFFF)
		for _, r := range runes {
			if int(r) >= n && r < m {
				m = r
			}
		}
		delta += (int(m) - n) * (h + 1)
		n = int(m)
		for _, r := range runes {
			if int(r) < n {
				delta++
			}
			if int(r) == n {
				q := delta
				for k := pcBase; ; k += pcBase {
					t := pcThreshold(k, bias)
					if q < t {
						break
					}
					out = append(out, digit(t+(q-t)%(pcBase-t)))
					q = (q - t) / (pcBase - t)
				}
				out = append(out, digit(q))
				bias = pcAdapt(delta, h+1, h == b)
				delta = 0
				h++
			}
		}
		delta++
		n++
	}
	return string(out)
}

// unpunycode decodes one label (RFC 3492 section 6.2); false for invalid input.
func unpunycode(s string) (string, bool) {
	var out []rune
	if i := strings.LastIndexByte(s, '-'); i >= 0 {
		for _, c := range s[:i] {
			if c >= 128 {
				return "", false
			}
			out = append(out, c)
		}
		s = s[i+1:]
	}
	const maxInt = 1 << 30 // far above anything a 63-byte label can mean
	n, i, bias := pcInitialN, 0, pcInitialBias
	for pos := 0; pos < len(s); {
		oldi, w := i, 1
		for k := pcBase; ; k += pcBase {
			if pos >= len(s) {
				return "", false
			}
			c := s[pos]
			pos++
			var d int
			switch {
			case c >= 'a' && c <= 'z':
				d = int(c - 'a')
			case c >= 'A' && c <= 'Z':
				d = int(c - 'A')
			case c >= '0' && c <= '9':
				d = int(c-'0') + 26
			default:
				return "", false
			}
			if d > (maxInt-i)/w {
				return "", false
			}
			i += d * w
			t := pcThreshold(k, bias)
			if d < t {
				break
			}
			if w > maxInt/(pcBase-t) {
				return "", false
			}
			w *= pcBase - t
		}
		bias = pcAdapt(i-oldi, len(out)+1, oldi == 0)
		n += i / (len(out) + 1)
		i %= len(out) + 1
		if n > utf8.MaxRune || (n >= 0xD800 && n <= 0xDFFF) {
			return "", false
		}
		out = append(out, 0)
		copy(out[i+1:], out[i:])
		out[i] = rune(n)
		i++
	}
	return string(out), true
}
