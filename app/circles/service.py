"""Circle rules.

Who may change a circle, who counts as a responder, and how an invitation
becomes a membership. Knows nothing about HTTP or SQL.

The rule underneath all of it: an invitee is not a responder. Only an accepted
member is ever alerted, so nobody is signed up to answer an emergency by
someone else typing their number.
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.circles.models import (
    Circle,
    CircleInvite,
    CircleMember,
    MemberStatus,
)
from app.circles.notifier import InviteNotifier
from app.circles.repository import CirclesRepository
from app.core.errors import (
    AlreadyCircleMember,
    CannotInviteSelf,
    CircleNotFound,
    InviteInvalid,
    NotCircleOwner,
)
from app.core.mobile import normalise_mobile
from app.ratelimit.limiter import RateLimit, RateLimiter
from app.users.models import User


@dataclass(frozen=True)
class Invitee:
    mobile: str
    display_name: str | None = None


@dataclass
class CircleView:
    """A circle as one particular person sees it."""

    circle: Circle
    members: list[CircleMember] = field(default_factory=list)
    is_owner: bool = False

    @property
    def accepted_count(self) -> int:
        return sum(1 for m in self.members if m.status is MemberStatus.ACCEPTED)

    @property
    def pending_count(self) -> int:
        return sum(1 for m in self.members if m.status is MemberStatus.INVITED)


@dataclass(frozen=True)
class InviteLink:
    token: str
    url: str
    expires_in: int


class CirclesService:
    def __init__(
        self,
        *,
        repository: CirclesRepository,
        notifier: InviteNotifier,
        rate_limiter: RateLimiter,
        send_limit: RateLimit,
        invite_base_url: str,
        invite_ttl_seconds: int,
    ):
        self._repo = repository
        self._notifier = notifier
        self._rate_limiter = rate_limiter
        self._send_limit = send_limit
        self._invite_base_url = invite_base_url.rstrip("/")
        self._invite_ttl_seconds = invite_ttl_seconds

    # ------------------------------------------------------------------ reads

    async def list_circles(self, user: User) -> list[CircleView]:
        return [
            await self._view(circle, user)
            for circle in await self._repo.list_circles_for_user(user.id)
        ]

    async def list_invitations(self, user: User) -> list[CircleView]:
        return [
            await self._view(circle, user)
            for circle in await self._repo.list_circles_inviting(user.mobile)
        ]

    async def get_circle(self, user: User, circle_id: str) -> CircleView:
        circle = await self._visible_circle(user, circle_id)
        return await self._view(circle, user)

    # ----------------------------------------------------------------- writes

    async def create_circle(
        self,
        user: User,
        *,
        name: str,
        include_in_sos_alerts: bool = True,
        invitees: list[Invitee] | None = None,
    ) -> CircleView:
        wanted = self._prepare_invitees(user, invitees or [])
        # Checked before anything is written, so a circle is never left
        # half-created when the invite budget runs out.
        await self._check_send_budget(user, len(wanted))

        circle = await self._repo.create_circle(
            Circle(
                id="",
                owner_user_id=user.id,
                name=name.strip(),
                include_in_sos_alerts=include_in_sos_alerts,
            )
        )
        # The creator answers their own SOS, so they are a member from the
        # start - accepted, never invited.
        await self._repo.save_member(
            CircleMember(
                id="",
                circle_id=circle.id,
                mobile=user.mobile,
                user_id=user.id,
                display_name=user.name,
                status=MemberStatus.ACCEPTED,
                is_owner=True,
                responded_at=datetime.now(timezone.utc),
            )
        )

        if wanted:
            join_url = (await self._new_invite_link(user, circle)).url
            for invitee in wanted:
                await self._invite(circle, user, invitee, join_url)
        return await self._view(circle, user)

    async def update_circle(
        self,
        user: User,
        circle_id: str,
        *,
        name: str | None = None,
        include_in_sos_alerts: bool | None = None,
    ) -> CircleView:
        circle = await self._owned_circle(user, circle_id)
        if name is not None:
            circle.name = name.strip()
        if include_in_sos_alerts is not None:
            circle.include_in_sos_alerts = include_in_sos_alerts
        return await self._view(await self._repo.save_circle(circle), user)

    async def delete_circle(self, user: User, circle_id: str) -> None:
        await self._owned_circle(user, circle_id)
        await self._repo.delete_circle(circle_id)

    async def add_member(
        self, user: User, circle_id: str, *, mobile: str, display_name: str | None = None
    ) -> CircleMember:
        circle = await self._owned_circle(user, circle_id)
        invitee = self._prepare_invitees(user, [Invitee(mobile, display_name)])[0]
        await self._check_send_budget(user, 1)
        join_url = (await self._new_invite_link(user, circle)).url
        return await self._invite(circle, user, invitee, join_url)

    async def remove_member(self, user: User, circle_id: str, member_id: str) -> None:
        await self._owned_circle(user, circle_id)
        member = await self._repo.get_member(circle_id, member_id)
        if member is None:
            raise CircleNotFound("No such member in this circle.")
        await self._repo.delete_member(circle_id, member_id)

    # ------------------------------------------------------------- invitations

    async def create_invite_link(self, user: User, circle_id: str) -> InviteLink:
        circle = await self._owned_circle(user, circle_id)
        return await self._new_invite_link(user, circle)

    async def join(self, user: User, token: str) -> CircleView:
        invite = await self._repo.get_invite_by_token(token)
        if invite is None or invite.expires_at <= datetime.now(timezone.utc):
            raise InviteInvalid()
        circle = await self._repo.get_circle(invite.circle_id)
        if circle is None:
            raise InviteInvalid()

        member = await self._repo.find_member_by_mobile(circle.id, user.mobile)
        if member is None:
            member = CircleMember(
                id="",
                circle_id=circle.id,
                mobile=user.mobile,
                display_name=user.name,
            )
        await self._repo.save_member(_accept(member, user))
        return await self._view(circle, user)

    async def accept(self, user: User, circle_id: str) -> CircleView:
        circle, member = await self._pending_invitation(user, circle_id)
        await self._repo.save_member(_accept(member, user))
        return await self._view(circle, user)

    async def decline(self, user: User, circle_id: str) -> None:
        _, member = await self._pending_invitation(user, circle_id)
        member.status = MemberStatus.DECLINED
        member.responded_at = datetime.now(timezone.utc)
        await self._repo.save_member(member)

    async def aclose(self) -> None:
        await self._notifier.aclose()

    # ---------------------------------------------------------------- private

    def _prepare_invitees(self, user: User, invitees: list[Invitee]) -> list[Invitee]:
        prepared: list[Invitee] = []
        seen: set[str] = set()
        for invitee in invitees:
            mobile = normalise_mobile(invitee.mobile)
            if mobile == user.mobile:
                raise CannotInviteSelf()
            if mobile in seen:
                raise AlreadyCircleMember()
            seen.add(mobile)
            prepared.append(Invitee(mobile=mobile, display_name=invitee.display_name))
        return prepared

    async def _check_send_budget(self, user: User, sends: int) -> None:
        """Every send is an SMS someone pays for, so the budget is per inviter."""
        for _ in range(sends):
            await self._rate_limiter.check(
                f"circles:invite:{user.id}", self._send_limit
            )

    async def _invite(
        self, circle: Circle, inviter: User, invitee: Invitee, join_url: str
    ) -> CircleMember:
        existing = await self._repo.find_member_by_mobile(circle.id, invitee.mobile)
        if existing and existing.status is not MemberStatus.DECLINED:
            # Refusing here is also what stops the same number being messaged
            # twice for one circle.
            raise AlreadyCircleMember()

        member = existing or CircleMember(id="", circle_id=circle.id, mobile=invitee.mobile)
        member.display_name = invitee.display_name or member.display_name
        member.status = MemberStatus.INVITED
        member.invited_at = datetime.now(timezone.utc)
        member.responded_at = None
        member.delivery = await self._notifier.notify(
            mobile=invitee.mobile,
            circle_name=circle.name,
            inviter_name=inviter.name,
            join_url=join_url,
        )
        return await self._repo.save_member(member)

    async def _new_invite_link(self, user: User, circle: Circle) -> InviteLink:
        token = secrets.token_urlsafe(24)
        invite = await self._repo.create_invite(
            CircleInvite(
                id="",
                circle_id=circle.id,
                token=token,
                created_by_user_id=user.id,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=self._invite_ttl_seconds),
            )
        )
        return InviteLink(
            token=invite.token,
            url=f"{self._invite_base_url}/{invite.token}",
            expires_in=self._invite_ttl_seconds,
        )

    async def _visible_circle(self, user: User, circle_id: str) -> Circle:
        circle = await self._repo.get_circle(circle_id)
        if circle is None:
            raise CircleNotFound()
        if circle.owner_user_id == user.id:
            return circle
        member = await self._repo.find_member_by_mobile(circle_id, user.mobile)
        # A circle nobody invited you to should not even confirm it exists.
        if member is None or member.status is MemberStatus.REMOVED:
            raise CircleNotFound()
        return circle

    async def _owned_circle(self, user: User, circle_id: str) -> Circle:
        circle = await self._repo.get_circle(circle_id)
        if circle is None:
            raise CircleNotFound()
        if circle.owner_user_id != user.id:
            raise NotCircleOwner()
        return circle

    async def _pending_invitation(
        self, user: User, circle_id: str
    ) -> tuple[Circle, CircleMember]:
        circle = await self._repo.get_circle(circle_id)
        if circle is None:
            raise CircleNotFound()
        member = await self._repo.find_member_by_mobile(circle_id, user.mobile)
        if member is None or member.status is not MemberStatus.INVITED:
            raise InviteInvalid("There is no open invitation for you in this circle.")
        return circle, member

    async def _view(self, circle: Circle, user: User) -> CircleView:
        return CircleView(
            circle=circle,
            members=await self._repo.list_members(circle.id),
            is_owner=circle.owner_user_id == user.id,
        )


def _accept(member: CircleMember, user: User) -> CircleMember:
    """Accepting is what ties a mobile number to a real account."""
    member.user_id = user.id
    member.status = MemberStatus.ACCEPTED
    member.responded_at = datetime.now(timezone.utc)
    return member
