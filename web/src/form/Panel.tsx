/** The commit surface, and the proposal review surface, which are the same
 *  screen because they must be.
 *
 *  A proposal is a write a machine wants: an agent over MCP, or an instrument
 *  that heard a number. Nothing it contains reaches the store until a person
 *  reads it here, in editable fields, and taps. The payload that is sent is
 *  the payload on screen after their edits, not the one proposed, and the
 *  original stays visible so the difference is not hidden.
 *
 *  For an irreversible operation the confirm is a second stage with an empty
 *  box that nothing prefills, and any edit empties it again. The guard denies
 *  an irreversible write from any surface but this one and denies it again
 *  without `confirmed`, so this screen is the only way through, on purpose.
 *
 *  `inline` draws the same screen inside the thread instead of over it, which
 *  is where a proposal belongs: a card the person reads, edits and confirms
 *  without leaving the conversation the agent proposed it in. Only the chrome
 *  differs. The payload, the validation, the diff, the confirm stage and the
 *  single client call below are the same ones the modal uses.
 */
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { ABHA_PENDING, demographicsFrom, payloadFor, runsJourney, type AbhaOutcome } from "../abha/sdk";
import { Journey } from "../abha/Journey";
import { ApiError, type Client } from "../api";
import { Form, labelled, validate } from "./Form";
import { walk } from "../validate";
import { trapTab } from "../parts";
import { questionnaire } from "../declarations";
import { fmt } from "../messages";
import type { Operation, Payload, Proposal } from "../types";
import { say } from "../announce";
import { Failed } from "../parts";
import { human } from "../words";
import { type ScribeDraft } from "../scribe/session";
import { mountsFor } from "../voice/instruments";
import { VoiceCapture } from "../voice/VoiceCapture";
import { Scan } from "../paper/Scan";
import { useDictation } from "../scribe/useDictation";
import { DictateBar } from "../scribe/DictateBar";
import { Box } from "../ui/Check";
import { dictateKey } from "../scribe/dictate";

const IRREVERSIBLE = "irreversible";

/** The chip under a field the journey filled. Two words, because the point is
 *  that this was not typed here, and the field's own highlight already says
 *  read me again. */
const FROM_ABHA = "From ABHA";

export function OperationPanel({
  op, thread, client, proposal, draft, instruments, inline, mobile, seed, start, found,
  amending, onDone, onCancel,
}: {
  /** This is a CORRECTION to what this operation already recorded on this
   *  visit, not a new record. The form is the same form; what changes is
   *  that the kernel replaces the rows instead of adding a second set. */
  amending?: boolean;
  op: Operation;
  thread: string;
  /** A mobile number the clerk has already typed, from the search that missed.
   *  Handed to the journey so nobody types it twice; a hint, never an answer on
   *  this form. */
  mobile?: string;
  /** Answers this panel opens with, already obtained rather than typed. The
   *  ABHA link panel gets one of these when the journey ran during
   *  registration: the identifier is known, so asking for the journey a second
   *  time would be asking the patient for a second one time password. */
  seed?: Payload;
  /** WHAT THE CLERK HAS ALREADY TYPED, carried into the fields.
   *
   *  Not a seed, and the difference is the whole reason it is a second prop.
   *  A seed is somebody the desk FOUND, and finding them is exactly what
   *  stops the national identity journey running. What a clerk typed into a
   *  search box is not a person anybody has found: the journey still has to
   *  run, because that is where a new patient's name and address come from
   *  instead of the keyboard.
   *
   *  Carrying it was the mockup's own promise on that row -- "keeps what you
   *  typed as the name" -- and it was broken: the typed name reached the row,
   *  the row would not hand it over as a seed in case the journey stopped,
   *  and the form opened empty. A clerk typed the name twice.
   *
   *  Nothing marks these values as coming from anywhere, because they came
   *  off this clerk's own keyboard thirty seconds ago. */
  start?: Payload;
  /** Where the seed came from, when it did not come from the ABHA journey.
   *
   *  The front desk seeds this form from somebody it FOUND: a row this centre
   *  already holds, or a profile the patient directory suggested. Those
   *  values are not ABHA's and must not say they are, so the chip under each
   *  field is this sentence instead. `evidence` is the field the match was
   *  made on, which kernel/directory.py puts beside every suggested value for
   *  exactly this reading, and `confidence` is the kernel's own cap -- it sits
   *  under the form's SURE threshold on purpose, so a directory match draws
   *  unconfirmed and gets read rather than waved through.
   *
   *  Supplying a seed at all is also what stops the identity journey running:
   *  spending a one time password to learn what is already on the screen is
   *  the registration-costs-as-much-with-ABHA-as-without anti-goal, and it is
   *  NHA's own test of whether the ABHA step is in the right place. */
  found?: {
    source: string;
    evidence?: Record<string, string>;
    confidence?: Record<string, number>;
  };
  /** Drawn inside the thread rather than over it. No Cancel: there is nothing
   *  to close, the card is the conversation. */
  inline?: boolean;
  /** The compiled instrument declarations. Which capture controls appear on
   *  this screen is entirely their answer, never this file's. */
  instruments?: Record<string, unknown>;
  /** The thread's flags. Unused since the encounter took the scribe's consent
   *  gate; kept so callers need not change. */
  flags?: string[];
  /** Whichever kernel this screen is talking to. The panel does not know or
   *  care which, so demo mode cannot write to a real store by accident. */
  client: Client;
  proposal?: Proposal;
  /** What a recording drafted for this operation. Its values open in the
   *  fields like any other answer, and every non-text one needs a tick before
   *  Commit: a heard number is not committed on the strength of the audio. */
  draft?: ScribeDraft;
  /** `carried` is what this commit learned that the NEXT panel needs: the ABHA
   *  identifier, when the journey ran on this screen. */
  onDone: (carried?: Payload) => void;
  onCancel?: () => void;
}) {
  const schema = questionnaire(op.input);
  const [payload, setPayload] = useState<Payload>({ ...(proposal?.payload ?? draft?.values ?? seed ?? start ?? {}) });
  /** A reading spoken into THIS panel, as against one the encounter handed
   *  down in `draft`. Both are the same thing from the same service, and this
   *  is what draws the words beside each value it filled.
   *
   *  A heard value used to owe a tick of its own before Commit would light.
   *  The owner removed that on 2026-11-01: the value is in an editable field,
   *  so a wrong one is corrected by typing over it. What is left is what the
   *  field shows -- drawn unconfirmed, with the words it came from -- and the
   *  one tap on Commit that every typed answer goes through. */
  const [spoken, setSpoken] = useState<ScribeDraft | null>(null);
  const heardDraft = spoken ?? draft ?? null;
  /** Per link_id, how sure the instrument that produced the value was. A
   *  value under 0.9 draws the field as unconfirmed. Typing over a value
   *  clears its entry: a number a person typed is not a heard number. */
  const [heard, setHeard] = useState<Record<string, number>>(draft?.confidence ?? found?.confidence ?? {});
  /** Which fields came back from the ABHA journey rather than off the keyboard.
   *  Marked on the form the same way an instrument's values are, and cleared
   *  field by field the moment somebody types over one. */
  const [fromAbha, setFromAbha] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.keys(seed ?? {}).map((id) => [id, found?.source ?? FROM_ABHA])),
  );
  /** The identifier this screen's journey produced, handed to whoever opens
   *  the next panel. Never committed from here: registration does not write an
   *  ABHA number, the link operation does. */
  const [carried, setCarried] = useState<Payload | undefined>(undefined);
  const [tried, setTried] = useState(false);
  const [stage, setStage] = useState<"edit" | "confirm">("edit");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  /** Whether the ABHA journey below has handed back an identifier. Declared
   *  with the other hooks and not beside the flag that reads it, because the
   *  "no questionnaire" branch above returns early. */
  const [journeyDone, setJourneyDone] = useState(false);
  // Two of these are on screen whenever a thread holds two pending proposals.
  const ids = useId();
  const [error, setError] = useState<ApiError | null>(null);
  /** Whether the keyboard has already been moved into this panel.
   *
   *  A callback ref and not an effect, and that is not a style preference:
   *  voice.check.ts asserts this file contains no effect and no timer at all,
   *  because the one thing that may reach a write here is a tap or the Enter
   *  key. Landing the focus on mount is done by the ref itself, which runs
   *  once, writes nothing, and leaves that property standing. */
  const landed = useRef(false);
  // Who had the keyboard before this covered the screen, and the box itself,
  // so Tab can be held inside it.
  const opener = useRef<HTMLElement | null>(null);
  const box = useRef<HTMLElement | null>(null);

  /** THE REF ITSELF HAS TO BE STABLE, AND THAT IS NOT A STYLE POINT.
   *
   *  React detaches and re-attaches a ref whose callback is a NEW FUNCTION on
   *  every render, which an inline arrow is. So this panel ran its "closing"
   *  branch and its "opening" branch once per keystroke: `opener.current` was
   *  refocused, `landed` was reset, and `el.focus()` moved the keyboard back
   *  onto the dialog box. The visible effect was that a clerk could type ONE
   *  character into a field and then found themselves typing into nothing --
   *  on every field, of every operation, on every screen that opens a panel.
   *  The guard above was written to prevent exactly this and could never
   *  fire, because the branch that resets it ran first every time.
   *
   *  `useCallback` with a stable identity is what makes the guard mean what
   *  it says: attached once when the panel opens, called with null once when
   *  it closes. It is not an effect and it is not a timer, so the property
   *  voice.check.ts asserts about this file still holds.
   */
  const landing = useCallback((el: HTMLElement | null) => {
    if (inline) return;
    if (!el) {
      // Closing. Whoever opened this gets the keyboard back; without this the
      // focus is left on a node React has already removed and the next Tab
      // starts again at the top of the document.
      opener.current?.focus();
      opener.current = null;
      landed.current = false;
      return;
    }
    if (landed.current) return;
    landed.current = true;
    opener.current = document.activeElement as HTMLElement | null;
    el.focus();
    box.current = el;
  }, [inline]);

  const problems = useMemo(() => (schema ? validate(schema, payload) : []), [schema, payload]);

  if (!schema) {
    return (
      <div className={inline ? "mod inline" : "mod"}>
        <div className="mod-bar" />
        <div className="state">
        <div className="state-t">No questionnaire for {op.id}.</div>
        {onCancel && <button className="cq" onClick={onCancel}>Back</button>}
        </div>
      </div>
    );
  }

  const irreversible = op.irreversibility === IRREVERSIBLE;

  /** SPEAKING INTO WHATEVER FIELD HAS THE CURSOR, on every form in the
   *  product, because no form in this product may exist that cannot be
   *  filled by voice. Mounted here rather than on each screen for exactly
   *  that reason: a form that forgot to mount it would be a form you have to
   *  type into, and there would be nothing to see. */
  const dictation = useDictation({ thread, operation: op.id, enabled: !busy });

  /** The ABHA operation is the one form in this product that is not a form.
   *  Its questionnaire is still what the kernel validates, but every answer
   *  comes back from Eka's own journey rather than being typed, so the fields
   *  are a readback and they do not appear until there is something to read
   *  back. Reviewing a proposal is the exception and keeps the plain form: a
   *  proposal is a payload somebody else produced, and re-running a national
   *  identity journey is not how you read one.
   *
   *  The guard refuses this operation to every surface but this one and
   *  refuses it again without `confirmed`, so nothing here shortens the path:
   *  the journey fills the fields, and the tap below is still the write.
   *
   *  A registration is the other screen it belongs on, and which operation
   *  that is, is the bundle's own answer: `abha.pending` is what an operation
   *  emits when it has just made a patient who has no national account yet.
   *  The health centre's registration says it, the laboratory's accession does
   *  not, and neither file mentions the other. There the journey fills the
   *  demographics; on the link panel, the identifier. The order is the point:
   *  a clerk should not type a name and a mobile that ABDM already holds. */
  const registration = !!op.emits?.includes(ABHA_PENDING);
  // The rule itself lives in abha/sdk.ts, where a check can run it. See
  // runsJourney for why: inverting it here is invisible to every text check
  // and costs a patient a one time password they did not need to spend.
  const mountsJourney = runsJourney(op.id, op.emits, { reviewing: !!proposal, found: !!seed });
  const showForm = !mountsJourney || journeyDone;
  const invalidate = () => {
    setConfirmed(false);           // an edit invalidates a confirm, always
    if (stage === "confirm") setStage("edit");
  };
  /** A value somebody typed over is theirs, whatever produced it first. Both
   *  marks are dropped per field, not wholesale. */
  const untouched = <T,>(was: Record<string, T>, next: Payload) =>
    Object.fromEntries(
      Object.entries(was).filter(([id]) => String(next[id] ?? "") === String(payload[id] ?? "")),
    );
  const edit = (next: Payload) => {
    setPayload(next);
    setHeard((was) => untouched(was, next));
    setFromAbha((was) => untouched(was, next));
    invalidate();
  };

  /** What an instrument produced. It lands in the same editable fields a
   *  person types into and it is committed by the same tap. There is no other
   *  path from here: this sets state, and state is not a write. */
  const fromInstrument = (heardNow: ScribeDraft) => {
    setPayload((was) => ({ ...was, ...heardNow.values }));
    setHeard((was) => ({ ...was, ...heardNow.confidence }));
    setSpoken(heardNow);
    invalidate();
  };

  /** What the ABHA journey produced. Same fields, same tap, and no instrument
   *  confidence attached: this value was returned by a gateway, not heard by a
   *  recogniser, and marking it "unsure" would be as untrue as marking it
   *  certain. It is marked with where it came from instead. */
  const fromJourney = (values: Record<string, unknown>) => {
    setPayload((was) => ({ ...was, ...values }));
    setFromAbha((was) => ({
      ...was,
      ...Object.fromEntries(Object.keys(values).map((id) => [id, FROM_ABHA])),
    }));
    invalidate();
  };
  const mounts = mountsFor(instruments, op, schema);

  const send = async () => {
    setTried(true);
    if (problems.length) return;
    if (irreversible && !confirmed) {
      setStage("confirm");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (proposal) await client.confirm(proposal.id, { payload, confirmed });
      else if (amending) await client.amend(op.id, { thread, payload, confirmed });
      else await client.commit(op.id, { thread, payload, confirmed });
      // SC 4.1.3: the panel closes and a row appears somewhere else on the
      // screen. Seeing that is how a sighted clerk knows the write landed;
      // everybody else was told nothing at all.
      say(`Saved: ${op.title}.`);
      onDone(carried);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), "This is a bug in the renderer."));
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      await client.reject(proposal.id, {});
      say(`Rejected: ${op.title}. Nothing was written.`);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), "This is a bug in the renderer."));
    } finally {
      setBusy(false);
    }
  };

  // What a person still owes this form before it can be sent. Shown before
  // they have tried, because a machine filled this in and the gap it left is
  // the first thing to say about it, not a scolding after the tap.
  const labels = new Map(labelled(schema, payload).map(([id, text]) => [id, text]));
  // One name per thing that is missing. A repeating group answers for every
  // sub field of its empty row and every one of those problems carries the
  // GROUP's link_id, so a blank prescription read "Missing: medications,
  // medications, medications, medications, medications, medications,
  // medications" in red above a form nobody had touched yet.
  const missing = [...new Set(
    problems
      .filter((p) => p.message.endsWith("is required"))
      .map((p) => labels.get(p.link_id) ?? p.link_id),
  )];

  /** Whether a MACHINE put anything in these fields: a proposal, a recording,
   *  a record the desk found, or the national journey. Only then is the list
   *  of what is still empty worth drawing before anybody has tried, because
   *  then it is a report on what the machine left out. On a form nobody has
   *  touched it is not that at all: it is five red words telling a clerk off
   *  for not having typed yet, which is the opposite of what this screen is
   *  for. What the clerk themselves typed into the search box does not count:
   *  they know what they typed. */
  const prefilled = !!proposal || !!draft || !!seed || Object.keys(fromAbha).length > 0;

  const changed = proposal
    ? labelled(schema, payload).filter(([id]) => String(proposal.payload?.[id] ?? "") !== String(payload[id] ?? ""))
    : [];

  return (
    <div
      /* A modal with nothing to say it is one. Opened from a quick action,
         focus stayed on the button behind the scrim, so Escape -- which is
         handled right here -- did nothing, and a screen reader was never
         taken to the thing that had just covered the screen. The inline
         variant is not a modal and does not pretend to be. */
      ref={landing}
      tabIndex={inline ? undefined : -1}
      role={inline ? undefined : "dialog"}
      aria-modal={inline ? undefined : true}
      aria-label={inline ? undefined : op.title}
      className={inline ? "mod inline" : "mod"}
      onKeyDown={(e) => {
        if (e.key === "Escape") { e.preventDefault(); onCancel?.(); return; }
        if (!inline) trapTab(e, box.current);
        // Enter commits, except inside a textarea, where it is a newline. A
        // consultation note committed because someone pressed return
        // mid-sentence is worse than one extra tap.
        const inText = (e.target as HTMLElement)?.tagName?.toLowerCase() === "textarea";
        if (e.key === "Enter" && !inText && !busy) { e.preventDefault(); void send(); }
      }}
    >
      <div className="mod-bar" />
      <div className="mod-h">
        {/* Title only. The eyebrow said "New entry" on every panel there is,
            and the summary restated the title over the fields it describes.
            No taxonomy badge either: the instrument is either on the panel
            or it is not, and an irreversible operation says so by making you
            do it twice (the confirm stage below), not by a word beside the
            title. */}
        {/* A FORM SAYS WHAT IT IS, wherever it is drawn. Inline used to be
            silent, which was right while the only inline form was a
            proposal sitting under a sentence that had just named it. Now
            every form opens inline, including one somebody chose from a row
            of eight actions, and an unnamed form is a form you have to
            infer from its fields. */}
        <div className={inline ? "mod-t mod-t-in" : "mod-t"}>{op.title}</div>
      </div>

      <div className="mod-b">

        {proposal?.transcript && (
          <div className="provenance">
            <div className="transcript">"{proposal.transcript}"</div>
          </div>
        )}


        {/* The camera, above the fields it fills. A declaration decides
            whether it is there at all; see paper/Scan.tsx. */}
        {showForm && (
          <Scan mounts={mounts} operation={op.id} disabled={busy}
                onDraft={fromInstrument} />
        )}

        <VoiceCapture
          mounts={mounts.filter((m) => m.kind !== "scribe" && m.kind !== "document")}
          operation={op.id}
          thread={thread}
          payload={payload}
          disabled={busy}
          ids={ids}
          onDraft={fromInstrument}
        />

        {/* Gone the moment the form is showing. What is left of it by then is
            a stale note and a button that would do what has already happened,
            and a control that does nothing is how a person learns to distrust
            the ones that do. The SDK tears its own root down on every terminal
            outcome, and on a failure it never mounted one. */}
        {mountsJourney && !journeyDone && (
          <Journey
            mobile={mobile}
            /* On the link panel the way out is to close it. On a registration
               panel it is to reveal the empty form underneath, which is the
               whole of "register now, link later" and is also what a clerk
               gets when the SDK will not load at all. */
            onSkipPath={registration ? () => setJourneyDone(true) : onCancel}
            onOutcome={(outcome: AbhaOutcome) => {
              if (outcome.kind !== "linked") {
                // A skipped, closed or failed journey fills nothing. On a
                // registration panel the form still opens, empty, and the
                // patient is registered ABHA pending as before.
                if (registration) setJourneyDone(true);
                return;
              }
              // Straight into the same editable fields a person used to type
              // into. Which answers those are is the operation's: the link
              // panel takes the identifier and nothing else, a registration
              // form takes the demographics the profile actually carried and
              // leaves every field it did not empty.
              const filled = registration
                ? demographicsFrom(outcome.raw, walk(schema.questions))
                : payloadFor(outcome);
              fromJourney(filled);
              // The identifier is not registration's to write. It is handed to
              // whoever opens the link panel next, so the patient is not asked
              // for a second one time password to say what is already known.
              const id = payloadFor(outcome);
              if (registration && id.abha_number) setCarried(id as Payload);
              setJourneyDone(true);
            }}
          />
        )}

        {showForm && prefilled && missing.length > 0 && !tried && (
          <div className="missing">Missing: {missing.join(", ")}</div>
        )}

        {showForm && <Form
          schema={schema}
          op={op}
          ids={ids}
          value={payload}
          onChange={edit}
          problems={tried ? problems : []}
          confidence={{ ...(proposal?.confidence ?? {}), ...heard }}
          sources={fromAbha}
          evidence={heardDraft?.evidence ?? found?.evidence}
          disabled={busy}
        />}

        {proposal && changed.length > 0 && (
          <div className="diff">
            <div className="eyebrow">You changed</div>
            {changed.map(([id, text]) => (
              <div key={id}>
                {text}: <s>{fmt(proposal.payload?.[id]) || "empty"}</s> to{" "}
                <b>{fmt(payload[id]) || "empty"}</b>
              </div>
            ))}
          </div>
        )}

        {stage === "confirm" && (
          <div className="confirmbox">
            <div className="card-t">This cannot be undone</div>
            <label className="f-check big">
              <Box checked={confirmed} disabled={busy} onChange={setConfirmed} />
              <span>I have read the values above and I am doing this.</span>
            </label>
          </div>
        )}

        {tried && problems.length > 0 && (
          <div className="f-bad block">
            {problems.length} thing{problems.length === 1 ? "" : "s"} to fix.
          </div>
        )}

        {error && <Failed error={error} what="Not saved" onRetry={() => setError(null)} />}
      </div>

      {heardDraft && heardDraft.unfilled.length > 0 && (
        <div className="f-hint">Heard but not filled: {heardDraft.unfilled.map((id) => labels.get(id) ?? id).join(", ")}</div>
      )}
      <div className="mod-f">
        {/* THE SHORTCUT, SAID OUT LOUD. A gesture nobody can discover is a
            gesture nobody uses, and this is a product whose whole claim is
            that you speak rather than type. It sits on the form's own foot
            rather than on every field, because it is one fact about the
            product and not a control per box.

            A browser that cannot record says nothing here rather than
            advertising a key that would do nothing. */}
        {dictation.supported && (
          <span className="dict-tip">
            <span className="kbd">{dictateKey()}</span>
            hold to speak into any field
          </span>
        )}
        <span style={{ flex: 1 }} />
        {onCancel && <button className="cq" onClick={onCancel} disabled={busy}>Cancel</button>}
        {proposal && (
          <button className="cq" onClick={reject} disabled={busy}>Reject</button>
        )}
        {showForm && <button
          className="cq rose"
          onClick={send}
          disabled={busy || (stage === "confirm" && !confirmed)}
        >
          {busy ? "Sending..." : stage === "confirm" ? "Commit" : proposal ? "Confirm" : irreversible ? "Continue" : "Commit"}
        </button>}
      </div>
      <DictateBar state={dictation.state} onDismiss={dictation.dismiss} />
    </div>
  );
}

export function proposalOperation(p: Proposal, ops: Record<string, Operation>): Operation {
  return (
    ops[p.operation] ?? {
      id: p.operation, kind: "write", short: human(p.operation), title: human(p.operation),
      summary: "This operation is not in the catalogue this renderer loaded.",
      capability: "", station: "", instrument: "form", preconditions: [],
      irreversibility: "irreversible", input: "", writes: [], emits: [],
      verified: "unverified", tool: "", description: "",
    }
  );
}
