/** The screens, run over what a real kernel answered, for two facilities.
 *
 *  Run: python3 scripts/check_live.py   (which takes the captures first)
 *
 *  This is the half that would notice a screen going back to inventing
 *  something. It imports the SAME modules the browser imports -- the form
 *  registry, the header rule, the quick action rule, the list's own filter and
 *  sort, the validator -- and feeds them two captures taken from two kernels
 *  that differ by one declared list. Nothing below is written twice for the
 *  two shapes: every assertion runs the one module over both.
 *
 *  What it cannot do. It is not a browser: no DOM, no cascade, no layout, no
 *  click. web/src/ui.check.ts says the same about itself. And "live" means
 *  this kernel and the threads bundles/phc/seed.yaml declares: no real
 *  patient, no call off this machine.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { load, options, questionnaire } from "./declarations.ts";
import { weigh } from "./loops.ts";
import { filterOptions, filterRows, sortOptions, sortRows } from "./loops.ts";
import { header, messages, queueViewFor, valuesOf, type Ctx } from "./messages.ts";
import { walk } from "./validate.ts";
import type { Catalogue, Questionnaire, QueueRow, ThreadView, ViewDecl, ViewResult } from "./types";

let checks = 0;
const ok = (what: string) => { checks++; console.log("ok   " + what); };

const dir = process.argv[2];
assert.ok(dir, "scripts/check_live.py passes the capture directory");

type Capture = {
  shape: string;
  facility: { facility: string; withheld: Record<string, string>; without: Record<string, string>;
              bundle: { workflow: string }; views: ViewDecl[]; roles: string[] };
  catalogue: Catalogue;
  questionnaires: Record<string, Questionnaire>;
  views: Record<string, ViewResult & { kind: string }>;
  refused: string[];
  threads: Record<string, ThreadView>;
  subjects: Record<string, { subject: Record<string, unknown>; encounters: unknown[] }>;
  valuesets: Record<string, { concepts: { value: string; display: string; system: string }[] }>;
};

const SHAPES = ["all-plugins", "no-laboratory"];
const caps: Record<string, Capture> = Object.fromEntries(
  SHAPES.map((s) => [s, JSON.parse(readFileSync(join(dir, `${s}.json`), "utf8")) as Capture]));

/** The registry, filled from a capture through the same two methods the real
 *  client exposes. Nothing reads a file: if `declarations.ts` still globbed
 *  the questionnaires off disk, the assertions below would pass for a reason
 *  that has nothing to do with the kernel, so the first one makes the
 *  registry prove where its answer came from. */
const feed = (c: Capture) => load({
  questionnaires: async () => ({ questionnaires: c.questionnaires }),
  valueset: async (slug: string) => c.valuesets[slug] ?? { concepts: [] },
});

// ------------------------------------------------------- 1. what a form asks

{
  // A slug this kernel never sent. If the registry can still answer it, it is
  // reading something other than what it was given, which is exactly the
  // build time glob this step removed.
  const first = caps[SHAPES[0]];
  const invented = "not.a.slug.any.kernel.sent";
  assert.equal(questionnaire(invented), null, "an unserved slug has no form");

  const counted = await feed(first);
  assert.ok(counted.forms > 0, "the kernel served forms");
  assert.equal(counted.forms, Object.keys(first.questionnaires).length,
    "the registry holds exactly what the kernel sent, no more");
  assert.equal(questionnaire(invented), null,
    "and still nothing for a slug it was not given");

  // Every operation's `input` resolves, and resolves to the kernel's copy.
  const ops = Object.values(first.catalogue.operations ?? {});
  const inputs = [...new Set(ops.map((o) => o.input).filter(Boolean))];
  assert.ok(inputs.length >= 10, `something to check: ${inputs.length}`);
  for (const slug of inputs) {
    const got = questionnaire(slug);
    assert.ok(got, `${slug}: an operation names a form the kernel does not serve`);
    assert.deepEqual(got, first.questionnaires[slug],
      `${slug}: the registry answered something other than the kernel's copy`);
  }
  ok(`forms: all ${inputs.length} questionnaires the operations name come from the kernel, not off disk`);

  // The bound choices. A question that binds its answer declares no
  // answer_option, so before the value set route was called from a screen
  // every one of these drew an empty dropdown.
  const bound = inputs.flatMap((slug) => walk(questionnaire(slug)!.questions ?? []))
    .filter((q) => q.answer_value_set);
  assert.ok(bound.length > 0, "this bundle binds at least one answer to a value set");
  for (const q of bound) {
    const offered = options(q);
    assert.ok(offered.length > 0,
      `${q.link_id} binds ${q.answer_value_set} and has nothing to choose`);
    const served = first.valuesets[q.answer_value_set!];
    assert.equal(offered.length, served.concepts.length,
      `${q.link_id}: the picker is not the kernel's expansion`);
    for (const o of offered) {
      assert.ok(served.concepts.some((c) => c.value === o.value),
        `${q.link_id}: ${o.value} is not a concept this kernel served`);
    }
  }
  ok(`forms: ${bound.length} bound choices draw the kernel's own expansion of ${Object.keys(first.valuesets).length} value sets`);
}

// ---------------------------------------------- 2. the list, and the thread

const ctxFor = (c: Capture): Ctx => ({
  operations: c.catalogue.operations ?? {},
  schema: questionnaire,
  badges: queueViewFor(c.catalogue, c.facility.bundle.workflow)?.badges ?? {},
});

for (const shape of SHAPES) {
  const c = caps[shape];
  await feed(c);
  const queue = queueViewFor(c.catalogue, c.facility.bundle.workflow)!;
  const decl = c.catalogue.views![queue.id];
  const rows = Object.values(c.views).filter((v) => v.kind === "queue")
    .flatMap((v) => (v.rows ?? []) as QueueRow[]);
  assert.ok(rows.length > 0, `${shape}: the kernel seeded a queue`);

  // The patient list. Every tab, every sort, over the kernel's rows.
  const { flags, stations } = filterOptions(decl, rows);
  assert.ok(stations.length > 0, `${shape}: the rows stand at stations`);
  for (const s of stations) {
    assert.deepEqual(filterRows(rows, { station: s }).map((r) => r.thread),
      rows.filter((r) => r.station === s).map((r) => r.thread), `${shape}/${s}`);
  }
  for (const f of flags) assert.ok(filterRows(rows, { flag: f }).length >= 0);
  for (const sort of sortOptions(decl)) {
    assert.equal(sortRows(rows, sort.key, decl).length, rows.length,
      `${shape}: sorting by ${sort.key} lost a row`);
  }

  // Every name on the list is a name the kernel sent, under a column the view
  // declared. This is the assertion that would catch a fixture creeping back.
  const subjectValues = new Set(rows.flatMap((r) => Object.values(r.subject ?? {})).map(String));
  for (const r of rows) {
    const h = header({ ...(c.threads[r.thread] ?? {}), subject: r.subject, flags: r.flags } as ThreadView, decl);
    assert.ok(subjectValues.has(h.name) || h.name === r.thread,
      `${shape}: "${h.name}" is on the list and the kernel never sent it`);
    for (const m of h.meta) {
      assert.ok(subjectValues.has(m), `${shape}: "${m}" is on the list and the kernel never sent it`);
    }
  }

  // The thread: its own cards, composed from the kernel's audit and the
  // kernel's forms. A card labelled from a form the kernel did not serve
  // would come back with the raw link_id instead.
  const ctx = ctxFor(c);
  let labelled = 0;
  for (const t of Object.values(c.threads)) {
    const posted = messages(t, ctx);
    assert.ok(Array.isArray(posted), `${shape}/${t.id}: no messages`);
    for (const a of t.audit ?? []) {
      const kv = valuesOf(ctx, a.operation, a.payload);
      for (const v of kv) {
        assert.ok(v.label && v.label !== v.link_id,
          `${shape}/${a.operation}: ${v.link_id} has no label, so its form never arrived`);
        labelled++;
      }
    }
  }
  assert.ok(labelled > 0, `${shape}: something was labelled from a served form`);
  ok(`${shape}: ${rows.length} rows, ${stations.length} stations and ${labelled} labelled values, all from this kernel`);
}

// ------------------------------- 3. one renderer, two facilities, no edit

{
  const [whole, noLab] = SHAPES.map((s) => caps[s]);

  const offeredIn = (c: Capture) => {
    const out = new Set<string>();
    for (const t of Object.values(c.threads)) {
      // §33's own rule: the operation that closes this step first, the rest
      // behind it. Read through weigh() rather than off t.actions, so what is
      // compared is what the quick action row would really offer.
      const { primary, overflow } = weigh(t.actions ?? [], t.closes);
      for (const op of [primary, ...overflow]) if (op) out.add(op.id);
    }
    return out;
  };
  const a = offeredIn(whole);
  const b = offeredIn(noLab);
  assert.ok(a.size > 0 && b.size > 0, "both facilities offer something");
  assert.notDeepEqual([...a].sort(), [...b].sort(),
    "the two facilities offer the same operations, so nothing was withheld");

  // Two reasons an operation can be offered at one centre and not the other,
  // and only one of them is this module's claim: a withheld plugin. The other
  // is that the two seeded days stand at different stations, which says
  // nothing about plugins. So the assertion is made over the capabilities the
  // KERNEL says are withheld, and it is made in both directions.
  const byPlugin = [...a].filter((id) =>
    noLab.facility.withheld[whole.catalogue.operations![id].capability]);
  assert.ok(byPlugin.length > 0,
    "nothing the narrowed centre withholds was ever offered at the whole one");
  for (const id of byPlugin) {
    assert.ok(!b.has(id),
      `${id} is still offered at a centre whose plugin for it is off`);
  }
  for (const id of b) {
    const cap = noLab.catalogue.operations![id].capability;
    assert.ok(!noLab.facility.withheld[cap],
      `${id} is offered although the kernel withheld ${cap}`);
  }
  ok(`actions: ${byPlugin.length} operations the quick action rule offers at one centre and none at the other, each withheld by a plugin the kernel named, and nothing withheld is offered`);

  // The line. A station nobody can reach is skipped, not pending, and that is
  // the kernel's answer: the renderer draws the statuses it is handed.
  // A station can be skipped on ONE thread at either centre: the step applies
  // only when a flag was raised, so a patient who needed no test skips it
  // wherever they are. What a centre without the plugin changes is that
  // NOBODY walks it, ever. So the comparison is per station over every
  // thread, not a set of stations that appear skipped somewhere.
  const statuses = (c: Capture, station: string) => new Set(Object.values(c.threads)
    .flatMap((t) => (t.line ?? []).filter((s) => s.station === station).map((s) => s.status)));
  const stationsOf = (c: Capture) => [...new Set(Object.values(c.threads)
    .flatMap((t) => (t.line ?? []).map((s) => s.station)))];
  assert.deepEqual(stationsOf(whole).sort(), stationsOf(noLab).sort(),
    "a facility declines a plugin; it does not shorten the declared line");
  const closed = stationsOf(noLab).filter((st) => {
    const there = statuses(noLab, st);
    return there.size === 1 && there.has("skipped")
      && !(statuses(whole, st).size === 1 && statuses(whole, st).has("skipped"));
  });
  assert.ok(closed.length > 0,
    "no station is closed to every thread at the narrowed centre, so the line did not change");
  ok(`line: ${closed.length} station every thread skips at one centre and some thread walks at the other (${closed.join(", ")})`);

  // The queue. Different rows, and a different number of them.
  const threads = (c: Capture) => Object.keys(c.threads).sort();
  assert.notDeepEqual(threads(whole), threads(noLab), "the two queues hold the same threads");
  assert.ok(threads(whole).length > threads(noLab).length,
    "the centre running everything has no more of a day than the one that does not");
  ok(`queue: ${threads(whole).length} threads against ${threads(noLab).length}, from one renderer and one list screen`);

  // What this centre does not run, in the words the bundle chose. The role
  // editor's disabled switches are built from exactly these two maps, so an
  // empty `without` is a sentence with a plugin id in it instead of a title.
  assert.deepEqual(whole.facility.withheld, {}, "a centre running everything withholds nothing");
  assert.deepEqual(whole.facility.without, {}, "and names nothing it does not run");
  assert.ok(Object.keys(noLab.facility.without).length > 0,
    "the narrowed centre withholds capabilities and names no plugin for them");
  for (const [cap, plugin] of Object.entries(noLab.facility.withheld)) {
    const title = noLab.facility.without[plugin];
    assert.ok(title, `${cap} is withheld by ${plugin} and the kernel sent no title for it`);
    assert.notEqual(title, plugin, `${plugin}'s title is just its id again`);
  }
  ok(`facility: ${Object.keys(noLab.facility.withheld).length} capabilities withheld by ${Object.keys(noLab.facility.without).length} named plugin, each with the title its bundle gave it`);

  // A summary section says which columns it carries AND in which order, so no
  // screen has to choose which one a row leads with.
  let sections = 0;
  for (const c of [whole, noLab]) {
    for (const view of Object.values(c.views)) {
      if (view.kind !== "summary") continue;
      for (const section of (view.rows ?? []) as { fields?: string[]; rows: unknown[]; resource?: string }[]) {
        if (!section.resource) continue;          // the line, the flags, the audit
        assert.ok(section.fields && section.fields.length > 0,
          `${c.shape}: a summary section carries rows and declares no fields`);
        for (const row of section.rows as Record<string, unknown>[]) {
          for (const k of Object.keys(row)) {
            assert.ok(section.fields!.includes(k),
              `${c.shape}: a row carries ${k}, which its section never declared`);
          }
        }
        sections++;
      }
    }
  }
  assert.ok(sections > 0, "something to check: no summary section carried a resource");
  ok(`summary: ${sections} sections each declare which columns a row carries, and in which order`);

  // And a view this centre cannot open never reaches the list screen at all.
  assert.ok(noLab.refused.length >= 0);
  assert.deepEqual(whole.refused, [], "a centre running every plugin is refused no view");
  ok(`views: ${Object.keys(whole.views).length} open at one centre, ${Object.keys(noLab.views).length} at the other, ${noLab.refused.length} refused by capability`);

  // The forms are the BUNDLE's, not the facility's, and this says so out loud
  // rather than leaving it to be discovered: what a facility narrows is which
  // operations it offers, and the forms behind the ones it withholds are
  // still served, because a card from a colleague's older visit still needs
  // its labels.
  assert.deepEqual(Object.keys(whole.questionnaires).sort(),
    Object.keys(noLab.questionnaires).sort(),
    "a form is a bundle's declaration; the two facilities should serve the same set");
  const reachable = (c: Capture) => new Set([...offeredIn(c)]
    .map((id) => c.catalogue.operations![id].input).filter(Boolean));
  assert.ok(reachable(whole).size > reachable(noLab).size,
    "the same forms are reachable at both centres");
  ok(`forms: both centres serve ${Object.keys(whole.questionnaires).length} forms and reach ${reachable(whole).size} against ${reachable(noLab).size} of them`);
}

console.log(`\n${checks} live checks passed`);
