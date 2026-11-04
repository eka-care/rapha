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

---

# Addendum, 2026-11-04: the parts I had not measured

The owner opened their own signed-in Heidi after telling me, fairly, that I
had designed from a description three times and got it wrong each time.
Read only: nothing was created, saved, recorded or deleted in their account.
This section is the reference for rebuilding Rapha's forms, and it exists
because section 3 above described WHAT Heidi has and never wrote down HOW
any of it is put together.

## 6.1 Context is not a form. It is a surface.

This is the finding that matters most, because Rapha shipped the opposite.

Heidi's Context tab is one empty writing surface. The whole of its chrome
is a row of five controls above it and a prompt where the text will go:

    [scan] [paperclip]              [mic ▾] [undo] [redo] [Copy ▾]

    Add any additional context about the patient or paste files here

That is it. No labels, no fields, no asterisks, no Commit button. You
scan a document into it, attach a file to it, dictate into it, paste into
it, or type into it, and what lands is yours to edit. The surface saves
itself.

Rapha's equivalent asks three questions in three boxes -- Who wrote it,
Date on it, What it says -- with no microphone anywhere on it. A clerk
holding a discharge summary has to read somebody else's letter and retype
it into our form. That is the product asking a person to do the work it
exists to do for them, and the owner was right to call it out.

**What follows for us.** Background becomes a surface, not a form: upload
or photograph the paper, or dictate it, and the text lands in one editable
body. Who wrote it and the date are derived where they can be and asked
for only when they cannot be -- and never as the first thing a person
meets.

## 6.2 Dictation has two modes, and a key

Under the microphone's own chevron, exactly two choices:

- **Start word-for-word dictation** -- literal, what was said.
- **Start smart dictation** -- cleaned up.

That distinction is doing real work. A clinician dictating a plan wants it
tidied; somebody copying another facility's letter wants it verbatim,
because correcting somebody else's document is falsification. Rapha's
context atom already says this in prose ("do not summarise it and do not
correct it") and should now say it with the mode.

The shortcut, from Heidi's own Shortcuts panel, under a group called
**Dictate**:

| What | How |
| --- | --- |
| Dictate into text field | **Hold** the key |
| Hands-free | **Double press** it |
| End hands-free | **Press** it |

The key is the rupee sign, U+20B9. Confirmed by the owner, and read off
the panel rather than guessed. Hold to talk into whatever field has
focus; double press to keep going without holding.

**The one risk, flagged rather than designed around.** There is no rupee
key on a plain US or UK Mac keyboard. If the centres run an Indian layout
this is a good key and a nice piece of local identity. If some do not, the
shortcut is unreachable for them. So in Rapha the key is a setting with
the rupee as its default, which costs nothing and removes the gamble.

## 6.3 The three columns, measured

At a 1440 by 900 viewport:

- **Icon rail**, about 40px, labels under the glyphs. A bell near the
  foot, with help, connectors and the account. Patients is a people glyph.
- **Session list**, about 320px, and the divider between it and the work
  surface is draggable.
- **The work surface**, one card, with the tab row INSIDE its own top bar
  rather than above it: patient, Context, Note, +. Everything in that
  column shares one left edge and one right edge.
- **The control panel** is an overlay, not a fourth column: 312px wide,
  inset 19px from the right, its top edge level with the top of the work
  surface, and it closes to nothing.

Rapha's right-hand rail is three separately bordered cards that begin
56px lower than the centre card they sit beside, which is the
misalignment the owner saw. Heidi's panel is one quiet column of grouped
rows -- Session, Note, Tools -- with no card borders at all, each group
collapsible.

## 6.4 What this changes, in order

1. **Forms become surfaces wherever the content is prose**, with a
   microphone on every one of them. Nothing that collects text ships
   without dictation into it; see the memory note of the same date.
2. **One dictation shortcut, global**, targeting the focused field, with
   both modes, and the key configurable.
3. **Background takes a document**, scanned or attached, before it ever
   offers a box to type in.
4. **The right rail becomes one aligned column**, top edge level with the
   centre card, groups instead of cards.
5. **The session list divider becomes draggable**, and the bell moves to
   the rail's foot in place of a nav row called "Needs you".
