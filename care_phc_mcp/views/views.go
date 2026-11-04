// Package views is kernel/views.py in Go: a queue, a summary, a dashboard or
// a tasklist, evaluated.
//
// There is one implementation per KIND and no per screen code. The renderer
// receives a ViewResult and draws it; a new queue for a dental chain is a
// markdown file, not a component. That is the property this package exists to
// keep, so nothing here may branch on a view id.
//
// METRICS ARE LOCAL AND THERE IS NO EXPORT HERE
// ---------------------------------------------
// kernel/views.py says it in its own first paragraph: "There is no export
// here and there must never be one: the numbers are computed on the machine
// that holds the records." Nothing in this file opens a socket, and the only
// thing it reads is the store it was handed.
//
// NO LITERAL INSTANT APPEARS IN THIS FILE
// ---------------------------------------
// Every window is derived from the clock it was given. Ten check scripts on
// this branch pinned a literal instant on 2026-10-31 and one of them mixed a
// literal with the wall clock and failed on every machine from 10:00 UTC that
// day. WindowStart takes `at` for exactly that reason, and the routes pass
// the current time.
//
// THE TWO WINDOW FUNCTIONS ARE NOT THE SAME FUNCTION
// --------------------------------------------------
// WindowStart below is kernel/views.window_start: a day is midnight today, a
// week is seven days back and a month is thirty, spelled with a Z. store's
// own StartOf is adapters/local/store._start_of, which the ADAPTER uses to
// scope `threads(scope="today")`: a week there is SIX days back and a month
// twenty-nine, and it spells the zone +00:00. Two windows that disagree by a
// day look like a bug and are two functions with two callers; both are
// transcribed rather than reconciled, because reconciling them would change
// what a dashboard counts.
package views

import (
	"fmt"
	"sort"
	"strconv"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/cohort"
	"github.com/eka-care/care_phc_mcp/kstate"
	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/schedule"
	"github.com/eka-care/care_phc_mcp/store"
)

// Reader is the part of the store a view may use. Narrow on purpose: a view
// is a query and may not write, and every method here is already on the Store
// protocol.
type Reader interface {
	kstate.Reader
	Threads(workflow, scope string) ([]store.ThreadRef, error)
	SelectNullable(resource string, thread *string, where store.Query, fields []string, limit int) ([]map[string]any, error)
}

// Bundle is the declarations a view resolves against. Named for the Python's
// Bundle, and carrying only what kernel/views.py actually reads off it.
type Bundle struct {
	// Catalogue is what a calendar's schedules are read from.
	Catalogue  *carephc.Catalogue
	Views      map[string]carephc.View
	Metrics    map[string]carephc.Metric
	Workflow   *carephc.Workflow
	Operations map[string]carephc.Operation
	// Each operation atom as the wire carries it, which is what a summary's
	// `actions` section sends: see kstate.View for why the atoms travel as
	// the compiled JSON rather than as the Go struct.
	Atoms map[string]map[string]any
}

// epoch is kernel/views._EPOCH: how far back "all" reaches.
const epoch = "0001-01-01T00:00:00Z"

// stamp is the one spelling kernel/views.py writes a timestamp in.
const stamp = "2006-01-02T15:04:05Z"

// back is kernel/views._BACK: how far back each window reaches. Weeks and
// months are rolling and not calendar aligned, which is the honest thing to
// compute without a locale.
var back = map[string]time.Duration{
	"day":   24 * time.Hour,
	"week":  7 * 24 * time.Hour,
	"month": 30 * 24 * time.Hour,
}

// WindowStart is kernel/views.window_start. `at` is the clock; a caller with
// no particular moment in mind passes time.Now().UTC().
func WindowStart(window string, at time.Time) (string, error) {
	at = at.UTC()
	if window == "all" {
		return epoch, nil
	}
	if window == "day" {
		return time.Date(at.Year(), at.Month(), at.Day(), 0, 0, 0, 0, time.UTC).
			Format(stamp), nil
	}
	span, declared := back[window]
	if !declared {
		// The Python raises KeyError here, which FastAPI turns into a 500.
		// Named rather than defaulted: a window nobody declared is a
		// declaration error and must not quietly read as "all time".
		return "", fmt.Errorf("unknown metric window '%s'", window)
	}
	return at.Add(-span).Format(stamp), nil
}

// bind is kernel/views._bind: replace the literal window.start in a query's
// conditions. Only inside a mapping, exactly as the Python does, so a plain
// equality against the string "window.start" is left alone.
func bind(q carephc.StateQuery, start string) carephc.StateQuery {
	where := map[string]any{}
	for field, cond := range q.Where {
		if inner, nested := cond.(map[string]any); nested {
			bound := map[string]any{}
			for op, v := range inner {
				if text, isText := v.(string); isText && text == "window.start" {
					bound[op] = start
				} else {
					bound[op] = v
				}
			}
			where[field] = bound
			continue
		}
		where[field] = cond
	}
	return carephc.StateQuery{Resource: q.Resource, Where: where}
}

func count(s Reader, q carephc.StateQuery) (int, error) {
	// Bound for the same reason kstate.count binds: a declared `where` may
	// name `now`, and an adapter must never learn what that means.
	where, err := kstate.Query(kstate.Bind(q.Where, time.Time{}))
	if err != nil {
		return 0, err
	}
	// thread=None: a metric is about the facility and not about one visit.
	return s.Count(q.Resource, nil, where)
}

// MetricValue is kernel/contracts.MetricValue, in the Python's own field
// order. Denominator is a pointer because a plain count declares none and
// None goes on the wire as null.
type MetricValue struct {
	Metric string `json:"metric"`
	// A float even when the count is whole, because kernel/views.py's
	// round(value, 2) is one. pyval.Float keeps the Python spelling, so 24
	// goes on the wire as 24.0 in both engines.
	Value       pyval.Float `json:"value"`
	Numerator   int         `json:"numerator"`
	Denominator *int        `json:"denominator"`
	Unit        string      `json:"unit"`
	Window      string      `json:"window"`
	WindowStart string      `json:"window_start"`
}

// round2 is Python's round(value, 2).
//
// Spelled through the decimal rendering rather than as math.Round(v*100)/100,
// because the multiply introduces its own error: Python rounds the DECIMAL
// value of the double, and so does strconv with 'f'. The one case where the
// two can still differ is an exact tie at the third decimal place, which
// Python breaks to even and Go breaks away from zero. No value either engine
// computes here reaches one, and the differential check would show it if one
// did, which is why this is noted rather than worked around.
func round2(value float64) float64 {
	rounded, err := strconv.ParseFloat(strconv.FormatFloat(value, 'f', 2, 64), 64)
	if err != nil {
		return value
	}
	return rounded
}

// Metric is kernel/views.metric: one MetricValue.
//
// A zero denominator is 0, not an error: an empty week is a normal week at a
// primary health centre.
func Metric(s Reader, m carephc.Metric, window string, at time.Time) (MetricValue, error) {
	if window == "" {
		window = m.Window
	}
	start, err := WindowStart(window, at)
	if err != nil {
		return MetricValue{}, err
	}
	num, err := count(s, bind(m.Numerator, start))
	if err != nil {
		return MetricValue{}, err
	}
	var den *int
	if m.Denominator != nil {
		n, err := count(s, bind(*m.Denominator, start))
		if err != nil {
			return MetricValue{}, err
		}
		den = &n
	}
	var value float64
	switch {
	case m.Unit == "count":
		value = float64(num)
	case den == nil || *den == 0:
		// `elif not den` in the Python: None and 0 are the same answer here.
		value = 0
	case m.Unit == "percent":
		value = float64(num) / float64(*den) * 100
	default:
		value = float64(num) / float64(*den)
	}
	return MetricValue{Metric: m.ID, Value: pyval.Float(round2(value)), Numerator: num,
		Denominator: den, Unit: m.Unit, Window: window, WindowStart: start}, nil
}

// QueueRow is kernel/contracts.QueueRow. EnteredAt is declared and never
// filled, exactly as the Python declares it: when a row entered its current
// station is a value the store does not track yet, and a renderer reads
// `entered_at ?? opened_at`.
type QueueRow struct {
	Thread    string            `json:"thread"`
	Subject   map[string]any    `json:"subject"`
	Station   any               `json:"station"`
	Flags     []string          `json:"flags"`
	Badges    map[string]string `json:"badges"`
	OpenedAt  string            `json:"opened_at"`
	EnteredAt any               `json:"entered_at"`
}

// Group is one entry of ViewResult.groups: {key, count}, with a null key for
// the trailing group of threads that have finished the line.
type Group struct {
	Key   any `json:"key"`
	Count int `json:"count"`
}

func queue(b Bundle, view carephc.View, s Reader) ([]QueueRow, []Group, error) {
	wf := b.Workflow
	refs, err := s.Threads(view.Workflow, view.Scope)
	if err != nil {
		return nil, nil, err
	}
	rows := make([]QueueRow, 0, len(refs))
	for _, ref := range refs {
		known, err := kstate.Flags(s, ref.ID, wf, time.Time{})
		if err != nil {
			return nil, nil, err
		}
		subject := map[string]any{}
		for _, column := range view.Columns {
			// A column the subject does not carry is null and not absent:
			// `ref.subject.get(k)` in the Python, so a thread with no patient
			// row still answers every declared column.
			subject[column] = ref.Subject[column]
		}
		badges := map[string]string{}
		for flag, style := range view.Badges {
			if known[flag] {
				badges[flag] = style
			}
		}
		rows = append(rows, QueueRow{
			Thread: ref.ID, Subject: subject,
			Station: nullIfEmpty(kstate.Station(wf, known)),
			Flags:   sortedKeys(known), Badges: badges, OpenedAt: ref.OpenedAt,
		})
	}

	groups := []Group{}
	switch {
	case view.GroupBy == "station":
		// In line order, with a trailing group for a finished thread. A
		// station two steps name appears twice, which is the Python's own
		// behaviour: it walks the steps, not the distinct stations.
		for _, step := range wf.Steps {
			n := 0
			for _, r := range rows {
				if at, _ := r.Station.(string); at == step.Station {
					n++
				}
			}
			groups = append(groups, Group{Key: step.Station, Count: n})
		}
		done := 0
		for _, r := range rows {
			if r.Station == nil {
				done++
			}
		}
		groups = append(groups, Group{Key: nil, Count: done})
	case view.GroupBy != "":
		held := 0
		for _, r := range rows {
			for _, flag := range r.Flags {
				if flag == view.GroupBy {
					held++
					break
				}
			}
		}
		groups = []Group{{Key: view.GroupBy, Count: held},
			{Key: "not " + view.GroupBy, Count: len(rows) - held}}
	}
	return rows, groups, nil
}

// TaskRow is kernel/contracts.TaskRow: a title, a count, the matching
// threads, and the verb if the declaration named one.
type TaskRow struct {
	Title     string   `json:"title"`
	Count     int      `json:"count"`
	Threads   []string `json:"threads"`
	Operation any      `json:"operation"`
}

// tasklist is kernel/views._tasklist: a row per declared task.
//
// Cross thread by construction, unlike a queue or a summary: each task walks
// every thread this workflow has today and tests a predicate over its flags,
// not the flags of one thread the caller already opened. Reads only flags,
// which is exactly what a queue row reads for its badges, so no Store method
// exists here that every adapter does not already serve.
func tasklist(b Bundle, view carephc.View, s Reader) ([]TaskRow, error) {
	wf := b.Workflow
	refs, err := s.Threads(view.Workflow, view.Scope)
	if err != nil {
		return nil, err
	}
	knownByThread := map[string]map[string]bool{}
	for _, ref := range refs {
		known, err := kstate.Flags(s, ref.ID, wf, time.Time{})
		if err != nil {
			return nil, err
		}
		knownByThread[ref.ID] = known
	}
	rows := make([]TaskRow, 0, len(view.Tasks))
	for _, task := range view.Tasks {
		want := carephc.AsList(task.Where["flag"])
		avoid := carephc.AsList(task.Where["not"])
		matches := []string{}
		for tid, known := range knownByThread {
			held := true
			for _, flag := range want {
				if !known[flag] {
					held = false
					break
				}
			}
			if !held {
				continue
			}
			for _, flag := range avoid {
				if known[flag] {
					held = false
					break
				}
			}
			if held {
				matches = append(matches, tid)
			}
		}
		sort.Strings(matches)
		var op any
		if task.Operation != nil {
			op = *task.Operation
		}
		rows = append(rows, TaskRow{Title: task.Title, Count: len(matches),
			Threads: matches, Operation: op})
	}
	return rows, nil
}

// SummaryBlock is one resolved section of a summary view.
//
// `fields` travels with the rows. The declaration already narrows which
// columns a row carries, but not which of them a screen leads with, and the
// renderer was choosing that for itself from a list of six field names it had
// typed out. Sending the declared order makes that the bundle's decision,
// which is what the view atom was for.
type SummaryBlock struct {
	Title    string   `json:"title"`
	Resource any      `json:"resource"`
	Fields   []string `json:"fields"`
	Rows     any      `json:"rows"`
}

func summary(b Bundle, view carephc.View, s Reader, thread string,
	caps map[string]bool) ([]SummaryBlock, error) {
	wf := b.Workflow
	known, err := kstate.Flags(s, thread, wf, time.Time{})
	if err != nil {
		return nil, err
	}
	out := make([]SummaryBlock, 0, len(view.Sections))
	for _, section := range view.Sections {
		var rows any
		switch {
		case section.Resource != nil:
			where, err := kstate.Query(kstate.Bind(section.Where, time.Time{}))
			if err != nil {
				return nil, err
			}
			// SelectNullable and not Select: this goes on the wire, and the
			// Python's select() answers None for an unfilled column while a
			// flattened read answers "". A renderer drawing an empty cell
			// sees the difference.
			found, err := s.SelectNullable(*section.Resource, &thread, where,
				section.Fields, 50)
			if err != nil {
				return nil, err
			}
			rows = found
		case section.Show == "line":
			rows = kstate.Line(wf, known)
		case section.Show == "flags":
			rows = sortedKeys(known)
		case section.Show == "actions":
			drawn := kstate.Actions(wf, b.Operations, known, caps, "", false, "", false, nil)
			atoms := make([]map[string]any, 0, len(drawn))
			for _, op := range drawn {
				atoms = append(atoms, b.Atoms[op.ID])
			}
			rows = atoms
		case section.Show == "proposals":
			found, err := s.Proposals(thread, "pending")
			if err != nil {
				return nil, err
			}
			rows = found
		case section.Show == "audit":
			found, err := s.Audit(thread)
			if err != nil {
				return nil, err
			}
			rows = found
		default:
			return nil, fmt.Errorf("unknown section show '%s'", section.Show)
		}
		fields := section.Fields
		if fields == nil {
			fields = []string{}
		}
		out = append(out, SummaryBlock{Title: section.Title,
			Resource: nullIfNil(section.Resource), Fields: fields, Rows: rows})
	}
	return out, nil
}

// covers is kernel/views._covers: whether a contact is owed on this day. A
// missed contact stays owed on every day after its window shuts, so its On
// list alone is not the answer; one rule serves both the day's rows and the
// month's counts, so they cannot disagree.
func covers(e cohort.Entry, iso string) bool {
	for _, d := range e.On {
		if d == iso {
			return true
		}
	}
	return e.State == schedule.Missed && e.Closes < iso
}

// MaxRangeDays is kernel/views.MAX_RANGE_DAYS.
const MaxRangeDays = 400

// parseDay is kernel/views._day: a calendar day is exactly YYYY-MM-DD. A
// timestamp would raise a timezone question the route cannot answer. One
// sentence for every refusal, naming the parameter that was wrong.
func parseDay(text, name string) (time.Time, error) {
	parsed, err := time.Parse("2006-01-02", text)
	// Year 0000 parses here and is refused by Python's date (MINYEAR 1).
	if err != nil || len(text) != 10 || parsed.Year() < 1 {
		return time.Time{}, Declared{Reason: name + " must be a real calendar day written YYYY-MM-DD, not " + pyval.Repr(text)}
	}
	return parsed, nil
}

// span is kernel/views._span: the days a range names, or ok=false when none
// was given. One sentence per refusal, written here once.
func span(on, since, until *string) (first, last time.Time, ok bool, err error) {
	if since == nil && until == nil {
		return first, last, false, nil
	}
	if on != nil {
		return first, last, false, Declared{Reason: "on and from/to answer different questions and must not be combined"}
	}
	if since == nil || until == nil {
		return first, last, false, Declared{Reason: "from and to go together: give both or neither"}
	}
	if first, err = parseDay(*since, "from"); err != nil {
		return first, last, false, err
	}
	if last, err = parseDay(*until, "to"); err != nil {
		return first, last, false, err
	}
	if first.After(last) {
		return first, last, false, Declared{Reason: "from must not be after to"}
	}
	if int(last.Sub(first).Hours()/24)+1 > MaxRangeDays {
		return first, last, false, Declared{Reason: fmt.Sprintf("a range may span at most %d days", MaxRangeDays)}
	}
	return first, last, true, nil
}

// calendar is kernel/views._calendar. Two different questions, answered by two
// different rules on purpose.
//
// `on` asks "what is owed on this day": selected by window (covers), the day's
// rows and the month's counts alike.
//
// A range asks "what falls due in this span": selected by due date, and a grid
// draws a visit once, on its due day. Rows and per-day counts both come from
// the one cell function, so they cannot disagree. Do not tidy one into the
// other.
func calendar(b Bundle, view carephc.View, s Reader, on, since, until *string,
	at time.Time) ([]cohort.Entry, []Group, error) {
	now := at.UTC()
	first, last, ranged, err := span(on, since, until)
	if err != nil {
		return nil, nil, err
	}
	if ranged {
		owed, err := cohort.Owed(b.Catalogue, s, b.Workflow, view.Episodes, first, last, at)
		if err != nil {
			return nil, nil, err
		}
		// A missed contact due before the range is a marker on today
		// instead, when today is in the range; if it is not, it has no cell
		// and is left out.
		lo, hi, today := first.Format("2006-01-02"), last.Format("2006-01-02"), now.Format("2006-01-02")
		marker := today >= lo && today <= hi
		cell := func(e cohort.Entry) string {
			if e.Due >= lo && e.Due <= hi {
				return e.Due
			}
			if e.State == schedule.Missed && marker {
				return today
			}
			return ""
		}
		rows := []cohort.Entry{}
		for _, e := range owed {
			if cell(e) != "" {
				rows = append(rows, e)
			}
		}
		groups := []Group{}
		for d := first; !d.After(last); d = d.AddDate(0, 0, 1) {
			iso, n := d.Format("2006-01-02"), 0
			for _, e := range rows {
				if cell(e) == iso {
					n++
				}
			}
			groups = append(groups, Group{Key: iso, Count: n})
		}
		return rows, groups, nil
	}
	day := now.Truncate(24 * time.Hour)
	if on != nil {
		if day, err = parseDay(*on, "on"); err != nil {
			return nil, nil, err
		}
	}
	first = time.Date(day.Year(), day.Month(), 1, 0, 0, 0, 0, time.UTC)
	last = first.AddDate(0, 1, -1)
	owed, err := cohort.Owed(b.Catalogue, s, b.Workflow, view.Episodes, first, last, at)
	if err != nil {
		return nil, nil, err
	}
	rows := []cohort.Entry{}
	for _, e := range owed {
		if covers(e, day.Format("2006-01-02")) {
			rows = append(rows, e)
		}
	}
	groups := []Group{}
	for d := first; !d.After(last); d = d.AddDate(0, 0, 1) {
		iso, n := d.Format("2006-01-02"), 0
		for _, e := range owed {
			if covers(e, iso) {
				n++
			}
		}
		groups = append(groups, Group{Key: iso, Count: n})
	}
	return rows, groups, nil
}

// ViewResult is kernel/contracts.ViewResult, in the Python's own field order.
type ViewResult struct {
	View        string  `json:"view"`
	Kind        string  `json:"kind"`
	Rows        any     `json:"rows"`
	GeneratedAt string  `json:"generated_at"`
	Groups      []Group `json:"groups"`
}

// Declared is kernel/views.resolve's `ValueError`: a failure a caller turns
// into a 400 rather than a 500. api/main.py catches ValueError around
// resolve() and nothing else, so this type is what that catch becomes.
type Declared struct{ Reason string }

func (e Declared) Error() string { return e.Reason }

// Resolve evaluates one view. `thread` is required for a summary and ignored
// otherwise. `caps` is the caller's; the capability to OPEN the view is the
// caller's check, at the route, not here. `on` is the day a calendar answers
// for (ISO date; today when nil) and is ignored otherwise. `since` and `until`
// are a range of days instead: both or neither, never with `on`.
func Resolve(b Bundle, viewID string, s Reader, thread *string,
	caps map[string]bool, at time.Time, on, since, until *string) (*ViewResult, error) {
	view, declared := b.Views[viewID]
	if !declared {
		return nil, Declared{Reason: fmt.Sprintf("unknown view '%s'", viewID)}
	}
	generatedAt := at.UTC().Format(stamp)
	result := &ViewResult{View: viewID, Kind: view.Kind, GeneratedAt: generatedAt,
		Groups: []Group{}}

	switch view.Kind {
	case "queue":
		rows, groups, err := queue(b, view, s)
		if err != nil {
			return nil, err
		}
		result.Rows, result.Groups = rows, groups
	case "summary":
		if thread == nil {
			return nil, Declared{Reason: viewID + " is a summary and needs ?thread="}
		}
		rows, err := summary(b, view, s, *thread, caps)
		if err != nil {
			return nil, err
		}
		result.Rows = rows
	case "dashboard":
		rows := make([]MetricValue, 0, len(view.Metrics))
		for _, mid := range view.Metrics {
			m, named := b.Metrics[mid]
			if !named {
				// The Python's KeyError, named. A dashboard naming a metric
				// no bundle declares is already refused by the lint, so this
				// is the belt the lint is the braces for.
				return nil, fmt.Errorf("unknown metric '%s'", mid)
			}
			// The VIEW's window wins over each metric's own, which is the
			// whole reason resolve() passes one at all: a dashboard that
			// read each metric's declared window would answer a week and a
			// day side by side on one screen headed "today".
			value, err := Metric(s, m, view.Window, at)
			if err != nil {
				return nil, err
			}
			rows = append(rows, value)
		}
		result.Rows = rows
	case "tasklist":
		rows, err := tasklist(b, view, s)
		if err != nil {
			return nil, err
		}
		result.Rows = rows
	case "calendar":
		rows, groups, err := calendar(b, view, s, on, since, until, at)
		if err != nil {
			return nil, err
		}
		result.Rows, result.Groups = rows, groups
	default:
		return nil, Declared{Reason: fmt.Sprintf("unknown view kind '%s'", view.Kind)}
	}
	return result, nil
}

func sortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for key := range set {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func nullIfNil(s *string) any {
	if s == nil {
		return nil
	}
	return *s
}
