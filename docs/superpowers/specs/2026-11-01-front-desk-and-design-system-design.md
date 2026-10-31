# The front desk, and moving the app onto the Eka Developers design system

**Status.** Settled with the owner on 2026-11-01, in the mockup conversation
recorded by `.superpowers/brainstorm/48124-1793472978/content/`. This document
is the spec the work is built against. It is not a proposal.

## Intent

Two things were agreed and never built, and one thing is being designed for the
first time.

1. **The design system.** Two artifacts carry the Eka Developers system applied
   to this product, published 2026-10-31. Neither reached the code. The running
   interface is a 2026-09-16 rebuild to an older reference. Measured: the
   artifacts' accent (`#215fff`), their typefaces (Geist, Newsreader, Geist
   Mono) and their token names appear nowhere under `web/`.
2. **The functionality in those artifacts** that the product does not have.
3. **The front desk**, designed in this conversation, for a clerk who would
   rather be writing on paper.

## Who it is for, and why it is hard

The clerk at a primary health centre desk. The patient is standing in front of
them; there is no paper slip to copy from. Roughly half the people who reach
the desk are already registered. The clerk has little tangible reason to prefer
this to a register book, so **every question put to the patient and every one
time password spent is a reason to stop using it.**

NHA's own guidance ranks the same way, and this design follows it: a question
to the patient costs more than three network calls; a one time password costs
more than a call. See `hiecm.concept.m1-counter-journey-order` and
`hiecm.concept.m1-deployment-interview` in the ABDM catalogue.

## Goals

- A returning patient reaches the nurse without the clerk typing a full record.
- A new patient's form opens **already filled** from their ABHA profile. The
  clerk corrects; they do not type.
- Self-registration by poster takes the clerk out of the loop entirely.
- One queue, numbered, that a clerk can filter.
- The running app looks like the two artifacts.

## Non-goals

- **No authentication.** There is none today and this work does not invent one.
  `X-PHC-Role` and `X-PHC-Actor` are carried unchanged.
- **No second registration form.** Both routes to a profile end on the same
  screen. `hiecm.concept.m1-two-routes-to-the-profile` is explicit that two
  forms drift apart.
- **No real ABDM calls.** ABHA stays on staging, because production creates
  permanent national health accounts.
- Not the whole of the second artifact. Stock, the shelf-is-empty moment and
  carry-forward are named in "What is not in this work" below.

## Anti-goals

Things that would make this a failure even if it shipped working:

- **A second ABHA number for one person.** Nothing merges two; the patient
  carries the mistake permanently. The journey must look before it creates, and
  must never ask the patient whether to log in or create.
- **A registration with an ABHA that took as many keystrokes as one without.**
  That is NHA's own test, and it means the ABHA step is in the wrong place.
- **Colour that does not mean anything.** In this system colour means clinical
  risk. A programme label is not a risk.
- **The renderer naming a station, flag, capability or bundle.** The rule
  predates this work and a check enforces it.

## Constraints

- **The renderer may never name a station, flag, capability or bundle.** The
  artifacts do, on screen. The port honours the rule, not the artifact: every
  station name, programme label and filter comes from the declarations.
- **The Go port is mid-flight.** Seven of nine slices have landed, and every
  slice proves `git diff -- web/ packages/` is empty. Work under `web/` and a
  Go slice therefore **cannot run at the same time**. The port pauses while
  this lands.
- **Eka is not a government integrator.** The demographic route — one call, no
  one time password — is government-only and unavailable. This is the single
  biggest constraint on the desk.
- The clinical sign-off on the condition and medicine lists is still
  outstanding and blocks one item here too.

## Decisions taken, and by whom

### The ABHA step comes first (owner)

Search, then ABHA, then the form. Not the form, then an identifier filed on
top. A verified profile already carries name, date of birth, sex, mobile, full
address and a photograph.

### The route set, not a journey (owner, after the deployment interview)

| Route | Questions | OTPs | Status here |
|---|---|---|---|
| Poster QR, scan and share | 0 | 0 | **Built.** Free, small share of patients. |
| Create with Aadhaar OTP | 1–2 | 1–2 | **The default today**, and the expensive one. |
| Create, fingerprint | 1 | 0 | **Not built.** Needs a certified reader per desk. |
| Create, demographics | 1 | 0 | **Unavailable.** Government integrators only. |

**Recorded plainly: until a fingerprint reader sits on the desk, every new
patient costs an OTP round trip to a handset the patient may not be carrying.**
That is the main thing standing between this and paper, and it is a purchase,
not code.

Each route is declared per facility and **adds**, never replaces, in the same
way a centre already declares that it has no laboratory. There is no second
build for a centre with a reader.

### The token (owner)

- **Numeric only**, incrementing: 1, 2, 3. Not `A01`, which is what the seed
  carries today.
- **One sequence** for everybody. Where a patient came from is a label, never a
  different number. Two sequences would put two people called "seven" in one
  waiting room.
- **Issued on arrival.** The poster QR carries a facility id and a *counter*
  id, so the scan happens at the counter and the scan is the arrival. The
  number is issued at that moment and is sent back to the patient's PHR app.
- The poster saves the typing. It never saves a place in the queue.

### Paper (owner)

Nothing prints at the desk. One printout, at the pharmacy, treated as the
building's printer rather than the pharmacy's — the default path ends there
anyway. The doctor can send a page to it for a patient who leaves earlier.

### The queue row (mine, owner approved)

- Token, name, where they are, labels, time.
- **The lotus** beside the name when the patient has an ABHA.
- **Programme labels** from the declared category, monochrome.
- **High risk in red**, because it is the only one of them that means clinical
  risk, so red keeps one meaning.
- A label the system inferred is drawn **dashed**, so a guess never looks like
  somebody's decision.
- Provenance is a **dot on the token**, not a word. It was the least important
  thing on the row and it was shouting.
- Filters across the top with live counts.

## Approaches considered

**A. Restyle only.** Swap the tokens and the typefaces, leave every screen
where it is. Cheapest, lands in a day, and does not deliver the desk — which is
the part the owner actually asked for. Rejected as the whole answer; it is
step one of C.

**B. Rebuild the renderer against the artifacts.** Treat the artifacts as the
target and rewrite the screens to match. Fastest route to something that looks
right, and it carries the artifacts' own defect: they name stations and
programmes on screen, which this product forbids and checks. Rejected.

**C. Tokens first, then the desk, then the declarations (chosen).** Three
layers, in dependency order: the colour and type tokens, which are contained to
one file by an existing rule; then the screens, which read everything they name
from declarations; then the kernel work for what the declarations cannot yet
say. Each layer leaves the gate green. Chosen because the first layer is nearly
free, the second delivers the brief, and the third is the only part that needs
anybody else.

## What the builder decides

- How the search field merges local patients and directory suggestions into one
  list, and what it does while the directory is slow or absent.
- Keyboard behaviour in detail: what Enter does on each row, how Tab carries a
  typed name into the new-patient path.
- Whether filters live in the URL.
- How the lotus is drawn. It must carry an accessible name and must not be the
  only way ABHA status is conveyed.

## What is not in this work, and why

- **High-risk pregnancy as a programme.** The declared categories are general,
  antenatal, NCD and TB. Adding one is a clinical decision and belongs with the
  sign-off already outstanding.
- **Fingerprint.** No reader, and it is outside the ABHA kit already loaded.
- **Stock, the empty-shelf substitution, and carry-forward** from the second
  artifact. Each needs declarations that do not exist. Named here so they are
  not mistaken for oversights.
- **Anything that would let the renderer name a station.**

## How we will know it worked

- A registration with an ABHA takes fewer keystrokes than one without. NHA's
  own test, and the counter on the form screen reports it.
- `sh scripts/check.sh` is green, and the renderer check that forbids naming a
  station still passes.
- The two artifacts and the running app are recognisably the same product.
