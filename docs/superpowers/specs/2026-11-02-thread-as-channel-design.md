# The thread as a channel

Design, 2026-11-02. Status: **awaiting the owner's decisions in §8.**

## 1. Intent

The visit thread should work the way a station channel works: people talk in
it, an agent answers in it, work is handed over in it, and files are dropped
into it. Today it does three of those four. What it does not do is hold a
file, and what it does badly is hold anything that is not a sentence.

The owner's words: *"think of thread as a channel between different stations
... I am able to upload files as part of the chat thread which also get stored
as part of the patient's files ... but the thread itself is getting too text
heavy now ... I need to be able to have separate views that open up for
scribe, open documents linked for that patient, or if a doctor wants to have a
private chat with the agent regarding the patient, or to check the patient's
previous visits. When I say a view think more along the lines of a slack chat
which allows for having a canvas, files etc."*

## 2. What already exists

Worth saying plainly, because most of the brief is already built and the
plan should not rebuild it.

| The brief | Where it lives today |
| --- | --- |
| A channel between stations | `web/src/thread/Thread.tsx`, one thread per visit |
| An agent in the channel | `agent/turn.py`, drawn as the agent's own node |
| `@` to hand over or assign | `thread/Composer.tsx` + `thread/Menu.tsx` |
| `/` for the actions this thread accepts | same, from the declared operations |
| The microphone | `scribe/ScribeBar.tsx`, started from the composer |
| Previous visits | `thread/Past.tsx` — `usePast`, `Carry`, `Trend` |
| Side panels beside a visit | `screens/rail.ts` — four, personal, folding |

So the genuine gaps are two:

1. **Files.** There is no attachment anywhere: not in the kernel, not in the
   declarations, not in the renderer. Nothing to extend.
2. **Views with room.** The four side panels are 280px cards that summarise.
   None of them is a surface you can read a lab report in, scroll a
   conversation in, or compare two visits in.

## 3. Goals

- A file dropped in the thread becomes one of the patient's records, in Eka,
  reachable from the patient's file long after this visit closes.
- The thread shows that it happened in one line, not in a card the size of a
  consultation.
- Four views open beside the thread with real room: **Scribe**, **Files**,
  **Ask about this patient**, **Previous visits**.
- The thread's own body gets shorter, not longer, as a result.

## 4. Non-goals and anti-goals

- **Not** a second place to record clinical data. A file is a document; it is
  not vitals, and it does not fill a questionnaire. If a report should become
  coded data, that is the scribe's or an operation's job, through the mapping,
  as it is today.
- **Not** a document store in our kernel. We do not become a records system.
- **Anti-goal: a thread you scroll to find things in.** If the four views ship
  and the thread is still a wall of text, the work failed.
- **Anti-goal: a view that is a narrower copy of the page behind it.** A view
  earns its place by doing something the thread cannot.

## 5. Constraints that decide the design

- **The renderer may not name a clinical thing.** `ui.check.ts` fails the build
  if any `.tsx` quotes a declared station, flag, capability, operation id or
  view column. So a view cannot be a hard-coded list of document types, and
  "Files" cannot be a fifth entry in a renderer-side array of clinical views.
- **A view belongs to a thread, not to the nav.** Established this week, and
  the reason the home screen was returning 400 on every load. The four views
  are opened from a visit and are not destinations.
- **The scribe leaks, twice.** The SDK prints the audio filename and builds
  exceptions from the audio path, so every call goes through `scribe.sdk()` and
  every message leaves through `_scrub`. Any new SDK gets the same treatment
  before its first call, not after.
- **Two engines.** `scripts/check_go_parity.py` asserts the Python and Go
  kernels name exactly the same routes. Any new route is written twice.
- **Tokens.** `tokens.css` is the only file in `web/src` that may name a
  colour, `color-mix` included.

## 6. Approaches considered

### For files: where does the document live?

**A. Eka's Medical Records Web SDK, in the browser. ← recommended**
`@eka-care/medical-records-ts-sdk`. Offline-first, caches to IndexedDB, retries
a failed upload on the next `sync()`, and runs in a browser. `addDocument` takes
the file, a document type, a date and a list of **cases** — and a case is a
folder a record can belong to several of, which is exactly a visit. Listing,
downloading, editing and deleting are all in the same SDK, so the Files view is
reads from one object. An upload also creates a care context, so the document
is discoverable over ABDM without us doing anything.

*Trades off:* the document is in Eka, not in our SQLite, so the kernel cannot
see it and a facility running the kernel alone has no files. It also needs a
business id and a patient id (`oid`) that we do not currently hold, and it
needs the session that only exists on an eka.care host — so files do not work
on localhost, like the rest of the gate.

**B. Our own attachment table, files on local disk.**
Works offline and on localhost, and the kernel can see the file. But it makes
us a records system: storage, retention, access control, deletion, a PHI
backup story, and a second copy of a document Eka already holds. For a PHC
pilot this is a liability, not a feature, and it is explicitly the thing the
owner said not to build ("like it was done in claims" means use the SDK).

**C. Presigned-URL APIs directly** (`POST /mr/api/v1/docs`, then the signed PUT).
The same destination as A with none of the offline queue, retry or cache. The
SDK exists so that we do not write that twice.

**Recommendation: A.** With one deliberate consequence: **uploading requires a
signed-in Eka session, and the Files view says so plainly when there is none**,
rather than failing quietly. This is the same honesty the sign-in screen
already practises about the cookie.

### For the views: what is a view?

**A. A fifth rail panel each.** Cheapest. Rejected: 280px is why we are here.

**B. A declared view kind.** Add `files` / `chat` to the kernel's view kinds so
the bundle declares them. Rejected for now: the kernel has no document and no
private conversation, so it would be declaring something it cannot serve. The
declaration should follow the capability, not precede it.

**C. A thread-local overlay with the width of the page. ← recommended**
One component, `thread/Side.tsx`, that opens over the right-hand rail and takes
its width — roughly 480px, and the full page under 900px. Four tabs across its
head, each a plain renderer concern rather than a clinical one, which keeps
`ui.check.ts` satisfied. Opened from the thread's own head and from the
composer's `/`; closed with Escape; remembered per person like the rail is.

## 7. The shape, as decided

**Files into the record.**

1. `web/src/records/sdk.ts` — the single wrapper. Every SDK call goes through
   it; every message out goes through a `_scrub` of the same kind the scribe
   has, because a filename is a patient's name more often than not.
2. `web/src/records/upload.ts` — takes a `File` and a visit, resolves the
   patient's `oid` and the case for this visit, calls `addDocument`, returns a
   receipt.
3. The composer gains a paperclip and accepts a drop onto the thread. The
   thread shows **one line**: who added what, and the file's name. Tapping it
   opens the Files view with that document selected.
4. A visit becomes a **case** the first time a file is added to it, so the
   patient's file shows the documents grouped by visit without us storing a
   grouping of our own.

**The four views.** Each is a tab in `thread/Side.tsx`:

- **Scribe** — what the microphone heard, the draft it produced, and the field
  it mapped to. Today this is a bar over the composer with no room to check a
  number; it is the one view a doctor will actually read before signing.
- **Files** — this patient's records from the SDK, this visit's first, the rest
  under it. Read a report without leaving the visit.
- **Ask about this patient** — the private doctor-to-agent conversation. Not in
  the thread, because the thread is the handover record and a doctor thinking
  out loud is not a handover. **Open question: is it kept? (§8.3)**
- **Previous visits** — `Past.tsx`'s data with room to compare, replacing the
  trend card rather than duplicating it.

**What leaves the thread.** The trend panel and the scribe bar both move into
views. That is the part that makes the thread shorter.

## 8. Decisions I am not making

These change what gets built, so they are the owner's.

1. **Does a file need a signed-in Eka session to be added?** Approach A says
   yes, and so files do nothing on a developer's machine and nothing at a
   centre whose session has lapsed. The alternative is B, and B makes us a
   records system. I recommend A and saying so on screen.
2. **Which document types does the picker offer?** The SDK wants one per
   upload. Offering all of Eka's is a menu; offering four is a judgement about
   a PHC's work. I would like the list to come from the bundle, like everything
   else clinical, which means a small declaration rather than a renderer array.
3. **Is the private agent chat kept, and who can read it?** Three answers, all
   defensible: not kept at all (safest, and it disappears when the page
   reloads); kept per person and per patient in this browser; kept in the
   kernel beside the visit, where it is discoverable and therefore disclosable.
   It is a clinical-record question, not a storage one.
4. **Does a photo taken at the bedside go in?** The camera is the obvious way a
   PHC adds a document, and it is also the fastest way to put an unconsented
   photograph into a national health record. I would ship file-pick first and
   camera only once there is an answer about consent.

## 9. Order of work

Each step leaves the gate green and the app usable.

1. **Move the station and tag filters into panel two.** Carried over, and
   first because it touches `screens/ListScreen.tsx`, whose seven assertions in
   `ui.check.ts` must be repointed. Doing it before the thread work means the
   shell is settled when the views land.
2. **`thread/Side.tsx` with two tabs: Previous visits and Scribe.** No new
   dependency, no new route, no open question. Proves the surface.
3. **The records SDK wrapper and its scrub**, with a test that a filename
   never reaches a log.
4. **Upload from the composer, and the Files view.** Needs §8.1 and §8.2.
5. **Ask about this patient.** Needs §8.3.

## 10. What is left to the builder

Tab order and the remembered-tab key; the exact width and the breakpoint at
which the view becomes the page; the empty state of each view; whether the
paperclip sits beside the microphone or inside `/`. None of these change what
the thing is.
