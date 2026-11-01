/** The mark becoming a garland.
 *
 *  It opens as the geometric daffodil this product is marked with, in the
 *  bottom left corner. Over half a minute that mark gives way to the thing
 *  it is a drawing OF: a sparse garland in the manner of a botanical border,
 *  a cluster of heads gathered at the corner and a few more thinning out
 *  along the bottom edge and up the left. Then it stops. Nothing loops: a
 *  page somebody signs in on should settle, and a movement that never ends
 *  is eventually only in the way.
 *
 *  FAR THINNER THAN THE REFERENCE IT COMES FROM. A border of that density
 *  belongs on a printed page with nothing else on it. This one has four
 *  heads, because a sign in screen has a card and a wordmark to read, and
 *  the drawing is the frame around them rather than the subject.
 *
 *  HOW IT GROWS, which is the owner's own direction: the stems along the
 *  bottom fill left to right, the ones up the side fill bottom to top. Each
 *  is a `clip-path: inset()` animating one edge, which the compositor does
 *  without touching layout. Leaves and heads live inside those groups, so
 *  each arrives as the stem carrying it reaches it.
 */

/** A strap leaf, the long narrow blade of the reference: parallel sided for
 *  most of its length, tapering to a point, with the midrib showing. Drawn
 *  growing up from its own origin, so a rotation is the angle it leaves the
 *  stem at. */
function Leaf({ x, y, turn, scale }: { x: number; y: number; turn: number; scale: number }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${turn}) scale(${scale})`}>
      <path className="bloom-leaf"
            d="M0 0C4 -16 8 -36 6 -56C5 -67 2.5 -74 0 -80C-2.5 -74 -5 -67 -6 -56C-8 -36 -4 -16 0 0Z" />
      <path className="bloom-rib" d="M0 -4C1.6 -20 2.6 -44 0 -76" />
    </g>
  );
}

/** The little sprung curl a stem throws out sideways, which is most of what
 *  keeps a border like this from looking drawn with a ruler. */
function Tendril({ x, y, turn, scale }: { x: number; y: number; turn: number; scale: number }) {
  return (
    <path className="bloom-tendril"
          transform={`translate(${x} ${y}) rotate(${turn}) scale(${scale})`}
          d="M0 0C11 -7 17 -17 11 -23C6 -28 -2 -24 -1 -17C0 -11 6 -9 9 -13" />
  );
}

/** One daffodil head, traced off the reference. Six petals, each a tapered
 *  lobe to a point with a vein down it and no two the same width; a short
 *  wide corona whose rim is a ruffle of small loops, which is the one
 *  feature that tells a daffodil from anything else with six petals; three
 *  stamens inside it; and the spathe, the dry paper sheath, at the neck. */
function Head({ x, y, scale, turn, at }: {
  x: number; y: number; scale: number; turn: number; at: number;
}) {
  const petals = [0, 59, 121, 182, 242, 301];
  const wide = [1, .92, 1.07, .96, 1.05, .94];

  // The ruffle: small loops around the top half of the corona's rim,
  // alternating size so the crown is uneven the way a real one is.
  const rim = Array.from({ length: 11 }, (_, i) => {
    const t = Math.PI + (i / 10) * Math.PI;
    return { cx: 9.6 * Math.cos(t), cy: -1 + 7 * Math.sin(t), r: i % 2 ? 1.4 : 1.95 };
  });

  return (
    <g className="bloom-head" style={{ animationDelay: `${at}s` }}
       transform={`translate(${x} ${y}) rotate(${turn}) scale(${scale})`}>
      {/* The spathe first, so the petals sit over it. */}
      <path className="bloom-spathe" d="M-3.4 9C-7 15 -5 22 0 25C5 22 7 15 3.4 9Z" />

      {petals.map((a, i) => (
        <g key={a} transform={`rotate(${a}) scale(${wide[i]} 1)`}>
          <path className="bloom-petal"
                d="M0 -8C-5 -14 -9 -21 -8 -28C-7 -35 -3.5 -40 -.6 -43.5C1.6 -40 6 -35 7.4 -28C8.8 -21 5 -14 0 -8Z" />
          <path className="bloom-vein" d="M-.4 -11C-1.2 -20 -1 -31 -.6 -41" />
        </g>
      ))}

      <path className="bloom-cup"
            d="M-9.6 -1C-9.6 -7 -5 -10.6 0 -10.6C5 -10.6 9.6 -7 9.6 -1C9.6 5.4 5 8.6 0 8.6C-5 8.6 -9.6 5.4 -9.6 -1Z" />
      {rim.map((c, i) => (
        <circle key={i} className="bloom-ruffle" cx={c.cx} cy={c.cy} r={c.r} />
      ))}
      <path className="bloom-stamen" d="M-2.6 2.4L-1.6 -3M0 3L0 -3.6M2.6 2.4L1.6 -3" />
    </g>
  );
}

export function Bloom() {
  return (
    <div className="bloom" aria-hidden="true">
      <svg viewBox="0 0 780 640" preserveAspectRatio="xMinYMax meet" className="bloom-svg">
        {/* The mark it opens as, at the corner the garland gathers in. */}
        <g className="bloom-seed">
          {[0, 60, 120, 180, 240, 300].map((a) => (
            <path key={a} transform={`rotate(${a} 96 556)`}
                  d="M96 544C82 536 76 520 76 506C76 492 85 483 96 482C107 483 116 492 116 506C116 520 110 536 96 544Z" />
          ))}
          <circle cx="96" cy="556" r="28" />
          <circle cx="96" cy="556" r="15" />
        </g>

        {/* ALONG THE BOTTOM, left to right, thinning as it goes. */}
        <g className="bloom-across a">
          <path className="bloom-stem"
                d="M0 634C70 626 140 616 214 608C296 599 372 604 448 596C512 589 560 592 606 586" />
          {/* The pedicels that carry two of the heads off the runner. */}
          <path className="bloom-stem" d="M140 616C146 598 150 584 154 574" />
          <path className="bloom-stem" d="M268 606C282 588 302 574 324 564" />
          <Leaf x={92} y={622} turn={-36} scale={.78} />
          <Leaf x={204} y={609} turn={24} scale={.6} />
          <Leaf x={396} y={599} turn={-30} scale={.52} />
          <Tendril x={470} y={594} turn={-58} scale={.7} />
          <Tendril x={596} y={587} turn={-40} scale={.5} />

          <Head x={156} y={566} scale={.92} turn={16} at={19} />
          <Head x={330} y={554} scale={.8} turn={6} at={22} />
        </g>

        {/* A second, lower runner, barely there: it reads as depth. */}
        <g className="bloom-across b">
          <path className="bloom-stem"
                d="M0 640C90 636 160 628 240 632C330 637 398 626 480 630" />
          <Leaf x={168} y={629} turn={-18} scale={.4} />
          <Leaf x={322} y={635} turn={16} scale={.34} />
        </g>

        {/* UP THE SIDE, bottom to top, two heads and then nothing. */}
        <g className="bloom-up a">
          <path className="bloom-stem"
                d="M14 638C4 566 24 500 16 432C8 368 30 322 46 294" />
          <path className="bloom-stem" d="M16 600C34 580 56 556 72 534" />
          <Leaf x={10} y={560} turn={72} scale={.74} />
          <Leaf x={18} y={452} turn={52} scale={.58} />
          <Leaf x={14} y={356} turn={78} scale={.64} />
          <Tendril x={20} y={408} turn={26} scale={.66} />

          <Head x={78} y={526} scale={1} turn={-18} at={16} />
          <Head x={50} y={286} scale={.76} turn={-8} at={25} />
        </g>

        <g className="bloom-up b">
          <path className="bloom-stem"
                d="M30 640C42 582 26 530 38 476C48 432 36 400 44 366" />
          <Leaf x={34} y={508} turn={62} scale={.44} />
          <Leaf x={40} y={414} turn={46} scale={.36} />
        </g>
      </svg>
    </div>
  );
}
