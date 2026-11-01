/** The corner being painted.
 *
 *  A seed at the bottom left, then the flowers gathering around it, then two
 *  boundary lines running out of them -- along the bottom, left to right,
 *  and up the left, bottom to top -- each reaching about seven tenths of the
 *  way. About half a minute, and then it stops. Nothing loops. A page
 *  somebody signs in on should settle.
 *
 *  THE FLOWERS ARE NOT THIS REPOSITORY'S. They are the owner's own tracing,
 *  cut down to the corner cluster and carried in `frame-strokes.ts`, which
 *  says what was taken and what was left behind. Nothing here invents a
 *  petal.
 *
 *  HOW THE PAINTING IS DONE. Every outline is STROKED rather than filled --
 *  the trace draws its ink as filled regions, and the boundary of a hairline
 *  region is the hairline -- so a dash the length of the line, pushed off
 *  the end and walked back on, is a line appearing at the speed a pen moves.
 *  The runs overlap by about half, so several lines are always appearing at
 *  once rather than one finishing before the next starts. That is the
 *  difference between a time lapse of somebody painting and a cursor.
 *
 *  THE BOUNDARY LINES ARE NOT IN THE TRACE and could not be: they have to
 *  reach a share of the SCREEN, and the drawing has a fixed shape. They are
 *  two elements with a hairline down each edge, revealed by a scale from the
 *  end they grow out of, which the compositor does without repainting
 *  anything at all.
 */
import { CLUSTER_ENDS, STROKES } from "./frame-strokes";

/** How long the mark is alone on screen before the painting starts. */
const SEED_HOLD = 3;

/** The lines leave the cluster before it is finished, the way a hand moves
 *  on while the paint is still wet. */
const LINES_AT = SEED_HOLD + CLUSTER_ENDS * 0.55;

export function Bloom() {
  return (
    <div className="bloom" aria-hidden="true">
      <svg className="bloom-plot" viewBox="0 320 700 745"
           preserveAspectRatio="xMinYMax meet">
        {/* The mark it opens as: the product's own geometric daffodil, at the
            corner the cluster is about to gather in. It hands over rather
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

      <div className="bloom-rail across"
           style={{ animationDelay: `${LINES_AT.toFixed(2)}s` }} />
      <div className="bloom-rail up"
           style={{ animationDelay: `${(LINES_AT + 1.5).toFixed(2)}s` }} />
    </div>
  );
}
