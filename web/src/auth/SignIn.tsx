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
import { canFrameLogin, gateApplies, loginUrl, returnTo } from "./client";
import { Bloom } from "./Bloom";
import { CLIENT_ID, ENV, LOGIN_URL, probe, type Answer } from "./session";
import { signedOutHere } from "./client";

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

  // SET TRUE ON THE WAY IN, and this is the whole bug that kept somebody
  // out of their own app. React's StrictMode mounts a component, runs the
  // cleanup, and mounts it again. With no setup body this effect was only a
  // cleanup, so the second mount left `alive` false FOREVER -- and every
  // line below that guards on it was then dead. The session arrived, was
  // thrown away, and the screen said nothing, because the line that says
  // what Eka answered was behind the same guard.
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const ask = useCallback(() => {
    // WHERE THE GATE DOES NOT APPLY, THE PROBE CAN ONLY SAY NO. The
    // `.eka.care` cookie is never sent to localhost, so asking Eka whether
    // this browser has a session is asking a question with one possible
    // answer -- and gating the way back in on it meant a developer who
    // signed out could not return. This screen is only reachable there by
    // signing out, so the way back is simply saying so.
    if (!gateApplies(location.hostname)) { onRetry(); return; }
    void probe().then((answer) => {
      if (!alive.current) return;
      setHeard(answer);
      // A session found while somebody is deliberately signed out is not a
      // reason to let them in; it is the cookie they already knew about.
      if (answer.ok && !signedOutHere()) onRetry();
    });
  }, [onRetry]);

  // While Eka's own page is on screen, ask now and then whether it worked.
  //
  // NOT WHEN SOMEBODY HAS JUST SIGNED OUT, and that was a real bug with a
  // simple shape: the Eka cookie belongs to login.eka.care and this app
  // cannot delete it, so the moment Sign out showed this screen, the very
  // next poll found the cookie still good and let the person straight back
  // in. The button looked broken because in effect it was.
  //
  // Nothing about the cookie changed -- it still cannot be deleted from
  // here -- but a person who asked to leave is not asked to prove it twice
  // a second. They stay out until they say otherwise, which is the button
  // below, and the poll is for the case it was written for: somebody
  // signing IN through Eka's page, where the cookie appears and the app
  // should notice without being told.
  const left = signedOutHere();
  useEffect(() => {
    if (!framed || checking || left) return;
    const id = setInterval(ask, ASK_EVERY);
    return () => clearInterval(id);
  }, [framed, checking, left, ask]);

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
        {/* SIGNED OUT HERE, ON PURPOSE. Eka's page is not drawn: it would
            find the cookie, this screen would let the person back in, and
            the button they just pressed would have done nothing. The way
            back is a sentence and a button, and the sentence is honest that
            the Eka session is still open and where it ends. */}
        {left ? (
          <div className="way-in-out">
            <p className="way-in-ob">
              You have signed out of {NAME} on this device. You are still
              signed in to Eka, which is a cookie this app cannot delete.
            </p>
            <div className="way-in-foot">
              <button className="way-in-again" onClick={onRetry}>
                Sign back in
              </button>
              <a className="way-in-tab" href={LOGIN_URL} target="_blank" rel="noreferrer">
                End the Eka session
              </a>
            </div>
          </div>
        ) : framed ? (
          <>
            {/* No card. Eka's page IS the right hand side of this screen. */}
            <iframe
              className="way-in-frame"
              src={loginUrl(ENV, CLIENT_ID, returnTo(location.origin, location.pathname))}
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
