"""The contract every OTP provider implements.

To wire a real vendor, write a class implementing `OtpProvider` and register it
in app/otp/registry.py. Nothing in the service layer changes. See
app/otp/msg91.py for a worked example.

Providers are async because sending an OTP is a network call.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OtpChallenge:
    """Handed back to the caller after an OTP is sent."""

    request_id: str
    mobile: str
    expires_in: int  # seconds
    # Only ever populated by development providers, never by a real vendor.
    debug_code: str | None = None


class OtpSender(ABC):
    @abstractmethod
    async def send(self, mobile: str) -> OtpChallenge:
        """Deliver an OTP to `mobile` and return a handle for verifying it."""


class OtpVerifier(ABC):
    @abstractmethod
    async def verify(self, request_id: str, mobile: str, code: str) -> None:
        """Check `code`.

        Returns None on success. Raises UnknownOtpRequest, OtpExpired,
        TooManyAttempts, InvalidOtp or OtpProviderUnavailable otherwise.
        """


class OtpResender(ABC):
    """Optional. Implement only if the vendor can retry a live OTP.

    Providers without a retry concept simply don't implement it, and
    /auth/otp/resend answers 501.
    """

    @abstractmethod
    async def resend(self, request_id: str, mobile: str, *, voice: bool = False) -> None:
        """Re-deliver the OTP already in flight for `mobile`."""


class OtpProvider(OtpSender, OtpVerifier, ABC):
    """Most vendors both send and verify, so providers implement both halves."""

    async def aclose(self) -> None:
        """Release any held resources (HTTP clients, pools). Default: nothing."""
