package cohort

import (
	"testing"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/store"
)

var lmp = time.Date(2026, 1, 5, 0, 0, 0, 0, time.UTC)

func day(offset int) time.Time { return lmp.AddDate(0, 0, offset) }

func iso(t time.Time) string { return t.Format("2006-01-02") }

func noon(t time.Time) time.Time { return t.Add(12 * time.Hour) }

type rig struct {
	t     *testing.T
	cat   *carephc.Catalogue
	store *store.SQLite
}

func centre(t *testing.T) *rig {
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
	for _, p := range [][2]string{{"p-amina", "Amina Sheikh"}, {"p-bilal", "Bilal Khan"}} {
		if _, err := s.Write("patient", map[string]any{"id": p[0], "name": p[1], "age": "30"}, "t-"+p[0]); err != nil {
			t.Fatal(err)
		}
	}
	return &rig{t: t, cat: cat, store: s}
}

func (r *rig) episode(id, patient, kind, status, when string, anchored bool, outcome string) {
	r.t.Helper()
	var anchor, basis any
	if anchored {
		anchor, basis = iso(lmp), "last_menstrual_period"
	}
	_, err := r.store.DB().Exec(
		"INSERT INTO episode_of_care (id, patient, type, status, anchor_date, anchor_basis,"+
			" outcome, created_date) VALUES (?,?,?,?,?,?,?,?)",
		id, patient, kind, status, anchor, basis, outcome, when)
	if err != nil {
		r.t.Fatal(err)
	}
}

func (r *rig) owed(since, until, at time.Time, types ...string) []Entry {
	r.t.Helper()
	if len(types) == 0 {
		types = []string{"pregnancy"}
	}
	got, err := Owed(r.cat, r.store, r.cat.Workflow, types, since, until, noon(at))
	if err != nil {
		r.t.Fatal(err)
	}
	return got
}

func (r *rig) contact(id string) carephc.Contact {
	for _, c := range r.cat.Schedules["phc.sched.antenatal"].Contacts {
		if c.ID == id {
			return c
		}
	}
	r.t.Fatalf("no contact %s", id)
	return carephc.Contact{}
}

const opened = "2026-02-01T09:00:00+00:00"

func TestAnOpenPregnancyOwesItsContactsToTheWindow(t *testing.T) {
	r := centre(t)
	r.episode("ep-1", "p-amina", "pregnancy", "active", opened, true, "")
	d := day(r.contact("anc1").Due)
	rows := r.owed(d, d, d)
	if len(rows) != 1 || rows[0].Contact.Contact != "anc1" {
		t.Fatalf("got %+v", rows)
	}
	row := rows[0]
	if row.Subject != "p-amina" || row.SubjectRow["name"] != "Amina Sheikh" {
		t.Fatalf("subject: %+v", row)
	}
	if len(row.On) != 1 || row.On[0] != iso(d) || row.State != "due" || row.Episode != "ep-1" {
		t.Fatalf("got %+v", row)
	}
}

func TestAnEndedPregnancyOwesNothingToAnyDay(t *testing.T) {
	r := centre(t)
	r.episode("ep-1", "p-amina", "pregnancy", "active", opened, true, "")
	r.episode("ep-2", "p-amina", "pregnancy", "ended", "2026-03-01T09:00:00+00:00", false, "miscarriage")
	for _, w := range [][3]int{{0, 300, 100}, {150, 160, 155}, {400, 500, 450}} {
		if got := r.owed(day(w[0]), day(w[1]), day(w[2])); len(got) != 0 {
			t.Fatalf("window %v: %+v", w, got)
		}
	}
	// Same instant for both rows: the opening still wins the tie. A second
	// patient, because ":memory:" is one database shared by every rig.
	r.episode("ep-s1", "p-bilal", "pregnancy", "active", opened, true, "")
	r.episode("ep-s2", "p-bilal", "pregnancy", "ended", opened, false, "live_birth")
	if got := r.owed(day(0), day(300), day(100)); len(got) != 0 {
		t.Fatalf("a delivery in one commit still reads as pregnant: %+v", got)
	}
}

func TestAMiscarriageOwesNoHomeVisitToAnyDay(t *testing.T) {
	r := centre(t)
	r.episode("ep-1", "p-amina", "pregnancy", "active", opened, true, "")
	r.episode("ep-2", "p-amina", "pregnancy", "ended", "2026-03-01T09:00:00+00:00", false, "miscarriage")
	if got := r.owed(day(0), day(400), day(60), "pregnancy", "postnatal"); len(got) != 0 {
		t.Fatalf("%+v", got)
	}
}

func TestAContactCoversEveryDayOfItsWindowAndNoOther(t *testing.T) {
	r := centre(t)
	r.episode("ep-1", "p-amina", "pregnancy", "active", opened, true, "")
	opens := r.contact("anc2").Opens
	only := func(rows []Entry) (found []Entry) {
		for _, row := range rows {
			if row.Contact.Contact == "anc2" {
				found = append(found, row)
			}
		}
		return
	}
	rows := only(r.owed(day(opens-10), day(opens+2), day(opens)))
	if len(rows) != 1 || len(rows[0].On) != 3 {
		t.Fatalf("%+v", rows)
	}
	for n, d := range rows[0].On {
		if d != iso(day(opens+n)) {
			t.Fatalf("day %d is %s", n, d)
		}
	}
	if got := only(r.owed(day(opens-5), day(opens-1), day(opens-1))); len(got) != 0 {
		t.Fatalf("%+v", got)
	}
}
