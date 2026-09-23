"""Signed, stateless OTP request handles.

Providers like MSG91 key an OTP by mobile number alone and give us nothing to
hold on to. Rather than invent server-side state, `request_id` is a short
signed token carrying the mobile number and the issue time. Verification checks
the signature and that the caller's mobile matches, so a client cannot forge a
handle or reuse one number's handle for another.

It survives restarts and works across instances, which a dict would not.
"""

import base64
import hmac
import time
from hashlib import sha256

from app.core.errors import OtpExpired, UnknownOtpRequest


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class ChallengeCodec:
    def __init__(self, secret: str, *, ttl_seconds: int):
        self._secret = secret.encode()
        self._ttl = ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def issue(self, mobile: str) -> str:
        payload = f"{mobile}:{int(time.time())}"
        return f"{_b64(payload.encode())}.{self._sign(payload)}"

    def open(self, request_id: str, mobile: str) -> None:
        """Raise unless `request_id` is a live handle this service issued for `mobile`."""
        try:
            encoded, signature = request_id.split(".", 1)
            payload = _unb64(encoded).decode()
            issued_for, issued_at = payload.rsplit(":", 1)
            issued_at = int(issued_at)
        except (ValueError, UnicodeDecodeError, base64.binascii.Error):
            raise UnknownOtpRequest() from None

        if not hmac.compare_digest(signature, self._sign(payload)):
            raise UnknownOtpRequest()
        if issued_for != mobile:
            raise UnknownOtpRequest()
        if time.time() - issued_at > self._ttl:
            raise OtpExpired()

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._secret, payload.encode(), sha256).digest())
