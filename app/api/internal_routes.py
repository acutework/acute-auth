"""Endpoints for other Acutework services, not for apps.

acute-core asks narrow questions. Whether a mobile number has an account,
so an invitation can go by push rather than an SMS - a bare boolean. Where an
SOS is - its pincode, for the sender's associations, and a name for responders
when the SOS came without one. And, for add-to-circle, one user's number and
name by id. That last endpoint discloses one user's contact, only to a holder
of the internal key; nothing here lists or searches users, and nothing here
returns a user's places or anything else from the user table.

Guarded by a shared key rather than a user token, because the caller is a
service and no user is involved. A blank key disables the endpoint entirely,
so a misconfigured deployment fails closed.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from app.core.errors import AuthError, UserNotFound
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


@router.get("/places/at")
async def place_at(
    settings: SettingsDep,
    onboarding: OnboardingServiceDep,
    user_id: Annotated[str, Query(min_length=1, max_length=64)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    accuracy_m: Annotated[float, Query(ge=0, le=100_000)] = 0.0,
    x_internal_key: Annotated[str | None, Header()] = None,
) -> dict[str, str | None]:
    """The pincode and a name for where an SOS is. Either may be null."""
    if not settings.internal_api_key or x_internal_key != settings.internal_api_key:
        raise InternalAccessDenied()
    place = await onboarding.place_at(user_id, lat, lng, accuracy_m=accuracy_m)
    return {"pincode": place.pincode, "label": place.label}


@router.get("/users/{user_id}/contact")
async def user_contact(
    user_id: str,
    settings: SettingsDep,
    auth: AuthServiceDep,
    x_internal_key: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """The number and name behind a user id, so acute-core can invite someone found
    in the directory without the app ever holding their number."""
    if not settings.internal_api_key or x_internal_key != settings.internal_api_key:
        raise InternalAccessDenied()
    contact = await auth.contact(user_id)
    if contact is None:
        raise UserNotFound()
    return {"mobile": contact.mobile, "name": contact.name}
