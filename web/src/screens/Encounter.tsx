/** §8: the encounter workspace. Thread on the left, context on the right,
 *  composer fixed at the bottom of the thread.
 *
 *  §99's hierarchy decides what is loud here: identity, then clinical state,
 *  then the required action, then content. The quick action row is capped at
 *  six (§33) and everything beyond it lives behind `/`, which is not a
 *  compromise -- an action row that grows without limit is a menu nobody reads.
 */
import { useMemo, useState } from "react";
import type { Client } from "../api";
import { OperationPanel } from "../form/Panel";
import { Icon } from "../icons";
import { cue, mine, offered, weigh } from "../loops";
import { agentLine, header, messages, queueViewFor, valuesOf, type Ctx, type Said } from "../messages";
import type { Catalogue, Operation, Payload, ThreadView } from "../types";
import { Composer } from "../thread/Composer";
import { Stream } from "../thread/Thread";
import { Line } from "../view/View";
import { human } from "../words";

const QUICK = 6;   // §33

export function Encounter({
  thread, cat, ctx, client, said, asking, onSay, onChanged,
}: {
  thread: ThreadView;
  cat: Catalogue;
  ctx: Ctx;
  client: Client;
  said: Said[];
  asking: boolean;
  onSay: (text: string) => void;
  onChanged: () => void;
}) {
  const [modal, setModal] = useState<{ op: Operation; seed?: Payload } | null>(null);

  const head = useMemo(() => header(thread, queueViewFor(cat, thread.workflow)), [thread, cat]);
  const msgs = useMemo(() => messages(thread, ctx, said), [thread, ctx, said]);
  const line = useMemo(() => agentLine(thread, ctx), [thread, ctx]);

  // §33: "ordering is deterministic and auditable". weigh() is that rule, and
  // it lives in loops.ts where loops.check.ts can prove it without a browser:
  // the operation closing this role's step at this station leads, and
  // everything else follows in declaration order. This file does not re-rank.
  const { primary, overflow } = useMemo(
    () => weigh(thread.actions, thread.closes),
    [thread.actions, thread.closes],
  );
  const ranked = useMemo(
    () => (primary ? [primary, ...overflow] : overflow),
    [primary, overflow],
  );
  const quick = ranked.slice(0, QUICK);

  // §2.6: the microphone is the only way in to dictation, so it appears when
  // and only when an operation declared with a scribe instrument is on offer.
  const scribeOp = ranked.find((o) => o.instrument === "scribe");

  const roles = Object.keys(cat.bundles ?? {});

  return (
    <div className="encounter">
      <div className="encounter__main">
        <header className="subject">
          <div className="subject__row">
            <h1 className="t-page" style={{ margin: 0 }}>{head.name}</h1>
            {head.identity && (
              <span className="status" data-tone="abdm">
                {head.identity.label} {head.identity.value}
              </span>
            )}
          </div>
          <div className="subject__meta t-meta">{head.meta.join(" · ")}</div>
          {head.badges.length > 0 && (
            <div className="subject__tags">
              {head.badges.map((b) => (
                <span className="status" data-tone={toneOf(b.style)} key={b.text}>{b.text}</span>
              ))}
            </div>
          )}
          <Line line={thread.line} />
          {quick.length > 0 && (
            <div className="quick" style={{ marginTop: "var(--space-4)" }}>
              {quick.map((op, i) => (
                <button
                  key={op.id}
                  className="btn"
                  data-variant={i === 0 ? "primary" : undefined}
                  onClick={() => setModal({ op })}
                >
                  {op.title}
                </button>
              ))}
              {ranked.length > QUICK && (
                <span className="t-meta u-faint">
                  {ranked.length - QUICK} more with <span className="kbd">/</span>
                </span>
              )}
            </div>
          )}
        </header>

        <Stream
          msgs={msgs}
          thread={thread}
          client={client}
          ctx={ctx}
          instruments={cat.instruments}
          onDone={onChanged}
        />

        {/* The agent's closing line sits above the composer, because it is
            about what to do next and the composer is where you do it. */}
        {line.sentences.length > 0 && (
          <div className="composer__context" style={{ paddingInline: "var(--space-5)" }}>
            {line.sentences.join(" ")}
          </div>
        )}

        <Composer
          about={head.name}
          context={`${head.name}${thread.station ? ` · ${human(thread.station)}` : ""}`}
          actions={ranked}
          roles={roles}
          asking={asking}
          onSay={onSay}
          onAction={(op) => setModal({ op })}
          onStartScribe={scribeOp ? () => setModal({ op: scribeOp }) : undefined}
        />
      </div>

      <ContextPanel thread={thread} ctx={ctx} />

      {modal && (
        <>
          <div className="scrim" onClick={() => setModal(null)} />
          <OperationPanel
            op={modal.op}
            thread={thread.id}
            client={client}
            instruments={cat.instruments}
            flags={thread.flags}
            seed={modal.seed}
            onDone={() => { setModal(null); onChanged(); }}
            onCancel={() => setModal(null)}
          />
        </>
      )}
    </div>
  );
}

const toneOf = (style: string) =>
  ({ crit: "critical", warn: "warning", ok: "success" } as Record<string, string>)[style] || undefined;

/** §25. A reference panel: what is known about this subject, beside the
 *  conversation about it rather than inside it.
 *
 *  §25 names its sections -- problems, medications, allergies, vitals, labs.
 *  This renderer may not: those are a health centre's words, and the same
 *  component draws a laboratory's bench. What it can do honestly is group the
 *  values that were actually committed under the title of the operation that
 *  wrote them, which is the declaration's own word for the same thing and
 *  arrives correct for a bundle nobody here has seen.
 *
 *  What is deliberately NOT here: the capability list. `thread.held` is which
 *  permissions the caller holds, which is plumbing -- it belongs in settings,
 *  not in a panel headed with the patient's name.
 */
function ContextPanel({ thread, ctx }: { thread: ThreadView; ctx: Ctx }) {
  const recorded = useMemo(() => {
    const out: { title: string; rows: { label: string; value: string; crit: boolean }[] }[] = [];
    for (const a of thread.audit) {
      if (a.outcome !== "committed" && a.outcome !== "confirmed" && a.outcome !== "allowed") continue;
      const rows = valuesOf(ctx, a.operation, a.payload).map((v) => ({
        label: v.label, value: v.value, crit: v.crit,
      }));
      if (!rows.length) continue;
      out.push({ title: ctx.operations[a.operation]?.title ?? human(a.operation), rows });
    }
    return out.reverse();        // most recent first, like the rest of the panel
  }, [thread.audit, ctx]);

  const flags = thread.flags.map(human);

  if (!flags.length && !recorded.length) {
    return (
      <aside className="context" aria-label="Context">
        <div className="t-meta u-faint">Nothing recorded yet.</div>
      </aside>
    );
  }

  return (
    <aside className="context" aria-label="Context">
      {flags.length > 0 && <Section title="State" rows={flags} />}
      {recorded.map((r, i) => (
        <div className="context__section" key={`${r.title}-${i}`}>
          <div className="context__head" style={{ cursor: "default" }}>{r.title}</div>
          <div className="context__body">
            <div className="kv">
              {r.rows.map((v) => (
                <div className="kv__row" key={v.label} data-critical={v.crit}>
                  <span className="kv__label">{v.label}</span>
                  <span className="kv__value">{v.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}
    </aside>
  );
}

function Section({ title, rows }: { title: string; rows: string[] }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="context__section">
      <button className="context__head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon name="chev" />
        {title}
        <span className="thread-object__header-end t-num">{rows.length}</span>
      </button>
      {open && (
        <div className="context__body">
          {rows.map((r, i) => <div className="t-body u-mute" key={`${r}-${i}`}>{r}</div>)}
        </div>
      )}
    </div>
  );
}

export { cue, mine, offered };
