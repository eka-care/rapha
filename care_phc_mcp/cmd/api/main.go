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
	"sync"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/planner"
	"github.com/eka-care/care_phc_mcp/plugins"
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

// AdminCapability is api/main.py's own literal: the one capability a role save
// needs. It is typed here for the reason the Python types it here, which is
// that this is the route's own rule rather than a declaration -- it names no
// operation, and neither the guard nor the decision path ever reads it, so on
// its own it unlocks no kernel write path. It sits in NO shipped preset on
// purpose, which is why the demo account is the union over declared
// capabilities rather than over the presets.
const AdminCapability = "facility.admin"

type kernel struct {
	cat *carephc.Catalogue

	bundle   string
	facility string            // the shape this process runs, or ""
	withheld map[string]string // capability -> the plugin id withholding it
	without  map[string]string // plugin id -> its declared title
	roles    map[string][]string
	caps     []string // every capability this bundle declares, sorted

	// A facility's own role combinations, saved AWAY from the shipped
	// presets, which is what api/main.py's OVERRIDES is and what CARE's
	// sync_permissions_roles deliberately never touches either. In process,
	// one facility per kernel, exactly as the Python says: a second facility
	// sharing this process is what makes it a row beside phc.sqlite3.
	//
	// Guarded, because PUT /roles writes it while any other request may be
	// reading it, and the Python's one-request-at-a-time habit is not a
	// property Go's server shares.
	overrides  map[string][]string
	overrideMu sync.RWMutex
	workflow   string
	routes     []string

	store *store.SQLite

	// The loaded bundle's operations, which is narrower than the embedded
	// catalogue-wide set, and the write path over them.
	operations map[string]carephc.Operation
	write      *proposals.Bundle

	// The spoken names for a questionnaire field, which is the planner's own
	// vocabulary behind POST /khoj. Read from the tree at startup, like the
	// questionnaires and the value sets, and never restated here.
	spoken planner.SpokenFields
}

// ---------------------------------------------------------------------------
// the facility's shape
// ---------------------------------------------------------------------------
//
// kernel/plugins.py is package plugins, beside this one. It began as five
// unexported functions here, which is where a transcription naturally lands;
// what moved them is the half of that module they left behind. A plugin that
// is off is a capability the caller does not hold, subtracted once, by
// plugins.Effective in caller() below, and the lint that refuses a shape
// which only LOOKS configured is run at startup. Both now live somewhere a
// test and a differential check can reach.

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
	// A facility's own combination if it saved one, the shipped preset
	// otherwise. The ORDER of these two lines is the whole of it: the
	// override is what a caller holds BEFORE the facility's subtraction, not
	// after. Subtracting first and then letting an override replace the
	// result would hand out a capability this centre does not run, and it
	// would read as correct at a centre that runs every plugin.
	k.overrideMu.RLock()
	if saved, deviated := k.overrides[role]; deviated {
		declared = saved
	}
	k.overrideMu.RUnlock()
	// The one subtraction, here, before anything reads the set: the guard,
	// visible(), the quick action row, /whoami and therefore the MCP tool
	// list, and every view's own capability gate.
	caps := plugins.Effective(declared, k.withheld)
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
		detail(w, http.StatusBadRequest, "no such role %s", pyRepr(refused))
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
		detail(w, http.StatusBadRequest, "no such role %s", pyRepr(refused))
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

// ---------------------------------------------------------------------------
// a facility's own role combinations
// ---------------------------------------------------------------------------

// rolesRoute is api/main.py's two role routes, which sit on one path: GET
// /roles reads the shipped presets and this facility's own deviations from
// them, and PUT /roles/{role} saves one.
//
// WHY BOTH COME BACK FROM THE GET
// -------------------------------
// The Python's own reason, carried: an editor that seeds only from `presets`
// shows a role exactly as it SHIPPED even after a facility has deliberately
// moved away from it, and the next unrelated save silently restores what
// somebody removed on purpose.
//
// THE PRESETS ARE NOT NARROWED, AND THAT IS NOT AN OVERSIGHT
// ---------------------------------------------------------
// `presets` is bundle.yaml's `roles:` whole, including capabilities this
// facility withholds. A facility DECLINES a capability; it does not delete one
// from the bundle, which is what would make a shape a fork. The narrowing
// happens once, in caller(), and `current` is the role that was narrowed. The
// same rule GET /facility already serves `capabilities` under.
func (k *kernel) rolesRoute(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path[strings.Index(r.URL.Path, "/roles")+len("/roles"):], "/")
	who, refused := k.caller(r)
	if refused != "" {
		detail(w, http.StatusBadRequest, "no such role %s", pyRepr(refused))
		return
	}
	if rest == "" {
		if r.Method != http.MethodGet {
			notAllowed(w)
			return
		}
		k.overrideMu.RLock()
		saved := map[string][]string{}
		for role, caps := range k.overrides {
			// make, not append to nil: a role deliberately saved with NO
			// capabilities is an empty list, and encoding/json writes a nil
			// slice as null. The Python answers [], and `null` here would
			// make a role editor read "this facility has not deviated" from a
			// facility that deviated all the way to nothing.
			copied := make([]string, 0, len(caps))
			saved[role] = append(copied, caps...)
		}
		k.overrideMu.RUnlock()
		writeJSON(w, http.StatusOK, map[string]any{
			"presets":   k.cat.Vocabulary.Roles,
			"overrides": saved,
			"current":   who.Role,
		})
		return
	}
	if r.Method != http.MethodPut {
		notAllowed(w)
		return
	}
	k.setRole(w, r, rest, who)
}

// setRole is api/main.py's set_role: a facility's own combination, saved away
// from the shipped preset. bundle.yaml ships as CARE is_system=True roles and
// a facility's deviation is its own is_system=False row, which CARE's
// sync_permissions_roles deliberately never touches. So a preset is never
// mutated here; what is written is a row beside it.
//
// THE CAPABILITIES A SAVE MAY NAME ARE THE BUNDLE'S SIXTEEN, NOT THE FILE'S
// TWENTY-TWO
// --------------------------------------------------------------------------
// `k.caps` is the LOADED bundle's own declared capabilities. The embedded
// catalogue's top-level `capabilities` key is the union over every bundle,
// because the file is embedded whole and narrowed at runtime, and validating
// a save against that union would let a health centre's role editor grant six
// laboratory capabilities this bundle does not declare -- to the only account
// the browser can be. That over-grant was measured once on this build and it
// is what this line prevents.
//
// AND IT IS THE WHOLE SIXTEEN, NOT THE NARROWED SET
// -------------------------------------------------
// A centre with no laboratory may still SAVE a role holding `lab.order`,
// exactly as the Python allows, because the role is a declaration about who
// does what and the facility's subtraction is applied afterwards, every time,
// in caller(). Validating against the narrowed set instead would refuse a
// legal save, and it would look right at a centre that runs every plugin.
func (k *kernel) setRole(w http.ResponseWriter, r *http.Request, role string, who user) {
	if !holds(who.Capabilities, AdminCapability) {
		detail(w, http.StatusForbidden, "missing capability "+AdminCapability)
		return
	}
	if _, known := k.roles[role]; !known {
		detail(w, http.StatusNotFound, "no such role %s", pyRepr(role))
		return
	}
	var body struct {
		Capabilities []string `json:"capabilities"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		detail(w, http.StatusUnprocessableEntity, "the body is not an object: %v", err)
		return
	}
	seen := map[string]bool{}
	caps := []string{}
	for _, cap := range body.Capabilities {
		if !seen[cap] {
			seen[cap] = true
			caps = append(caps, cap)
		}
	}
	sort.Strings(caps)
	declared := map[string]bool{}
	for _, cap := range k.caps {
		declared[cap] = true
	}
	unknown := []string{}
	for _, cap := range caps {
		if !declared[cap] {
			unknown = append(unknown, cap)
		}
	}
	if len(unknown) > 0 {
		detail(w, http.StatusBadRequest, "not capabilities of this bundle: %s",
			pyStrList(unknown))
		return
	}
	k.overrideMu.Lock()
	k.overrides[role] = caps
	k.overrideMu.Unlock()
	writeJSON(w, http.StatusOK, map[string]any{"role": role, "capabilities": caps})
}

func holds(caps []string, want string) bool {
	for _, cap := range caps {
		if cap == want {
			return true
		}
	}
	return false
}

// notAllowed is FastAPI's own answer to a method a path does not serve: the
// Python registers GET on /roles and PUT on /roles/{role}, so the other verb
// on each is a 405 and not a 404.
func notAllowed(w http.ResponseWriter) {
	detail(w, http.StatusMethodNotAllowed, "Method Not Allowed")
}

// pyRepr renders a string the way Python's %r does, because that is what the
// message a caller reads already says.
func pyRepr(s string) string {
	if !strings.Contains(s, "'") {
		return "'" + s + "'"
	}
	return "\"" + s + "\""
}

// pyStrList renders a list of strings the way Python's %s of a list does.
func pyStrList(in []string) string {
	quoted := make([]string, 0, len(in))
	for _, one := range in {
		quoted = append(quoted, pyRepr(one))
	}
	return "[" + strings.Join(quoted, ", ") + "]"
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
	{"/roles", ""},
	{"/roles/{role}", ""},
	{"/threads", ""},
	{"/threads/{thread_id}", ""},
	// The arrival a patient makes for themselves at the printed poster, which
	// issues a number out of the same day sequence the desk draws from and
	// answers with it.
	//
	// THE SEQUENCE IS NOW ACTUALLY PORTED, which this line used to claim
	// while it was not. Package tokens is kernel/tokens.py's rule and
	// Store.IssueToken is the atomic reservation under it, so POST /threads
	// here issues a real number out of the same counter in the same file
	// that api/main.py draws from, and the two engines cannot disagree about
	// whose turn it is.
	//
	// What is still missing is this ROUTE: the provenance mark a poster's
	// arrival carries, and the unauthenticated surface that answers with the
	// number and nothing else. Both are api/main.py's and neither is the
	// sequence. Named here so the route is visibly not served rather than
	// silently absent.
	{"/arrivals", "the day sequence is ported and so is the atomic reservation under it; what is not ported is this route, its provenance mark and its unauthenticated surface"},
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
	// The ask-and-search turn, which G8b brought: the deterministic router of
	// agent/planner.py and the ordering, carding and wording of
	// agent/turn.py, over the same guard on the same machine surface. The one
	// half NOT here is that module's llm backend, which would need a network
	// call and an SDK; package planner refuses it by name rather than
	// planning with the router under it. /agent/say is the deprecated
	// spelling and delegates, exactly as the Python's does.
	{"/khoj", ""},
	{"/agent/say", ""},
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
		// One path, two methods: GET reads the presets and the deviations,
		// PUT saves one. Registered as a subtree so PUT /roles/{role} reaches
		// the same handler, which is how api/main.py's two decorators sit on
		// one router.
		mux.HandleFunc(prefix+"/roles", k.rolesRoute)
		mux.HandleFunc(prefix+"/roles/", k.rolesRoute)
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
		// The composer's endpoint, and its deprecated spelling, which
		// api/main.py serves by delegating to the same function. One handler,
		// so this spelling has no logic of its own to drift out of step with
		// the other.
		mux.HandleFunc(prefix+"/khoj", only(http.MethodPost, k.khoj))
		mux.HandleFunc(prefix+"/agent/say", only(http.MethodPost, k.khoj))
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

	// One bundle: the one this catalogue was compiled with. REFUSED BY NAME
	// rather than served wrongly, because serving a laboratory's threads out
	// of a health centre's manifest is the kind of wrong that reads as
	// working.
	//
	// The refusal is unchanged and is still right. What changed on 2026-11-01
	// is that it is now SATISFIABLE WITHOUT REBUILDING THIS BINARY: the
	// catalogue is read from the tree, so a second bundle is compiled by the
	// Python and pointed at with PHC_CATALOGUE. Before that the only way to
	// change which bundle this process could serve was to compile it again,
	// which is why the laboratory's separation rule was unprovable here.
	want := os.Getenv("PHC_BUNDLE")
	if want == "" {
		want = cat.Manifest.ID
	}
	if want != cat.Manifest.ID {
		log.Fatalf("PHC_BUNDLE=%q, and the catalogue this kernel read (%s) was "+
			"compiled for %q.\n\nCompile that bundle and point this process at "+
			"it:\n\n  python3 -m kernel.declarations %s --out /somewhere/catalogue.json\n"+
			"  %s=/somewhere/catalogue.json\n\nOr run against the reference "+
			"implementation with PHC_BACKEND=python.",
			want, cat.Source, cat.Manifest.ID, want, carephc.CatalogueEnv)
	}
	// Which catalogue answered, said once at startup. A kernel reading the
	// tree and a kernel reading its own embedded copy are different
	// deployments, and a log that does not distinguish them is how a check
	// reports a second bundle passing while the first one answered.
	log.Printf("bundle %s %s, from %s", cat.Manifest.ID, cat.Manifest.Version,
		cat.Source)
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
	// And the planner's own field vocabulary behind POST /khoj, read from the
	// same tree for the same reason. Loud on failure: a planner that quietly
	// lost this still answers, and what it answers is a thinner payload that
	// reads as the utterance never having said the value.
	spokenFields, err := planner.LoadSpoken(root)
	if err != nil {
		log.Fatalf("%v\n\nSet PHC_ROOT to the repository root, or run from it.", err)
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

	// Which plugins every declared shape runs, linted before anything is
	// resolved off it, which is where kernel/declarations.load does it: a
	// facility that looks configured and is not must stop the kernel rather
	// than serve a narrowed clinic that is quietly the whole one.
	//
	// Fatal, and that is the point. The failure this closes was measured on
	// this engine: PHC_FACILITY misspelt by one letter resolved to no
	// declaration, no declaration withheld nothing, and a centre meant to
	// have no laboratory served every laboratory tool with a green log line.
	if bad := plugins.Lint(plugins.ShapeOf(cat)); len(bad) > 0 {
		log.Fatalf("this bundle's plugin declarations do not hold:\n\n%s\n",
			strings.Join(bad, "\n"))
	}

	k := &kernel{cat: cat, bundle: cat.Manifest.ID, store: rows,
		overrides: map[string][]string{}, spoken: spokenFields}
	k.facility = plugins.Chosen(cat, "")
	k.withheld = plugins.Withheld(cat, k.facility)
	k.without = plugins.Absent(cat, k.facility)

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
		if _, err := store.Seed(rows, plugins.Seeded(declaredSeed, cat.Operations, k.withheld)); err != nil {
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

	// The outbox sweeper, started with the process and before the first
	// request, because a retention ceiling that waits for a request is off at
	// a clinic nobody is using yet and yesterday's audio is what is sitting
	// there. See cmd/api/outbox.go for what this engine does and does not do.
	stopSweeper := startSweeper(sweepSeconds * time.Second)
	defer stopSweeper()

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
