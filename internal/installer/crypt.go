package installer

import (
	"crypto/rand"
	"crypto/sha512"
	"errors"
	"strconv"
	"strings"
)

// SHA-512 crypt ("$6$", Ulrich Drepper's specification, as used by glibc and shadow-utils).
// The account password is hashed here so the plaintext never reaches a command line or disk.

const (
	cryptAlphabet     = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
	sha512DefaultRnds = 5000
	sha512MinRounds   = 1000
	sha512MaxRounds   = 999999999
	sha512SaltMax     = 16
)

// NewSalt returns 16 random characters from the crypt alphabet.
func NewSalt() (string, error) {
	b := make([]byte, sha512SaltMax)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	for i := range b {
		b[i] = cryptAlphabet[int(b[i])%len(cryptAlphabet)]
	}
	return string(b), nil
}

// HashPassword hashes a password with a random salt: "$6$<salt>$<hash>".
func HashPassword(password []byte) (string, error) {
	salt, err := NewSalt()
	if err != nil {
		return "", err
	}
	return SHA512Crypt(password, "$6$"+salt)
}

// SHA512Crypt computes a crypt(3) SHA-512 hash. setting is "$6$salt" or "$6$rounds=N$salt"
// (a trailing "$hash" is ignored, so a full hash can be passed to verify).
func SHA512Crypt(password []byte, setting string) (string, error) {
	if !strings.HasPrefix(setting, "$6$") {
		return "", errors.New("crypt: not a $6$ setting")
	}
	rest := setting[3:]
	rounds, custom := sha512DefaultRnds, false
	if strings.HasPrefix(rest, "rounds=") {
		end := strings.IndexByte(rest, '$')
		if end < 0 {
			return "", errors.New("crypt: bad rounds")
		}
		n, err := strconv.Atoi(rest[len("rounds="):end])
		if err != nil {
			return "", errors.New("crypt: bad rounds")
		}
		rounds, custom = n, true
		if rounds < sha512MinRounds {
			rounds = sha512MinRounds
		}
		if rounds > sha512MaxRounds {
			rounds = sha512MaxRounds
		}
		rest = rest[end+1:]
	}
	salt := rest
	if i := strings.IndexByte(salt, '$'); i >= 0 {
		salt = salt[:i]
	}
	if len(salt) > sha512SaltMax {
		salt = salt[:sha512SaltMax]
	}
	p, s := password, []byte(salt)

	b := sha512.New()
	b.Write(p)
	b.Write(s)
	b.Write(p)
	sumB := b.Sum(nil)

	a := sha512.New()
	a.Write(p)
	a.Write(s)
	cnt := len(p)
	for ; cnt > 64; cnt -= 64 {
		a.Write(sumB)
	}
	a.Write(sumB[:cnt])
	for cnt = len(p); cnt > 0; cnt >>= 1 {
		if cnt&1 != 0 {
			a.Write(sumB)
		} else {
			a.Write(p)
		}
	}
	sumA := a.Sum(nil)

	dp := sha512.New()
	for i := 0; i < len(p); i++ {
		dp.Write(p)
	}
	sumDP := dp.Sum(nil)
	pBytes := make([]byte, 0, len(p))
	for cnt = len(p); cnt >= 64; cnt -= 64 {
		pBytes = append(pBytes, sumDP...)
	}
	pBytes = append(pBytes, sumDP[:cnt]...)

	ds := sha512.New()
	for i := 0; i < 16+int(sumA[0]); i++ {
		ds.Write(s)
	}
	sumDS := ds.Sum(nil)
	sBytes := make([]byte, 0, len(s))
	for cnt = len(s); cnt >= 64; cnt -= 64 {
		sBytes = append(sBytes, sumDS...)
	}
	sBytes = append(sBytes, sumDS[:cnt]...)

	c := sumA
	for i := 0; i < rounds; i++ {
		h := sha512.New()
		if i&1 != 0 {
			h.Write(pBytes)
		} else {
			h.Write(c)
		}
		if i%3 != 0 {
			h.Write(sBytes)
		}
		if i%7 != 0 {
			h.Write(pBytes)
		}
		if i&1 != 0 {
			h.Write(c)
		} else {
			h.Write(pBytes)
		}
		c = h.Sum(nil)
	}
	for i := range pBytes {
		pBytes[i] = 0
	}

	var out strings.Builder
	out.WriteString("$6$")
	if custom {
		out.WriteString("rounds=" + strconv.Itoa(rounds) + "$")
	}
	out.WriteString(salt)
	out.WriteByte('$')
	order := [][3]int{
		{0, 21, 42}, {22, 43, 1}, {44, 2, 23}, {3, 24, 45}, {25, 46, 4}, {47, 5, 26}, {6, 27, 48},
		{28, 49, 7}, {50, 8, 29}, {9, 30, 51}, {31, 52, 10}, {53, 11, 32}, {12, 33, 54}, {34, 55, 13},
		{56, 14, 35}, {15, 36, 57}, {37, 58, 16}, {59, 17, 38}, {18, 39, 60}, {40, 61, 19}, {62, 20, 41},
	}
	for _, o := range order {
		b64From24(&out, c[o[0]], c[o[1]], c[o[2]], 4)
	}
	b64From24(&out, 0, 0, c[63], 2)
	return out.String(), nil
}

func b64From24(out *strings.Builder, b2, b1, b0 byte, n int) {
	w := uint(b2)<<16 | uint(b1)<<8 | uint(b0)
	for i := 0; i < n; i++ {
		out.WriteByte(cryptAlphabet[w&0x3f])
		w >>= 6
	}
}
