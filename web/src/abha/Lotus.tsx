/** The ABDM lotus, as the approved mockup draws it
 *  (docs/reference/front-desk/queue-labels.html).
 *
 *  It lives in abha/ for the reason sdk.ts records at length: ABHA is a
 *  national identifier with one national journey, so it is the one concept
 *  this renderer may name without a declaration. Nothing else in here is
 *  exempt, and this file adds no second exception.
 *
 *  Three things about how it is drawn:
 *
 *  - It takes its colour from `currentColor`, so the only file that names a
 *    colour is still style/tokens.css. The caller sets `color` from
 *    --color-abdm, which that file reserves for national identity.
 *  - It carries an accessible name, because a mark with no name is a mark a
 *    screen reader reads as nothing at all.
 *  - It is never the only thing that says this. The bundle declares a badge
 *    for the state a patient is in when an ABHA belongs on the record and is
 *    not there yet, so every row that has no mark says so in words instead,
 *    and the filter chip above the list carries the count either way. The mark
 *    is the short form of something the list already says twice.
 */
export function Lotus({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="13"
      height="13"
      viewBox="0 0 24 24"
      role="img"
      aria-label="Linked to a national health account"
      focusable="false"
    >
      <title>Linked to a national health account</title>
      <path
        d="M12 2.6c1.7 2.4 2.6 4.8 2.6 7.2 0 2.4-.9 4.8-2.6 7.2-1.7-2.4-2.6-4.8-2.6-7.2 0-2.4.9-4.8 2.6-7.2z"
        fill="currentColor"
      />
      <path
        d="M20.6 8.4c-.4 2.9-1.5 5.2-3.2 6.9-1.7 1.7-4 2.8-6.9 3.2 1.2-2.7 2.6-4.7 4.3-6.1 1.7-1.4 3.6-2.4 5.8-4z"
        fill="currentColor"
        opacity=".62"
      />
      <path
        d="M3.4 8.4c2.2 1.6 4.1 2.6 5.8 4 1.7 1.4 3.1 3.4 4.3 6.1-2.9-.4-5.2-1.5-6.9-3.2C4.9 13.6 3.8 11.3 3.4 8.4z"
        fill="currentColor"
        opacity=".62"
      />
      <path
        d="M4 18.4c2.6-.7 5.3-1 8-1s5.4.3 8 1c-2.1 2-4.8 3-8 3s-5.9-1-8-3z"
        fill="currentColor"
        opacity=".4"
      />
    </svg>
  );
}
