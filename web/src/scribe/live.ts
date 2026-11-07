/** Which visit is being scribed right now, shared across the app.
 *
 *  The recorder lives inside a visit's screen, and a person with a patient in
 *  front of them still has to be able to look at the list, the register or
 *  another visit. So the visit that holds the recorder publishes its state
 *  here, the rail reads it to show a way back, and the app keeps that visit's
 *  screen mounted (hidden) while the person is elsewhere. */
import { useSyncExternalStore } from "react";
import type { Phase } from "./ScribeBar";

export type LiveScribe = { thread: string; name: string; phase: Phase; seconds: number } | null;

let current: LiveScribe = null;
const listeners = new Set<() => void>();

export function setLiveScribe(next: LiveScribe) {
  const same = current && next && current.thread === next.thread && current.name === next.name
    && current.phase === next.phase && current.seconds === next.seconds;
  if (same || (current === null && next === null)) return;
  current = next;
  listeners.forEach((l) => l());
}

/** Clear it only if it is still this visit's, so a visit unmounting late cannot wipe the next one's. */
export function clearLiveScribe(thread: string) {
  if (current?.thread === thread) setLiveScribe(null);
}

export function useLiveScribe(): LiveScribe {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => current,
  );
}
