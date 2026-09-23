from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base; all ORM models subclass this.

    Alembic autogenerate targets ``Base.metadata``.
    """
