"""Storage contract for circles, their members and their invite links.

One interface for all three because a circle is never read without its
members, and an invite token is meaningless without its circle.
"""

from abc import ABC, abstractmethod

from app.circles.models import Circle, CircleInvite, CircleMember


class CirclesRepository(ABC):
    # Circles
    @abstractmethod
    async def create_circle(self, circle: Circle) -> Circle: ...

    @abstractmethod
    async def get_circle(self, circle_id: str) -> Circle | None: ...

    @abstractmethod
    async def save_circle(self, circle: Circle) -> Circle: ...

    @abstractmethod
    async def delete_circle(self, circle_id: str) -> bool:
        """Deletes the circle's members and invites with it."""

    @abstractmethod
    async def list_circles_for_user(self, user_id: str) -> list[Circle]:
        """Circles this user owns or has accepted."""

    @abstractmethod
    async def list_circles_inviting(self, mobile: str) -> list[Circle]:
        """Circles holding an unanswered invitation for this number."""

    # Members
    @abstractmethod
    async def list_members(self, circle_id: str) -> list[CircleMember]: ...

    @abstractmethod
    async def get_member(self, circle_id: str, member_id: str) -> CircleMember | None: ...

    @abstractmethod
    async def find_member_by_mobile(
        self, circle_id: str, mobile: str
    ) -> CircleMember | None: ...

    @abstractmethod
    async def save_member(self, member: CircleMember) -> CircleMember: ...

    @abstractmethod
    async def delete_member(self, circle_id: str, member_id: str) -> bool: ...

    # Invite links
    @abstractmethod
    async def create_invite(self, invite: CircleInvite) -> CircleInvite: ...

    @abstractmethod
    async def get_invite_by_token(self, token: str) -> CircleInvite | None: ...
