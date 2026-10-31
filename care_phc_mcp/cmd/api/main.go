// care_phc_api is the Go backend: the kernel with a socket on it.
//
// api/main.py is the contract. Every shape this serves was read off a running
// Python kernel and matched field for field, and where the Python does
// something that looks wrong it is copied rather than fixed
// (docs/superpowers/plans/2026-10-31-go-backend-port.md, "Behaviour is
// copied, not reinterpreted").
//
// WHAT THIS SERVES TODAY, which is slices G1 to G4 of nine
// --------------------------------------------------------
//
//	GET /                       the service, the bundle, and its own routes
//	GET /api/v1/phc/whoami      what the MCP server builds its tool list from
//	GET /api/v1/phc/facility    the bundle, the shape, and what it withholds
//	GET /api/v1/phc/catalogue   the compiled catalogue, the loaded bundle's
//	GET /api/v1/phc/questionnaires   every form this bundle's operations ask
//	GET /api/v1/phc/valuesets/{slug} one bound choice, expanded
//	GET /api/v1/phc/queue            the declared queue, and the seeded day
//	GET /api/v1/phc/views/{id}        a queue, a summary, a dashboard, a tasklist
//	GET /api/v1/phc/subjects/{id}     the spine: one subject, every visit
//	GET /api/v1/phc/patients/search   the local register; see package directory
//	GET /api/v1/phc/patients/pending  the rows no registry has seen
//	the write path                   POST /threads, commit, propose, confirm,
//	                                 reject, and GET a thread or a proposal
//
// Everything else in api/main.py answers 501 with the slice that will serve
// it. Not 404: a route this engine has not reached yet and a route that does
// not exist are different facts, and a check driving the Go backend should be
// able to tell them apart without reading this file.
//
// THERE IS NO AUTHENTICATION AND THIS DOES NOT INVENT ONE
// -------------------------------------------------------
// api/main.py's caller() reads X-PHC-Role and X-PHC-Actor from the request,
// or ?role=, and falls back to a `demo` account that holds every capability
// the bundle declares, facility.admin included. The header is carried here
// unchanged and the gap is named rather than filled: who a caller is, and
// whether a header may say so, is the owner's decision and not an agent's.
//
// WHAT IT CANNOT DO YET, said here rather than discovered
// -------------------------------------------------------
// One bundle: the one catalogue.json was compiled with. The embedded file
// carries every bundle's operation atoms but only the LOADED bundle's
// manifest, views, plugins and vocabulary, because that is what
// kernel/declarations.compile_json emits. So PHC_BUNDLE naming anything else
// is refused at startup by name rather than served wrongly.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/proposals"
	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/store"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// The two prefixes api/main.py mounts the one router under: /api is what the
// renderer calls and /api/v1/phc is what the MCP server calls, and those paths
// do not move.
var prefixes = []string{"/api", "/api/v1/phc"}

// DemoRole is api/main.py's DEMO_ROLE: the account this kernel hands out with
// no login at all. It holds every declared capability, which is safe only
// because there is no authentication yet.
const DemoRole = "demo"

type kernel struct {
	cat *carephc.Catalogue

	bundle   string
	facility string            // the shape this process runs, or ""
	withheld map[string]string // capability -> the plugin id withholding it
	without  map[string]string // plugin id -> its declared title
	roles    map[string][]string
	caps     []string // every capability this bundle declares, sorted
	workflow string
	routes   []string

	store *store.SQLite

	// The loaded bundle's operations, which is narrower than the embedded
	// catalogue-wide set, and the write path over them.
	operations map[string]carephc.Operation
	write      *proposals.Bundle
}

// ---------------------------------------------------------------------------
// the facility's shape: kernel/plugins.py, in Go
// ---------------------------------------------------------------------------
//
// A transcription, not a reinterpretation. A plugin that is off is a
// capability the caller does not hold, subtracted once before anything reads
// it, and that subtraction is the whole of a facility's runtime effect.

// chosen is kernel/plugins.chosen: the argument wins over PHC_FACILITY, which
// wins over the bundle's own default. A bundle declaring no facilities has one
// shape and no choice to make, which is what keeps bundles/lab valid.
func chosen(cat *carephc.Catalogue, want string) string {
	if len(cat.Facilities.Declared) == 0 {
		return ""
	}
	if want != "" {
		return want
	}
	if env := os.Getenv("PHC_FACILITY"); env != "" {
		return env
	}
	return cat.Facilities.Default
}

// off is kernel/plugins.off: the plugin ids this facility does not run, in
// declaration order, and only those the bundle actually declares.
func off(cat *carephc.Catalogue, facility string) []string {
	var out []string
	for _, pid := range cat.Facilities.Declared[facility].Without {
		if _, declared := cat.Plugins[pid]; declared {
			out = append(out, pid)
		}
	}
	return out
}

// withheldBy is kernel/plugins.withheld: {capability: the plugin id that
// withholds it}. The guard reads it to name a denial and effective() reads it
// to subtract. There is no second form.
func withheldBy(cat *carephc.Catalogue, facility string) map[string]string {
	out := map[string]string{}
	for _, pid := range off(cat, facility) {
		for _, cap := range cat.Plugins[pid].Capabilities {
			out[cap] = pid
		}
	}
	return out
}

// absent is kernel/plugins.absent: {plugin id: its declared title}. The same
// fact read from the other end, and it exists separately because a screen has
// to be able to SAY it without typing a plugin's name at a clinician.
func absent(cat *carephc.Catalogue, facility string) map[string]string {
	out := map[string]string{}
	for _, pid := range off(cat, facility) {
		title := cat.Plugins[pid].Title
		if title == "" {
			title = pid
		}
		out[pid] = title
	}
	return out
}

// effective is kernel/plugins.effective: caps minus what this facility
// withholds, order preserved. One function, called once, in caller().
func effective(caps []string, held map[string]string) []string {
	out := make([]string, 0, len(caps))
	for _, cap := range caps {
		if _, gone := held[cap]; !gone {
			out = append(out, cap)
		}
	}
	return out
}

// ---------------------------------------------------------------------------
// who is asking
// ---------------------------------------------------------------------------

type user struct {
	ID           string   `json:"id"`
	Role         string   `json:"role"`
	Capabilities []string `json:"capabilities"`
	Scopes       []string `json:"scopes"`
}

// caller is api/main.py's caller(), including its own admission that there is
// no authentication tonight. The role comes from a header or a query
// parameter and the service is meant for localhost.
//
// Returns the role name it refused, when it refused one, so the route can
// answer 400 with the same message the Python does.
func (k *kernel) caller(r *http.Request) (user, string) {
	role := r.Header.Get("X-PHC-Role")
	if role == "" {
		role = r.URL.Query().Get("role")
	}
	if role == "" {
		role = DemoRole
	}
	declared, known := k.roles[role]
	if !known {
		return user{}, role
	}
	// The one subtraction, here, before anything reads the set: the guard,
	// visible(), the quick action row, /whoami and therefore the MCP tool
	// list, and every view's own capability gate.
	caps := effective(declared, k.withheld)
	actor := r.Header.Get("X-PHC-Actor")
	if actor == "" {
		actor = "user:" + role
	}
	scopes := append([]string(nil), caps...)
	sort.Strings(scopes)
	return user{ID: actor, Role: role, Capabilities: caps, Scopes: scopes}, ""
}

// ---------------------------------------------------------------------------
// the routes
// ---------------------------------------------------------------------------

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("care-phc: could not write a response: %v", err)
	}
}

// detail is FastAPI's HTTPException shape, which every caller in this
// repository already reads: {"detail": "..."}.
func detail(w http.ResponseWriter, status int, format string, a ...any) {
	writeJSON(w, status, map[string]any{"detail": fmt.Sprintf(format, a...)})
}

func (k *kernel) index(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"service": "care-phc kernel",
		"bundle":  k.cat.Manifest.ID,
		"routes":  k.routes,
	})
}

// whoami is what the MCP server reads to build its tool list. api/main.py's
// own docstring says the shape is frozen, so it is one key.
func (k *kernel) whoami(w http.ResponseWriter, r *http.Request) {
	who, refused := k.caller(r)
	if refused != "" {
		detail(w, http.StatusBadRequest, "no such role %q", refused)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"capabilities": who.Capabilities})
}

type viewOut struct {
	ID         string `json:"id"`
	Kind       string `json:"kind"`
	Title      string `json:"title"`
	Capability string `json:"capability"`
}

// facility is the bundle this kernel loaded, its views, and who the caller is.
//
// `capabilities` is the WHOLE of what the bundle declares and stays whole: a
// facility declines a capability, it does not delete one from the bundle,
// which is what would make a shape a fork. The caller's own narrowed set is in
// `user`, and `withheld` and `without` say why it is narrower.
func (k *kernel) facility_(w http.ResponseWriter, r *http.Request) {
	who, refused := k.caller(r)
	if refused != "" {
		detail(w, http.StatusBadRequest, "no such role %q", refused)
		return
	}

	// asdict(BUNDLE.manifest) with workflow=WORKFLOW.id added. Built by
	// re-marshalling the embedded manifest rather than by listing its fields,
	// so a field added to kernel/contracts.Manifest arrives here without
	// being retyped.
	bundle := map[string]any{}
	if err := json.Unmarshal(k.cat.ManifestRaw, &bundle); err != nil {
		detail(w, http.StatusInternalServerError, "the embedded manifest is not an object: %v", err)
		return
	}
	bundle["workflow"] = k.workflow

	views := make([]viewOut, 0, len(k.cat.Views))
	for _, v := range k.cat.Views {
		views = append(views, viewOut{ID: v.ID, Kind: v.Kind, Title: v.Title, Capability: v.Capability})
	}
	// BUNDLE.views is built from sorted(bundle dir glob), and a declaration's
	// filename is its id, so the Python's order is by id. Go maps have none.
	sort.Slice(views, func(i, j int) bool { return views[i].ID < views[j].ID })

	roles := make([]string, 0, len(k.roles))
	for role := range k.roles {
		roles = append(roles, role)
	}
	sort.Strings(roles)

	writeJSON(w, http.StatusOK, map[string]any{
		"bundle":       bundle,
		"facility":     nullIfEmpty(k.facility),
		"withheld":     k.withheld,
		"without":      k.without,
		"capabilities": k.caps,
		"views":        views,
		"roles":        roles,
		"user":         who,
	})
}

// notYet answers a route api/main.py serves and this engine does not.
//
// 501 and not 404 on purpose: a check driving the Go backend has to be able to
// tell "this engine has not reached that route" from "no such route", and the
// slice named in the message is where it is coming from.
func notYet(slice string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		detail(w, http.StatusNotImplemented,
			"the Go backend does not serve %s yet: %s. Run this check with "+
				"PHC_BACKEND=python, which is the default.", r.URL.Path, slice)
	}
}

// eitherSpelling is api/main.py's middleware of the same name. ROUTES in
// kernel/contracts.py spells every path with a trailing slash and the handlers
// are registered without one; rather than pick a winner and break one of the
// two clients, both spellings reach the same handler.
//
// Without it the trailing slash form is a redirect, which costs the browser a
// second CORS preflight per write and makes a plain curl return nothing at all
// unless the caller remembered -L.
func eitherSpelling(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// CORS, as api/main.py's CORSMiddleware allows it: any origin, any
		// method, any header. That is a localhost service with no
		// authentication, and it is the Python's choice being carried rather
		// than a new one.
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "*")
		w.Header().Set("Access-Control-Allow-Headers", "*")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		if len(r.URL.Path) > 1 && strings.HasSuffix(r.URL.Path, "/") {
			r.URL.Path = strings.TrimRight(r.URL.Path, "/")
		}
		next.ServeHTTP(w, r)
	})
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// ---------------------------------------------------------------------------
// startup
// ---------------------------------------------------------------------------

// served is every path api/main.py mounts under both prefixes, spelled
// exactly as FastAPI's own route table spells it, with the slice that will
// bring it. The three with no slice are the ones this engine serves.
//
// Written out rather than discovered for two reasons. It is what GET /
// answers with, and scripts/check_go_parity.py holds this list against the
// Python's live route table, so a route added to api/main.py and not here
// fails the gate instead of quietly reading as a route the Go serves.
var served = []struct {
	path  string
	slice string
}{
	{"/whoami", ""},
	{"/facility", ""},
	{"/catalogue", ""},
	{"/operations", ""},
	{"/operations/{op_id}/commit", ""},
	{"/operations/{op_id}/propose", ""},
	{"/proposals/{proposal_id}", ""},
	{"/proposals/{proposal_id}/confirm", ""},
	{"/proposals/{proposal_id}/reject", ""},
	{"/roles", "G7 serves a facility's own role combinations"},
	{"/roles/{role}", "G7 serves a facility's own role combinations"},
	{"/threads", ""},
	{"/threads/{thread_id}", ""},
	{"/subjects/{subject_id}", ""},
	{"/questionnaires", ""},
	// The expansion seam is G4's; the ROUTE is G3's, because a bound choice
	// with nothing to choose is an empty dropdown on a form and
	// scripts/check_live.py asks for every value set a question binds to.
	// What G4 still owes is the rest of kernel/terminology.py: the semantic
	// tags, the codification seam and the three binding forms at build time.
	{"/valuesets/{slug}", ""},
	{"/queue", ""},
	{"/views/{view_id}", ""},
	// The guard is served; the planner behind these two is agent/turn.py and
	// is a port of its own. Said as the slice rather than left reading as
	// though G2 had covered it.
	{"/khoj", "the ask-and-search planner behind it is agent/turn.py, not the guard"},
	{"/agent/say", "the ask-and-search planner behind it is agent/turn.py, not the guard; this spelling is deprecated"},
	// The LOCAL half of kernel/directory.py: the register this facility
	// already holds, and the rows no registry has seen. The vendor behind the
	// seam is not here and nothing in Go reads a credential, so a search
	// always answers the kernel's own "the directory could not be asked".
	// That is the designed degraded path and not a stub; see package
	// directory. Publishing is the one verb that sends a person's details OFF
	// this machine, so it waits for a connector rather than being faked.
	{"/patients/search", ""},
	{"/patients/pending", ""},
	{"/patients/publish", "a publish needs a directory to publish TO, and Go has no vendor behind that seam"},
	{"/abha/config", "G1 does not reach ABDM"},
	{"/scribe/templates", "G8 serves the outbox, and the scribe with it"},
	{"/scribe/sessions", "G8 serves the outbox, and the scribe with it"},
	{"/scribe/sessions/{session_id}", "G8 serves the outbox, and the scribe with it"},
	{"/scribe/sessions/{session_id}/extract", "G8 serves the outbox, and the scribe with it"},
	{"/scribe/webhook", "G8 serves the outbox, and the scribe with it"},
}

// literal is the part of a route before its first template segment, which is
// what a Go mux can be given. "/proposals/{proposal_id}/confirm" mounts as a
// subtree at "/proposals", so a path under it answers 501 rather than falling
// through to the root handler and reading as a healthy service that answered
// something else.
func literal(path string) string {
	if i := strings.Index(path, "{"); i >= 0 {
		path = path[:i]
	}
	return strings.TrimRight(path, "/")
}

func (k *kernel) mount() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", k.index)
	for _, prefix := range prefixes {
		// Anything under a prefix that no route below claims is FastAPI's own
		// 404, not the root route. Without this a path the Python 404s fell
		// through to k.index and answered 200 with a healthy-looking service
		// description, which is the worst of the three possible answers.
		mux.Handle(prefix+"/", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			detail(w, http.StatusNotFound, "Not Found")
		}))
		seen := map[string]bool{}
		for _, route := range served {
			if route.slice == "" {
				continue
			}
			at := prefix + literal(route.path)
			if seen[at] {
				continue
			}
			seen[at] = true
			mux.Handle(at, notYet(route.slice))
			mux.Handle(at+"/", notYet(route.slice))
		}
		// Registered last so they win over any subtree above them.
		mux.HandleFunc(prefix+"/whoami", k.whoami)
		mux.HandleFunc(prefix+"/facility", k.facility_)
		// api/main.py puts /catalogue and /operations on one function, and
		// GET is the only method either answers.
		mux.HandleFunc(prefix+"/catalogue", only(http.MethodGet, k.catalogue))
		mux.HandleFunc(prefix+"/operations", only(http.MethodGet, k.catalogue))
		mux.HandleFunc(prefix+"/questionnaires", only(http.MethodGet, k.questionnaires))
		mux.HandleFunc(prefix+"/valuesets/{slug}", only(http.MethodGet, k.valueset))
		mux.HandleFunc(prefix+"/queue", only(http.MethodGet, k.queue))
		mux.HandleFunc(prefix+"/views/{view_id}", only(http.MethodGet, k.view))
		mux.HandleFunc(prefix+"/subjects/{subject_id}", only(http.MethodGet, k.subject))
		mux.HandleFunc(prefix+"/patients/search", only(http.MethodGet, k.patientSearch))
		mux.HandleFunc(prefix+"/patients/pending", only(http.MethodGet, k.patientPending))
		k.mountGuard(mux, prefix)
	}
	return eitherSpelling(mux)
}

func main() {
	host := flag.String("host", "127.0.0.1", "the interface to bind")
	port := flag.Int("port", 8000, "the port to bind")
	flag.Parse()

	cat, err := carephc.Load()
	if err != nil {
		log.Fatal(err)
	}

	// One bundle: the one catalogue.json was compiled with. Refused by name
	// rather than served wrongly, because serving a laboratory's threads out
	// of a health centre's manifest is the kind of wrong that reads as
	// working.
	want := os.Getenv("PHC_BUNDLE")
	if want == "" {
		want = cat.Manifest.ID
	}
	if want != cat.Manifest.ID {
		log.Fatalf("PHC_BUNDLE=%q, and the embedded catalogue was compiled for "+
			"%q. Recompile it with PHC_BUNDLE=%s python3 -m kernel.declarations, "+
			"or run this check with PHC_BACKEND=python.", want, cat.Manifest.ID, want)
	}
	// The typed workflow, the compiled mapping and each atom's own JSON. Not
	// part of Load, because cmd/mcp builds a tool list and has no business
	// failing on a mapping it will never evaluate.
	if err := cat.LoadDeclarations(); err != nil {
		log.Fatal(err)
	}

	// The declarations the guard reads that do NOT live in catalogue.json:
	// the questionnaires an operation's validator is loaded from, and the
	// offline value sets a coding is checked against. Read from the tree, as
	// the port plan says ("the Go engine reads them; it does not restate
	// them"), relative to PHC_ROOT or the working directory.
	//
	// Loud on failure, and that is guard step 1's fail-closed rule reaching
	// as far back as startup: a kernel that cannot load a questionnaire
	// cannot validate a payload, and a kernel that cannot validate a payload
	// must not serve a write.
	root := os.Getenv("PHC_ROOT")
	if root == "" {
		root = "."
	}
	schemas, err := questionnaire.Load(filepath.Join(root, "questionnaires"))
	if err != nil {
		log.Fatalf("the questionnaires did not load, so no write could be "+
			"validated: %v\n\nSet PHC_ROOT to the repository root, or run from it.", err)
	}
	terms, err := terminology.Load(filepath.Join(root, "terminology"))
	if err != nil {
		log.Fatalf("the value sets did not load, so no coding could be "+
			"checked: %v\n\nSet PHC_ROOT to the repository root, or run from it.", err)
	}

	// PHC_STORE names the seam, and there is one adapter behind it: `local`,
	// the SQLite file. Refused by name for the reason api/main.py refuses it,
	// which is that the seam is the thing of value.
	if which := os.Getenv("PHC_STORE"); which != "" && which != "local" {
		log.Fatalf("PHC_STORE=%q is not an adapter. There is one: local.", which)
	}
	dbPath := os.Getenv("PHC_DB")
	if dbPath == "" {
		dbPath = "phc.sqlite3"
	}
	rows, err := store.Open(dbPath)
	if err != nil {
		log.Fatalf("could not open %s: %v", dbPath, err)
	}
	defer rows.Close()

	k := &kernel{cat: cat, bundle: cat.Manifest.ID, store: rows}
	k.facility = chosen(cat, "")
	k.withheld = withheldBy(cat, k.facility)
	k.without = absent(cat, k.facility)

	// The demo day, seeded on first use so the queue is never an empty
	// screen: api/main.py's make_store(), condition for condition. The rows
	// are the bundle's own (bundles/<id>/seed.yaml) and this facility's
	// shape narrows them, because a thread whose history names an operation
	// nobody here may perform is a lie about what happened here.
	//
	// Loud on failure. A kernel that silently started with no demo day would
	// read as a clinic with nobody in it, which is indistinguishable from a
	// clinic whose records did not load.
	declaredSeed, err := store.LoadSeed(filepath.Join(root, "bundles", cat.Manifest.ID))
	if err != nil {
		log.Fatalf("the seed did not load: %v\n\nSet PHC_ROOT to the repository "+
			"root, or run from it.", err)
	}
	empty, err := rows.IsEmpty()
	if err != nil {
		log.Fatalf("could not read %s: %v", dbPath, err)
	}
	if empty {
		if _, err := store.Seed(rows, seeded(declaredSeed, cat.Operations, k.withheld)); err != nil {
			log.Fatalf("the demo day did not seed: %v", err)
		}
	}
	k.workflow = cat.Workflow.ID
	k.operations = cat.BundleOperations()
	k.write = &proposals.Bundle{
		Catalogue: cat, Operations: k.operations, Workflow: cat.Workflow,
		Schemas: schemas, Terms: terms, Withheld: k.withheld,
	}

	k.caps = append([]string(nil), cat.Vocabulary.Capabilities...)
	sort.Strings(k.caps)
	k.roles = map[string][]string{}
	for role, caps := range cat.Vocabulary.Roles {
		k.roles[role] = append([]string(nil), caps...)
	}
	// api/main.py's own note: demo is deliberately a superuser sandbox and not
	// one more preset, it is the account this kernel hands out with no login
	// at all, and facility.admin sits in no preset on purpose. It is the union
	// over every DECLARED capability, not over the presets, because naming
	// five quietly withheld two and made the lab bundle's own dashboard
	// unreachable from the only account the browser can be.
	k.roles[DemoRole] = append([]string(nil), k.caps...)

	for _, prefix := range prefixes {
		for _, route := range served {
			k.routes = append(k.routes, prefix+route.path)
		}
	}
	k.routes = append(k.routes, "/")
	sort.Strings(k.routes)

	where := fmt.Sprintf("%s:%d", *host, *port)
	shape := k.facility
	if shape == "" {
		shape = "one shape"
	}
	log.Printf("care-phc: bundle %s %s, %s, withholding %d capabilities, on %s",
		cat.Manifest.ID, cat.Manifest.Version, shape, len(k.withheld), where)
	if err := http.ListenAndServe(where, k.mount()); err != nil {
		log.Fatal(err)
	}
}
