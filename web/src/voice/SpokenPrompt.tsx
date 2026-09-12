/** The consent line, on screen, always. `spoken: true` also has the browser
 *  say it, but speech fails silently in more ways than anyone notices: a
 *  muted device, no audio hardware, no Web Speech API, an autoplay policy
 *  refusing an utterance with no gesture behind it. `spoken: false` was
 *  always the on-screen path (`fallback: text`); this makes it the only
 *  path, and speech an enhancement on top of it rather than a replacement
 *  for it.
 *
 *  This draws a sentence. It cannot answer for the patient: the fields it
 *  names are answered on the form below, by the clerk's own tap, through the
 *  same validation every other answer goes through. Nothing here holds a
 *  payload, a client or an onChange.
 */
import { useEffect, useRef } from "react";
import type { Mount } from "./instruments";

export function SpokenPrompt({ mount }: { mount: Extract<Mount, { kind: "spoken-prompt" }> }) {
  const said = useRef(false);

  useEffect(() => {
    if (!mount.spoken || said.current) return;
    said.current = true;
    try {
      const synth = window.speechSynthesis;
      if (!synth) return;
      synth.speak(new SpeechSynthesisUtterance(mount.says));
    } catch {
      // The sentence is already on screen below. Speech is the extra, not
      // the consent, so a throw here changes nothing else.
    }
  }, [mount.spoken, mount.says]);

  return (
    <div className="v-row say-row">
      <div className="say-line">{mount.says}</div>
    </div>
  );
}
