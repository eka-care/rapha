/** Which panels sit beside an open visit. A personal setting; see rail.ts. */
import { useState } from "react";
import { Icon } from "../icons";
import { RAIL, railShown, setRailShown, type RailId } from "./rail";

export function RailPrefs() {
  const [on, setOn] = useState<RailId[]>(() => railShown());

  const flip = (id: RailId) => {
    const next = on.includes(id) ? on.filter((x) => x !== id) : [...on, id];
    setOn(next);
    setRailShown(next);
  };

  return (
    <div className="cp-body">
      <div className="cp-choices">
        {RAIL.map((r) => {
          const shown = on.includes(r.id);
          return (
            <button key={r.id} type="button" role="switch" aria-checked={shown}
                    className={`cp-choice${shown ? " on" : ""}`} onClick={() => flip(r.id)}>
              <span className="cp-choice-i">
                <Icon name={shown ? "eye" : "box"} className="i sm" />
              </span>
              <span className="cp-choice-b">
                <span className="cp-choice-t">{r.title}</span>
                <span className="cp-choice-s">{r.blurb}</span>
              </span>
              {shown && <Icon name="check" className="i sm cp-choice-on" />}
            </button>
          );
        })}
      </div>
      <p className="cp-note">
        Saved on this device. The whole rail folds away from the visit itself.
      </p>
    </div>
  );
}
