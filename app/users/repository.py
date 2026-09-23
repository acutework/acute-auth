"""The storage contract for users.

Two implementations: [InMemoryUserRepository] for tests and quick local runs,
[PostgresUserRepository] for everything else. Chosen in app/deps.py.
"""

from abc import ABC, abstractmethod

from app.users.models import User


class UserRepository(ABC):
    @abstractmethod
    async def get_by_mobile(self, mobile: str) -> User | None: ...

    @abstractmethod
    async def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    async def create(
        self, *, mobile: str, name: str, email: str | None = None
    ) -> User: ...

    async def bump_token_version(self, user_id: str) -> None:
        """Invalidate every token this user holds.

        Used for a lost phone, or a release that must sign everyone out:

            UPDATE users SET token_version = token_version + 1;
        """
        raise NotImplementedError
