/** The border being sketched.
 *
 *  A seed at the bottom left corner, and then somebody invisible draws the
 *  border: along the bottom first, then up the left, one line at a time,
 *  the way a hand does it. About half a minute, and then the hand lifts.
 *  Nothing loops. A page somebody signs in on should settle.
 *
 *  THE DRAWING IS NOT THIS REPOSITORY'S. It is the owner's own tracing, cut
 *  down to the bottom and left border and carried in `frame-strokes.ts`,
 *  which says what was taken and what was left behind. Nothing here invents
 *  a petal.
 *
 *  HOW THE SKETCHING IS DONE. Every outline is STROKED rather than filled --
 *  the trace draws its ink as filled regions, and the boundary of a hairline
 *  region is the hairline -- so a dash the length of the line, pushed off
 *  the end and walked back on, is a line appearing at the speed a pen moves.
 *  That is the whole trick. The runs are pre-measured, so each draws at the
 *  same speed whatever is in it, and they overlap slightly so the hand never
 *  visibly stops between them.
 */
import { SKETCH_ENDS, STROKES } from "./frame-strokes";

/** How long the mark is alone on screen before the drawing starts. */
const SEED_HOLD = 3;

export function Bloom() {
  return (
    <div className="bloom" aria-hidden="true">
      <svg viewBox="0 320 700 745" preserveAspectRatio="xMinYMax meet"
           className="bloom-svg" data-ends={SKETCH_ENDS}>
        {/* The mark it opens as: the product's own geometric daffodil, at the
            corner the border is about to grow out of. It hands over rather
            than sitting there, which is the point of starting with it. */}
        <g className="bloom-seed">
          {[0, 60, 120, 180, 240, 300].map((a) => (
            <path key={a} transform={`rotate(${a} 96 952)`}
                  d="M96 940C82 932 76 916 76 902C76 888 85 879 96 878C107 879 116 888 116 902C116 916 110 932 96 940Z" />
          ))}
          <circle cx="96" cy="952" r="28" />
          <circle cx="96" cy="952" r="15" />
        </g>

        {STROKES.map((s, i) => (
          <path
            key={i}
            className="bloom-ink"
            d={s.d}
            style={{
              strokeDasharray: s.len,
              strokeDashoffset: s.len,
              animationDuration: `${s.dur}s`,
              animationDelay: `${(SEED_HOLD + s.at).toFixed(2)}s`,
            }}
          />
        ))}
      </svg>
    </div>
  );
}
