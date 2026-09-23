"""Postgres-backed user storage."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sqlalchemy import update

from app.core.errors import UserAlreadyExists
from app.models.user import User as UserRow
from app.users.models import User
from app.users.repository import UserRepository


class PostgresUserRepository(UserRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get_by_mobile(self, mobile: str) -> User | None:
        async with self._session_factory() as session:
            row = await session.scalar(select(UserRow).where(UserRow.mobile == mobile))
            return _to_domain(row)

    async def get_by_id(self, user_id: str) -> User | None:
        try:
            key = uuid.UUID(user_id)
        except ValueError:
            # A token carrying a non-UUID subject cannot match any row.
            return None
        async with self._session_factory() as session:
            return _to_domain(await session.get(UserRow, key))

    async def bump_token_version(self, user_id: str) -> None:
        key = _as_uuid(user_id)
        if key is None:
            return
        async with self._session_factory() as session:
            await session.execute(
                update(UserRow)
                .where(UserRow.id == key)
                .values(token_version=UserRow.token_version + 1)
            )
            await session.commit()

    async def create(self, *, mobile: str, name: str, email: str | None = None) -> User:
        async with self._session_factory() as session:
            row = UserRow(id=uuid.uuid4(), mobile=mobile, name=name, email=email)
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                # Two registrations for one number raced; the unique index won.
                await session.rollback()
                raise UserAlreadyExists() from exc
            await session.refresh(row)
            return _to_domain(row)


def _to_domain(row: UserRow | None) -> User | None:
    if row is None:
        return None
    return User(
        id=str(row.id),
        mobile=row.mobile,
        name=row.name,
        email=row.email,
        token_version=row.token_version,
    )
