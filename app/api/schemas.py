"""Request and response bodies."""

from pydantic import BaseModel, Field


class RequestOtpIn(BaseModel):
    # Accepted with or without '+'; normalised to digits-only before use.
    mobile: str = Field(min_length=10, max_length=20, examples=["919999999999"])


class RequestOtpOut(BaseModel):
    request_id: str
    expires_in: int
    # Present only when a development OTP provider is wired up.
    debug_code: str | None = None


class VerifyOtpIn(BaseModel):
    request_id: str
    mobile: str
    code: str = Field(min_length=4, max_length=8)


class ResendOtpIn(BaseModel):
    request_id: str
    mobile: str
    # MSG91 can retry by voice call instead of SMS.
    voice: bool = False


class UserOut(BaseModel):
    id: str
    mobile: str
    name: str
    email: str | None = None


class VerifyOtpOut(BaseModel):
    """One shape for both outcomes; `is_new_user` says which fields are filled.

    Existing user -> access_token, refresh_token, user.
    New user      -> registration_token. Post it to /auth/register to sign up.
    """

    is_new_user: bool
    token_type: str = "bearer"
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    user: UserOut | None = None
    registration_token: str | None = None


class RegisterIn(BaseModel):
    """The registration token travels in the Authorization header, not here."""

    name: str = Field(min_length=1, max_length=120)
    email: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    user: UserOut | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class ErrorOut(BaseModel):
    code: str
    message: str
