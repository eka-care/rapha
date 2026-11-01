/** The way in: the daffodil opening, and Eka's own login in a card beside it.
 *
 *  THE LOGIN IS REALLY EKA'S. The card holds login.eka.care itself, in a
 *  frame, because the header it sends says that is allowed from an eka.care
 *  origin -- `frame-ancestors 'self' https://eka.care https://*.dev.eka.care
 *  https://*.eka.care` -- and this app is served from one of those whenever
 *  the session matters at all. Nothing here asks for a password, sees one,
 *  or could. The person signs in to Eka, on Eka's page, and the cookie that
 *  lands is the session.
 *
 *  Anywhere else the browser refuses the frame and draws a blank box, so
 *  anywhere else this offers the same page in a new tab instead and says
 *  why. `canFrameLogin` is that rule, read off the header rather than
 *  guessed at.
 *
 *  AND IT WATCHES. A login that completes in the card leaves a cookie and
 *  nothing else: no message crosses that origin boundary. So while the card
 *  is open this asks, quietly, whether the session has appeared -- which is
 *  the same question the app asks on load, and the only one there is.
 */
import { useEffect, useRef, useState } from "react";
import { NAME } from "../brand";
import { canFrameLogin, loginUrl } from "./client";
import { CLIENT_ID, ENV, LOGIN_URL, signedIn } from "./session";

/** How often the card asks whether the cookie has arrived. Slow on purpose:
 *  it is a courtesy, the person can press the button, and a login page does
 *  not need a heartbeat. */
const ASK_EVERY = 2500;

export function SignIn({ checking, onRetry }: {
  checking: boolean;
  onRetry: () => void;
}) {
  const framed = canFrameLogin(location.hostname);
  const [waiting, setWaiting] = useState(false);
  const alive = useRef(true);

  useEffect(() => () => { alive.current = false; }, []);

  // While Eka's own page is on screen, ask now and then whether it worked.
  useEffect(() => {
    if (!framed || checking) return;
    const id = setInterval(() => {
      void signedIn().then((yes) => { if (yes && alive.current) onRetry(); });
    }, ASK_EVERY);
    return () => clearInterval(id);
  }, [framed, checking, onRetry]);

  return (
    <div className="way-in">
      <Bloom />

      <section className="way-in-say">
        <h1 className="way-in-t">{NAME}</h1>
        <p className="way-in-b">
          Every record committed by a person who was there.
        </p>
      </section>

      <section className="way-in-card" aria-label={`Sign in to ${NAME}`}>
        {checking ? (
          <div className="way-in-wait">Checking your session…</div>
        ) : framed ? (
          <iframe
            className="way-in-frame"
            src={loginUrl(ENV, CLIENT_ID, location.origin + location.pathname)}
            title="Sign in with Eka"
            onLoad={() => setWaiting(true)}
          />
        ) : (
          <div className="way-in-out">
            <p className="way-in-ob">
              Sign in to Eka in this browser, then come back.
            </p>
            <a className="way-in-go" href={LOGIN_URL} target="_blank" rel="noreferrer">
              Open Eka
            </a>
            <button className="way-in-again" onClick={onRetry}>I have signed in</button>
            {/* The one thing a person on this screen cannot work out, and the
                reason a developer meets it on localhost: both the cookie and
                the frame belong to eka.care. */}
            <p className="way-in-n">
              This page is on <b>{location.hostname}</b>. The session is a cookie on
              eka.care, and Eka only allows its login inside a page served from
              there, so the card cannot be shown here.
            </p>
          </div>
        )}
        {framed && waiting && (
          <button className="way-in-again wide" onClick={onRetry}>I have signed in</button>
        )}
      </section>
    </div>
  );
}

/** The motion: a daffodil opening, over and over, slowly.
 *
 *  Six petals drawn in sequence by running a dash along each outline, a
 *  trumpet that arrives last, and a slow breath under the whole head. It is
 *  the product's own mark rather than an animation bought in: a person
 *  waiting here should be looking at the thing they are signing in to.
 *
 *  Every part of it is one CSS property on one element, so the browser keeps
 *  it on the compositor, and all of it stops under `prefers-reduced-motion`.
 */
function Bloom() {
  // The petal, the trumpet and the ring come from the same geometry the mark
  // is drawn from; kept here as numbers rather than imported so this file can
  // stagger them without the icon sheet learning about animation.
  const PETAL = "M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1"
    + "C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z";
  return (
    <div className="bloom" aria-hidden="true">
      <svg viewBox="0 0 24 24" className="bloom-svg">
        <g className="bloom-head">
          {[0, 60, 120, 180, 240, 300].map((a, i) => (
            <path
              key={a}
              className="bloom-petal"
              d={PETAL}
              transform={`rotate(${a} 12 12)`}
              style={{ animationDelay: `${i * 0.28}s` }}
            />
          ))}
          <circle className="bloom-cup" cx="12" cy="12" r="3.5" />
          <circle className="bloom-throat" cx="12" cy="12" r="1.9" />
        </g>
        {/* Three rings leaving the flower, one after another: the line
            moving, which is what this product watches all day. */}
        {[0, 1, 2].map((i) => (
          <circle
            key={i}
            className="bloom-ring"
            cx="12"
            cy="12"
            r="6"
            style={{ animationDelay: `${i * 1.6}s` }}
          />
        ))}
      </svg>
    </div>
  );
}
