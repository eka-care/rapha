/** The `/` menu's OWN verbs: the things this screen can do that are not
 *  operations.
 *
 *  `/` has always listed the thread's declared actions, narrowed by the
 *  kernel to the ones the guard would actually allow. That is most of what a
 *  clinician wants and none of what the screen itself can do: start
 *  recording, open a tab, show the panels beside the visit, leave for the
 *  patient's whole record. Those are controls that already exist on screen,
 *  reachable only by finding the right pixel.
 *
 *  THE ONE CATEGORY THIS LAYER MAY NAME. `ui.check.ts` forbids the renderer
 *  from typing a station, a flag, a capability, an operation id or a view
 *  column, and nothing here does: a verb names a tab, a panel or a
 *  microphone, all of which are this renderer's own furniture. The tab
 *  titles arrive from the caller, so a bundle that renames a tab renames its
 *  command.
 *
 *  A VERB THAT CANNOT RUN IS NOT OFFERED, which is the same rule the actions
 *  half of this menu already keeps: the kernel hands over only what the
 *  guard would allow, and §14 forbids displaying an unusable command. So the
 *  microphone is absent without consent rather than present and refusing,
 *  and the tab you are already looking at is not offered.
 */

export type Verb = {
  key: string;
  label: string;
  /** The small grey line under the label. */
  sub?: string;
  run: () => void;
};

/** Everything the visit screen itself can do, in the order a person would
 *  look for it: record, move around, then leave. */
export function commands(s: {
  /** The tabs this visit has, and which one is open. Titles are the
   *  caller's, never typed here. */
  tabs: { id: string; title: string }[];
  open: string;
  goTab: (id: string) => void;
  /** Absent when the microphone cannot be started on this visit -- which
   *  today means consent is not recorded. */
  record?: () => void;
  /** The rail beside the visit, and which way the control goes. */
  railFolded: boolean;
  toggleRail: () => void;
  /** The patient's whole record, when this visit belongs to one. */
  openRecord?: () => void;
}): Verb[] {
  const out: Verb[] = [];

  if (s.record) {
    out.push({
      key: "record",
      label: "Start recording",
      sub: "Dictate this visit",
      run: s.record,
    });
  }

  for (const t of s.tabs) {
    if (t.id === s.open) continue;      // you are looking at it
    out.push({ key: `tab:${t.id}`, label: `Go to ${t.title}`, run: () => s.goTab(t.id) });
  }

  out.push({
    key: "rail",
    label: s.railFolded ? "Show the panels beside this visit"
                        : "Hide the panels beside this visit",
    run: s.toggleRail,
  });

  if (s.openRecord) {
    out.push({
      key: "record-open",
      label: "Open the patient record",
      sub: "Every visit, not just this one",
      run: s.openRecord,
    });
  }

  return out;
}
