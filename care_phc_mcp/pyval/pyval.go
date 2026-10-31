// Package pyval renders a decoded JSON value the way Python would.
//
// WHY THIS EXISTS AT ALL
// ----------------------
// Every sentence the guard refuses with is part of the contract: a clerk
// reads it, agent/turn.py branches near it, and scripts/check_go_parity.py
// compares it between the two engines character for character. Several of
// those sentences interpolate a payload value, a range bound or a sorted list
// of allowed choices. So Go has to spell a number and a list exactly as
// Python's str() and repr() do, or the two engines disagree about a denial
// they actually agree about.
//
// WHAT IS NOT CLAIMED
// -------------------
// This is not a Python runtime. It covers the value shapes a questionnaire
// answer and a questionnaire declaration can hold: a string, a bool, an
// integer, a float, a list and a mapping. A float outside the range clinical
// data lives in (one needing an exponent, an infinity, a NaN) is rendered by
// Go's own shortest round-trip and the result is close to but not guaranteed
// identical to CPython's repr. There is none in the declarations and a
// questionnaire with one would be a different problem.
//
// NUMBERS ARRIVE AS json.Number ON PURPOSE
// ----------------------------------------
// encoding/json's default is float64 for every number, which loses the
// difference between the integer 140 and the float 140.0. Python keeps it,
// and the difference is visible in a denial: an integer answer outside its
// range says "300" and a decimal one says "41.0". So every decoder in this
// module's Go side is given UseNumber, and Decode below is the one place that
// is arranged.
package pyval

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
)

// Decode parses JSON with numbers kept as json.Number, so an integer stays
// distinguishable from a float with the same value.
func Decode(raw []byte, into any) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	return dec.Decode(into)
}

// IsBlank is kernel/mapping._blank: None, "", [] or {}.
func IsBlank(v any) bool {
	switch t := v.(type) {
	case nil:
		return true
	case string:
		return t == ""
	case []any:
		return len(t) == 0
	case map[string]any:
		return len(t) == 0
	}
	return false
}

// IsUnanswered is the `value in (None, "")` test the validator and the
// terminology rules both use, which is narrower than IsBlank: an empty list
// IS an answer to those two.
func IsUnanswered(v any) bool {
	if v == nil {
		return true
	}
	s, ok := v.(string)
	return ok && s == ""
}

// Str is Python's str() for the values a payload holds. It is what an
// f-string interpolates.
func Str(v any) string {
	switch t := v.(type) {
	case nil:
		return "None"
	case bool:
		if t {
			return "True"
		}
		return "False"
	case string:
		return t
	case json.Number:
		return numberStr(t)
	case int:
		return strconv.Itoa(t)
	case int64:
		return strconv.FormatInt(t, 10)
	case float64:
		return FloatStr(t)
	case []any:
		return Repr(v)
	case map[string]any:
		return Repr(v)
	}
	return fmt.Sprint(v)
}

// Repr is Python's repr(): a string in quotes, everything else as str().
func Repr(v any) string {
	switch t := v.(type) {
	case string:
		return QuoteString(t)
	case []any:
		parts := make([]string, 0, len(t))
		for _, item := range t {
			parts = append(parts, Repr(item))
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case map[string]any:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		// repr() of a dict is in insertion order, which Go cannot keep.
		// Sorted, and said here rather than discovered: no sentence this
		// module renders interpolates a dict, and one that did would need the
		// order carried.
		sort.Strings(keys)
		parts := make([]string, 0, len(keys))
		for _, k := range keys {
			parts = append(parts, QuoteString(k)+": "+Repr(t[k]))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	}
	return Str(v)
}

// ReprStrings is repr() of a sorted list of strings, which is what the choice
// denial interpolates: ['a', 'b'].
func ReprStrings(values []string) string {
	sorted := append([]string(nil), values...)
	sort.Strings(sorted)
	parts := make([]string, 0, len(sorted))
	for _, s := range sorted {
		parts = append(parts, QuoteString(s))
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

// QuoteString is Python's repr() of a str: single quotes unless the string
// holds one and no double quote, in which case double quotes, with the
// backslash escapes Python uses.
func QuoteString(s string) string {
	quote := byte('\'')
	if strings.Contains(s, "'") && !strings.Contains(s, `"`) {
		quote = '"'
	}
	var b strings.Builder
	b.WriteByte(quote)
	for _, r := range s {
		switch r {
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case rune(quote):
			b.WriteByte('\\')
			b.WriteRune(r)
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte(quote)
	return b.String()
}

// numberStr renders a json.Number the way Python renders the value json.load
// produced from the same token: an integer literal is an int, anything with a
// point or an exponent is a float.
func numberStr(n json.Number) string {
	text := string(n)
	if !strings.ContainsAny(text, ".eE") {
		return text
	}
	f, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return text
	}
	return FloatStr(f)
}

// FloatStr is Python's str() of a float: the shortest text that reads back as
// the same value, with a decimal point always present so 41.0 is not "41".
func FloatStr(f float64) string {
	if math.IsInf(f, 1) {
		return "inf"
	}
	if math.IsInf(f, -1) {
		return "-inf"
	}
	if math.IsNaN(f) {
		return "nan"
	}
	s := strconv.FormatFloat(f, 'g', -1, 64)
	if !strings.ContainsAny(s, ".eE") {
		s += ".0"
	}
	return s
}

// AsFloat is Python's float(value): a number, a numeric string or a bool.
func AsFloat(v any) (float64, bool) {
	switch t := v.(type) {
	case bool:
		if t {
			return 1, true
		}
		return 0, true
	case json.Number:
		f, err := strconv.ParseFloat(strings.TrimSpace(string(t)), 64)
		return f, err == nil
	case float64:
		return t, true
	case int:
		return float64(t), true
	case string:
		f, err := strconv.ParseFloat(strings.TrimSpace(t), 64)
		return f, err == nil
	}
	return 0, false
}

// AsInt is Python's int(value), including its two awkward corners: a float is
// truncated towards zero rather than refused, and a string must be an integer
// literal, so int("140.5") is a failure where float("140.5") is not.
func AsInt(v any) (int64, bool) {
	switch t := v.(type) {
	case bool:
		if t {
			return 1, true
		}
		return 0, true
	case json.Number:
		text := strings.TrimSpace(string(t))
		if i, err := strconv.ParseInt(text, 10, 64); err == nil {
			return i, true
		}
		// A JSON float literal: int() truncates towards zero.
		f, err := strconv.ParseFloat(text, 64)
		if err != nil {
			return 0, false
		}
		return int64(math.Trunc(f)), true
	case float64:
		return int64(math.Trunc(t)), true
	case int:
		return int64(t), true
	case string:
		i, err := strconv.ParseInt(strings.TrimSpace(t), 10, 64)
		return i, err == nil
	}
	return 0, false
}

// Equal is Python's == between two decoded JSON values, which is what a
// choice check does: a string answer never equals a numeric option, and two
// numbers are equal by value whatever they were spelled as.
func Equal(a, b any) bool {
	as, aStr := a.(string)
	bs, bStr := b.(string)
	if aStr || bStr {
		return aStr && bStr && as == bs
	}
	ab, aBool := a.(bool)
	bb, bBool := b.(bool)
	if aBool && bBool {
		return ab == bb
	}
	af, aNum := AsFloat(a)
	bf, bNum := AsFloat(b)
	if aNum && bNum && !aBool && !bBool {
		return af == bf
	}
	return false
}

// Dumps is json.dumps(value, sort_keys=True): Python's separators (", " and
// ": "), its sorted keys, and its ensure_ascii escaping. One mapping source
// stores a whole payload this way, so a Go engine writing the row has to
// produce the same bytes or the same visit reads differently depending on
// which engine recorded it.
func Dumps(v any) string {
	var b strings.Builder
	dump(&b, v)
	return b.String()
}

func dump(b *strings.Builder, v any) {
	switch t := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if t {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case string:
		b.WriteString(jsonString(t))
	case json.Number:
		b.WriteString(numberStr(t))
	case float64:
		b.WriteString(FloatStr(t))
	case int:
		b.WriteString(strconv.Itoa(t))
	case int64:
		b.WriteString(strconv.FormatInt(t, 10))
	case []any:
		b.WriteByte('[')
		for i, item := range t {
			if i > 0 {
				b.WriteString(", ")
			}
			dump(b, item)
		}
		b.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		b.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				b.WriteString(", ")
			}
			b.WriteString(jsonString(k))
			b.WriteString(": ")
			dump(b, t[k])
		}
		b.WriteByte('}')
	default:
		b.WriteString(jsonString(fmt.Sprint(v)))
	}
}

// jsonString is Python's json string encoding with ensure_ascii=True: every
// non-ASCII rune as a \u escape, and the same short escapes for the controls.
func jsonString(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			switch {
			case r < 0x20:
				fmt.Fprintf(&b, `\u%04x`, r)
			case r < 0x7f:
				b.WriteRune(r)
			case r > 0xffff:
				r -= 0x10000
				fmt.Fprintf(&b, `\u%04x\u%04x`, 0xd800+(r>>10), 0xdc00+(r&0x3ff))
			default:
				fmt.Fprintf(&b, `\u%04x`, r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}
