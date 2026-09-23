"""An OTP provider that sends nothing and accepts a fixed code.

For local development and tests only. The code is logged and returned in the
API response so you can complete the flow without a phone.

Unlike MSG91, there is no vendor holding the OTP, so this provider tracks
expiry and attempts itself - through an [OtpChallengeStore], which is Redis in
a real deployment and a dict in tests.
"""

import logging

from app.core.errors import (
    InvalidOtp,
    OtpExpired,
    TooManyAttempts,
    UnknownOtpRequest,
)
from app.otp.base import OtpChallenge, OtpProvider, OtpResender
from app.otp.challenge import ChallengeCodec
from app.otp.store import InMemoryChallengeStore, OtpChallengeStore, StoredChallenge

logger = logging.getLogger(__name__)

# Four digits, matching the app's designs.
FIXED_CODE = "4732"


class FakeOtpProvider(OtpProvider, OtpResender):
    def __init__(
        self,
        *,
        codec: ChallengeCodec,
        store: OtpChallengeStore | None = None,
        ttl_seconds: int = 300,
        max_attempts: int = 3,
        code: str = FIXED_CODE,
    ):
        self._codec = codec
        self._store = store or InMemoryChallengeStore()
        self._ttl_seconds = ttl_seconds
        self._max_attempts = max_attempts
        self._code = code

    async def send(self, mobile: str) -> OtpChallenge:
        request_id = self._codec.issue(mobile)
        await self._store.put(
            request_id,
            StoredChallenge(
                mobile=mobile, code=self._code, attempts_left=self._max_attempts
            ),
            self._ttl_seconds,
        )
        logger.info("FakeOtpProvider: OTP for %s is %s", mobile, self._code)
        return OtpChallenge(
            request_id=request_id,
            mobile=mobile,
            expires_in=self._ttl_seconds,
            debug_code=self._code,
        )

    async def verify(self, request_id: str, mobile: str, code: str) -> None:
        challenge = await self._store.get(request_id)
        if challenge is None:
            # Either it never existed, or the store expired it.
            self._codec.open(request_id, mobile)  # raises OtpExpired if stale
            raise UnknownOtpRequest()
        if challenge.mobile != mobile:
            raise UnknownOtpRequest()

        if challenge.code != code:
            attempts_left = await self._store.decrement_attempts(request_id)
            if attempts_left <= 0:
                await self._store.delete(request_id)
                raise TooManyAttempts()
            raise InvalidOtp(f"The OTP is incorrect. {attempts_left} attempts left.")

        # Single use: a verified challenge cannot be replayed.
        await self._store.delete(request_id)

    async def resend(self, request_id: str, mobile: str, *, voice: bool = False) -> None:
        challenge = await self._store.get(request_id)
        if challenge is None or challenge.mobile != mobile:
            raise UnknownOtpRequest()
        logger.info(
            "FakeOtpProvider: resending OTP %s to %s (voice=%s)",
            challenge.code, mobile, voice,
        )
