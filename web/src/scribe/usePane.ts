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
import { useEffect, useState } from "react";
import { currentRole } from "../api";
import { library as loadLibrary, templates, type LibraryItem, type Templates } from "./client";
import type { Phase } from "./ScribeBar";
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
  const [sub, setSub] = useState<Sub>("notes");
  const [menu, setMenu] = useState<Templates | null>(null);
  const [library, setLibrary] = useState<Library>(null);
  const [op, setOp] = useState("");
  const [lib, setLib] = useState<string[]>([]);
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");

  // A different visit is a different recording. This component is not keyed by
  // thread, so what one patient's recording chose must not follow the reader
  // to the next patient's.
  useEffect(() => {
    setSub("notes"); setOp(""); setLib([]); setSession(null); setPhase("idle");
  }, [thread]);

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

  const chooseOp = (id: string) => {
    setOp(id);
    rememberTemplate(currentRole(), station, id);
  };

  /** Ask for a library template, or take it back. Past the most one recording
   *  may carry, the oldest choice makes way rather than the click doing
   *  nothing. */
  const toggleLib = (id: string) =>
    setLib((now) => (now.includes(id) ? now.filter((x) => x !== id) : [...now, id].slice(-MOST_NOTES)));

  return { sub, setSub, menu, library, op, chooseOp, lib, toggleLib, session, setSession, phase, setPhase };
}
