// Package toml is a small, dependency-free parser for the subset of TOML the Arctic Linux
// catalog and profiles use: comments, bare/quoted/dotted keys, [tables], [[arrays of tables]],
// basic/literal/multi-line strings, booleans, integers, floats, arrays (multi-line, trailing
// commas) and inline tables. Dates and times are not supported.
//
// Parse returns a tree of map[string]any, []any, string, bool, int64 and float64.
// Unmarshal decodes that tree into Go structs (see decode.go).
package toml

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Error is a parse or decode error with a 1-based line number (0 when unknown).
type Error struct {
	Line int
	Msg  string
}

func (e *Error) Error() string {
	if e.Line > 0 {
		return fmt.Sprintf("toml: line %d: %s", e.Line, e.Msg)
	}
	return "toml: " + e.Msg
}

type parser struct {
	src  []rune
	pos  int
	line int

	root    map[string]any
	current map[string]any
	// tables explicitly defined with [header]; redefining one is an error.
	defined map[string]bool
}

// Parse parses a TOML document into a map.
func Parse(data []byte) (map[string]any, error) {
	if !utf8.Valid(data) {
		return nil, &Error{Msg: "document is not valid UTF-8"}
	}
	p := &parser{src: []rune(string(data)), line: 1, root: map[string]any{}, defined: map[string]bool{}}
	p.current = p.root
	if err := p.document(); err != nil {
		return nil, err
	}
	return p.root, nil
}

func (p *parser) errf(format string, a ...any) error {
	return &Error{Line: p.line, Msg: fmt.Sprintf(format, a...)}
}

func (p *parser) eof() bool { return p.pos >= len(p.src) }

func (p *parser) peek() rune {
	if p.eof() {
		return 0
	}
	return p.src[p.pos]
}

func (p *parser) peekAt(off int) rune {
	if p.pos+off >= len(p.src) {
		return 0
	}
	return p.src[p.pos+off]
}

func (p *parser) next() rune {
	r := p.src[p.pos]
	p.pos++
	if r == '\n' {
		p.line++
	}
	return r
}

func (p *parser) hasPrefix(s string) bool {
	i := 0
	for _, r := range s {
		if p.peekAt(i) != r {
			return false
		}
		i++
	}
	return true
}

// skipWS skips spaces and tabs.
func (p *parser) skipWS() {
	for !p.eof() && (p.peek() == ' ' || p.peek() == '\t') {
		p.pos++
	}
}

// skipComment skips a comment up to (not including) the newline.
func (p *parser) skipComment() {
	if p.peek() == '#' {
		for !p.eof() && p.peek() != '\n' {
			p.pos++
		}
	}
}

// endOfLine expects optional whitespace, an optional comment and a newline or EOF.
func (p *parser) endOfLine() error {
	p.skipWS()
	p.skipComment()
	if p.eof() {
		return nil
	}
	if p.peek() == '\r' && p.peekAt(1) == '\n' {
		p.pos++
	}
	if p.peek() != '\n' {
		return p.errf("unexpected %q after value", p.peek())
	}
	p.next()
	return nil
}

func (p *parser) document() error {
	for {
		p.skipWS()
		if p.eof() {
			return nil
		}
		switch r := p.peek(); {
		case r == '#':
			p.skipComment()
		case r == '\n':
			p.next()
		case r == '\r' && p.peekAt(1) == '\n':
			p.pos++
			p.next()
		case r == '[':
			if err := p.header(); err != nil {
				return err
			}
			if err := p.endOfLine(); err != nil {
				return err
			}
		default:
			if err := p.keyValue(p.current); err != nil {
				return err
			}
			if err := p.endOfLine(); err != nil {
				return err
			}
		}
	}
}

func (p *parser) header() error {
	p.next() // [
	array := false
	if p.peek() == '[' {
		p.next()
		array = true
	}
	p.skipWS()
	keys, err := p.key()
	if err != nil {
		return err
	}
	p.skipWS()
	if p.peek() != ']' {
		return p.errf("expected ] after table name")
	}
	p.next()
	if array {
		if p.peek() != ']' {
			return p.errf("expected ]] after array-of-tables name")
		}
		p.next()
	}
	full := strings.Join(keys, ".")

	// Walk to the parent, creating implicit tables.
	t := p.root
	for i, k := range keys[:len(keys)-1] {
		v, ok := t[k]
		if !ok {
			nt := map[string]any{}
			t[k] = nt
			t = nt
			continue
		}
		switch x := v.(type) {
		case map[string]any:
			t = x
		case []any:
			// Last element of an array of tables.
			if len(x) == 0 {
				return p.errf("cannot extend %q", strings.Join(keys[:i+1], "."))
			}
			m, ok := x[len(x)-1].(map[string]any)
			if !ok {
				return p.errf("key %q is not a table", strings.Join(keys[:i+1], "."))
			}
			t = m
		default:
			return p.errf("key %q is already a value", strings.Join(keys[:i+1], "."))
		}
	}
	last := keys[len(keys)-1]
	if array {
		v, ok := t[last]
		var arr []any
		if ok {
			a, isArr := v.([]any)
			if !isArr || !p.isTableArray(a) {
				return p.errf("key %q is not an array of tables", full)
			}
			arr = a
		}
		nt := map[string]any{}
		t[last] = append(arr, nt)
		p.current = nt
		return nil
	}
	if p.defined[full] {
		return p.errf("table [%s] defined twice", full)
	}
	p.defined[full] = true
	v, ok := t[last]
	if !ok {
		nt := map[string]any{}
		t[last] = nt
		p.current = nt
		return nil
	}
	m, isMap := v.(map[string]any)
	if !isMap {
		return p.errf("key %q is already a value", full)
	}
	p.current = m
	return nil
}

func (p *parser) isTableArray(a []any) bool {
	for _, e := range a {
		if _, ok := e.(map[string]any); !ok {
			return false
		}
	}
	return len(a) > 0
}

// key parses a possibly dotted key.
func (p *parser) key() ([]string, error) {
	var parts []string
	for {
		p.skipWS()
		var k string
		switch r := p.peek(); {
		case r == '"':
			s, err := p.basicString()
			if err != nil {
				return nil, err
			}
			k = s
		case r == '\'':
			s, err := p.literalString()
			if err != nil {
				return nil, err
			}
			k = s
		case isBareKeyRune(r):
			start := p.pos
			for !p.eof() && isBareKeyRune(p.peek()) {
				p.pos++
			}
			k = string(p.src[start:p.pos])
		default:
			return nil, p.errf("expected a key, found %q", r)
		}
		parts = append(parts, k)
		p.skipWS()
		if p.peek() != '.' {
			return parts, nil
		}
		p.next()
	}
}

func isBareKeyRune(r rune) bool {
	return r == '_' || r == '-' || (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')
}

func (p *parser) keyValue(t map[string]any) error {
	keys, err := p.key()
	if err != nil {
		return err
	}
	p.skipWS()
	if p.peek() != '=' {
		return p.errf("expected = after key %q", strings.Join(keys, "."))
	}
	p.next()
	p.skipWS()
	val, err := p.value()
	if err != nil {
		return err
	}
	for i, k := range keys[:len(keys)-1] {
		v, ok := t[k]
		if !ok {
			nt := map[string]any{}
			t[k] = nt
			t = nt
			continue
		}
		m, isMap := v.(map[string]any)
		if !isMap {
			return p.errf("key %q is already a value", strings.Join(keys[:i+1], "."))
		}
		t = m
	}
	last := keys[len(keys)-1]
	if _, dup := t[last]; dup {
		return p.errf("duplicate key %q", strings.Join(keys, "."))
	}
	t[last] = val
	return nil
}

func (p *parser) value() (any, error) {
	if p.eof() {
		return nil, p.errf("expected a value")
	}
	switch r := p.peek(); {
	case r == '"':
		if p.hasPrefix(`"""`) {
			return p.multiBasicString()
		}
		return p.basicString()
	case r == '\'':
		if p.hasPrefix(`'''`) {
			return p.multiLiteralString()
		}
		return p.literalString()
	case r == '[':
		return p.array()
	case r == '{':
		return p.inlineTable()
	case p.hasPrefix("true") && !isBareKeyRune(p.peekAt(4)):
		p.pos += 4
		return true, nil
	case p.hasPrefix("false") && !isBareKeyRune(p.peekAt(5)):
		p.pos += 5
		return false, nil
	default:
		return p.number()
	}
}

func (p *parser) basicString() (string, error) {
	p.next() // "
	var b strings.Builder
	for {
		if p.eof() || p.peek() == '\n' {
			return "", p.errf("unterminated string")
		}
		r := p.next()
		switch r {
		case '"':
			return b.String(), nil
		case '\\':
			if err := p.escape(&b); err != nil {
				return "", err
			}
		default:
			if r < 0x20 && r != '\t' || r == 0x7f {
				return "", p.errf("control character %U in string", r)
			}
			b.WriteRune(r)
		}
	}
}

func (p *parser) escape(b *strings.Builder) error {
	if p.eof() {
		return p.errf("unterminated escape")
	}
	r := p.next()
	switch r {
	case 'b':
		b.WriteByte('\b')
	case 't':
		b.WriteByte('\t')
	case 'n':
		b.WriteByte('\n')
	case 'f':
		b.WriteByte('\f')
	case 'r':
		b.WriteByte('\r')
	case 'e':
		b.WriteByte(0x1b)
	case '"':
		b.WriteByte('"')
	case '\\':
		b.WriteByte('\\')
	case 'u', 'U':
		n := 4
		if r == 'U' {
			n = 8
		}
		if p.pos+n > len(p.src) {
			return p.errf("short unicode escape")
		}
		code, err := strconv.ParseUint(string(p.src[p.pos:p.pos+n]), 16, 32)
		if err != nil || !utf8.ValidRune(rune(code)) {
			return p.errf("invalid unicode escape")
		}
		p.pos += n
		b.WriteRune(rune(code))
	default:
		return p.errf("invalid escape \\%c", r)
	}
	return nil
}

func (p *parser) multiBasicString() (string, error) {
	p.pos += 3
	// A newline right after the opening delimiter is trimmed.
	if p.peek() == '\r' && p.peekAt(1) == '\n' {
		p.pos++
	}
	if p.peek() == '\n' {
		p.next()
	}
	var b strings.Builder
	for {
		if p.eof() {
			return "", p.errf("unterminated multi-line string")
		}
		if p.hasPrefix(`"""`) {
			p.pos += 3
			// Up to two additional quotes belong to the content.
			for i := 0; i < 2 && p.peek() == '"'; i++ {
				b.WriteByte('"')
				p.pos++
			}
			return b.String(), nil
		}
		r := p.next()
		if r == '\\' {
			// Line-ending backslash: trim whitespace and newlines.
			save, saveLine := p.pos, p.line
			for !p.eof() && (p.peek() == ' ' || p.peek() == '\t') {
				p.pos++
			}
			if p.peek() == '\n' || (p.peek() == '\r' && p.peekAt(1) == '\n') {
				for !p.eof() && (p.peek() == ' ' || p.peek() == '\t' || p.peek() == '\n' || p.peek() == '\r') {
					p.next()
				}
				continue
			}
			p.pos, p.line = save, saveLine
			if err := p.escape(&b); err != nil {
				return "", err
			}
			continue
		}
		b.WriteRune(r)
	}
}

func (p *parser) literalString() (string, error) {
	p.next() // '
	start := p.pos
	for {
		if p.eof() || p.peek() == '\n' {
			return "", p.errf("unterminated literal string")
		}
		if p.peek() == '\'' {
			s := string(p.src[start:p.pos])
			p.next()
			return s, nil
		}
		p.pos++
	}
}

func (p *parser) multiLiteralString() (string, error) {
	p.pos += 3
	if p.peek() == '\r' && p.peekAt(1) == '\n' {
		p.pos++
	}
	if p.peek() == '\n' {
		p.next()
	}
	var b strings.Builder
	for {
		if p.eof() {
			return "", p.errf("unterminated multi-line literal string")
		}
		if p.hasPrefix(`'''`) {
			p.pos += 3
			for i := 0; i < 2 && p.peek() == '\''; i++ {
				b.WriteByte('\'')
				p.pos++
			}
			return b.String(), nil
		}
		b.WriteRune(p.next())
	}
}

// skipArrayWS skips whitespace, newlines and comments inside arrays.
func (p *parser) skipArrayWS() {
	for !p.eof() {
		switch p.peek() {
		case ' ', '\t', '\n', '\r':
			p.next()
		case '#':
			p.skipComment()
		default:
			return
		}
	}
}

func (p *parser) array() ([]any, error) {
	p.next() // [
	arr := []any{}
	for {
		p.skipArrayWS()
		if p.eof() {
			return nil, p.errf("unterminated array")
		}
		if p.peek() == ']' {
			p.next()
			return arr, nil
		}
		v, err := p.value()
		if err != nil {
			return nil, err
		}
		arr = append(arr, v)
		p.skipArrayWS()
		switch p.peek() {
		case ',':
			p.next()
		case ']':
			p.next()
			return arr, nil
		default:
			return nil, p.errf("expected , or ] in array")
		}
	}
}

func (p *parser) inlineTable() (map[string]any, error) {
	p.next() // {
	t := map[string]any{}
	p.skipWS()
	if p.peek() == '}' {
		p.next()
		return t, nil
	}
	for {
		p.skipWS()
		if err := p.keyValue(t); err != nil {
			return nil, err
		}
		p.skipWS()
		switch p.peek() {
		case ',':
			p.next()
		case '}':
			p.next()
			return t, nil
		default:
			return nil, p.errf("expected , or } in inline table")
		}
	}
}

func (p *parser) number() (any, error) {
	start := p.pos
	for !p.eof() {
		r := p.peek()
		if r == ' ' || r == '\t' || r == '\n' || r == '\r' || r == ',' || r == ']' || r == '}' || r == '#' {
			break
		}
		p.pos++
	}
	tok := string(p.src[start:p.pos])
	if tok == "" {
		return nil, p.errf("expected a value")
	}
	switch tok {
	case "inf", "+inf":
		return math.Inf(1), nil
	case "-inf":
		return math.Inf(-1), nil
	case "nan", "+nan", "-nan":
		return math.NaN(), nil
	}
	if err := checkUnderscores(tok); err != nil {
		return nil, p.errf("invalid number %q: %v", tok, err)
	}
	clean := strings.ReplaceAll(tok, "_", "")
	if strings.HasPrefix(clean, "0x") || strings.HasPrefix(clean, "0o") || strings.HasPrefix(clean, "0b") {
		base := map[byte]int{'x': 16, 'o': 8, 'b': 2}[clean[1]]
		n, err := strconv.ParseInt(clean[2:], base, 64)
		if err != nil {
			return nil, p.errf("invalid integer %q", tok)
		}
		return n, nil
	}
	if strings.ContainsAny(clean, ".eE") {
		digits := strings.TrimLeft(clean, "+-")
		if strings.HasPrefix(digits, ".") || strings.HasSuffix(digits, ".") || strings.Contains(digits, ".e") || strings.Contains(digits, ".E") {
			return nil, p.errf("invalid float %q", tok)
		}
		f, err := strconv.ParseFloat(clean, 64)
		if err != nil {
			return nil, p.errf("invalid float %q", tok)
		}
		return f, nil
	}
	digits := strings.TrimLeft(clean, "+-")
	if len(digits) > 1 && digits[0] == '0' {
		return nil, p.errf("leading zeros are not allowed in %q", tok)
	}
	n, err := strconv.ParseInt(clean, 10, 64)
	if err != nil {
		if strings.ContainsAny(tok, ":T") || strings.Count(tok, "-") >= 2 {
			return nil, p.errf("dates and times are not supported (%q)", tok)
		}
		return nil, p.errf("invalid value %q", tok)
	}
	return n, nil
}

func checkUnderscores(tok string) error {
	if strings.HasPrefix(tok, "_") || strings.HasSuffix(tok, "_") || strings.Contains(tok, "__") {
		return fmt.Errorf("misplaced underscore")
	}
	for i := 0; i < len(tok); i++ {
		if tok[i] != '_' {
			continue
		}
		if !isDigitish(tok[i-1]) || !isDigitish(tok[i+1]) {
			return fmt.Errorf("underscore must sit between digits")
		}
	}
	return nil
}

func isDigitish(c byte) bool {
	return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}
