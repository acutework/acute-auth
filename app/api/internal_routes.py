"""Endpoints for other Acutework services, not for apps.

acute-core needs one thing from identity: whether a mobile number already has
an account, so an invitation can go by push rather than costing an SMS. That is
the only question answered here, and it returns a bare boolean - never a user
id, a name or anything else that would let this become a back door into the
user table.

Guarded by a shared key rather than a user token, because the caller is a
service and no user is involved. A blank key disables the endpoint entirely,
so a misconfigured deployment fails closed.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from app.core.errors import AuthError
from app.deps import AuthServiceDep, SettingsDep

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
