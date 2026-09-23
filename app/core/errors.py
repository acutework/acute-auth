"""Domain errors.

The service layer raises these; app/main.py maps them to HTTP responses so
that no business logic has to know about status codes.
"""


class AuthError(Exception):
    """Base class for every error this service raises on purpose."""

    status_code = 400
    code = "auth_error"
    message = "Authentication error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message


class InvalidOtp(AuthError):
    status_code = 400
    code = "invalid_otp"
    message = "The OTP is incorrect."


class OtpExpired(AuthError):
    status_code = 400
    code = "otp_expired"
    message = "The OTP has expired. Request a new one."


class TooManyAttempts(AuthError):
    status_code = 429
    code = "too_many_attempts"
    message = "Too many incorrect attempts. Request a new OTP."


class UnknownOtpRequest(AuthError):
    status_code = 404
    code = "unknown_otp_request"
    message = "No such OTP request."


class InvalidToken(AuthError):
    status_code = 401
    code = "invalid_token"
    message = "The token is invalid or has expired."


class UserAlreadyExists(AuthError):
    status_code = 409
    code = "user_already_exists"
    message = "An account already exists for this mobile number."


class UserNotFound(AuthError):
    status_code = 404
    code = "user_not_found"
    message = "No account for this mobile number."


class InvalidMobile(AuthError):
    status_code = 422
    code = "invalid_mobile"
    message = "The mobile number is not in a usable format."


class OtpProviderUnavailable(AuthError):
    status_code = 502
    code = "otp_provider_unavailable"
    message = "The OTP provider is unreachable. Try again shortly."


class OtpSendFailed(AuthError):
    status_code = 502
    code = "otp_send_failed"
    message = "The OTP provider refused to send the OTP."


class NotSupported(AuthError):
    status_code = 501
    code = "not_supported"
    message = "The configured OTP provider does not support this operation."


class TooManyRequests(AuthError):
    status_code = 429
    code = "too_many_requests"
    message = "Too many attempts. Try again later."


class TokenRevoked(AuthError):
    status_code = 401
    code = "token_revoked"
    message = "This session was signed out. Sign in again."


class PlaceProviderUnavailable(AuthError):
    status_code = 502
    code = "place_provider_unavailable"
    message = "Address lookup is unreachable. Type the address instead."


class PlaceLookupFailed(AuthError):
    status_code = 502
    code = "place_lookup_failed"
    message = "Address lookup failed. Type the address instead."


class PlaceSearchDisabled(AuthError):
    status_code = 501
    code = "place_search_disabled"
    message = "Address search is not configured. Type the address instead."


class OnboardingIncomplete(AuthError):
    status_code = 422
    code = "onboarding_incomplete"
    message = "Some required details are missing."


class ProfileRequired(AuthError):
    status_code = 409
    code = "profile_required"
    message = "Save your profile before this step."


class PlaceNotFound(AuthError):
    status_code = 404
    code = "place_not_found"
    message = "No such saved place."


class SessionSuperseded(AuthError):
    """The token predates a forced sign-out (token_version was bumped)."""

    status_code = 401
    code = "session_superseded"
    message = "You were signed out. Sign in again."
