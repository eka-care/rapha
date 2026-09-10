"""Run: python3 -m care_phc.tests.test_token

No network and no credential: the transport and the clock are injected, so the
token rules are testable before anyone has a secret.
"""
from care_phc.connectors.abdm.token import SKEW_SECONDS, TokenManager


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def manager(responses=None, clock=None, **kw):
    clock = clock or Clock()
    calls = []

    def transport(url, body):
        calls.append((url, body))
        if responses:
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return {"access_token": f"tok{len(calls)}", "expires_in": 3600,
                "refresh_token": f"ref{len(calls)}"}

    return TokenManager("https://api.dev.eka.care/", "cid", "sek", transport,
                        now=clock, **kw), calls, clock


def test_first_call_logs_in_and_the_rest_reuse_it():
    m, calls, _ = manager()
    assert m.token() == "tok1"
    assert m.token() == "tok1"
    assert m.token() == "tok1"
    assert m.logins == 1, "re-authenticated when the cached token was still good"
    assert calls[0][0].endswith("/connect-auth/v1/account/login")
    assert calls[0][1] == {"client_id": "cid", "client_secret": "sek"}


def test_a_sharing_key_is_sent_only_when_given():
    m, calls, _ = manager(sharing_key="sk1")
    m.token()
    assert calls[0][1]["sharing_key"] == "sk1"


def test_the_token_is_renewed_before_the_server_expires_it():
    clock = Clock()
    m, calls, _ = manager(clock=clock)
    m.token()
    clock.t += 3600 - SKEW_SECONDS - 1     # just inside the safety margin
    assert m.logins == 1
    clock.t += 2                            # now past it, still before real expiry
    m.token()
    assert m.logins == 1, "should have refreshed, not logged in again"
    assert calls[-1][0].endswith("/refresh")


def test_expiry_prefers_refresh_over_a_full_login():
    clock = Clock()
    m, calls, _ = manager(clock=clock)
    m.token()
    clock.t += 99999
    assert m.token() == "tok2"
    assert m.logins == 1
    assert calls[-1][1] == {"refresh_token": "ref1"}


def test_a_dead_refresh_token_falls_back_to_logging_in():
    clock = Clock()
    m, calls, _ = manager(
        responses=[{"access_token": "a", "expires_in": 3600, "refresh_token": "r"},
                   RuntimeError("refresh rejected"),
                   {"access_token": "b", "expires_in": 3600}],
        clock=clock)
    assert m.token() == "a"
    clock.t += 99999
    assert m.token() == "b", "a dead refresh token should not be fatal"
    assert m.logins == 2


def test_invalidate_forces_reauthentication():
    m, calls, _ = manager()
    assert m.token() == "tok1"
    before = len(calls)
    m.invalidate()
    assert m.token() == "tok2", "kept serving the token a 401 just rejected"
    assert len(calls) == before + 1
    assert calls[-1][0].endswith("/refresh")


def test_a_missing_expires_in_does_not_make_an_immortal_token():
    clock = Clock()
    m, _, _ = manager(responses=[{"access_token": "a"},
                                 {"access_token": "b", "expires_in": 3600}],
                      clock=clock)
    assert m.token() == "a"
    clock.t += 31
    assert m.token() == "b", "a token with no stated lifetime was trusted forever"


def test_concurrent_callers_trigger_one_login_not_a_herd():
    import threading
    m, _, _ = manager()
    out = []
    threads = [threading.Thread(target=lambda: out.append(m.token())) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(out)) == 1
    assert m.logins == 1, f"{m.logins} logins for 12 concurrent callers"


def test_the_secret_never_appears_in_repr():
    m, _, _ = manager()
    m.token()
    assert "sek" not in repr(m)
    assert "tok1" not in repr(m)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
