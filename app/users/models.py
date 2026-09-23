from dataclasses import dataclass


@dataclass
class User:
    id: str
    mobile: str
    name: str
    email: str | None = None
    # Bumped to invalidate every token this user holds - a lost phone, or a
    # release that must sign everyone out. See app/core/security.py.
    token_version: int = 0
