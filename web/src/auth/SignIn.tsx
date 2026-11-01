/** The screen when there is no Eka session.
 *
 *  nectar's abdm-parent shows one line -- "Session expired. Please log in
 *  again." -- on an error overlay, and offers nothing else, because there is
 *  nothing else: the session belongs to Eka and is renewed there. This says
 *  the same thing and adds the way back, which is the one thing a person on
 *  that screen wants.
 */
import { NAME } from "../brand";
import { LOGIN_URL } from "./session";

export function SignIn({ checking, onRetry }: {
  checking: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="signin">
      <div className="signin-card">
        <svg className="signin-mark" viewBox="0 0 24 24" aria-hidden="true">
          <use href="#i-mark-lg" />
        </svg>
        <h1 className="signin-t">{NAME}</h1>
        {checking ? (
          <p className="signin-b">Checking your session…</p>
        ) : (
          <>
            <p className="signin-b">
              Session expired. Sign in to Eka in this browser, then come back.
            </p>
            <div className="signin-f">
              <a className="signin-go" href={LOGIN_URL} target="_blank" rel="noreferrer">
                Sign in to Eka
              </a>
              <button className="signin-again" onClick={onRetry}>
                I have signed in
              </button>
            </div>
            {/* The one thing a person on this screen cannot work out for
                themselves, and the reason a developer sees it on localhost:
                the cookie belongs to .eka.care and is not sent anywhere
                else. */}
            <p className="signin-n">
              The session is a cookie on eka.care, so this page has to be served
              from a subdomain of it over https.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
