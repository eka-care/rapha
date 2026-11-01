package queues

import (
	"fmt"
	"regexp"
	"strings"
)

// What must never reach this row, or a log line about it.
//
// The three patterns are kernel/queues.py's and care_phc/connectors/redact.py's,
// carried rather than re-invented. The ORDER they are applied in is the whole
// of what makes each one safe and it is the Python's order exactly: OTP first,
// because it is matched by the word next to it and the mobile rule would
// otherwise have eaten a long enough code; Aadhaar next; mobile last, because
// an Aadhaar number is twelve digits and would otherwise be reduced to its
// last four and called a phone number, which is a worse answer than removing
// it. Four digits of an Aadhaar number is still four digits of an Aadhaar
// number.

// Anything that looks like a one time password, removed whole. Matched on the
// word beside it rather than on the digits alone, because four to eight bare
// digits is also an age, a token number and a systolic reading.
var otpPattern = regexp.MustCompile(
	`(?i)\b(otp|o\.t\.p|one[ -]time[ -](?:password|code|pin)|pin)\b` +
		`\W{0,4}\d{4,8}\b`)

// OTPMark is what replaces it. kernel/queues.OTP_MARK.
const OTPMark = "<otp-removed>"

// Anything Aadhaar shaped: twelve digits, optionally spaced or hyphenated.
// care_phc/connectors/redact._AADHAAR.
var aadhaarPattern = regexp.MustCompile(`\b\d{4}[ -]?\d{4}[ -]?\d{4}\b`)

// AadhaarMark is care_phc/connectors/redact.AADHAAR_MARK.
const AadhaarMark = "<aadhaar-redacted>"

// Anything mobile shaped, reduced to its last four digits: ten digits or more,
// so a token number, an age and a year are not caught. An optional country
// code is eaten with it, so +91 does not survive as a prefix on a number whose
// body has gone.
//
// THE PYTHON'S PATTERN HAS TWO LOOKAROUNDS AND THIS ONE CANNOT.
// kernel/queues._MOBILE is
//
//	(?<!\d)(?:\+?\d{1,3}[ -]?)?(\d[\d -]{8,}\d)(?!\d)
//
// and Go's regexp is RE2, which has neither lookbehind nor lookahead. They are
// dropped here rather than approximated with something that means something
// else, and the reason that is sound is the matching discipline rather than a
// hope:
//
//   - the leading (?<!\d) says the match may not begin in the middle of a run
//     of digits. Matching is leftmost, so a match that could have begun at an
//     earlier digit did; there is no position where this engine starts inside a
//     run it could have started before.
//   - the trailing (?!\d) says it may not end in the middle of one. [\d -] is
//     greedy, so a run of digits is consumed to its end before the final \d
//     backtracks onto the last digit; there is no digit left immediately after.
//
// Both halves are asserted in TestTheMobileRuleIsNotTrickedByAdjacentDigits
// rather than left as this reasoning, because the reasoning is the thing most
// likely to be wrong.
var mobilePattern = regexp.MustCompile(`(?:\+?\d{1,3}[ -]?)?\d[\d -]{8,}\d`)

var notDigits = regexp.MustCompile(`\D`)

// ErrorChars is how much of a remote's sentence is kept. Long enough to name a
// cause, short enough that a response body cannot arrive whole through the
// gap. kernel/queues.ERROR_CHARS.
const ErrorChars = 300

func mobileToLast4(match string) string {
	digits := notDigits.ReplaceAllString(match, "")
	if len(digits) < 10 {
		// Not a mobile number. Handed back exactly as it came, which is
		// kernel/queues._mobile_to_last4's own answer: a redactor that eats
		// identifiers a person needs to read is a redactor people route
		// around.
		return match
	}
	return "<mobile ending " + digits[len(digits)-4:] + ">"
}

// Scrubbed is the only text this package ever writes to disk or to a log.
//
// Truncated by RUNE and not by byte. The Python slices a str, which is
// characters; slicing Go bytes at 300 would cut a multibyte character in half
// and put a replacement character on the row.
func Scrubbed(text string) string {
	out := otpPattern.ReplaceAllString(text, OTPMark)
	out = aadhaarPattern.ReplaceAllString(out, AadhaarMark)
	out = mobilePattern.ReplaceAllStringFunc(out, mobileToLast4)
	runes := []rune(out)
	if len(runes) > ErrorChars {
		return string(runes[:ErrorChars])
	}
	return string(runes)
}

// scrubbedError is Scrubbed over an error, which is what every call site here
// actually has. Separate so that no call site is tempted to write the raw
// sentence and scrub it later.
func scrubbedError(err error) string {
	if err == nil {
		return ""
	}
	return Scrubbed(err.Error())
}

// typeName is what is kept from a failure that is not an Unsendable: the type
// and nothing else. kernel/queues.pump's own rule, and the reason for it is
// that an arbitrary failure's text on this path is a response body, and a
// response body here is a consultation.
//
// THE NAME ITSELF CANNOT MATCH THE PYTHON'S and is not meant to. The Python
// writes `type(broke).__name__`, so a sender raising ValueError puts
// "ValueError" on the row; Go has no such name and %T gives the concrete type,
// which for a sender's own error type is that type. What is carried is the
// property rather than the spelling: the row names a KIND of failure and never
// the sentence that came with it. The parity check compares the two engines on
// the state and the attempt count, not on this string, and says so.
func typeName(err error) string {
	if err == nil {
		return "<nil>"
	}
	return strings.TrimPrefix(fmt.Sprintf("%T", err), "*")
}
