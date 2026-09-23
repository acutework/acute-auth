"""The authentication flow.

This is the only place the OTP provider, the user store, the token service, the
rate limiter and the revocation list meet. It knows nothing about HTTP and
nothing about any particular vendor or database.
"""

from dataclasses import dataclass

from app.core.errors import (
    InvalidToken,
    NotSupported,
    TokenRevoked,
    UserAlreadyExists,
    UserNotFound,
)
from app.core.mobile import normalise_mobile
from app.core.security import TokenService, TokenType
from app.otp.base import OtpChallenge, OtpProvider, OtpResender
from app.ratelimit.limiter import RateLimit, RateLimiter
from app.tokens.denylist import TokenDenylist
from app.users.models import User
from app.users.repository import UserRepository


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass
class VerificationResult:
    """Either the user is known (tokens) or they are not (registration token)."""

    is_new_user: bool
    user: User | None = None
    tokens: TokenPair | None = None
    registration_token: str | None = None


class AuthService:
    def __init__(
        self,
        *,
        otp_provider: OtpProvider,
        users: UserRepository,
        tokens: TokenService,
        rate_limiter: RateLimiter,
        denylist: TokenDenylist,
        send_limit: RateLimit,
        verify_limit: RateLimit,
    ):
        self._otp = otp_provider
        self._users = users
        self._tokens = tokens
        self._rate_limiter = rate_limiter
        self._denylist = denylist
        self._send_limit = send_limit
        self._verify_limit = verify_limit

    async def request_otp(self, mobile: str) -> OtpChallenge:
        mobile = normalise_mobile(mobile)
        # Checked before the provider is called, so a flood costs no SMS credits.
        await self._rate_limiter.check(f"otp:send:{mobile}", self._send_limit)
        return await self._otp.send(mobile)

    async def resend_otp(self, *, request_id: str, mobile: str, voice: bool) -> None:
        if not isinstance(self._otp, OtpResender):
            raise NotSupported(
                f"{type(self._otp).__name__} cannot resend an OTP. "
                "Request a new one instead."
            )
        mobile = normalise_mobile(mobile)
        await self._rate_limiter.check(f"otp:send:{mobile}", self._send_limit)
        await self._otp.resend(request_id, mobile, voice=voice)

    async def verify_otp(
        self, *, request_id: str, mobile: str, code: str
    ) -> VerificationResult:
        mobile = normalise_mobile(mobile)
        # Caps guessing across challenges, which a per-challenge counter cannot.
        await self._rate_limiter.check(f"otp:verify:{mobile}", self._verify_limit)

        # Raises on a bad, expired or exhausted code.
        await self._otp.verify(request_id, mobile, code)

        user = await self._users.get_by_mobile(mobile)
        if user is None:
            return VerificationResult(
                is_new_user=True,
                registration_token=self._tokens.create_registration_token(mobile=mobile),
            )
        return VerificationResult(
            is_new_user=False, user=user, tokens=self._issue_tokens(user)
        )

    async def register(
        self, *, registration_token: str, name: str, email: str | None = None
    ) -> tuple[User, TokenPair]:
        claims = self._tokens.decode(registration_token, expected_type=TokenType.REGISTER)
        mobile = claims["mobile"]

        if await self._users.get_by_mobile(mobile) is not None:
            raise UserAlreadyExists()

        # The repository raises UserAlreadyExists too, if two registrations race.
        user = await self._users.create(mobile=mobile, name=name, email=email)
        return user, self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = await self._decode_live(refresh_token, TokenType.REFRESH)
        user = await self._users.get_by_id(claims["sub"])
        if user is None:
            raise UserNotFound()
        # Refuses a token issued before this user's last forced sign-out.
        TokenService.check_version(claims, user.token_version)

        # The old refresh token is spent, so a stolen copy cannot be reused.
        await self._revoke(claims)
        return self._issue_tokens(user)

    async def sign_out(self, refresh_token: str) -> None:
        """Revoke a refresh token. Its access token dies on its own within minutes."""
        claims = await self._decode_live(refresh_token, TokenType.REFRESH)
        await self._revoke(claims)

    async def current_user(self, access_token: str) -> User:
        claims = self._tokens.decode(access_token, expected_type=TokenType.ACCESS)
        user = await self._users.get_by_id(claims["sub"])
        if user is None:
            raise InvalidToken("The account for this token no longer exists.")
        # The user row is loaded here anyway, so checking the version costs
        # nothing and makes a forced sign-out take effect immediately rather
        # than when the access token happens to expire.
        TokenService.check_version(claims, user.token_version)
        return user

    async def aclose(self) -> None:
        await self._otp.aclose()

    async def _decode_live(self, token: str, token_type: TokenType) -> dict:
        """Decode a token and refuse it if it has been revoked."""
        claims = self._tokens.decode(token, expected_type=token_type)
        if await self._denylist.is_revoked(claims.get("jti", "")):
            raise TokenRevoked()
        return claims

    async def _revoke(self, claims: dict) -> None:
        await self._denylist.revoke(
            claims.get("jti", ""), TokenService.seconds_until_expiry(claims)
        )

    def _issue_tokens(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=self._tokens.create_access_token(
                user_id=user.id, mobile=user.mobile, token_version=user.token_version
            ),
            refresh_token=self._tokens.create_refresh_token(
                user_id=user.id, mobile=user.mobile, token_version=user.token_version
            ),
            expires_in=self._tokens.access_token_ttl_seconds,
        )
