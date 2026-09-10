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
 */
import { useMemo, useState } from "react";
import { ApiError, type Client } from "./api";
import { Form, labelled, validate } from "./Form";
import { questionnaire } from "./declarations";
import type { Operation, Payload, Proposal } from "./types";
import { Badge, Empty, Failed, human } from "./ui";

const IRREVERSIBLE = "irreversible";

export function OperationPanel({
  op, thread, client, proposal, onDone, onCancel,
}: {
  op: Operation;
  thread: string;
  /** Whichever kernel this screen is talking to. The panel does not know or
   *  care which, so demo mode cannot write to a real store by accident. */
  client: Client;
  proposal?: Proposal;
  onDone: () => void;
  onCancel: () => void;
}) {
  const schema = questionnaire(op.input);
  const [payload, setPayload] = useState<Payload>({ ...(proposal?.payload ?? {}) });
  const [tried, setTried] = useState(false);
  const [stage, setStage] = useState<"edit" | "confirm">("edit");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const problems = useMemo(() => (schema ? validate(schema, payload) : []), [schema, payload]);

  if (!schema) {
    return (
      <Empty>
        <div className="state-t">No questionnaire for {op.id}.</div>
        <p className="state-p">
          The operation names <b>{op.input}</b> as its input, and there is no such file in
          questionnaires/. Either the id is wrong in catalogue/ops/, or the form was never written.
        </p>
        <button className="cq" onClick={onCancel}>Back</button>
      </Empty>
    );
  }

  const irreversible = op.irreversibility === IRREVERSIBLE;
  const edit = (next: Payload) => {
    setPayload(next);
    setConfirmed(false);           // an edit invalidates a confirm, always
    if (stage === "confirm") setStage("edit");
  };

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

  const changed = proposal
    ? labelled(schema, payload).filter(([id]) => String(proposal.payload?.[id] ?? "") !== String(payload[id] ?? ""))
    : [];

  return (
    <div className="card panelcard">
      <div className="card-h">
        <div>
          <div className="eyebrow">{proposal ? "Proposed, not recorded" : "New entry"}</div>
          <div className="card-t" style={{ marginTop: 2 }}>{op.title}</div>
        </div>
        <div className="ml-auto" style={{ display: "flex", gap: 6 }}>
          <Badge>{op.instrument}</Badge>
          {irreversible && <Badge style="crit">irreversible</Badge>}
        </div>
      </div>

      <div className="panelbody">
        <p className="f-hint">{op.summary}</p>

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

        <Form
          schema={schema}
          value={payload}
          onChange={edit}
          problems={tried ? problems : []}
          confidence={proposal?.confidence}
          disabled={busy}
        />

        {proposal && changed.length > 0 && (
          <div className="diff">
            <div className="eyebrow">You changed</div>
            {changed.map(([id, text]) => (
              <div key={id}>
                {text}: <s>{String(proposal.payload?.[id] ?? "empty")}</s> to{" "}
                <b>{String(payload[id] ?? "empty")}</b>
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

      <div className="panelfoot">
        <button className="cq" onClick={onCancel} disabled={busy}>Cancel</button>
        {proposal && (
          <button className="cq" onClick={reject} disabled={busy}>Reject</button>
        )}
        <button
          className="cq rose ml-auto"
          onClick={send}
          disabled={busy || (stage === "confirm" && !confirmed)}
        >
          {busy ? "Sending..." : stage === "confirm" ? "Commit" : proposal ? "Confirm" : irreversible ? "Continue" : "Commit"}
        </button>
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
