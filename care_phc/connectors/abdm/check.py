"""Run: python3 -m care_phc.connectors.abdm.check

The compliance guards, the SDK delegation and the retry path, with a client
double in place of ekacare.EkaCareClient, so no credential and no socket are
involved. Supersedes care_phc/tests/test_eka.py and care_phc/tests/test_token.py:
the hand-rolled transport and TokenManager those exercised are gone.

The load-bearing ones are the first three. Delete the scrub in eka.py and they
fail with an Aadhaar number in the message, which is the point of them.
"""
from ekacare.utils.exceptions import EkaCareAPIError, EkaCareAuthError

from care_phc.connectors.abdm.base import AbdmError
from care_phc.connectors.abdm.eka import CHECK_PHR, EkaAbdm, _scrub, last4

AADHAAR = "1234 5678 9012"
ECHOED = '{"error":"invalid aadhaar %s","code":"ABDM-1008"}' % AADHAAR


class Response:
    """Only what eka.py reads off a requests.Response."""

    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.text = text if text is not None else __import__("json").dumps(body or {})
        self.content = self.text.encode()

    def json(self):
        return self._body if self._body is not None else {}


class Profile:
    """Stands in for ekacare.abdm.profile.Profile."""

    def __init__(self, owner):
        self.owner = owner

    def _record(self, name, *args):
        self.owner.calls.append((name, args))
        out = self.owner.next()
        if isinstance(out, Exception):
            raise out
        return out

    def get_profile(self):
        return self._record("get_profile")

    def get_abha_card(self):
        return self._record("get_abha_card")

    def get_abha_qr_code(self):
        return self._record("get_abha_qr_code")

    def initiate_kyc(self, method, identifier):
        return self._record("initiate_kyc", method, identifier)

    def verify_kyc_otp(self, txn_id, otp):
        return self._record("verify_kyc_otp", txn_id, otp)

    def resend_kyc_otp(self, txn_id):
        return self._record("resend_kyc_otp", txn_id)


class Client:
    """Stands in for ekacare.EkaCareClient: the same three things eka.py uses,
    request(), set_access_token() and abdm_profile."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.tokens_cleared = 0
        self.client_id, self.client_secret = "cid", "sek"
        self.base_url = "https://api.eka.care"
        self.abdm_profile = Profile(self)

    def next(self):
        return self.outcomes.pop(0)

    def request(self, method=None, endpoint=None, json=None, headers=None,
                raw_response=False, **kw):
        self.calls.append({"method": method, "endpoint": endpoint,
                           "body": json, "headers": headers or {}})
        out = self.next()
        if isinstance(out, Exception):
            raise out
        return out

    def set_access_token(self, token):
        if token is None:
            self.tokens_cleared += 1


def build(outcomes, **kw):
    client = Client(outcomes)
    return EkaAbdm(client=client, **kw), client


# ---- the guards ------------------------------------------------------------

def test_an_aadhaar_number_never_survives_into_a_log_line():
    for text in ("failed for 1234 5678 9012", "aadhaar=123456789012 rejected",
                 "1234-5678-9012"):
        assert "<aadhaar-redacted>" in _scrub(text)
        assert "5678" not in _scrub(text)


def test_a_gateway_error_echoing_an_aadhaar_is_scrubbed_on_the_raw_path():
    """The real leak: the gateway echoes the request back in its error body and
    that string becomes an exception message, a traceback and a log line."""
    eka, _ = build([Response(400, text=ECHOED)])
    try:
        eka.start_aadhaar_enrolment("123456789012")
    except AbdmError as e:
        assert "5678" not in str(e), f"an Aadhaar number reached the exception: {e}"
        assert "<aadhaar-redacted>" in str(e)
        assert e.status == 400 and e.code == "ABDM-1008"
    else:
        raise AssertionError("a 400 did not raise")


def test_an_sdk_error_echoing_an_aadhaar_is_scrubbed_too():
    """The SDK builds its message as f"API error {code}: {response.text}", so
    its own exception objects carry the echo. Ours must not."""
    eka, _ = build([EkaCareAPIError("API error 400: " + ECHOED)])
    try:
        eka.start_kyc(method="aadhaar", identifier="123456789012")
    except AbdmError as e:
        assert "5678" not in str(e), f"the SDK's error leaked through: {e}"
        assert e.status == 400
        assert e.__suppress_context__, \
            "the unscrubbed SDK error would print in a traceback"
        assert "5678" not in str(e.__cause__ or "")
    else:
        raise AssertionError("an SDK error did not become an AbdmError")


def test_mobile_numbers_are_kept_as_last_four_only():
    assert last4("+91 98765 43210") == "3210"
    assert last4("9876543210") == "3210"
    assert last4("12") == ""
    assert last4(None) == ""


def test_an_otp_and_an_aadhaar_are_never_kept_on_the_connector():
    eka, _ = build([Response(200, {"txn_id": "t1", "hint": "XXXXXX3210"}),
                    {"status": "ok"}])
    eka.start_aadhaar_enrolment("123456789012")
    eka.verify_kyc(txn_id="t1", otp="123456")
    assert set(vars(eka)) == {"_client", "_hip_id"}, \
        f"the connector grew state during the journey: {sorted(vars(eka))}"
    assert "123456" not in repr(eka) and "<EkaAbdm" in repr(eka)


# ---- raw REST, the half the SDK does not implement -------------------------

def test_the_raw_calls_go_out_on_the_sdk_client():
    eka, client = build([Response(200, {"exists": False})], hip_id="HIP123")
    assert eka.abha_address_exists("someone99") is False
    sent = client.calls[0]
    assert sent["endpoint"] == CHECK_PHR and sent["method"] == "POST"
    assert sent["body"] == {"abha_address": "someone99"}
    assert sent["headers"]["X-Hip-Id"] == "HIP123"


def test_linking_a_care_context_sends_the_shape_the_link_api_takes():
    eka, client = build([Response(202, {})], hip_id="HIP123")
    eka.link_care_context(abha_address="ramesh.k@abdm", encounter_ref="enc-002",
                          display="OP visit 11 Sep", patient_ref="pat-7")
    sent = client.calls[0]
    assert sent["endpoint"] == "/abdm/v1/care-contexts/link"
    assert sent["headers"]["X-Partner-Pt-Id"] == "pat-7"
    assert sent["body"]["care_contexts"] == [{
        "care_context_id": "enc-002", "display": "OP visit 11 Sep",
        "hi_type": "OPConsultation"}]


def test_the_known_gateway_500_reaches_the_caller_in_the_gateway_s_own_words():
    """Reproduces the blocker of 2026-09-10: Eka's validation layer is fine and
    the hop to NHA is not. A clerk is told that, not 'something went wrong'."""
    gateway = '{"error":"couldn\'t connect with ABDM servers"}'
    eka, _ = build([Response(500, text=gateway)])
    try:
        eka.abha_address_exists("testuser99")
    except AbdmError as e:
        assert e.status == 500 and "couldn't connect with ABDM servers" in str(e)
    else:
        raise AssertionError("a 500 was swallowed")


def test_the_journey_past_otp_is_honestly_unimplemented():
    eka, _ = build([])
    try:
        eka.create_or_link_abha(method="create_new", patient={})
    except NotImplementedError:
        pass
    else:
        raise AssertionError("returned something instead of admitting it is unwritten")


# ---- SDK backed ------------------------------------------------------------

def test_profile_card_qr_and_kyc_are_the_sdk_s_calls_not_ours():
    eka, client = build([{"abha_address": "x@abdm"}, b"\x89PNG...", {"qr": "..."},
                         {"txn_id": "t1"}, {"status": "ok"}, {"txn_id": "t2"}])
    assert eka.profile()["abha_address"] == "x@abdm"
    assert eka.abha_card().startswith(b"\x89PNG")
    assert eka.abha_qr() == {"qr": "..."}
    eka.start_kyc(method="aadhaar", identifier="123456789012")
    eka.verify_kyc(txn_id="t1", otp="123456")
    eka.resend_kyc_otp(txn_id="t1")
    assert [name for name, _ in client.calls] == [
        "get_profile", "get_abha_card", "get_abha_qr_code",
        "initiate_kyc", "verify_kyc_otp", "resend_kyc_otp"]
    assert client.calls[3][1] == ("aadhaar", "123456789012")
    assert not [c for c in client.calls if isinstance(c, dict)], \
        "a profile call went out as raw REST instead of through the SDK"


def test_an_error_body_wearing_the_type_bytes_is_not_returned_as_a_card():
    """get_abha_card asks the SDK for a raw response and returns .content
    without checking the status, so a failure arrives as JSON in bytes."""
    eka, _ = build([b'{"error":"no profile"}'])
    try:
        eka.abha_card()
    except AbdmError as e:
        assert "no profile" in str(e)
    else:
        raise AssertionError("an error body was handed back as an image")


def test_for_patient_keeps_the_facility_credentials_and_swaps_the_token():
    eka, _ = build([], hip_id="HIP123")
    bound = eka.for_patient("patient-token")
    assert bound._client.client_id == "cid" and bound._hip_id == "HIP123"
    assert bound._client._access_token == "patient-token"
    assert bound._client is not eka._client, "rebinding mutated the facility client"


# ---- token expiry, which the SDK does not handle itself --------------------

def test_a_401_clears_the_cached_token_and_retries_once():
    eka, client = build([Response(401, text='{"error":"expired"}'),
                         Response(200, {"exists": True})])
    assert eka.abha_address_exists("someone99") is True
    assert client.tokens_cleared == 1, "the stale token was kept"
    assert len(client.calls) == 2


def test_a_401_from_the_sdk_half_is_retried_the_same_way():
    eka, client = build([EkaCareAuthError("Authentication error: 401 - expired"),
                         {"abha_address": "x@abdm"}])
    assert eka.profile()["abha_address"] == "x@abdm"
    assert client.tokens_cleared == 1


def test_a_second_401_surfaces_rather_than_looping():
    eka, client = build([Response(401, text="expired"), Response(401, text="expired")])
    try:
        eka.abha_address_exists("someone99")
    except AbdmError as e:
        assert e.status == 401
    else:
        raise AssertionError("a persistent 401 should surface, not loop")
    assert len(client.calls) == 2


def test_a_500_is_not_retried():
    eka, client = build([Response(500, text="upstream down")])
    try:
        eka.abha_address_exists("someone99")
    except AbdmError as e:
        assert e.status == 500
    assert len(client.calls) == 1, "a 500 was retried; only a 401 should be"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
