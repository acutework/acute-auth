import pytest

from app.otp.challenge import ChallengeCodec
from app.otp.fake import FakeOtpProvider
from app.otp.msg91 import MSG91OtpProvider
from app.otp.registry import build_otp_provider
from tests.conftest import make_settings as Settings

CODEC = ChallengeCodec("test-secret", ttl_seconds=300)


def test_fake_is_the_default():
    assert isinstance(build_otp_provider(Settings(otp_provider="fake"), CODEC),
                      FakeOtpProvider)


def test_msg91_is_wired_by_name():
    settings = Settings(
        otp_provider="msg91", msg91_authkey="k", msg91_otp_template_id="t"
    )

    assert isinstance(build_otp_provider(settings, CODEC), MSG91OtpProvider)


def test_an_unknown_provider_name_says_what_is_available():
    with pytest.raises(ValueError, match="fake, msg91"):
        build_otp_provider(Settings(otp_provider="nope"), CODEC)


def test_msg91_without_credentials_fails_at_startup_not_at_request_time():
    with pytest.raises(ValueError, match="MSG91_AUTHKEY"):
        build_otp_provider(Settings(otp_provider="msg91"), CODEC)
