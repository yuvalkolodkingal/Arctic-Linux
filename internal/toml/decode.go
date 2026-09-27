package toml

import (
	"fmt"
	"math"
	"reflect"
	"sort"
	"strings"
)

// Unmarshal parses data and decodes it into v, which must be a non-nil pointer.
//
// Struct fields are matched by their `toml:"name"` tag (or the lower-cased field name);
// `toml:"-"` skips a field. Decoding is strict: a key with no matching field is an error,
// which catches typos in hand-written manifests. Supported targets: string, bool, all int
// and float kinds, slices, arrays of tables into []struct, nested structs, pointers to
// structs, map[string]T and interface{} (receives the raw parsed value).
func Unmarshal(data []byte, v any) error {
	tree, err := Parse(data)
	if err != nil {
		return err
	}
	return Decode(tree, v)
}

// Decode decodes an already parsed tree into v.
func Decode(tree map[string]any, v any) error {
	rv := reflect.ValueOf(v)
	if rv.Kind() != reflect.Pointer || rv.IsNil() {
		return &Error{Msg: "Unmarshal needs a non-nil pointer"}
	}
	return decodeValue("", tree, rv.Elem())
}

func decodeValue(path string, src any, dst reflect.Value) error {
	if dst.Kind() == reflect.Pointer {
		if dst.IsNil() {
			dst.Set(reflect.New(dst.Type().Elem()))
		}
		return decodeValue(path, src, dst.Elem())
	}
	if dst.Kind() == reflect.Interface && dst.NumMethod() == 0 {
		dst.Set(reflect.ValueOf(src))
		return nil
	}
	switch dst.Kind() {
	case reflect.String:
		s, ok := src.(string)
		if !ok {
			return typeErr(path, "a string", src)
		}
		dst.SetString(s)
	case reflect.Bool:
		b, ok := src.(bool)
		if !ok {
			return typeErr(path, "true or false", src)
		}
		dst.SetBool(b)
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		n, ok := src.(int64)
		if !ok {
			return typeErr(path, "an integer", src)
		}
		if dst.OverflowInt(n) {
			return &Error{Msg: fmt.Sprintf("%s: %d does not fit", path, n)}
		}
		dst.SetInt(n)
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		n, ok := src.(int64)
		if !ok || n < 0 {
			return typeErr(path, "a non-negative integer", src)
		}
		if dst.OverflowUint(uint64(n)) {
			return &Error{Msg: fmt.Sprintf("%s: %d does not fit", path, n)}
		}
		dst.SetUint(uint64(n))
	case reflect.Float32, reflect.Float64:
		switch x := src.(type) {
		case float64:
			dst.SetFloat(x)
		case int64:
			dst.SetFloat(float64(x))
		default:
			return typeErr(path, "a number", src)
		}
		if dst.Kind() == reflect.Float32 && !math.IsInf(dst.Float(), 0) && math.Abs(dst.Float()) > math.MaxFloat32 {
			return &Error{Msg: fmt.Sprintf("%s: value does not fit", path)}
		}
	case reflect.Slice:
		arr, ok := src.([]any)
		if !ok {
			return typeErr(path, "an array", src)
		}
		out := reflect.MakeSlice(dst.Type(), len(arr), len(arr))
		for i, e := range arr {
			if err := decodeValue(fmt.Sprintf("%s[%d]", path, i), e, out.Index(i)); err != nil {
				return err
			}
		}
		dst.Set(out)
	case reflect.Map:
		m, ok := src.(map[string]any)
		if !ok {
			return typeErr(path, "a table", src)
		}
		if dst.Type().Key().Kind() != reflect.String {
			return &Error{Msg: fmt.Sprintf("%s: map keys must be strings", path)}
		}
		if dst.IsNil() {
			dst.Set(reflect.MakeMapWithSize(dst.Type(), len(m)))
		}
		for _, k := range sortedKeys(m) {
			ev := reflect.New(dst.Type().Elem()).Elem()
			if err := decodeValue(join(path, k), m[k], ev); err != nil {
				return err
			}
			dst.SetMapIndex(reflect.ValueOf(k).Convert(dst.Type().Key()), ev)
		}
	case reflect.Struct:
		m, ok := src.(map[string]any)
		if !ok {
			return typeErr(path, "a table", src)
		}
		fields := structFields(dst.Type())
		for _, k := range sortedKeys(m) {
			idx, ok := fields[k]
			if !ok {
				return &Error{Msg: fmt.Sprintf("unknown key %q", join(path, k))}
			}
			if err := decodeValue(join(path, k), m[k], dst.FieldByIndex(idx)); err != nil {
				return err
			}
		}
	default:
		return &Error{Msg: fmt.Sprintf("%s: unsupported target type %s", path, dst.Type())}
	}
	return nil
}

func structFields(t reflect.Type) map[string][]int {
	out := map[string][]int{}
	for i := 0; i < t.NumField(); i++ {
		f := t.Field(i)
		if !f.IsExported() {
			continue
		}
		tag := f.Tag.Get("toml")
		if tag == "-" {
			continue
		}
		name, _, _ := strings.Cut(tag, ",")
		if f.Anonymous && name == "" && f.Type.Kind() == reflect.Struct {
			for k, idx := range structFields(f.Type) {
				out[k] = append([]int{i}, idx...)
			}
			continue
		}
		if name == "" {
			name = strings.ToLower(f.Name)
		}
		out[name] = []int{i}
	}
	return out
}

func sortedKeys(m map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func join(path, k string) string {
	if path == "" {
		return k
	}
	return path + "." + k
}

func typeErr(path, want string, got any) error {
	return &Error{Msg: fmt.Sprintf("%s: expected %s, got %s", path, want, describe(got))}
}

func describe(v any) string {
	switch x := v.(type) {
	case string:
		return fmt.Sprintf("string %q", x)
	case bool:
		return fmt.Sprintf("boolean %v", x)
	case int64:
		return fmt.Sprintf("integer %d", x)
	case float64:
		return fmt.Sprintf("float %v", x)
	case []any:
		return "an array"
	case map[string]any:
		return "a table"
	default:
		return fmt.Sprintf("%T", v)
	}
}
