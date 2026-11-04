package views

import (
	"errors"
	"testing"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/cohort"
	"github.com/eka-care/care_phc_mcp/schedule"
)

// A calendar day is exactly YYYY-MM-DD; kernel/views._day refuses the rest.
func TestACalendarDayIsOnlyYYYYMMDD(t *testing.T) {
	for _, bad := range []string{"31st October", "2026-11-04T00:00:00", "20261104",
		"2026-W45-3", "2026-1-4", "", "2026-02-30", "2026-13-01", "0000-01-01", "2026-02-29"} {
		on := bad
		_, _, err := calendar(Bundle{}, carephc.View{}, nil, &on, nil, nil, time.Now())
		var declared Declared
		if !errors.As(err, &declared) {
			t.Errorf("%q was accepted as a day (err %v)", bad, err)
		} else if want := "on must be a real calendar day written YYYY-MM-DD, not '" + bad + "'"; declared.Reason != want {
			t.Errorf("%q: reason %q, want %q", bad, declared.Reason, want)
		}
	}
}

func TestALeapDayIsADayInALeapYearOnly(t *testing.T) {
	// A well-formed date gets past the check and on to the read, which a nil
	// store cannot do: so a panic here means "accepted".
	accepted := func(on string) (ok bool) {
		defer func() {
			if recover() != nil {
				ok = true
			}
		}()
		_, _, err := calendar(Bundle{}, carephc.View{}, nil, &on, nil, nil, time.Now())
		var declared Declared
		return !errors.As(err, &declared)
	}
	if !accepted("2024-02-29") {
		t.Error("2024-02-29 was refused")
	}
	if accepted("2026-02-29") {
		t.Error("2026-02-29 was accepted")
	}
}

// A missed contact stays owed on every day after its window shuts, and not on
// a day before it opened: the rule the overdue list turns on.
func TestAMissedContactIsOwedEveryDayAfterItsWindowShuts(t *testing.T) {
	missed := cohort.Entry{Contact: schedule.Contact{State: schedule.Missed, Closes: "2026-04-05"}}
	if !covers(missed, "2026-04-06") || !covers(missed, "2026-11-04") {
		t.Error("a missed contact dropped off the day after its window shut")
	}
	if covers(missed, "2026-04-05") {
		t.Error("a missed contact with no day in the window was counted inside it")
	}
	done := cohort.Entry{Contact: schedule.Contact{State: schedule.Done, Closes: "2026-04-05"}}
	if covers(done, "2026-04-06") {
		t.Error("a done contact stayed owed after its window")
	}
	due := cohort.Entry{Contact: schedule.Contact{State: schedule.Due, Closes: "2026-04-05"}, On: []string{"2026-04-05"}}
	if !covers(due, "2026-04-05") {
		t.Error("a day in On was not covered")
	}
}

// Each refusal of a range, with the sentence kernel/views._span raises.
func TestARangeIsRefusedInTheSentencesThePythonUses(t *testing.T) {
	p := func(v string) *string { return &v }
	cases := []struct {
		label            string
		on, since, until *string
		want             string
	}{
		{"on with a range", p("2026-11-04"), p("2026-11-01"), p("2026-11-07"),
			"on and from/to answer different questions and must not be combined"},
		{"on with only from", p("2026-11-04"), p("2026-11-01"), nil,
			"on and from/to answer different questions and must not be combined"},
		{"from alone", nil, p("2026-11-01"), nil, "from and to go together: give both or neither"},
		{"to alone", nil, nil, p("2026-11-01"), "from and to go together: give both or neither"},
		{"inverted", nil, p("2026-11-07"), p("2026-11-01"), "from must not be after to"},
		{"over the cap", nil, p("2026-01-01"), p("2027-02-05"), "a range may span at most 400 days"},
		{"malformed from", nil, p("20261101"), p("2026-11-07"),
			"from must be a real calendar day written YYYY-MM-DD, not '20261101'"},
		{"malformed to", nil, p("2026-11-01"), p("2026-02-30"),
			"to must be a real calendar day written YYYY-MM-DD, not '2026-02-30'"},
		{"empty from", nil, p(""), p("2026-11-07"),
			"from must be a real calendar day written YYYY-MM-DD, not ''"},
	}
	for _, c := range cases {
		_, _, err := calendar(Bundle{}, carephc.View{}, nil, c.on, c.since, c.until, time.Now())
		var declared Declared
		if !errors.As(err, &declared) {
			t.Errorf("%s: not refused (err %v)", c.label, err)
		} else if declared.Reason != c.want {
			t.Errorf("%s: reason %q, want %q", c.label, declared.Reason, c.want)
		}
	}
}

// 400 days exactly is allowed and 401 is not: the cap counts both ends.
func TestTheCapCountsBothEndsOfARange(t *testing.T) {
	p := func(v string) *string { return &v }
	if _, _, ok, err := span(nil, p("2026-01-01"), p("2027-02-04")); err != nil || !ok {
		t.Errorf("400 days refused: %v", err)
	}
	if _, _, _, err := span(nil, p("2026-01-01"), p("2027-02-05")); err == nil {
		t.Error("401 days accepted")
	}
}
