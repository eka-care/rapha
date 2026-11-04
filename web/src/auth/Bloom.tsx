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
import { MOTIFS, type MotifName } from "./garland-motifs";

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

/** THE GARLANDS. The sign in screen's flowers, rearranged for the screens a
 *  person works in, rather than its corner pasted into them.
 *
 *  A column is tall and narrow, so it gets a VINE: one stem climbing its
 *  left edge, the flowers getting smaller as it rises, a tendril or two.
 *  A card is wide and short, so it gets a SPRAY trailing in from its right
 *  edge along the bottom. The flowers are the trace's own, cut out one at a
 *  time in `garland-motifs.ts`; only the stems, leaves and tendrils are
 *  drawn here, in the same hairline, because in the trace those are all
 *  joined to each other and cannot be cut out.
 *
 *  Nothing moves. The sign in screen paints itself once; a screen somebody
 *  spends the day on is not the place for a drawing that redraws.
 */
type Place = { m: MotifName; x: number; y: number; s: number; r?: number };

interface Arrangement {
  /** The drawing's own box. It is anchored at the corner it grows from, so
   *  a shorter column crops its top rather than shrinking it. */
  w: number; h: number;
  /** Stems, leaves and tendrils, as one path each. */
  ink: string[];
  flowers: Place[];
}

const VINE: Arrangement = {
  w: 240, h: 900,
  ink: [
    // The stem, as the trace draws one: two hairlines a little apart.
    "M22 900C30 820 14 760 26 690S42 560 30 480S18 360 34 262S42 200 36 170",
    "M25 900C33 820 17 760 29 690S45 560 33 480S21 360 37 262S45 200 39 170",
    // Leaves from the root: a long blade with its midrib, and a short one.
    "M24 900C42 842 70 792 98 758C76 798 48 848 31 900Z",
    "M30 896C48 846 72 800 94 763",
    "M21 900C9 852 6 806 12 764C17 806 21 852 27 900Z",
    "M30 470C52 452 78 446 104 452C80 456 56 462 32 476Z",
    // Pedicels out to each flower.
    "M28 790C40 784 50 776 58 764",
    "M32 585C44 580 54 572 62 562",
    "M33 438C44 434 52 428 58 420",
    "M37 300C44 298 50 294 54 288",
    // Tendrils.
    "M28 690C44 684 54 670 48 660C44 652 34 654 35 662C36 667 42 668 44 664",
    "M35 352C50 350 60 340 56 330C53 323 45 325 46 332C47 336 51 337 53 334",
    "M37 180C46 172 48 160 42 154C37 150 32 155 35 160",
  ],
  flowers: [
    { m: "bigL", x: 30, y: 732, s: 0.78 },
    { m: "front", x: 40, y: 512, s: 0.58, r: -8 },
    { m: "trumpet", x: 40, y: 380, s: 0.55, r: 6 },
    { m: "buds", x: 36, y: 244, s: 0.5, r: -14 },
  ],
};

const SPRAY: Arrangement = {
  w: 420, h: 220,
  ink: [
    "M420 196C360 200 300 186 250 160S170 112 120 120S70 140 52 124",
    "M420 199C360 203 300 189 250 163S170 115 120 123S70 143 52 127",
    "M420 212C380 202 332 182 300 152C336 178 380 194 420 204Z",
    "M418 207C380 196 340 178 304 155",
    "M380 220C350 214 320 206 296 194C324 202 352 208 382 213Z",
    "M300 176C292 166 288 154 290 144",
    "M206 136C202 126 202 116 206 108",
    "M108 122C104 114 102 106 104 98",
    "M52 124C40 116 38 104 46 100C52 97 56 104 51 108",
  ],
  flowers: [
    { m: "lowR", x: 290, y: 52, s: 0.62 },
    { m: "trumpet", x: 182, y: 64, s: 0.46, r: -18 },
    { m: "buds", x: 70, y: 66, s: 0.42, r: -28 },
  ],
};

const ARRANGEMENTS = { vine: VINE, spray: SPRAY } as const;

export function Garland({ kind }: { kind: keyof typeof ARRANGEMENTS }) {
  const a = ARRANGEMENTS[kind];
  return (
    <div className={`garland ${kind}`} aria-hidden="true">
      <svg className="garland-plot" viewBox={`0 0 ${a.w} ${a.h}`}
           width={a.w} height={a.h}>
        {a.ink.map((d, i) => <path key={i} d={d} />)}
        {a.flowers.map((f, i) => {
          const m = MOTIFS[f.m];
          return (
            <path key={`f${i}`} d={m.d} vectorEffect="non-scaling-stroke"
                  transform={`translate(${f.x} ${f.y}) scale(${f.s})`
                    + (f.r ? ` rotate(${f.r} ${m.w / 2} ${m.h / 2})` : "")} />
          );
        })}
      </svg>
    </div>
  );
}
