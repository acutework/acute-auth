"""Circle endpoints.

Everything here is scoped to the signed-in user, taken from the access token -
no endpoint accepts a user id, so nobody can read or edit another person's
circles, and an invitation is only ever matched against the caller's own
verified mobile number.
"""

from fastapi import APIRouter, status

from app.api.circle_schemas import (
    CircleIn,
    CircleMemberOut,
    CircleOut,
    CirclePatch,
    InviteeIn,
    InviteLinkOut,
    JoinIn,
)
from app.circles.models import CircleMember
from app.circles.service import CircleView, Invitee
from app.deps import CirclesServiceDep, CurrentUserDep

router = APIRouter(prefix="/circles", tags=["circles"])


def _member_out(member: CircleMember) -> CircleMemberOut:
    return CircleMemberOut(
        id=member.id,
        mobile=member.mobile,
        display_name=member.display_name,
        status=member.status,
        is_owner=member.is_owner,
        delivery=member.delivery,
        invited_at=member.invited_at,
        responded_at=member.responded_at,
    )


def _circle_out(view: CircleView) -> CircleOut:
    return CircleOut(
        id=view.circle.id,
        name=view.circle.name,
        include_in_sos_alerts=view.circle.include_in_sos_alerts,
        is_owner=view.is_owner,
        accepted_count=view.accepted_count,
        pending_count=view.pending_count,
        created_at=view.circle.created_at,
        members=[_member_out(m) for m in view.members],
    )


@router.get("", response_model=list[CircleOut])
async def list_circles(
    user: CurrentUserDep, service: CirclesServiceDep
) -> list[CircleOut]:
    """Circles I own or have accepted - never ones I have only been invited to."""
    return [_circle_out(v) for v in await service.list_circles(user)]


@router.post("", response_model=CircleOut, status_code=status.HTTP_201_CREATED)
async def create_circle(
    body: CircleIn, user: CurrentUserDep, service: CirclesServiceDep
) -> CircleOut:
    """Create a circle and invite people to it.

    An invitation that could not be delivered is reported on the member rather
    than failing the call: the circle matters more than the message.
    """
    view = await service.create_circle(
        user,
        name=body.name,
        include_in_sos_alerts=body.include_in_sos_alerts,
        invitees=[Invitee(i.mobile, i.display_name) for i in body.invitees],
    )
    return _circle_out(view)


@router.get("/invitations", response_model=list[CircleOut])
async def list_invitations(
    user: CurrentUserDep, service: CirclesServiceDep
) -> list[CircleOut]:
    """Circles inviting me that I have not answered."""
    return [_circle_out(v) for v in await service.list_invitations(user)]


@router.post("/join", response_model=CircleOut)
async def join_circle(
    body: JoinIn, user: CurrentUserDep, service: CirclesServiceDep
) -> CircleOut:
    """Join by a shared link's token, invited beforehand or not."""
    return _circle_out(await service.join(user, body.token))


@router.get("/{circle_id}", response_model=CircleOut)
async def get_circle(
    circle_id: str, user: CurrentUserDep, service: CirclesServiceDep
) -> CircleOut:
    return _circle_out(await service.get_circle(user, circle_id))


@router.patch("/{circle_id}", response_model=CircleOut)
async def update_circle(
    circle_id: str,
    body: CirclePatch,
    user: CurrentUserDep,
    service: CirclesServiceDep,
) -> CircleOut:
    view = await service.update_circle(
        user,
        circle_id,
        name=body.name,
        include_in_sos_alerts=body.include_in_sos_alerts,
    )
    return _circle_out(view)


@router.delete("/{circle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_circle(
    circle_id: str, user: CurrentUserDep, service: CirclesServiceDep
) -> None:
    await service.delete_circle(user, circle_id)


@router.post(
    "/{circle_id}/members",
    response_model=CircleMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    circle_id: str,
    body: InviteeIn,
    user: CurrentUserDep,
    service: CirclesServiceDep,
) -> CircleMemberOut:
    member = await service.add_member(
        user, circle_id, mobile=body.mobile, display_name=body.display_name
    )
    return _member_out(member)


@router.delete(
    "/{circle_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    circle_id: str,
    member_id: str,
    user: CurrentUserDep,
    service: CirclesServiceDep,
) -> None:
    await service.remove_member(user, circle_id, member_id)


@router.post("/{circle_id}/invite-link", response_model=InviteLinkOut)
async def create_invite_link(
    circle_id: str, user: CurrentUserDep, service: CirclesServiceDep
) -> InviteLinkOut:
    """A shareable link; anyone holding it can join until it expires."""
    link = await service.create_invite_link(user, circle_id)
    return InviteLinkOut(token=link.token, url=link.url, expires_in=link.expires_in)


@router.post("/{circle_id}/accept", response_model=CircleOut)
async def accept_invitation(
    circle_id: str, user: CurrentUserDep, service: CirclesServiceDep
) -> CircleOut:
    """Accepting is what makes someone a responder, not being invited."""
    return _circle_out(await service.accept(user, circle_id))


@router.post("/{circle_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_invitation(
    circle_id: str, user: CurrentUserDep, service: CirclesServiceDep
) -> None:
    await service.decline(user, circle_id)
