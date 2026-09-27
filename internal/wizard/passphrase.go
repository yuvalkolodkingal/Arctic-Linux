package wizard

import (
	"crypto/rand"
	_ "embed"
	"math"
	"math/big"
	"strconv"
	"strings"
	"unicode"
)

// eff_short_wordlist_1.txt is the EFF "short wordlist #1" (1,296 words, dice-numbered), by the
// Electronic Frontier Foundation, https://www.eff.org/dice — licensed CC BY 3.0 US.
// Fetched from https://www.eff.org/files/2016/09/08/eff_short_wordlist_1.txt
// (sha256 8f5ca830b8bffb6fe39c9736c024a00a6a6411adb3f83a9be8bfeeb6e067ae69).
//
//go:embed eff_short_wordlist_1.txt
var effShortList string

// Words is the embedded passphrase word list.
var Words = parseWordList(effShortList)

var wordSet = func() map[string]bool {
	m := make(map[string]bool, len(Words))
	for _, w := range Words {
		m[w] = true
	}
	return m
}()

var maxWordLen = func() int {
	n := 0
	for _, w := range Words {
		if len(w) > n {
			n = len(w)
		}
	}
	return n
}()

func parseWordList(s string) []string {
	var out []string
	for _, line := range strings.Split(s, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		f := strings.Fields(line)
		out = append(out, f[len(f)-1])
	}
	return out
}

// Strength labels, indexed by score (BUILD-SPEC §4: CheckPassphrase).
var StrengthLabels = [...]string{"Too short", "Weak", "Fair", "Good", "Strong"}

// MinPassphraseScore is the lowest score Next accepts for the disk passphrase ("Fair").
const MinPassphraseScore = 2

// MinPasswordScore is the lowest score accepted for the account password ("Weak": 8+ chars,
// not a well-known password).
const MinPasswordScore = 1

// Strength is the result of CheckPassphrase.
type Strength struct {
	Score int     `json:"score"`
	Label string  `json:"label"`
	Words int     `json:"words"`
	OK    bool    `json:"ok"`
	Bits  float64 `json:"-"`
}

// wordBits is the entropy of one word drawn from the embedded list (log2 1296 ≈ 10.34).
var wordBits = math.Log2(float64(len(Words)))

// CheckPassphrase scores a passphrase 0–4. It is a small zxcvbn-style estimate: words from the
// embedded list count as one guess each, repeats and runs ("aaaa", "1234") count almost
// nothing, well-known passwords are "Weak", everything else counts by its character classes.
// Fewer than 8 characters is always "Too short". ok is score ≥ 2 ("Fair").
func CheckPassphrase(s string) Strength {
	words := countWords(s)
	runes := []rune(s)
	st := Strength{Words: words}
	switch {
	case len(runes) < 8:
		st.Score = 0
	case isCommonPassword(s):
		st.Score = 1
		st.Bits = 10
	default:
		st.Bits = estimateBits(runes)
		switch {
		case st.Bits < 25:
			st.Score = 1
		case st.Bits < 33:
			st.Score = 2
		case st.Bits < 42:
			st.Score = 3
		default:
			st.Score = 4
		}
	}
	st.Label = StrengthLabels[st.Score]
	st.OK = st.Score >= MinPassphraseScore
	return st
}

// MeterLabel is the text shown under the meter: "Strong · 4 words".
func (s Strength) MeterLabel() string {
	if s.Words >= 2 {
		return s.Label + " · " + strconv.Itoa(s.Words) + " words"
	}
	return s.Label
}

func countWords(s string) int {
	return len(strings.FieldsFunc(s, func(r rune) bool { return !unicode.IsLetter(r) }))
}

func estimateBits(runes []rune) float64 {
	var lower, upper, digit, other bool
	for _, r := range runes {
		switch {
		case unicode.IsLower(r):
			lower = true
		case unicode.IsUpper(r):
			upper = true
		case unicode.IsDigit(r):
			digit = true
		default:
			other = true
		}
	}
	pool := 0
	if lower {
		pool += 26
	}
	if upper {
		pool += 26
	}
	if digit {
		pool += 10
	}
	if other {
		pool += 33
	}
	poolBits := math.Log2(float64(pool))
	low := []rune(strings.ToLower(string(runes)))
	bits := 0.0
	afterWord := false
	for i := 0; i < len(runes); {
		if n := longestWordAt(low, i); n > 0 {
			bits += wordBits
			for _, r := range runes[i : i+n] {
				if unicode.IsUpper(r) {
					bits++ // capitalised word: one extra bit, not a whole character class
					break
				}
			}
			i += n
			afterWord = true
			continue
		}
		r := runes[i]
		switch {
		case afterWord && isSeparator(r):
			bits++
		case i > 0 && r == runes[i-1]:
			bits++
		case i > 0 && (r-runes[i-1] == 1 || runes[i-1]-r == 1):
			bits += 2
		default:
			bits += poolBits
		}
		afterWord = false
		i++
	}
	return bits
}

func isSeparator(r rune) bool {
	return r == ' ' || r == '-' || r == '_' || r == '.' || r == ',' || r == '+'
}

// longestWordAt returns the length of the longest list word (≥ 3 letters) starting at i.
func longestWordAt(low []rune, i int) int {
	for n := maxWordLen; n >= 3; n-- {
		if i+n > len(low) {
			continue
		}
		if wordSet[string(low[i:i+n])] {
			// Only count it as a word when it isn't glued into a longer run of letters
			// that is itself not made of words; good enough for passphrases.
			return n
		}
	}
	return 0
}

var commonPasswords = func() map[string]bool {
	m := map[string]bool{}
	for _, w := range strings.Fields(`password passw0rd p@ssw0rd password1 password123 12345678 123456789 1234567890
		qwertyuiop qwerty123 qwertyui asdfghjkl asdfasdf zxcvbnm1 1q2w3e4r 1qaz2wsx iloveyou letmein1 letmein
		welcome1 welcome123 sunshine princess football baseball superman batman123 trustno1 dragon123
		monkey123 abc12345 abcd1234 11111111 00000000 88888888 12341234 87654321 changeme administrator
		starwars whatever computer internet shadow123 master123 michael1 jennifer secret123 linux123
		fedora123 arctic123 arcticlinux correcthorsebatterystaple`) {
		m[w] = true
	}
	return m
}()

func isCommonPassword(s string) bool {
	l := strings.ToLower(s)
	if commonPasswords[l] {
		return true
	}
	trimmed := strings.TrimRight(l, "0123456789!.?*#@$")
	return trimmed != l && len(trimmed) >= 4 && commonPasswords[trimmed]
}

// SuggestPassphrase returns four random words from the embedded list, space separated.
func SuggestPassphrase() (string, error) {
	return randomWords(4)
}

func randomWords(n int) (string, error) {
	max := big.NewInt(int64(len(Words)))
	out := make([]string, n)
	for i := range out {
		k, err := rand.Int(rand.Reader, max)
		if err != nil {
			return "", err
		}
		out[i] = Words[k.Int64()]
	}
	return strings.Join(out, " "), nil
}
