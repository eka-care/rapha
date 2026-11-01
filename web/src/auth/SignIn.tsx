/** The way in: the drawing in the corner, and Eka's own login beside it.
 *
 *  THE LOGIN IS REALLY EKA'S, AND IT IS NOT IN A BOX. login.eka.care is on
 *  the screen itself, in a frame with no card around it, because the header
 *  it sends says framing is allowed from an eka.care origin --
 *  `frame-ancestors 'self' https://eka.care https://*.dev.eka.care
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
 *  AND IT WATCHES, TWO WAYS. A login that completes leaves a cookie and
 *  nothing else: no message crosses that origin boundary. So this asks,
 *  quietly, whether the session has appeared -- on a timer, and again every
 *  time the frame navigates, because a cross origin frame still reports
 *  that it loaded even when it will not say to what. Signing in moves that
 *  frame, so the load is the earliest news there is.
 *
 *  AND IT SAYS WHAT IT HEARD. A sign in that does nothing is the worst
 *  answer a screen can give. When Eka refuses the session this shows the
 *  number Eka gave, because somebody looking at a screen that will not let
 *  them in needs something to go on, and so does anybody helping them.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { EXPANDS_TO, NAME } from "../brand";
import { canFrameLogin, loginUrl } from "./client";
import { Bloom } from "./Bloom";
import { CLIENT_ID, ENV, LOGIN_URL, probe, type Answer } from "./session";

/** How often it asks whether the cookie has arrived. The frame's own load
 *  is the quick route; this is the net under it. */
const ASK_EVERY = 2500;

export function SignIn({ checking, onRetry }: {
  checking: boolean;
  onRetry: () => void;
}) {
  const framed = canFrameLogin(location.hostname);
  const alive = useRef(true);
  const [heard, setHeard] = useState<Answer | null>(null);

  useEffect(() => () => { alive.current = false; }, []);

  const ask = useCallback(() => {
    void probe().then((answer) => {
      if (!alive.current) return;
      setHeard(answer);
      if (answer.ok) onRetry();
    });
  }, [onRetry]);

  // While Eka's own page is on screen, ask now and then whether it worked.
  useEffect(() => {
    if (!framed || checking) return;
    const id = setInterval(ask, ASK_EVERY);
    return () => clearInterval(id);
  }, [framed, checking, ask]);

  if (checking) {
    return (
      <div className="way-in">
        <Bloom />
        <section className="way-in-say">
          <h1 className="way-in-t">{NAME}</h1>
          <p className="way-in-b">{EXPANDS_TO}</p>
        </section>
        <div className="way-in-wait">Checking your session…</div>
      </div>
    );
  }

  return (
    <div className="way-in">
      <Bloom />

      <section className="way-in-say">
        <h1 className="way-in-t">{NAME}</h1>
        {/* The abbreviation, not a promise. This is the one screen with room
            for it and the one moment somebody meets the name cold. */}
        <p className="way-in-b">{EXPANDS_TO}</p>
      </section>

      <section className="way-in-eka" aria-label={`Sign in to ${NAME}`}>
        {framed ? (
          <>
            {/* No card. Eka's page IS the right hand side of this screen. */}
            <iframe
              className="way-in-frame"
              src={loginUrl(ENV, CLIENT_ID)}
              title="Sign in with Eka"
              onLoad={ask}
            />
            <div className="way-in-foot">
              <button className="way-in-again" onClick={ask}>I have signed in</button>
              <a className="way-in-tab" href={LOGIN_URL} target="_blank" rel="noreferrer">
                Open in a tab instead
              </a>
            </div>
            {/* Only once there is something to report, and only when it is
                bad news: a screen that narrates every poll is noise. */}
            {heard && !heard.ok && (
              <p className="way-in-n">
                Signed in and still here? Eka has not issued a session for{" "}
                <b>{location.hostname}</b> yet — it answered <b>{heard.said}</b>.
              </p>
            )}
          </>
        ) : (
          <div className="way-in-out">
            <p className="way-in-ob">
              Sign in to Eka in this browser, then come back.
            </p>
            <a className="way-in-go" href={LOGIN_URL} target="_blank" rel="noreferrer">
              Open Eka
            </a>
            <button className="way-in-again" onClick={ask}>I have signed in</button>
            {/* The one thing a person on this screen cannot work out, and the
                reason a developer meets it on localhost: both the cookie and
                the frame belong to eka.care. */}
            <p className="way-in-n">
              This page is on <b>{location.hostname}</b>. The session is a cookie on
              eka.care, and Eka only allows its login inside a page served from
              there, so it cannot be shown here.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
