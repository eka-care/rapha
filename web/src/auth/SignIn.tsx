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
import { useEffect, useRef } from "react";
import { NAME } from "../brand";
import { canFrameLogin, loginUrl } from "./client";
import { Bloom } from "./Bloom";
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
        {framed && (
          /* ALWAYS, not only once the frame reports a load. The card can
             land on a page that refuses -- Eka answers a sign-in aimed at an
             unregistered return address with its own 403, and a 403 inside a
             frame is a dead end with no way out of it. The way out is here
             whatever the frame is showing. */
          <div className="way-in-foot">
            <button className="way-in-again" onClick={onRetry}>I have signed in</button>
            <a className="way-in-tab" href={LOGIN_URL} target="_blank" rel="noreferrer">
              Open in a tab instead
            </a>
          </div>
        )}
      </section>
    </div>
  );
}
