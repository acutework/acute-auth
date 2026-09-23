"""Maps a provider name from config to a provider instance.

Adding a vendor is two steps: write the class, add a line to _PROVIDERS.
"""

from collections.abc import Callable

from app.config import Settings
from app.otp.base import OtpProvider
from app.otp.challenge import ChallengeCodec
from app.otp.fake import FakeOtpProvider
from app.otp.msg91 import MSG91OtpProvider
from app.otp.store import OtpChallengeStore

ProviderFactory = Callable[[Settings, ChallengeCodec, OtpChallengeStore | None], OtpProvider]


def _build_fake(
    settings: Settings, codec: ChallengeCodec, store: OtpChallengeStore | None
) -> OtpProvider:
    return FakeOtpProvider(
        codec=codec,
        store=store,
        ttl_seconds=settings.otp_ttl_seconds,
        max_attempts=settings.otp_max_attempts,
    )


def _build_msg91(
    settings: Settings, codec: ChallengeCodec, store: OtpChallengeStore | None
) -> OtpProvider:
    # MSG91 holds the OTP itself, so it needs no challenge store.
    return MSG91OtpProvider(
        authkey=settings.msg91_authkey,
        template_id=settings.msg91_otp_template_id,
        codec=codec,
        send_url=settings.msg91_otp_send_url,
        verify_url=settings.msg91_otp_verify_url,
        retry_url=settings.msg91_otp_retry_url,
    )


_PROVIDERS: dict[str, ProviderFactory] = {
    "fake": _build_fake,
    "msg91": _build_msg91,
}


def build_otp_provider(
    settings: Settings,
    codec: ChallengeCodec,
    store: OtpChallengeStore | None = None,
) -> OtpProvider:
    try:
        factory = _PROVIDERS[settings.otp_provider]
    except KeyError:
        known = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unknown OTP provider {settings.otp_provider!r}. Known providers: {known}"
        ) from None
    return factory(settings, codec, store)
