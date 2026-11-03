# Heidi, walked through, and what it says about Rapha

Done 2026-11-03 in a signed-in Heidi account (a demo profile, "John Done",
two test sessions). Everything below was seen in the running app, not read
off the marketing site. Nothing was recorded, sent, shared or deleted.

## 1. How Heidi is built

**A left icon rail with labels**, which is the same pattern Rapha arrived at
independently: Scribe, Evidence, Tasks, Patients, Templates, under a single
prominent create button. At the foot: connectors, Remote, Dictate, help,
notifications, account.

**Scribe is a list of sessions, not of patients.** Grouped by recency. Each
row is a patient avatar, the patient's name, the session's own title
("Untitled session") and a time. You can change the scope between your
sessions and the organisation's.

**A session is three columns.**

- The session list, which is draggable to resize.
- The session itself, with a **tab row across the top**: the patient, then
  `Context`, then `Note`, then `+`. The `+` offers "Queue document" and
  "New smart dictation", so a document and a dictation each become a tab.
- A collapsible control panel on the right: Session (patient, date and
  time, language, Share, More options), Note (template "Auto", style
  "Goldilocks", More options), Tools (Calculations).

**One agent composer, pinned under every tab.** It says "Working with Sam"
and "Type / for shortcuts", offers the chips Clinical Considerations, Prep
and Questions, shows how much context it is carrying (+7k), and sits above
a permanent line: "Medical knowledge only. Not for autonomous decision
making. Check sources and use your clinical judgement."

**The primary action is Transcribe**, top right, a split button with a
transcription-mode menu beside it and a separate audio-input picker.

**Patients is a plain table** — identifier, name, date of birth, gender,
total sessions — with Import and New patient. Nothing else.

**Tasks is empty with a promise**: "Tasks saved from your sessions will
appear here", filtered by status.

**Templates is the biggest screen in the product.** Filters for Notes, Docs
and Forms. Three groups: *Queued* ("added to every session and generated
after your note"), *Favourites*, and all the rest. Each row carries a
creator and a visibility. Dozens ship with it, many of them not clinical at
all — board minutes, clinical governance, supervision notes. There is a
"Browse community" button and a "Create template" button.

**Evidence is a second product.** A chat that opens "Who are we seeing
today, John?" with a Sources control and six intents: Look up, Work up,
Treat, Prepare, Write, Fill form. Beside it: a library, calculators, recent
chats, and a CPD tracker that turns a clinician's everyday reading into
logged professional development.

**The day can be loaded in.** The session list offers to build the day's
sessions from a CSV **or a screenshot of your schedule**.

## 2. What we already have, and should not change

The two biggest structural choices match, which is reassuring rather than
surprising — both products are solving the same visibility problem.

- The labelled icon rail.
- Tabs on the encounter. Heidi: patient, Context, Note. Rapha: Messages,
  What was heard, Earlier visits. Same shape, different contents.
- One composer with `/` shortcuts, carried across tabs.

And four things Rapha has that Heidi has nothing resembling, because Heidi
is a scribe for one clinician in one room:

- **The line, the stations and handover.** A PHC is a relay. Heidi has no
  concept of a patient moving from a nurse to a doctor to a pharmacy, and
  no `@` to hand anyone over.
- **Refusal.** Heidi writes what it heard and asks a human to check it.
  Rapha's kernel refuses an operation the person lacks the capability for,
  and says so on the thread. That is a stronger safety position, and it is
  the thing that makes Rapha slower to extend.
- **Coded data and FHIR.** Heidi's output is prose for an EHR to swallow.
  Rapha maps what was said onto declared fields and emits ABDM-compliant
  records. Different products wearing similar clothes.
- **Plain language for a reader with little English.** Heidi assumes a
  fluent professional throughout.

## 3. The gaps, worst first

### 3.1 A centre cannot write its own template

This is the real gap and everything else is smaller. In Heidi a clinician
creates a note format, favourites it, queues it to run on every session,
decides who else sees it, and can pull one from a community library. In
Rapha the questionnaires and note shapes are declared in the bundle, by us,
and a centre that wants its own ANC form waits for a release.

It is also the reason Heidi is hard to leave. A clinician with fifteen of
their own templates has built something they would lose.

This cuts against the declared-not-coded kernel in an interesting way
rather than a fatal one: a template is a declaration, and the question is
only who is allowed to author one and what validates it.

### 3.2 There is nowhere to put what you knew before the visit

Heidi's Context tab takes anything — a prior letter, a result, a paste —
before the consultation starts, and the note is written knowing it. Rapha
has no "before the patient sits down" surface at all. We have the tab shape
already, so this is cheap.

### 3.3 Nothing survives the visit

Heidi turns a session into tasks that outlive it. In Rapha, when a visit
closes the thread stops and the follow-up exists only in somebody's head.
For chronic care at a PHC — the NCD and ANC work — this is a serious
omission.

### 3.4 The day has to be typed in one patient at a time

Heidi builds the day from a photograph of the schedule. A PHC runs on a
paper register. A clerk photographing that register and getting the day's
line is a better idea for us than it is for them.

### 3.5 No way to look something up

Heidi's Evidence is a whole second destination with sources, calculators
and a library. Rapha's agent only exists inside a visit. A medical officer
with a question and no patient in front of them has nowhere to go.

The CPD tracker is the cleverest thing in the product: the clinician's
reading accrues to their own professional record automatically. India has
an equivalent obligation. Nobody is doing this there.

### 3.6 The recording is less controllable than theirs

Heidi has: a transcription-mode menu, a separate audio-input picker, smart
dictation as its own mode distinct from ambient capture, 110+ languages,
and a wearable offline mic with on-device encryption. Rapha has one
microphone, one mode, one language setting, and a browser at a desk. In a
noisy PHC, the device choice alone matters.

### 3.7 Smaller things

- Note length is a one-click control ("Goldilocks"). We have no dial.
- A session can be shared, and the organisation has its own session list.
- Documents queue into the session as tabs — which is the Files tab we
  deferred, and confirms the tab shape was right.

## 4. The difference underneath all of it

**Heidi is session-first. Rapha is patient-and-line-first.** Heidi's patient
record is a table row with a count of sessions on it; the session is the
real object. For us the patient is the spine and the visit hangs off it.

That is the right call for a PHC and we should not drift. But it explains
why Heidi feels faster: a session needs nothing before it starts, and ours
needs a registration, a station and a capability.

## 5. What I would do, in order

1. **Let a centre author a template.** Biggest gap, and the thing that makes
   Heidi sticky. Needs a decision about who may author and what validates.
2. **A Context tab.** Cheap, and the tab is already built.
3. **Tasks that outlive the visit.** Chronic care needs it.
4. **Build the day from a photograph of the register.**
5. **Audio input choice**, alongside the waveform already planned.

Items 1 and 3 are product decisions, not work I should start unasked.
