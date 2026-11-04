package views

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/cohort"
	"github.com/eka-care/care_phc_mcp/schedule"
	"github.com/eka-care/care_phc_mcp/store"
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

// ---- the ranged branch, through a real read -------------------------------
//
// The refusal tests above return before any read. These reach the grid itself:
// one open pregnancy nobody has visited, long enough ago that its early
// contacts are missed, read through an in-memory store.

type grid struct {
	t      *testing.T
	b      Bundle
	view   carephc.View
	s      Reader
	today  time.Time
	missed cohort.Entry
}

func gridCentre(t *testing.T) *grid {
	t.Helper()
	cat, err := carephc.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := cat.LoadDeclarations(); err != nil {
		t.Fatal(err)
	}
	s, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	if _, err := s.Write("patient", map[string]any{"id": "p-g", "name": "G", "age": "30"}, "t-g"); err != nil {
		t.Fatal(err)
	}
	if _, err := s.DB().Exec("INSERT INTO episode_of_care (id, patient, type, status, anchor_date," +
		" anchor_basis, outcome, created_date) VALUES ('ep-g','p-g','pregnancy','active'," +
		"'2026-01-05','last_menstrual_period','','2026-02-01T09:00:00+00:00')"); err != nil {
		t.Fatal(err)
	}
	g := &grid{t: t, b: Bundle{Catalogue: cat, Workflow: cat.Workflow}, s: s,
		view:  carephc.View{Episodes: []string{"pregnancy"}},
		today: time.Date(2026, 9, 1, 12, 0, 0, 0, time.UTC)}
	wide, err := cohort.Owed(cat, s, cat.Workflow, g.view.Episodes,
		time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC), time.Date(2026, 12, 31, 0, 0, 0, 0, time.UTC), g.today)
	if err != nil {
		t.Fatal(err)
	}
	for _, e := range wide {
		if e.State == schedule.Missed && e.Due < "2026-08-01" {
			g.missed = e
			break
		}
	}
	if g.missed.Due == "" {
		t.Fatal("the fixture has no missed contact to place")
	}
	return g
}

func (g *grid) ask(from, to string) ([]CalendarRow, []Group) {
	g.t.Helper()
	rows, groups, err := calendar(g.b, g.view, g.s, nil, &from, &to, g.today)
	if err != nil {
		g.t.Fatal(err)
	}
	return rows, groups
}

// A range answers the span it was asked, not one day.
func TestARangeAnswersTheSpanAndNotOneDay(t *testing.T) {
	g := gridCentre(t)
	for _, c := range []struct {
		from, to string
		days     int
	}{{"2026-08-30", "2026-09-05", 7}, {"2026-08-01", "2026-08-31", 31},
		{"2026-12-28", "2027-01-03", 7}, {"2026-09-01", "2026-09-01", 1}} {
		_, groups := g.ask(c.from, c.to)
		if len(groups) != c.days {
			t.Errorf("%s..%s: %d groups, want %d", c.from, c.to, len(groups), c.days)
		}
		if groups[0].Key != c.from {
			t.Errorf("%s..%s starts at %v", c.from, c.to, groups[0].Key)
		}
	}
}

// The three places a missed contact can land.
func TestAMissedContactIsPlacedOnItsDueDayOrTodayOrNowhere(t *testing.T) {
	g := gridCentre(t)
	due := g.missed.Due
	id := g.missed.Contact.Contact
	cellOf := func(rows []CalendarRow, groups []Group) (drawn bool, cells []string) {
		for _, r := range rows {
			if r.Contact.Contact == id {
				drawn = true
			}
		}
		return
	}
	// Due inside the range (today is inside too): counted on its due day.
	day := func(plus int) string {
		d, _ := time.Parse(dateLayout, due)
		return d.AddDate(0, 0, plus).Format(dateLayout)
	}
	rows, groups := g.ask(day(-1), "2026-09-02")
	if drawn, _ := cellOf(rows, groups); !drawn {
		t.Fatal("a missed contact due inside the range was not drawn")
	}
	for _, grp := range groups {
		if grp.Key == due && grp.Count < 1 {
			t.Errorf("not counted on its due day %s", due)
		}
	}
	todayInside := countOn(groups, "2026-09-01")
	// Due before the range, today inside: a marker on today, once.
	rows2, groups2 := g.ask(day(1), "2026-09-02")
	if drawn, _ := cellOf(rows2, groups2); !drawn {
		t.Fatal("a missed contact due before the range lost its marker on today")
	}
	if countOn(groups2, "2026-09-01") < 1 {
		t.Error("the marker was not counted on today")
	}
	if todayInside >= countOn(groups2, "2026-09-01") && due != "2026-09-01" {
		t.Error("the due-day case also counted it on today")
	}
	// Due before the range, today outside too: absent from both.
	rows3, groups3 := g.ask("2026-09-05", "2026-09-11")
	if drawn, _ := cellOf(rows3, groups3); drawn {
		t.Error("a missed contact with no cell was drawn")
	}
	for _, e := range rows3 {
		if e.State == schedule.Missed {
			t.Errorf("missed %s drawn with today outside the range", e.Contact.Contact)
		}
	}
}

func countOn(groups []Group, key string) int {
	for _, g := range groups {
		if g.Key == key {
			return g.Count
		}
	}
	return -1
}

// Every row has a counted cell and the counts sum to the rows drawn.
func TestRowsAndCountsOfARangeAgree(t *testing.T) {
	g := gridCentre(t)
	for _, c := range [][2]string{{"2026-08-30", "2026-09-05"}, {"2026-01-01", "2026-12-31"},
		{"2026-09-05", "2026-09-11"}, {"2026-09-01", "2026-09-01"}} {
		rows, groups := g.ask(c[0], c[1])
		sum := 0
		for _, grp := range groups {
			sum += grp.Count
		}
		if sum != len(rows) {
			t.Errorf("%v: %d counted for %d rows", c, sum, len(rows))
		}
	}
}

func TestEveryRangeRowSaysItsCell(t *testing.T) {
	g := gridCentre(t)
	from, to := "2026-08-30", "2026-09-05"
	rows, groups := g.ask(from, to)
	keys := map[string]int{}
	for _, grp := range groups {
		keys[grp.Key.(string)] = grp.Count
	}
	seen := map[string]int{}
	for _, r := range rows {
		if _, in := keys[r.Cell]; !in {
			t.Errorf("%s has cell %q outside the span", r.Contact.Contact, r.Cell)
		}
		seen[r.Cell]++
	}
	for k, n := range keys {
		if seen[k] != n {
			t.Errorf("%s: %d rows say it, %d counted", k, seen[k], n)
		}
	}
	// A missed contact due before the span carries today.
	for _, r := range rows {
		if r.State == schedule.Missed && r.Due < from && r.Cell != "2026-09-01" {
			t.Errorf("%s due %s carries %s, not today", r.Contact.Contact, r.Due, r.Cell)
		}
	}
	var late int
	for _, r := range rows {
		if r.Due < from {
			late++
		}
	}
	if late == 0 {
		t.Fatal("the fixture has no late contact in the span")
	}
	// A due day inside the span is its own cell.
	inside, _ := g.ask("2026-01-01", "2026-12-31")
	for _, r := range inside {
		if r.Cell != r.Due {
			t.Errorf("%s due %s carries %s", r.Contact.Contact, r.Due, r.Cell)
		}
	}
}

func TestADayHasNoCellOnItsRows(t *testing.T) {
	g := gridCentre(t)
	on := "2026-09-01"
	rows, _, err := calendar(g.b, g.view, g.s, &on, nil, nil, g.today)
	if err != nil || len(rows) == 0 {
		t.Fatalf("rows %d err %v", len(rows), err)
	}
	for _, r := range rows {
		if r.Cell != "" {
			t.Errorf("%s carries cell %q on ?on=", r.Contact.Contact, r.Cell)
		}
	}
	raw, _ := json.Marshal(rows[0])
	if strings.Contains(string(raw), `"cell"`) {
		t.Errorf("cell on the wire: %s", raw)
	}
}
