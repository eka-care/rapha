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
import { useId, useMemo, useState } from "react";
import { ABHA_OP, ABHA_PENDING, demographicsFrom, payloadFor, type AbhaOutcome } from "../abha/sdk";
import { Journey } from "../abha/Journey";
import { ApiError, type Client } from "../api";
import { Form, labelled, validate } from "./Form";
import { walk } from "../validate";
import { questionnaire } from "../declarations";
import { fmt } from "../messages";
import type { Operation, Payload, Proposal } from "../types";
import { Failed } from "../parts";
import { human } from "../words";
import { Recorder } from "../scribe/Recorder";
import { mountsFor } from "../voice/instruments";
import { VoiceCapture } from "../voice/VoiceCapture";
import { SpokenPrompt } from "../voice/SpokenPrompt";

const IRREVERSIBLE = "irreversible";

/** The chip under a field the journey filled. Two words, because the point is
 *  that this was not typed here, and the field's own highlight already says
 *  read me again. */
const FROM_ABHA = "From ABHA";

export function OperationPanel({
  op, thread, client, proposal, instruments, flags, inline, mobile, seed, onDone, onCancel,
}: {
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
  /** Drawn inside the thread rather than over it. No Cancel: there is nothing
   *  to close, the card is the conversation. */
  inline?: boolean;
  /** The compiled instrument declarations. Which capture controls appear on
   *  this screen is entirely their answer, never this file's. */
  instruments?: Record<string, unknown>;
  /** The thread's flags, because the scribe declaration gates on one. */
  flags?: string[];
  /** Whichever kernel this screen is talking to. The panel does not know or
   *  care which, so demo mode cannot write to a real store by accident. */
  client: Client;
  proposal?: Proposal;
  /** `carried` is what this commit learned that the NEXT panel needs: the ABHA
   *  identifier, when the journey ran on this screen. */
  onDone: (carried?: Payload) => void;
  onCancel?: () => void;
}) {
  const schema = questionnaire(op.input);
  const [payload, setPayload] = useState<Payload>({ ...(proposal?.payload ?? seed ?? {}) });
  /** Per link_id, how sure the instrument that produced the value was. A
   *  value under 0.9 draws the field as unconfirmed. Typing over a value
   *  clears its entry: a number a person typed is not a heard number. */
  const [heard, setHeard] = useState<Record<string, number>>({});
  /** Which fields came back from the ABHA journey rather than off the keyboard.
   *  Marked on the form the same way an instrument's values are, and cleared
   *  field by field the moment somebody types over one. */
  const [fromAbha, setFromAbha] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.keys(seed ?? {}).map((id) => [id, FROM_ABHA])),
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
  const mountsJourney = !proposal && !seed && (op.id === ABHA_OP || registration);
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
  const fromInstrument = (values: Record<string, unknown>, confidence: Record<string, number>) => {
    setPayload((was) => ({ ...was, ...values }));
    setHeard((was) => ({ ...was, ...confidence }));
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
      else await client.commit(op.id, { thread, payload, confirmed });
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
  const missing = problems
    .filter((p) => p.message.endsWith("is required"))
    .map((p) => labels.get(p.link_id) ?? p.link_id);

  const changed = proposal
    ? labelled(schema, payload).filter(([id]) => String(proposal.payload?.[id] ?? "") !== String(payload[id] ?? ""))
    : [];

  return (
    <div
      className={inline ? "mod inline" : "mod"}
      onKeyDown={(e) => {
        if (e.key === "Escape") { e.preventDefault(); onCancel?.(); return; }
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
        {!inline && <div className="mod-t">{op.title}</div>}
      </div>

      <div className="mod-b">

        {proposal?.transcript && (
          <div className="provenance">
            <div className="transcript">"{proposal.transcript}"</div>
          </div>
        )}

        {/* The consent line. Rendered whenever the form below carries the
            fields it names, whatever `spoken` resolves to: a failed or
            absent utterance must never be the only place a patient was told
            anything. See web/src/voice/SpokenPrompt.tsx. */}
        {mounts.filter((m) => m.kind === "spoken-prompt").map((m) => (
          <SpokenPrompt key={m.id} mount={m as Extract<typeof m, { kind: "spoken-prompt" }>} />
        ))}

        <VoiceCapture
          mounts={mounts.filter((m) => m.kind !== "scribe" && m.kind !== "spoken-prompt")}
          operation={op.id}
          payload={payload}
          disabled={busy}
          ids={ids}
          onValues={fromInstrument}
        />

        {/* The scribe, which is a recording and not a microphone in this
            browser, so it is drawn by its own component with its own bar. It
            appears only where the declaration allows it AND the visit carries
            whatever flag that declaration REQUIRES; without it the reason is
            said in words and the keyboard below is the whole of the fallback.
            The flag is `requires:` on the instrument, not a constant in this
            renderer: the health centre's consent flag used to be written here,
            which gated nothing in a bundle that spells its own differently.
            The kernel refuses it a second time besides, which is the check
            that counts. */}
        {mounts.filter((m) => m.kind === "scribe").map((m) =>
          (!m.requires || (flags ?? []).includes(m.requires)) ? (
            <Recorder
              key={m.id}
              mount={m as Extract<typeof m, { kind: "scribe" }>}
              thread={thread}
              operation={op.id}
              schema={schema}
              payload={payload}
              ids={ids}
              disabled={busy}
              onValues={fromInstrument}
            />
          ) : (
            <div className="v-row" key={m.id}>
              <span className="v-off">Scribe off</span>
              <div className="f-hint">No capture consent.</div>
            </div>
          ),
        )}

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

        {showForm && missing.length > 0 && !tried && (
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
              <input type="checkbox" checked={confirmed} disabled={busy}
                     onChange={(e) => setConfirmed(e.target.checked)} />
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

      <div className="mod-f">
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
