"""Endpoints for other Acutework services, not for apps.

acute-core asks two narrow questions. Whether a mobile number has an account,
so an invitation can go by push rather than an SMS - a bare boolean. And the
pincode at a point during an SOS, so the sender's associations there can be
alerted - a bare pincode. Never a user id, a name, a place or anything else
that would let this become a back door into the user table.

Guarded by a shared key rather than a user token, because the caller is a
service and no user is involved. A blank key disables the endpoint entirely,
so a misconfigured deployment fails closed.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from app.core.errors import AuthError
from app.deps import AuthServiceDep, OnboardingServiceDep, SettingsDep

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


class InternalAccessDenied(AuthError):
    status_code = 401
    code = "internal_access_denied"
    message = "This endpoint is for Acutework services."


@router.get("/users/exists")
async def user_exists(
    settings: SettingsDep,
    auth: AuthServiceDep,
    mobile: Annotated[str, Query(min_length=8, max_length=20)],
    x_internal_key: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    """Whether `mobile` has an account. Nothing else is disclosed."""
    if not settings.internal_api_key or x_internal_key != settings.internal_api_key:
        raise InternalAccessDenied()

    try:
        return {"exists": await auth.has_account(mobile)}
    except AuthError:
        # A number that cannot be canonical cannot have an account.
        return {"exists": False}


@router.get("/places/pincode")
async def pincode_at(
    settings: SettingsDep,
    onboarding: OnboardingServiceDep,
    user_id: Annotated[str, Query(min_length=1, max_length=64)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    x_internal_key: Annotated[str | None, Header()] = None,
) -> dict[str, str | None]:
    """The pincode at a point, or null. Nothing else is disclosed."""
    if not settings.internal_api_key or x_internal_key != settings.internal_api_key:
        raise InternalAccessDenied()
    return {"pincode": await onboarding.pincode_at(user_id, lat, lng)}

