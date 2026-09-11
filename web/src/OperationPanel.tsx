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
import { ABHA_OP, payloadFor, type AbhaOutcome } from "./abha/sdk";
import { Journey } from "./abha/Journey";
import { ApiError, type Client } from "./api";
import { Form, labelled, validate } from "./Form";
import { questionnaire } from "./declarations";
import { CONSENT, fmt } from "./messages";
import type { Operation, Payload, Proposal } from "./types";
import { Badge, Failed, human } from "./ui";
import { Recorder } from "./scribe/Recorder";
import { mountsFor } from "./voice/instruments";
import { VoiceCapture } from "./voice/VoiceCapture";

const IRREVERSIBLE = "irreversible";

export function OperationPanel({
  op, thread, client, proposal, instruments, flags, inline, onDone, onCancel,
}: {
  op: Operation;
  thread: string;
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
  onDone: () => void;
  onCancel?: () => void;
}) {
  const schema = questionnaire(op.input);
  const [payload, setPayload] = useState<Payload>({ ...(proposal?.payload ?? {}) });
  /** Per link_id, how sure the instrument that produced the value was. A
   *  value under 0.9 draws the field as unconfirmed. Typing over a value
   *  clears its entry: a number a person typed is not a heard number. */
  const [heard, setHeard] = useState<Record<string, number>>({});
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
        <p className="state-p">
          The operation names <b>{op.input}</b> as its input, and there is no such file in
          questionnaires/. Either the id is wrong in catalogue/ops/, or the form was never written.
        </p>
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
   *  the journey fills the fields, and the tap below is still the write. */
  const mountsJourney = op.id === ABHA_OP && !proposal;
  const showForm = !mountsJourney || journeyDone;
  const invalidate = () => {
    setConfirmed(false);           // an edit invalidates a confirm, always
    if (stage === "confirm") setStage("edit");
  };
  const edit = (next: Payload) => {
    setPayload(next);
    setHeard((was) =>
      Object.fromEntries(
        Object.entries(was).filter(([id]) => String(next[id] ?? "") === String(payload[id] ?? "")),
      ),
    );
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
      onDone();
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
    <div className={inline ? "mod inline" : "mod"}>
      <div className="mod-bar" />
      <div className="mod-h" style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
        <div>
          <div className="eyebrow">{proposal ? "Proposed, not recorded" : "New entry"}</div>
          <div className="mod-t" style={{ marginTop: 2 }}>{op.title}</div>
          <div className="mod-s">{op.summary}</div>
        </div>
        <div className="ml-auto" style={{ display: "flex", gap: 6 }}>
          <Badge>{op.instrument}</Badge>
          {irreversible && <Badge style="crit">irreversible</Badge>}
        </div>
      </div>

      <div className="mod-b">

        {proposal && (
          <div className="provenance">
            <div className="eyebrow">Where this came from</div>
            <div>
              {proposal.proposed_by ?? "An unattributed caller"} proposed this over{" "}
              <b>{proposal.surface}</b> at {proposal.created_at}. It has changed nothing.
              Read every value; the ones a machine is unsure of are marked.
            </div>
            {proposal.transcript && <div className="transcript">"{proposal.transcript}"</div>}
          </div>
        )}

        <VoiceCapture
          mounts={mounts.filter((m) => m.kind !== "scribe")}
          operation={op.id}
          payload={payload}
          disabled={busy}
          ids={ids}
          onValues={fromInstrument}
        />

        {/* The scribe, which is a recording and not a microphone in this
            browser, so it is drawn by its own component with its own bar. It
            appears only where the declaration allows it AND the visit carries
            capture consent; without the consent the reason is said in words and
            the keyboard below is the whole of the fallback. The kernel refuses
            it a second time besides, which is the check that counts. */}
        {mounts.filter((m) => m.kind === "scribe").map((m) =>
          (flags ?? []).includes(CONSENT) ? (
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
              <div className="f-hint">
                Capture consent is not recorded on this visit, so nothing is recorded. Ask the
                patient, record the consent, and {m.title.toLowerCase()} appears here. Type the note
                meanwhile: it is the same record, and declining is not a barrier to care.
              </div>
            </div>
          ),
        )}

        {mountsJourney && (
          <Journey
            onSkipPath={onCancel}
            onOutcome={(outcome: AbhaOutcome) => {
              if (outcome.kind !== "linked") return;
              // Straight into the same editable fields a person used to type
              // into, with no instrument confidence attached: this value was
              // returned by a gateway, not heard by a recogniser, and marking
              // it "unsure" would be as untrue as marking it certain. Only the
              // identifier: the journey does not know the other two answers and
              // this screen does not invent them.
              fromInstrument(payloadFor(outcome), {});
              setJourneyDone(true);
            }}
          />
        )}

        {showForm && missing.length > 0 && !tried && (
          <div className="missing">
            Still missing: {missing.join(", ")}. Fill {missing.length === 1 ? "it" : "them"} in below.
            Nothing is sent until you tap {irreversible ? "Continue" : proposal ? "Confirm" : "Commit"}.
          </div>
        )}

        {showForm && <Form
          schema={schema}
          op={op}
          ids={ids}
          value={payload}
          onChange={edit}
          problems={tried ? problems : []}
          confidence={{ ...(proposal?.confidence ?? {}), ...heard }}
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
            <p className="state-p">
              {op.title} is irreversible: {op.writes.join(", ") || "the record"} cannot be taken back
              from this screen. Nothing has ticked this box for you and nothing can.
            </p>
            <label className="f-check big">
              <input type="checkbox" checked={confirmed} disabled={busy}
                     onChange={(e) => setConfirmed(e.target.checked)} />
              <span>I have read the values above and I am doing this.</span>
            </label>
          </div>
        )}

        {tried && problems.length > 0 && (
          <div className="f-bad block">
            {problems.length} thing{problems.length === 1 ? "" : "s"} to fix before this can be sent.
            The server checks the same list, so fixing them here is the same as fixing them there.
          </div>
        )}

        {error && <Failed error={error} what="Not saved" onRetry={() => setError(null)} />}
      </div>

      <div className="mod-f">
        <span className="f-hint" style={{ flex: 1 }}>
          Actor, surface, payload and outcome are written to the audit log.
        </span>
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
