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

**C. Tabs across the top of the visit, the way a channel has them. ← built**
Owner, on a screenshot of a channel's own tab row: *"all of these should be
tabs, records, scribe, etc."* So the conversation is not the screen; it is
the FIRST TAB of the screen, and each tab takes the card's full width. One
component, `thread/Tabs.tsx`, draws the row and nothing else — the tabs and
the body under them both come from the screen above, which is how a surface
stays clean of anything `ui.check.ts` forbids this renderer to name.

An earlier draft of this note proposed a panel beside the thread instead.
That was wrong for the same reason the old inline draft was: it rationed
width. A tab does not.

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

- **What was heard — the canvas.** Owner's words, 2026-11-02: *"when someone starts
  scribe it also opens in another view within the session like canvas, with
  the live audiowave at the center and transcription."* So this is not a
  panel that appears after the recording; it is where the recording happens.
  Pressing the microphone opens it. Three things, in this order down the page:

  1. **The waveform, centred and live.** It is the one thing on the screen
     that proves the microphone is working, which a bar saying "Listening"
     does not — a dead microphone says "Listening" too. Drawn from the audio
     we are already capturing, through the Web Audio API, with no new
     dependency and nothing extra sent anywhere.
  2. **The transcription, as it arrives.** Corrected 2026-11-03 after
     reading the scribe backend: the streaming socket is upload-only and
     sends nothing back. But a chunk's transcript is fetchable the moment
     that chunk is transcribed, which happens while the consultation is
     still going on, and each generated document announces itself
     separately. So real words can appear during the recording — by
     polling per chunk, not by a stream, and the screen should not pretend
     otherwise. See `2026-11-03-eka-scribe-backend-notes.md`.
  3. **The draft, and the field each value mapped to**, which the doctor
     reads and signs. Today it is a form in a 42vh letterbox under the
     conversation; here it has the width of the view.

  The waveform, the transcript and the draft are all buildable now. What
  the screen must not do is imply a live stream when what is happening is
  a poll each time a chunk is cut.
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

## 8a. The scribe delay, and why the canvas needs it fixed

Measured, not assumed: 25 to 52 seconds of Eka processing for 92 seconds of
audio, and the upload of the whole file happens only after recording stops,
through our server, twice over the wire.

Three separate costs, and the canvas is blocked on the third:

1. **Nothing is sent until the doctor stops talking.** `MediaRecorder` is
   started with no timeslice, so the first byte leaves after the last word.
2. **It travels twice** — browser to our API, our API to Eka.
3. **We show nothing until the structured note is finished**, and we find out
   by asking every three seconds.

Eka's current API fixes all three: chunked upload during recording, the raw
transcript the moment recording ends, a streaming mode, and a notification
instead of polling. The cost of moving is real and is named in §11.

## 9. Order of work

Each step leaves the gate green and the app usable.

1. **Move the station and tag filters into panel two.** Carried over, and
   first because it touches `screens/ListScreen.tsx`, whose seven assertions in
   `ui.check.ts` must be repointed. Doing it before the thread work means the
   shell is settled when the views land.
2. ~~**The tab row, with Messages, What was heard and Earlier visits.**~~
   **Done, 2026-11-02.** The recorder and its drafts left the foot of the
   thread; earlier visits gained a page that shows each visit's values. Next
   on this tab: the waveform and the transcript area.
3. **The records SDK wrapper and its scrub**, with a test that a filename
   never reaches a log.
4. **Upload from the composer, and the Files view.** Needs §8.1 and §8.2.
5. **Ask about this patient.** Needs §8.3.

## 10. What is left to the builder

Tab order and the remembered-tab key; the exact width and the breakpoint at
which the view becomes the page; the empty state of each view; whether the
paperclip sits beside the microphone or inside `/`. None of these change what
the thing is.
