"""In-memory circle storage, for tests and infra-free local runs."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone

from app.circles.models import Circle, CircleInvite, CircleMember, MemberStatus
from app.circles.repository import CirclesRepository


class InMemoryCirclesRepository(CirclesRepository):
    def __init__(self) -> None:
        self._circles: dict[str, Circle] = {}
        self._members: dict[str, CircleMember] = {}
        self._invites: dict[str, CircleInvite] = {}

    async def create_circle(self, circle: Circle) -> Circle:
        if not circle.id:
            circle = replace(circle, id=str(uuid.uuid4()))
        self._circles[circle.id] = circle
        return circle

    async def get_circle(self, circle_id: str) -> Circle | None:
        return self._circles.get(circle_id)

    async def save_circle(self, circle: Circle) -> Circle:
        circle.updated_at = datetime.now(timezone.utc)
        self._circles[circle.id] = circle
        return circle

    async def delete_circle(self, circle_id: str) -> bool:
        if self._circles.pop(circle_id, None) is None:
            return False
        for member_id in [
            m.id for m in self._members.values() if m.circle_id == circle_id
        ]:
            del self._members[member_id]
        for invite_id in [
            i.id for i in self._invites.values() if i.circle_id == circle_id
        ]:
            del self._invites[invite_id]
        return True

    async def list_circles_for_user(self, user_id: str) -> list[Circle]:
        ids = {
            m.circle_id
            for m in self._members.values()
            if m.user_id == user_id and m.status is MemberStatus.ACCEPTED
        }
        return self._sorted(ids)

    async def list_circles_inviting(self, mobile: str) -> list[Circle]:
        ids = {
            m.circle_id
            for m in self._members.values()
            if m.mobile == mobile and m.status is MemberStatus.INVITED
        }
        return self._sorted(ids)

    async def list_members(self, circle_id: str) -> list[CircleMember]:
        members = [m for m in self._members.values() if m.circle_id == circle_id]
        # The owner first, then in the order they were invited.
        return sorted(members, key=lambda m: (not m.is_owner, m.invited_at))

    async def get_member(self, circle_id: str, member_id: str) -> CircleMember | None:
        member = self._members.get(member_id)
        return member if member and member.circle_id == circle_id else None

    async def find_member_by_mobile(
        self, circle_id: str, mobile: str
    ) -> CircleMember | None:
        return next(
            (
                m
                for m in self._members.values()
                if m.circle_id == circle_id and m.mobile == mobile
            ),
            None,
        )

    async def save_member(self, member: CircleMember) -> CircleMember:
        if not member.id:
            member.id = str(uuid.uuid4())
        self._members[member.id] = member
        return member

    async def delete_member(self, circle_id: str, member_id: str) -> bool:
        if await self.get_member(circle_id, member_id) is None:
            return False
        del self._members[member_id]
        return True

    async def create_invite(self, invite: CircleInvite) -> CircleInvite:
        if not invite.id:
            invite = replace(invite, id=str(uuid.uuid4()))
        self._invites[invite.id] = invite
        return invite

    async def get_invite_by_token(self, token: str) -> CircleInvite | None:
        return next((i for i in self._invites.values() if i.token == token), None)

    def _sorted(self, circle_ids: set[str]) -> list[Circle]:
        circles = [self._circles[cid] for cid in circle_ids if cid in self._circles]
        return sorted(circles, key=lambda c: c.created_at)
