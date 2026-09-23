"""JWT creation and verification.

Every token carries a `type` claim. Verification always demands the expected
type, so a registration token can never be replayed as an access token.
"""

import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from jose import JWTError, jwt

from app.config import Settings
from app.core.errors import InvalidToken


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    REGISTER = "register"


class TokenService:
    def __init__(self, settings: Settings):
        self._settings = settings

    def create_access_token(
        self, *, user_id: str, mobile: str, token_version: int = 0
    ) -> str:
        return self._create(
            TokenType.ACCESS,
            subject=user_id,
            mobile=mobile,
            ttl=timedelta(minutes=self._settings.access_token_ttl_minutes),
            token_version=token_version,
        )

    def create_refresh_token(
        self, *, user_id: str, mobile: str, token_version: int = 0
    ) -> str:
        return self._create(
            TokenType.REFRESH,
            subject=user_id,
            mobile=mobile,
            ttl=timedelta(days=self._settings.refresh_token_ttl_days),
            token_version=token_version,
        )

    def create_registration_token(self, *, mobile: str) -> str:
        """Proof that `mobile` passed OTP verification but has no account yet."""
        return self._create(
            TokenType.REGISTER,
            subject=mobile,
            mobile=mobile,
            ttl=timedelta(minutes=self._settings.registration_token_ttl_minutes),
        )

    def decode(self, token: str, *, expected_type: TokenType) -> dict:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
            )
        except JWTError as exc:
            raise InvalidToken() from exc

        if claims.get("type") != expected_type.value:
            raise InvalidToken(f"Expected a {expected_type.value} token.")
        return claims

    def _create(
        self,
        token_type: TokenType,
        *,
        subject: str,
        mobile: str,
        ttl: timedelta,
        token_version: int = 0,
    ) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "sub": subject,
            "mobile": mobile,
            "type": token_type.value,
            # A unique id per token, so a refresh token can be revoked by id.
            "jti": uuid.uuid4().hex,
            # Checked against the user's current token_version on every use.
            "ver": token_version,
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        }
        return jwt.encode(
            claims, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm
        )

    @property
    def access_token_ttl_seconds(self) -> int:
        return self._settings.access_token_ttl_minutes * 60

    @staticmethod
    def check_version(claims: dict, current_version: int) -> None:
        """Refuse a token issued before the user's last forced sign-out."""
        from app.core.errors import SessionSuperseded

        if int(claims.get("ver", 0)) != current_version:
            raise SessionSuperseded()

    @staticmethod
    def seconds_until_expiry(claims: dict) -> int:
        """How long a token has left, for sizing a revocation record."""
        expires_at = int(claims.get("exp", 0))
        return max(0, expires_at - int(datetime.now(timezone.utc).timestamp()))
