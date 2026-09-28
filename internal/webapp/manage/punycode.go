package manage

import (
	"strings"
	"unicode/utf8"
)

// toPunycodeHost encodes each non-ASCII label as "xn--" + Punycode (RFC 3492), so the preview
// can show a look-alike host for what it is. The standard library has no IDNA encoder.
func toPunycodeHost(host string) string {
	labels := strings.Split(strings.ToLower(host), ".")
	for i, l := range labels {
		ascii := true
		for _, r := range l {
			if r > 127 {
				ascii = false
				break
			}
		}
		if !ascii {
			labels[i] = "xn--" + punycode(l)
		}
	}
	return strings.Join(labels, ".")
}

func punycode(s string) string {
	const (
		base, tmin, tmax, skew, damp = 36, 1, 26, 38, 700
		initialBias, initialN        = 72, 128
	)
	adapt := func(delta, numPoints int, first bool) int {
		if first {
			delta /= damp
		} else {
			delta /= 2
		}
		delta += delta / numPoints
		k := 0
		for delta > ((base-tmin)*tmax)/2 {
			delta /= base - tmin
			k += base
		}
		return k + (base-tmin+1)*delta/(delta+skew)
	}
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
	n, delta, bias := initialN, 0, initialBias
	for h < utf8.RuneCountInString(s) {
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
				for k := base; ; k += base {
					t := k - bias
					if t < tmin {
						t = tmin
					} else if t > tmax {
						t = tmax
					}
					if q < t {
						break
					}
					out = append(out, digit(t+(q-t)%(base-t)))
					q = (q - t) / (base - t)
				}
				out = append(out, digit(q))
				bias = adapt(delta, h+1, h == b)
				delta = 0
				h++
			}
		}
		delta++
		n++
	}
	return string(out)
}
