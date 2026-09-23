"""Application settings, read from the environment (or a .env file)."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEV_SECRET = "dev-only-insecure-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which OTP provider to wire up. See app/otp/registry.py for the names.
    otp_provider: str = "fake"

    jwt_secret: str = DEV_SECRET
    jwt_algorithm: str = "HS256"

    access_token_ttl_minutes: int = 15
    # A year, and it slides: every refresh issues a new one. Someone who
    # opens the app at all stays signed in until they log out.
    refresh_token_ttl_days: int = 365
    registration_token_ttl_minutes: int = 10

    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 3

    # Storage. Leave database_url empty to run on in-memory stores (no Postgres
    # needed); leave redis_url empty to run without Redis, which also turns off
    # rate limiting and token revocation.
    database_url: str = ""
    redis_url: str = ""

    # Rate limits, as <count> per <window> seconds.
    otp_send_limit: int = 5
    otp_send_window_seconds: int = 3600
    otp_verify_limit: int = 10
    otp_verify_window_seconds: int = 900

    # Address lookup. Blank disables search; users can still type an address.
    # "google" is wired today - see app/places/registry.py to add a free one.
    places_provider: str = "google"
    google_places_api_key: str = ""
    places_region_code: str = "in"
    places_language_code: str = "en"

    # MSG91 (used when otp_provider="msg91").
    msg91_authkey: str = ""
    msg91_otp_template_id: str = ""
    msg91_otp_send_url: str = "https://control.msg91.com/api/v5/otp"
    msg91_otp_verify_url: str = "https://control.msg91.com/api/v5/otp/verify"
    msg91_otp_retry_url: str = "https://control.msg91.com/api/v5/otp/retry"
    # Circle invitations go out over MSG91's flow API. Blank template id means
    # no SMS is attempted at all - see app/circles/notifier.py.
    msg91_invite_template_id: str = ""
    msg91_flow_url: str = "https://control.msg91.com/api/v5/flow/"

    # Circles. An invitation SMS costs money, so sends are capped per inviter.
    invite_send_limit: int = 20
    invite_send_window_seconds: int = 86400
    app_invite_base_url: str = "https://acutework.app/join"
    invite_link_ttl_seconds: int = 604800  # a week


    @property
    def uses_postgres(self) -> bool:
        return bool(self.database_url)

    @property
    def uses_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def uses_place_search(self) -> bool:
        return bool(self.places_provider and self.google_places_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.uses_postgres:
        logger.warning(
            "DATABASE_URL is not set - users are kept in memory and lost on restart."
        )
    if not settings.uses_redis:
        logger.warning(
            "REDIS_URL is not set - rate limiting and token revocation are disabled."
        )
    if settings.jwt_secret == DEV_SECRET:
        logger.warning(
            "JWT_SECRET is not set - using the insecure development default. "
            "Set JWT_SECRET before deploying anywhere real."
        )
    return settings
