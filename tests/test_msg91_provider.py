"""MSG91 provider tests, driven by a stubbed transport.

No network. Each test asserts on the exact request MSG91 would receive, so the
wire protocol stays pinned: query params, the authkey header on verify, and the
`type`/`message` response convention.
"""

import httpx
import pytest

from app.core.errors import (
    InvalidOtp,
    OtpExpired,
    OtpProviderUnavailable,
    OtpSendFailed,
    UnknownOtpRequest,
)
from app.otp.challenge import ChallengeCodec
from app.otp.msg91 import MSG91OtpProvider

MOBILE = "919999999999"


def make_provider(handler, *, ttl_seconds: int = 300) -> MSG91OtpProvider:
    return MSG91OtpProvider(
        authkey="test-authkey",
        template_id="test-template",
        codec=ChallengeCodec("test-secret", ttl_seconds=ttl_seconds),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def responder(payload: dict, status_code: int = 200):
    """A handler that records the request it saw and returns `payload`."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status_code, json=payload)

    return handler, seen


async def test_send_posts_the_documented_params():
    handler, seen = responder({"type": "success", "message": "ok"})
    provider = make_provider(handler)

    challenge = await provider.send(MOBILE)

    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v5/otp"
    assert dict(request.url.params) == {
        "template_id": "test-template",
        "mobile": MOBILE,
        "authkey": "test-authkey",
    }
    assert challenge.mobile == MOBILE
    assert challenge.request_id
    # A real vendor never leaks the code.
    assert challenge.debug_code is None


async def test_send_failure_is_reported_with_msg91s_wording():
    handler, _ = responder({"type": "error", "message": "invalid template_id"})
    provider = make_provider(handler)

    with pytest.raises(OtpSendFailed, match="invalid template_id"):
        await provider.send(MOBILE)


async def test_verify_sends_the_authkey_as_a_header():
    handler, seen = responder({"type": "success", "message": "OTP verified success"})
    provider = make_provider(handler)
    challenge = await provider.send(MOBILE)

    await provider.verify(challenge.request_id, MOBILE, "123456")

    request = seen[-1]
    assert request.method == "GET"
    assert request.url.path == "/api/v5/otp/verify"
    assert dict(request.url.params) == {"otp": "123456", "mobile": MOBILE}
    assert request.headers["authkey"] == "test-authkey"
    # The authkey must not also ride along in the query string.
    assert "authkey" not in request.url.params


async def test_a_wrong_code_becomes_invalid_otp():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/verify"):
            return httpx.Response(200, json={"type": "error", "message": "OTP not match"})
        return httpx.Response(200, json={"type": "success"})

    provider = make_provider(handler)
    challenge = await provider.send(MOBILE)

    with pytest.raises(InvalidOtp, match="OTP not match"):
        await provider.verify(challenge.request_id, MOBILE, "000000")


async def test_resend_defaults_to_text_and_can_ask_for_voice():
    handler, seen = responder({"type": "success", "message": "ok"})
    provider = make_provider(handler)
    challenge = await provider.send(MOBILE)

    await provider.resend(challenge.request_id, MOBILE)
    assert seen[-1].url.params["retrytype"] == "text"
    assert seen[-1].url.path == "/api/v5/otp/retry"

    await provider.resend(challenge.request_id, MOBILE, voice=True)
    assert seen[-1].url.params["retrytype"] == "voice"


async def test_transport_failure_becomes_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    provider = make_provider(handler)

    with pytest.raises(OtpProviderUnavailable):
        await provider.send(MOBILE)


async def test_a_5xx_becomes_provider_unavailable():
    handler, _ = responder({"type": "error"}, status_code=503)
    provider = make_provider(handler)

    with pytest.raises(OtpProviderUnavailable):
        await provider.send(MOBILE)


async def test_a_forged_request_id_never_reaches_msg91():
    handler, seen = responder({"type": "success"})
    provider = make_provider(handler)

    with pytest.raises(UnknownOtpRequest):
        await provider.verify("forged.handle", MOBILE, "123456")
    assert seen == []


async def test_a_handle_issued_for_another_number_is_rejected():
    handler, seen = responder({"type": "success"})
    provider = make_provider(handler)
    challenge = await provider.send(MOBILE)
    seen.clear()

    with pytest.raises(UnknownOtpRequest):
        await provider.verify(challenge.request_id, "918888888888", "123456")
    assert seen == []


async def test_an_expired_handle_never_reaches_msg91():
    handler, seen = responder({"type": "success"})
    provider = make_provider(handler, ttl_seconds=-1)
    challenge = await provider.send(MOBILE)
    seen.clear()

    with pytest.raises(OtpExpired):
        await provider.verify(challenge.request_id, MOBILE, "123456")
    assert seen == []


async def test_missing_credentials_fail_loudly_at_startup():
    with pytest.raises(ValueError, match="MSG91_AUTHKEY"):
        MSG91OtpProvider(
            authkey="", template_id="t", codec=ChallengeCodec("s", ttl_seconds=300)
        )
