"""MSG91 OTP provider.

Wire protocol (MSG91 API v5):

    send    POST /api/v5/otp         ?template_id&mobile&authkey
    verify  GET  /api/v5/otp/verify  ?otp&mobile      authkey in the header
    resend  GET  /api/v5/otp/retry   ?authkey&retrytype&mobile

Every response carries a `type` field; anything other than "success" is a
failure and `message` explains it.

MSG91 holds the OTP itself - it generates the code, expires it and counts
attempts server-side. This class therefore keeps no OTP state. It issues a
signed `request_id` (see app/otp/challenge.py) purely so the API shape matches
every other provider.
"""

import logging

import httpx

from app.core.errors import (
    InvalidOtp,
    OtpProviderUnavailable,
    OtpSendFailed,
)
from app.otp.base import OtpChallenge, OtpProvider, OtpResender
from app.otp.challenge import ChallengeCodec

logger = logging.getLogger(__name__)


class MSG91OtpProvider(OtpProvider, OtpResender):
    def __init__(
        self,
        *,
        authkey: str,
        template_id: str,
        codec: ChallengeCodec,
        send_url: str = "https://control.msg91.com/api/v5/otp",
        verify_url: str = "https://control.msg91.com/api/v5/otp/verify",
        retry_url: str = "https://control.msg91.com/api/v5/otp/retry",
        client: httpx.AsyncClient | None = None,
    ):
        if not authkey or not template_id:
            raise ValueError(
                "MSG91 needs MSG91_AUTHKEY and MSG91_OTP_TEMPLATE_ID to be set."
            )
        self._authkey = authkey
        self._template_id = template_id
        self._codec = codec
        self._send_url = send_url
        self._verify_url = verify_url
        self._retry_url = retry_url
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def send(self, mobile: str) -> OtpChallenge:
        data = await self._request(
            "POST",
            self._send_url,
            params={
                "template_id": self._template_id,
                "mobile": mobile,
                "authkey": self._authkey,
            },
        )
        self._require_success(data, OtpSendFailed)
        return OtpChallenge(
            request_id=self._codec.issue(mobile),
            mobile=mobile,
            expires_in=self._codec.ttl_seconds,
        )

    async def verify(self, request_id: str, mobile: str, code: str) -> None:
        # Raises UnknownOtpRequest / OtpExpired before we spend a call on MSG91.
        self._codec.open(request_id, mobile)

        data = await self._request(
            "GET",
            self._verify_url,
            params={"otp": code, "mobile": mobile},
            headers={"authkey": self._authkey},
        )
        # MSG91 owns expiry and attempt counting, so every rejection reaches us
        # as one error. Pass its wording through - it distinguishes the cases.
        self._require_success(data, InvalidOtp)

    async def resend(self, request_id: str, mobile: str, *, voice: bool = False) -> None:
        self._codec.open(request_id, mobile)

        data = await self._request(
            "GET",
            self._retry_url,
            params={
                "authkey": self._authkey,
                "retrytype": "voice" if voice else "text",
                "mobile": mobile,
            },
        )
        self._require_success(data, OtpSendFailed)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _require_success(data: dict, error: type[Exception]) -> None:
        if data.get("type") != "success":
            message = data.get("message") or "MSG91 rejected the request."
            logger.warning("MSG91 returned a failure: %s", message)
            raise error(str(message))

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> dict:
        logger.debug("MSG91 %s %s mobile=%s", method, url, params.get("mobile"))
        try:
            response = await self._client.request(
                method, url, params=params, headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            # Covers transport errors and non-2xx alike: from the caller's point
            # of view MSG91 simply did not answer usefully.
            logger.warning("MSG91 is unavailable: %r", exc)
            raise OtpProviderUnavailable(str(exc)) from exc
        except ValueError as exc:  # body was not JSON
            logger.warning("MSG91 returned a non-JSON body: %r", exc)
            raise OtpProviderUnavailable("MSG91 returned an unreadable response.") from exc
