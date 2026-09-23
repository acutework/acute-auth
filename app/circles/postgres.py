"""Postgres-backed circle storage."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.circles.models import (
    Circle,
    CircleInvite,
    CircleMember,
    InviteDelivery,
    MemberStatus,
)
from app.circles.repository import CirclesRepository
from app.models.circles import CircleInviteRow, CircleMemberRow, CircleRow


class PostgresCirclesRepository(CirclesRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def create_circle(self, circle: Circle) -> Circle:
        async with self._session_factory() as session:
            row = CircleRow(
                id=_as_uuid(circle.id) or uuid.uuid4(),
                owner_user_id=_as_uuid(circle.owner_user_id),
                name=circle.name,
                include_in_sos_alerts=circle.include_in_sos_alerts,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _circle_to_domain(row)

    async def get_circle(self, circle_id: str) -> Circle | None:
        key = _as_uuid(circle_id)
        if key is None:
            return None
        async with self._session_factory() as session:
            row = await session.get(CircleRow, key)
            return _circle_to_domain(row) if row else None

    async def save_circle(self, circle: Circle) -> Circle:
        async with self._session_factory() as session:
            row = await session.get(CircleRow, _as_uuid(circle.id))
            row.name = circle.name
            row.include_in_sos_alerts = circle.include_in_sos_alerts
            await session.commit()
            await session.refresh(row)
            return _circle_to_domain(row)

    async def delete_circle(self, circle_id: str) -> bool:
        key = _as_uuid(circle_id)
        if key is None:
            return False
        async with self._session_factory() as session:
            result = await session.execute(
                delete(CircleRow).where(CircleRow.id == key)
            )
            await session.commit()
            return result.rowcount > 0

    async def list_circles_for_user(self, user_id: str) -> list[Circle]:
        key = _as_uuid(user_id)
        if key is None:
            return []
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(CircleRow)
                .join(CircleMemberRow, CircleMemberRow.circle_id == CircleRow.id)
                .where(
                    CircleMemberRow.user_id == key,
                    CircleMemberRow.status == MemberStatus.ACCEPTED.value,
                )
                .order_by(CircleRow.created_at)
            )
            return [_circle_to_domain(row) for row in rows]

    async def list_circles_inviting(self, mobile: str) -> list[Circle]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(CircleRow)
                .join(CircleMemberRow, CircleMemberRow.circle_id == CircleRow.id)
                .where(
                    CircleMemberRow.mobile == mobile,
                    CircleMemberRow.status == MemberStatus.INVITED.value,
                )
                .order_by(CircleRow.created_at)
            )
            return [_circle_to_domain(row) for row in rows]

    async def list_members(self, circle_id: str) -> list[CircleMember]:
        key = _as_uuid(circle_id)
        if key is None:
            return []
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(CircleMemberRow)
                .where(CircleMemberRow.circle_id == key)
                .order_by(
                    CircleMemberRow.is_owner.desc(), CircleMemberRow.invited_at
                )
            )
            return [_member_to_domain(row) for row in rows]

    async def get_member(self, circle_id: str, member_id: str) -> CircleMember | None:
        circle_key, member_key = _as_uuid(circle_id), _as_uuid(member_id)
        if circle_key is None or member_key is None:
            return None
        async with self._session_factory() as session:
            row = await session.get(CircleMemberRow, member_key)
            return (
                _member_to_domain(row)
                if row and row.circle_id == circle_key
                else None
            )

    async def find_member_by_mobile(
        self, circle_id: str, mobile: str
    ) -> CircleMember | None:
        key = _as_uuid(circle_id)
        if key is None:
            return None
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CircleMemberRow).where(
                    CircleMemberRow.circle_id == key,
                    CircleMemberRow.mobile == mobile,
                )
            )
            return _member_to_domain(row) if row else None

    async def save_member(self, member: CircleMember) -> CircleMember:
        member_key = _as_uuid(member.id) if member.id else None
        async with self._session_factory() as session:
            row = await session.get(CircleMemberRow, member_key) if member_key else None
            if row is None:
                row = CircleMemberRow(
                    id=member_key or uuid.uuid4(),
                    circle_id=_as_uuid(member.circle_id),
                    mobile=member.mobile,
                    invited_at=member.invited_at,
                )
                session.add(row)
            row.user_id = _as_uuid(member.user_id)
            row.display_name = member.display_name
            row.status = member.status.value
            row.is_owner = member.is_owner
            row.delivery = member.delivery.value if member.delivery else None
            row.invited_at = member.invited_at
            row.responded_at = member.responded_at
            await session.commit()
            await session.refresh(row)
            return _member_to_domain(row)

    async def delete_member(self, circle_id: str, member_id: str) -> bool:
        circle_key, member_key = _as_uuid(circle_id), _as_uuid(member_id)
        if circle_key is None or member_key is None:
            return False
        async with self._session_factory() as session:
            result = await session.execute(
                delete(CircleMemberRow).where(
                    CircleMemberRow.id == member_key,
                    CircleMemberRow.circle_id == circle_key,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def create_invite(self, invite: CircleInvite) -> CircleInvite:
        async with self._session_factory() as session:
            row = CircleInviteRow(
                id=_as_uuid(invite.id) or uuid.uuid4(),
                circle_id=_as_uuid(invite.circle_id),
                token=invite.token,
                created_by_user_id=_as_uuid(invite.created_by_user_id),
                expires_at=invite.expires_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _invite_to_domain(row)

    async def get_invite_by_token(self, token: str) -> CircleInvite | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CircleInviteRow).where(CircleInviteRow.token == token)
            )
            return _invite_to_domain(row) if row else None


def _as_uuid(value: str | None) -> uuid.UUID | None:
    """Tokens and paths are not always well-formed; a bad id must not 500."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _aware(value: datetime | None) -> datetime | None:
    """asyncpg can hand back naive datetimes; comparisons here are always UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _circle_to_domain(row: CircleRow) -> Circle:
    return Circle(
        id=str(row.id),
        owner_user_id=str(row.owner_user_id),
        name=row.name,
        include_in_sos_alerts=row.include_in_sos_alerts,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _member_to_domain(row: CircleMemberRow) -> CircleMember:
    return CircleMember(
        id=str(row.id),
        circle_id=str(row.circle_id),
        mobile=row.mobile,
        user_id=str(row.user_id) if row.user_id else None,
        display_name=row.display_name,
        status=MemberStatus(row.status),
        is_owner=row.is_owner,
        delivery=InviteDelivery(row.delivery) if row.delivery else None,
        invited_at=_aware(row.invited_at),
        responded_at=_aware(row.responded_at),
    )


def _invite_to_domain(row: CircleInviteRow) -> CircleInvite:
    return CircleInvite(
        id=str(row.id),
        circle_id=str(row.circle_id),
        token=row.token,
        created_by_user_id=str(row.created_by_user_id),
        expires_at=_aware(row.expires_at),
        created_at=_aware(row.created_at),
    )
