/** What the Scribe tab's three sub-tabs share: which template the recording
 *  will fill, which of Eka's library templates will write a note, the session
 *  that comes back, and where it is.
 *
 *  It is a hook rather than state in the encounter because the encounter is
 *  already the largest screen in the product, and because these six values
 *  belong together: the Templates tab chooses, the recorder obeys, and the
 *  Transcript and Notes tabs read what came back.
 *
 *  It can write nothing. It lists templates and holds a transcript; every
 *  value that reaches a record still arrives in a form and waits for a tap.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { currentRole } from "../api";
import { library as loadLibrary, templates, threadNotes, type LibraryItem, type Templates, type ThreadNote } from "./client";
import type { Status } from "./ScribeBar";
import { lastTemplate, rememberTemplate, type ScribeSession } from "./session";

export type Sub = "notes" | "transcript" | "templates";

/** The library as the tab draws it: not asked for yet, loaded, or said no. */
export type Library = { items: LibraryItem[] } | { error: string } | null;

/** The most library templates one recording may ask for. api/main.py keeps
 *  the same number: each one is another document the service has to write. */
export const MOST_NOTES = 2;

export function usePane({ thread, station, open, asked }: {
  thread: string;
  station: string;
  /** The Scribe tab is the one showing. Nothing is fetched until it is. */
  open: boolean;
  /** The operation chosen on the thread before the microphone opened, or "" for
   *  "whatever this station recorded last", or null when nothing is starting. */
  asked: string | null;
}) {
  // The recorder lives on the Transcript view, so that is where a visit to the
  // tab opens: a person who came to record finds the way to start in front of
  // them, and the notes are one tap away.
  const [sub, setSub] = useState<Sub>("transcript");
  const [menu, setMenu] = useState<Templates | null>(null);
  const [library, setLibrary] = useState<Library>(null);
  const [op, setOp] = useState("");
  const [lib, setLib] = useState<string[]>([]);
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [status, setStatus] = useState<Status>({ phase: "idle", seconds: 0 });
  /** What this visit has had written, by anybody, kept on the server. */
  const [kept, setKept] = useState<ThreadNote[]>([]);
  /** Whether a person has chosen a note template themselves. Until they have,
   *  the station's default is chosen for them; after, their choice stands,
   *  including choosing none. */
  const touched = useRef(false);

  // A different visit is a different recording. This component is not keyed by
  // thread, so what one patient's recording chose must not follow the reader
  // to the next patient's.
  useEffect(() => {
    setSub("transcript"); setOp(""); setLib([]); setSession(null);
    setStatus({ phase: "idle", seconds: 0 }); setKept([]); touched.current = false;
  }, [thread]);

  // A different station is a different default and a different list of forms.
  useEffect(() => { setMenu(null); }, [station, thread]);

  const reloadKept = useCallback(() => {
    threadNotes(thread).then(setKept).catch(() => {});
  }, [thread]);

  // The notes already written on this visit, by whoever wrote them, when the
  // tab is first looked at and again whenever a recording hands one in.
  useEffect(() => { if (open) reloadKept(); }, [open, reloadKept, session]);

  // What this station may fill, once the tab is first looked at.
  useEffect(() => {
    if (!open || menu) return;
    let live = true;
    templates(station).then((t) => live && setMenu(t)).catch(() => live && setMenu({ default: null, choose: [] }));
    return () => { live = false; };
  }, [open, station, menu]);

  // Eka's library, on the same first look. A failure is a sentence on the
  // tab, not a reason the recorder cannot start: the forms still work.
  useEffect(() => {
    if (!open || library) return;
    let live = true;
    loadLibrary().then((items) => live && setLibrary({ items }))
      .catch((e) => live && setLibrary({ error: String(e?.message ?? e) }));
    return () => { live = false; };
  }, [open, library]);

  // THE FORM A RECORDING FILLS. What was asked for on the thread wins, then
  // what this station recorded last, then its declared default: the same order
  // the picker on the recording bar used, which this tab replaced.
  useEffect(() => {
    if (!menu) return;
    const known = (id: string) => (menu.choose.some((c) => c.operation === id) ? id : "");
    const pick = known(asked ?? "")
      || (op ? "" : known(lastTemplate(currentRole(), station) ?? "") || menu.default || "");
    if (pick && pick !== op) setOp(pick);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [menu, asked]);

  // THE STATION'S NOTE, UNLESS THE PERSON HAS SAID OTHERWISE. Choosing a
  // template is not required, so this only ever fills in a choice that was
  // not made: the nurse and the doctor both arrive with the default
  // prescription note already picked, and either can turn it off.
  useEffect(() => {
    const id = menu?.note?.id;
    if (!id || touched.current) return;
    setLib((now) => (now.includes(id) ? now : [...now, id].slice(-MOST_NOTES)));
  }, [menu, thread]);

  const chooseOp = (id: string) => {
    setOp(id);
    rememberTemplate(currentRole(), station, id);
  };

  /** Ask for a library template, or take it back. Past the most one recording
   *  may carry, the oldest choice makes way rather than the click doing
   *  nothing. */
  const toggleLib = (id: string) => {
    touched.current = true;
    setLib((now) => (now.includes(id) ? now.filter((x) => x !== id) : [...now, id].slice(-MOST_NOTES)));
  };

  return {
    sub, setSub, menu, library, op, chooseOp, lib, toggleLib, session, setSession,
    status, setStatus, phase: status.phase, kept,
  };
}
