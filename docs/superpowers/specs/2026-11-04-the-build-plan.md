# The build plan

Design, 2026-11-04. Supersedes the ordering in the two notes before it;
their reasoning still stands and is referenced rather than repeated.

- `2026-11-02-thread-as-channel-design.md` — the tabs, files, agent chat
- `2026-11-03-heidi-teardown.md` — what a mature scribe product has
- `2026-11-03-hera-and-the-cleaner-shell-design.md` — the hackathon, the shell
- `2026-11-03-eka-scribe-backend-notes.md` — what Eka's backend really does

**Still unanswered and still blocking the sequencing: when is the
hackathon.** Everything below is ordered by dependency, not by date.

## 1. The backend question, first, because it changes everything after it

The owner's words: *"I want to possibly reuse the eka scribe be else we'll
have to manage a completely new be over eka scribe increasing
dependencies."*

That worry is correct, and the duplication it describes **already exists
and is ours.**

### 1.1 What we are actually running

Rapha serves `/scribe/sessions`, `/scribe/sessions/{id}`,
`/scribe/sessions/{id}/extract`, `/scribe/webhook`, `/scribe/templates`.
Eka serves `/voice/v1/sessions`, `/voice/v1/sessions/{id}`,
`/voice/v1/sessions/{id}/end`, `/voice/v1/sessions/{id}/audio/{file}`,
templates and a discovery document.

Those are the same API. `api/scribe.py` is 703 lines of transaction layer
standing in front of a transaction layer, and it is why the notes arrive
late: ours waits for everything, theirs does not. Add the audio queue and
outbox and we maintain roughly 2,300 lines of backend to forward audio to
a service that already accepts audio three different ways.

### 1.2 Three ways to go

**A. Put Rapha's kernel inside voice2rx-be.** One service, one deploy.
Rejected. It is a shared Eka service with its own team and cadence, AWS
Secrets Manager, DynamoDB, SQS, Chalice lambdas, region middleware and a
private `echo` dependency that needs git credentials to build. Our release
would be gated on theirs and theirs on ours. It also kills the
second-implementation promise that `connectors/scribe/base.py` and the Go
twin exist to keep — and a digital public good cannot have a vendor's
service as its only backend.

**B. Keep our kernel. Delete our copy of theirs. ← recommended**
The browser talks to Eka directly over the MedScribeAlliance protocol for
everything that is audio: create a session, upload chunks while recording,
end it, fetch a chunk's transcript, fetch each document. We keep only what
is genuinely ours, which is small:

| Stays | Why |
| --- | --- |
| `/scribe/nudges/{station}` | the bundle's own prompts; pure declaration |
| `extract` → `draft.py` + `kernel/mapping.py` | turns Eka's structured output into **filled declared fields**. Eka returns a note; we return a questionnaire with answers in it. Nothing at Eka does this and nothing should. |
| the consent gate and the capability guard | the kernel refuses; Eka does not |
| a webhook receiver | to learn a document is ready without polling |

Everything else goes: the session mirror, the poll loop, and the audio
outbox.

**C. Change nothing.** Keep paying the delay and re-implementing each Eka
feature by hand.

### 1.3 The one real cost of B, and it is a decision

`kernel/queues.py` and `api/outbox.py` exist so a recording survives the
line going down, held for a signed 24 hours and swept. If the browser
uploads straight to Eka, consultation audio never touches our disk — which
removes a retention liability we would rather not have — but the offline
hold goes with it.

For a rural PHC that hold is not a nicety. **Decision §6.2.** The honest
middle is: upload direct when the line is up, fall back to our hold when it
is not, and keep the outbox for that path only.

### 1.4 What B buys immediately

- The transcript appears **during** the consultation, per chunk.
- Each note appears as it is finished, not after all of them.
- Parrotlet and the other Indian-language engines, already wired.
- The telephony path, for free, when we come to it.
- ~2,000 fewer lines of our own backend.

## 2. The shell

Ordered so each step leaves the gate green and nothing is built on a
surface that is about to change.

### 2.1 Scribe tab — rename, Start, shortcut
Rename **What was heard** to **Scribe**. Opening it with nothing recorded
shows **one centred Start session button**, not a sentence. Recording
already moves to the tab. Add a keyboard shortcut that starts a session
from anywhere in a visit. *(Hera plan §2.2, §2.3. No decisions.)*

### 2.2 Slim the thread objects
A handover and a committed update each draw a full-width card with a 44px
icon, a title, a summary and an arrow. Stacked down a visit they are most
of the page. They become one nimble line; only the primary action keeps its
weight. *(Hera plan §2.4.)*

### 2.3 The simplicity pass
One card per screen, not cards inside cards. The right rail collapses by
default. The carry strip and the agent's node merge — both answer "what
matters about this person right now". *(Hera plan §2.7.)*

### 2.4 Forms become templates, not pop-ups
An operation opens **in place**, the way the scribe's drafts already do,
instead of over a scrim. Every `modal` and `editing` call site follows.
This is the largest renderer change and must land before anything new is
built on a modal. *(Hera plan §2.1.)*

Note a distinction worth keeping straight: Eka's "templates" describe the
**shape of an output note**; Rapha's questionnaires describe the **fields
an operation writes**. The owner's instruction is about presentation — a
form should not be a pop-up — not about replacing one with the other.

### 2.5 The scribe canvas
On the Scribe tab: the waveform centred and live, the transcript filling in
beneath it as chunks are transcribed, then the draft with the field each
value mapped to. Depends on §1, because the per-chunk transcript is the
whole point. *(Thread plan §7, corrected by the backend notes.)*

### 2.6 More `/` commands
`/` keeps listing the declared operations and gains the renderer's own
verbs: start recording, open a tab, hand over, ask the agent, add context.
*(Hera plan §2.6.)*

### 2.7 Asking the agent, in two shapes
Inside a patient, a question opens **a tab** in the same thread interface.
Outside a patient, it opens **a centred overlay** in the shape Fern's docs
use. *(Hera plan §2.5.)*

### 2.8 Station and tag filters into panel two
Carried since 2026-11-02. Touches seven assertions in `ui.check.ts` that
read `screens/ListScreen.tsx`.

### 2.9 A Context tab
The pre-visit scratchpad: paste a prior letter or a result before the
patient sits down, and the note is written knowing it. Heidi's clearest
idea and the tab shape already exists. *(Heidi teardown §3.2.)*

## 3. What Hera needs that does not exist anywhere yet

These are the deck's promises, and they are kernel work, written twice for
Go parity.

### 3.1 A referral that stays open
An object with a state, an owner, a due date and a closure, surviving the
visit that raised it. This is "every referral closed" and there is nothing
to build on. **Needs §6.3.**

### 3.2 Reminders
Overdue means a clock and a message out. Through Eka's existing telephony
layer, not Twilio, and carrying identifiers only — which is Eka's own house
rule, so it needs no argument. *(Backend notes §6.)*

### 3.3 Tasks that outlive the visit
The general case of 3.1, and what Heidi already has. Chronic care at a PHC
needs it. *(Heidi teardown §3.3.)*

### 3.4 A tier above the facility
The district view counts across PHCs; everything in the kernel is scoped to
one. **Needs §6.4 — real or seeded.**

### 3.5 The pregnancy as a spine
"Longitudinal pregnancy record across visits" is not a patient with many
visits: a pregnancy has a start, an expected date, a sequence of contacts
and an end. `Earlier visits` shows a list; this needs an arc.

## 4. Parked, deliberately

**The phoned-in visit.** The owner's call, 2026-11-04: in the plan, built
later. The analysis stands — resolve the workspace from the dialled number,
identify the worker by the caller's, move the unique key, and never let the
call silently join a patient. Three things it still needs when its turn
comes: the confirm-the-match screen, spoken consent, and a decision about
whether the demo leads with it. *(Backend notes §5.1–5.3.)*

**Files in the thread, and the private agent chat.** Still blocked on the
four decisions in the thread plan §8.

**Centre-authored templates.** Right idea, wrong hackathon.
*(Heidi teardown §3.1.)*

## 5. Order

1. **§1 backend decision**, then the direct-to-Eka path for audio.
2. **§2.1, §2.2, §2.3** — the visible shell wins. No decisions, do them first.
3. **§2.4 forms as templates** — the big renderer change.
4. **§2.5 the scribe canvas** — needs 1 and 3.
5. **§2.6, §2.7, §2.8, §2.9** — the rest of the shell.
6. **§3.1, §3.2** — referral and reminders. The demo's story.
7. **§3.3, §3.4, §3.5** — tasks, district, pregnancy arc.

Steps 2 and 3 need nothing from the owner and I can start today.

## 6. Decisions still open

1. **URGENT — do flags stay automatic?** The deck's safety slide says the AI
   never scores or stratifies risk and that clinicians mark high-risk cases.
   The kernel raises flags today. They are declared rules, not a model,
   which is a *better* story than the slide tells — but the slide as written
   contradicts the demo. Recommendation: keep the flags, change the slide.
2. **Does audio still need our offline hold?** §1.3. Recommendation: direct
   upload when the line is up, our hold when it is not.
3. **What closes a referral?** The receiving facility recording the visit,
   the sending clinician marking it, or the agent seeing a record appear.
   Only the first is evidence; only the second works offline.
4. **Is the district tier real or seeded?** A genuine multi-facility tier is
   about a week. A seeded view is an afternoon and is honest if the demo
   says so.
5. **When is the hackathon.** Asked three times; still the thing that
   decides how much of §3 is real.
