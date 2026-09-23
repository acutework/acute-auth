"""In-memory user storage. Everything is lost on restart - development only."""

import uuid

from app.users.models import User
from app.users.repository import UserRepository


class InMemoryUserRepository(UserRepository):
    def __init__(self, seed: list[User] | None = None):
        self._by_id: dict[str, User] = {}
        for user in seed or []:
            self._by_id[user.id] = user

    async def get_by_mobile(self, mobile: str) -> User | None:
        return next((u for u in self._by_id.values() if u.mobile == mobile), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    async def bump_token_version(self, user_id: str) -> None:
        user = self._by_id.get(user_id)
        if user is not None:
            user.token_version += 1

    async def create(self, *, mobile: str, name: str, email: str | None = None) -> User:
        user = User(id=uuid.uuid4().hex, mobile=mobile, name=name, email=email)
        self._by_id[user.id] = user
        return user


def demo_users() -> list[User]:
    """One known account so the 'existing user' path works out of the box."""
    return [User(id="demo-user-1", mobile="919999999999", name="Demo User")]
