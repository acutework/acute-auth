"""Unit tests for the fake provider - the contract every provider must honour."""

import pytest

from app.core.errors import InvalidOtp, OtpExpired, TooManyAttempts, UnknownOtpRequest
from app.otp.challenge import ChallengeCodec
from app.otp.fake import FIXED_CODE, FakeOtpProvider

MOBILE = "911111111111"


def make_provider(**kwargs) -> FakeOtpProvider:
    codec = ChallengeCodec("test-secret", ttl_seconds=kwargs.pop("ttl_seconds", 300))
    return FakeOtpProvider(codec=codec, ttl_seconds=codec.ttl_seconds, **kwargs)


async def test_send_returns_a_challenge_with_the_code():
    provider = make_provider()
    challenge = await provider.send(MOBILE)

    assert challenge.mobile == MOBILE
    assert challenge.request_id
    assert challenge.debug_code == "4732"


async def test_verify_accepts_the_correct_code():
    provider = make_provider()
    challenge = await provider.send(MOBILE)

    await provider.verify(challenge.request_id, MOBILE, challenge.debug_code)


async def test_a_verified_challenge_cannot_be_reused():
    provider = make_provider()
    challenge = await provider.send(MOBILE)
    await provider.verify(challenge.request_id, MOBILE, FIXED_CODE)

    with pytest.raises(UnknownOtpRequest):
        await provider.verify(challenge.request_id, MOBILE, FIXED_CODE)


async def test_unknown_request_id_is_rejected():
    provider = make_provider()

    with pytest.raises(UnknownOtpRequest):
        await provider.verify("nope", MOBILE, FIXED_CODE)


async def test_a_challenge_belongs_to_one_mobile_number():
    provider = make_provider()
    challenge = await provider.send(MOBILE)

    with pytest.raises(UnknownOtpRequest):
        await provider.verify(challenge.request_id, "912222222222", FIXED_CODE)


async def test_expired_challenge_is_rejected():
    provider = make_provider(ttl_seconds=0)
    challenge = await provider.send(MOBILE)

    with pytest.raises(OtpExpired):
        await provider.verify(challenge.request_id, MOBILE, FIXED_CODE)


async def test_attempts_are_limited():
    provider = make_provider(max_attempts=3)
    challenge = await provider.send(MOBILE)

    for _ in range(2):
        with pytest.raises(InvalidOtp):
            await provider.verify(challenge.request_id, MOBILE, "000000")

    with pytest.raises(TooManyAttempts):
        await provider.verify(challenge.request_id, MOBILE, "000000")

    # The challenge is burned - even the right code no longer works.
    with pytest.raises(UnknownOtpRequest):
        await provider.verify(challenge.request_id, MOBILE, FIXED_CODE)
