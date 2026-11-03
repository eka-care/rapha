# Hera, and the cleaner shell

Design, 2026-11-03. Status: **four decisions open (§6), one of them urgent.**

Two things arrived together and they belong in one plan, because the second
is what makes the first demonstrable: the Hera pitch deck (FOGSI hackathon,
2026) and a list of changes to the shell drawn from walking Heidi.

## 1. What Hera promises, and how much of it Rapha already is

Hera is *"voice-first care coordination for high-risk pregnancies, from the
household to the district"*, and its line is **"every voice heard, every
referral closed."** The deck names five places the pathway breaks: the ASHA
visit is verbal and on paper; there is no record of change across visits;
the PHC does not know which women in its area are high-risk; a referral is
sent and nobody checks it happened; the district sees no load, no overdue
cases, no capacity.

Rapha is already most of the answer to the first three.

| Hera's four actors | Where Rapha stands |
| --- | --- |
| **Frontline** — ASHA, ANM, MLHP record a visit by speaking, in their own language; each visit becomes a structured record; **no forms** | Built. The scribe maps speech onto declared fields through the questionnaire and mapping; `community` is already a station and ASHA and ANM are already roles. Language is set to en-IN and needs opening up. |
| **PHC doctor** — marks high-risk, tracks on a live dashboard, full record in the EMR | Mostly built. Flags, the line, the facility dashboard and the thread all exist. "Marks high-risk" as a deliberate clinician act does not. |
| **Care agent** — keeps every referral open until closed, reminds on overdue visits | **Not built.** This is the single biggest hole. The thread ends when the visit ends. Nothing outlives it, nothing is overdue, nothing is chased. |
| **District** — real-time high-risk caseload, overdue follow-ups, facility capacity | **Not built.** Rapha has one facility. There is no tier above it and no role that sees across facilities. |

So the hackathon build is not "make Rapha"; it is **two new things on top of
Rapha**: a referral that stays open until someone closes it, and a tier
above the facility that can see many of them.

### 1.1 The one place the deck and the kernel disagree

The safety slide says the AI **never** *"scores or stratifies risk"* and
that *"clinicians mark high-risk cases."* Rapha's kernel already computes
flags — `vitals flagged` is on a patient's badge today — and the home
screen colours a station by load.

These are **declared deterministic rules from the bundle, not a model
scoring anybody**, which is a genuinely stronger position than the deck
claims for itself. But a judge who reads the slide and then sees a red
badge appear without a clinician touching it will think the slide is
untrue. Two honest ways out, and one of them has to be chosen before the
demo:

- **Say what it actually is on the slide**: "rules the centre declares,
  not a model" — and keep the flags. I recommend this; it is a better
  story than the one currently on the slide.
- Or make every flag require a clinician to confirm it, which is slower
  and throws away the part of the kernel that is most defensible.

This is decision §6.1 and it is the urgent one, because it changes both the
deck and the demo.

### 1.2 Stack differences worth noting, none fatal

The deck names PostgreSQL, Redis, Twilio, Pipecat, Parrotlet and
Matrix + Echo. Rapha is SQLite, no queue, Eka Scribe, and a Go twin held in
parity by `scripts/check_go_parity.py`. For a hackathon demo none of that
has to change: reminders need a timer and a message out, and Twilio is the
only genuinely new dependency. Swapping the speech engine to Parrotlet is a
connector change behind `scribe/base.py`, which is what that boundary is
for — but it is not free, and it buys native-language capture that the
Frontline card depends on.

## 2. The shell changes

All seven are the owner's, 2026-11-03, after walking Heidi. Ordered by how
much they change.

### 2.1 Forms stop being pop-ups and become templates

Today an operation opens `OperationPanel` over the screen, behind a scrim.
The Hera deck promises frontline workers **"no forms"**, and the whole
product's claim is that you speak instead of filling things in. A modal is
the most form-like thing an interface can do.

So: an operation opens **in place, as a template** — the same component,
drawn inline in the tab, the way the scribe's drafts already are since the
tab row landed. Nothing is stacked over the conversation. The amend path
and the seeded-from-registration path both follow.

This is the largest of the seven and it touches every call site that
currently sets `modal` or `editing`.

### 2.2 The scribe tab is called Scribe, and it can start a session

- Rename **What was heard** to **Scribe**. Plainer, and it is the word the
  deck, the team and the owner all already use.
- Starting a recording moves to that tab and begins, which it already does.
- Opening the tab by hand with nothing recorded shows **one Start session
  button, centred** — not the sentence of explanation that is there now.
  Heidi does exactly this ("Press transcribe to start") and it is the
  clearest empty state in their product.

### 2.3 A shortcut to start a session

A single key, from anywhere in a visit, starts recording. The microphone in
the composer stays; this is for the doctor who already knows.

### 2.4 A handover is a line, not a slab

A station handover and a committed update each draw a full-width card: a
44px icon, a 14px title, a 12px summary and an arrow. Stacked down a visit
they are most of the page, and the one thing a doctor is there to do sits
in a row of equals.

They become **nimble**: one line, the action's own words, the icon small
and inline, no summary unless the line is the only thing on screen. The
primary action keeps its weight; everything behind it loses it.

### 2.5 Asking the agent, in two places with two shapes

- **Inside a patient**, a question opens **a tab in the same thread
  interface** — not Heidi's right-hand panel. The visit already has tabs
  and the answer is about this patient, so it belongs beside the
  conversation, not in a second column.
- **Outside a patient**, a question opens **a centred overlay**, in the
  shape Fern's docs use: the bot comes forward in the middle of the page.
  There is no patient to sit beside, so there is nothing to sit beside.

This is the gap the Heidi walkthrough found — a medical officer with a
question and nobody in front of them currently has nowhere to go.

### 2.6 More `/` commands

Today `/` lists the operations this thread will accept. It should also
carry the things that are not operations: start recording, open a tab,
hand over, ask the agent, look something up, add context. The list stays
declared where it is declared; what is added is the renderer's own verbs,
which is the one category `ui.check.ts` permits this layer to name.

### 2.7 Simplicity, as a pass rather than a feature

Heidi's screens are quiet: one primary action, a collapsible control panel,
few borders, no card inside a card. Rapha's visit currently draws a card,
inside it a header, a carry strip, a tab row, a thread of cards, an agent
bubble containing more cards, a composer with a chip row, and a rail of
four more cards beside it.

The pass is: **one card per screen, not cards inside cards**; the control
rail collapses by default; the carry strip and the agent's own node merge,
because both say "here is what matters about this person right now".

## 3. What Hera needs that neither Rapha nor Heidi has

1. **A referral that stays open.** An object with a state, an owner, a due
   date and a closure, which survives the visit that raised it. This is
   "every referral closed" and there is nothing in the kernel to build on.
2. **A reminder that goes out.** Overdue means a clock and a message. The
   outbox already holds and retries things; this is a different queue with
   a different trigger.
3. **A tier above the facility.** The district view counts across PHCs.
   Everything in the kernel today is scoped to one.
4. **The pregnancy itself as the spine.** The deck's "longitudinal
   pregnancy record across visits" is not the same as a patient with many
   visits: a pregnancy has a start, an expected date, a sequence of
   contacts, and an end. `Earlier visits` shows a list; this needs an arc.

## 4. What I would NOT copy from Heidi

Worth writing down, because the temptation is real after a walkthrough.

- **Session-first.** Heidi's patient is a table row with a count on it. For
  a PHC the patient is the spine and Hera makes that sharper, not softer: a
  pregnancy is followed for nine months across four workers.
- **A standing disclaimer in place of a refusal.** Heidi writes what it
  heard and asks a human to check. Our kernel refuses and says why on the
  thread. The Hera safety slide is describing our behaviour better than
  Heidi's.
- **A community template library.** Right idea, wrong hackathon.

## 5. Order of work

Each step leaves the gate green.

1. **Scribe tab: rename, centred Start session, keyboard shortcut.** Small,
   visible, no decisions. (§2.2, §2.3)
2. **Slim the thread objects.** (§2.4) Then the simplicity pass, because
   half of it is this. (§2.7)
3. **Forms become templates.** (§2.1) Largest renderer change; do it before
   anything new is built on top of a modal.
4. **More `/` commands**, including the two new verbs the steps above
   create. (§2.6)
5. **Ask the agent, both shapes.** (§2.5)
6. **The referral object and its closure.** Kernel work, written twice for
   parity. Needs §6.2.
7. **Reminders.** Needs §6.3.
8. **The district view.** Needs §6.4.

Steps 1 to 5 are the demo's surface and need no answers. Steps 6 to 8 are
the demo's story and every one of them needs one.

## 6. Decisions I am not making

1. **URGENT — does a flag stay automatic?** §1.1. It changes the safety
   slide and the demo, and the slide as written contradicts what the kernel
   already does. My recommendation: keep the flags, change the slide to say
   "declared rules, not a model", because that is both true and stronger.
2. **What closes a referral?** The receiving facility recording the visit,
   the sending clinician marking it, or the agent seeing the record appear?
   Only the first is real evidence; only the second works offline.
3. **How does a reminder reach an ASHA?** Largely answered on 2026-11-03
   by reading the scribe backend. It already has a provider-agnostic
   telephony layer (Vobiz, Exotel, Plivo) with a phone-number-to-workspace
   table, so reminders should go through that rather than adding Twilio as
   a fourth provider. And Eka's own webhook rule is identifiers only, with
   the client fetching details over an authenticated API, which settles the
   disclosure question: the reminder says a visit is overdue and nothing
   about who. What is left for the owner is only whether that is acceptable
   to the programme.

5. **NEW — does the demo lead with a phoned-in visit?** The same telephony
   layer means an ASHA with a feature phone can call a number and speak the
   visit: no smartphone, no app, no data, no form. It is the strongest
   version of the deck's "Frontline — no forms" card and the one that works
   where the deck's version does not. Most of the machinery exists. See
   `2026-11-03-eka-scribe-backend-notes.md` §5.
4. **Is the district real or demonstrated?** A genuine multi-facility tier
   is a week of kernel work. A district view over seeded data is an
   afternoon and is honest if the demo says so. For a hackathon I would
   seed it and say so out loud.

## 7. What is left to the builder

Which key starts a session; the exact tab order; whether the centred agent
overlay is dismissed on Escape alone or also on a click outside; where the
Start session button sits vertically. None of these change what the thing
is.
