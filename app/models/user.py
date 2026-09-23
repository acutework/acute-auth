import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """An account, identified by a verified mobile number.

    acute-auth owns identity for the whole system: other services should treat
    the JWT's ``sub`` as the user id and keep their own profile data keyed by
    it, rather than storing mobile numbers of their own.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Canonical form: <countrycode><number>, digits only. See app/core/mobile.py.
    mobile: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    # Every token carries this number; a mismatch means the token predates a
    # forced sign-out and is refused. Bump it to revoke everything at once.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
