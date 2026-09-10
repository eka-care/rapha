"""Run: python3 -m care_phc.tests.test_eka

The compliance guards and the retry path, tested with an injected transport so
no credential and no network are involved.
"""
from care_phc.connectors.abdm.base import AbdmError
from care_phc.connectors.abdm.eka import EkaAbdm, _scrub, last4


def build(responses):
    calls = []

    def transport(url, body, headers=None):
        calls.append({"url": url, "body": body, "headers": headers or {}})
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    return EkaAbdm("https://api.eka.care", "cid", "sek", transport=transport), calls


TOKEN = {"access_token": "t1", "expires_in": 3600, "refresh_token": "r1"}


def test_an_aadhaar_number_never_survives_into_a_log_line():
    for text in ("failed for 1234 5678 9012", "aadhaar=123456789012 rejected",
                 "1234-5678-9012"):
        assert "<aadhaar-redacted>" in _scrub(text)
        assert "5678" not in _scrub(text)


def test_a_gateway_error_carrying_an_aadhaar_is_scrubbed_before_it_is_raised():
    """The real leak path: the gateway echoes the request back in an error and
    that string becomes an exception message, a traceback, and a log line."""
    import io
    import urllib.error
    import urllib.request
    from care_phc.connectors.abdm import eka as mod

    body = b'{"error":"invalid aadhaar 1234 5678 9012","code":400}'
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    real = urllib.request.urlopen
    urllib.request.urlopen = boom
    try:
        mod._post("https://api.eka.care/x", {"aadhaar_number": "123456789012"})
    except AbdmError as e:
        assert "5678" not in str(e), f"an Aadhaar number reached the exception: {e}"
        assert "<aadhaar-redacted>" in str(e)
        assert e.status == 400 and e.code == 400
    else:
        raise AssertionError("a 400 did not raise")
    finally:
        urllib.request.urlopen = real


def test_mobile_numbers_are_kept_as_last_four_only():
    assert last4("+91 98765 43210") == "3210"
    assert last4("9876543210") == "3210"
    assert last4("12") == ""
    assert last4(None) == ""


def test_the_bearer_token_is_attached_and_reused():
    eka, calls = build([TOKEN, {"exists": False}, {"exists": True}])
    assert eka.abha_address_exists("someone99") is False
    assert eka.abha_address_exists("another99") is True
    auths = [c["headers"].get("Authorization") for c in calls[1:]]
    assert auths == ["Bearer t1", "Bearer t1"], "re-authenticated unnecessarily"
    assert calls[1]["url"].endswith("/abdm/na/v1/registration/phr/check")
    assert calls[1]["body"] == {"abha_address": "someone99"}


def test_a_401_triggers_one_reauth_and_one_retry():
    eka, calls = build([TOKEN,
                        AbdmError("expired", status=401),
                        {"access_token": "t2", "expires_in": 3600},
                        {"exists": True}])
    assert eka.abha_address_exists("someone99") is True
    assert calls[-1]["headers"]["Authorization"] == "Bearer t2"


def test_a_second_401_is_not_retried_forever():
    eka, _ = build([TOKEN,
                    AbdmError("expired", status=401),
                    {"access_token": "t2", "expires_in": 3600},
                    AbdmError("still expired", status=401)])
    try:
        eka.abha_address_exists("someone99")
    except AbdmError as e:
        assert e.status == 401
    else:
        raise AssertionError("a persistent 401 should surface, not loop")


def test_a_non_401_error_is_not_retried():
    eka, calls = build([TOKEN, AbdmError("upstream down", status=500)])
    try:
        eka.abha_address_exists("someone99")
    except AbdmError as e:
        assert e.status == 500
    assert len(calls) == 2, "a 500 was retried; only a 401 should be"


def test_the_hip_id_header_is_sent_when_configured():
    eka, calls = build([TOKEN, {"exists": False}])
    eka._hip_id = "HIP123"
    eka.abha_address_exists("someone99")
    assert calls[1]["headers"]["X-Hip-Id"] == "HIP123"


def test_the_journey_past_otp_is_honestly_unimplemented():
    eka, _ = build([])
    for call in (lambda: eka.create_or_link_abha(method="create_new", patient={}),
                 lambda: eka.link_care_context(abha_number="1", encounter_ref="e", display="d")):
        try:
            call()
        except NotImplementedError:
            pass
        else:
            raise AssertionError("returned something instead of admitting it is unwritten")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
