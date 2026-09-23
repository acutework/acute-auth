"""HTTP layer. Translates requests into service calls and results into bodies."""

from fastapi import APIRouter, status

from app.api.schemas import (
    RefreshIn,
    ResendOtpIn,
    RegisterIn,
    RequestOtpIn,
    RequestOtpOut,
    TokenOut,
    UserOut,
    VerifyOtpIn,
    VerifyOtpOut,
)
from app.deps import AuthServiceDep, BearerTokenDep, CurrentUserDep
from app.services.auth_service import TokenPair
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, mobile=user.mobile, name=user.name, email=user.email)


def _token_out(user: User, tokens: TokenPair) -> TokenOut:
    return TokenOut(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=_user_out(user),
    )


@router.post("/otp/request", response_model=RequestOtpOut)
async def request_otp(body: RequestOtpIn, auth: AuthServiceDep) -> RequestOtpOut:
    """Send an OTP to a mobile number."""
    challenge = await auth.request_otp(body.mobile)
    return RequestOtpOut(
        request_id=challenge.request_id,
        expires_in=challenge.expires_in,
        debug_code=challenge.debug_code,
    )


@router.post("/otp/verify", response_model=VerifyOtpOut)
async def verify_otp(body: VerifyOtpIn, auth: AuthServiceDep) -> VerifyOtpOut:
    """Check an OTP.

    Known number -> tokens. Unknown number -> a registration token to post to
    /auth/register.
    """
    result = await auth.verify_otp(
        request_id=body.request_id, mobile=body.mobile, code=body.code
    )
    if result.is_new_user:
        return VerifyOtpOut(
            is_new_user=True, registration_token=result.registration_token
        )
    return VerifyOtpOut(
        is_new_user=False,
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
        user=_user_out(result.user),
    )


@router.post("/otp/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_otp(body: ResendOtpIn, auth: AuthServiceDep) -> dict[str, bool]:
    """Re-deliver the OTP already in flight.

    Answers 501 when the configured provider has no retry concept.
    """
    await auth.resend_otp(
        request_id=body.request_id, mobile=body.mobile, voice=body.voice
    )
    return {"sent": True}


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, auth: AuthServiceDep, registration_token: BearerTokenDep
) -> TokenOut:
    """Create the account for a number that just passed OTP verification.

    Send the registration token as `Authorization: Bearer <token>`.
    """
    user, tokens = await auth.register(
        registration_token=registration_token, name=body.name, email=body.email
    )
    return _token_out(user, tokens)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, auth: AuthServiceDep) -> TokenOut:
    """Trade a refresh token for a fresh pair.

    The token presented is revoked in the process, so each refresh token works
    exactly once.
    """
    tokens = await auth.refresh(body.refresh_token)
    user = await auth.current_user(tokens.access_token)
    return _token_out(user, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, auth: AuthServiceDep) -> None:
    """Sign out by revoking the refresh token.

    The matching access token is not revoked - it expires on its own within
    minutes, which is the trade-off stateless access tokens buy.
    """
    await auth.sign_out(body.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUserDep) -> UserOut:
    """The account behind the access token."""
    return _user_out(user)
