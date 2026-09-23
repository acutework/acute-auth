import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerProfileRow(Base):
    """One profile per user. Every credential field is self-declared."""

    __tablename__ = "worker_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(255))

    # Free-text lists as entered. JSON rather than join tables because nothing
    # queries across them - they are shown back to the person who typed them.
    degrees: Mapped[list] = mapped_column(JSON, default=list)
    specialties: Mapped[list] = mapped_column(JSON, default=list)
    nursing_qualifications: Mapped[list] = mapped_column(JSON, default=list)

    medical_council_reg_no: Mapped[str | None] = mapped_column(String(64))
    nursing_council_reg_no: Mapped[str | None] = mapped_column(String(64))
    certification_level: Mapped[str | None] = mapped_column(String(64))
    paramedic_licence_no: Mapped[str | None] = mapped_column(String(64))
    role_description: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OnboardingStateRow(Base):
    __tablename__ = "onboarding_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_step: Mapped[str] = mapped_column(String(32), default="role")
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkplaceMembershipRow(Base):
    __tablename__ = "workplace_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    invite_code: Mapped[str | None] = mapped_column(String(64))
    organisation_name: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(120))
    employee_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SavedPlaceRow(Base):
    """A place a worker works from, with coordinates kept for SOS matching."""

    __tablename__ = "saved_places"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(80))
    address_line: Mapped[str] = mapped_column(String(400))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which lookup service produced this, so a later provider change is legible.
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_place_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogItemRow(Base):
    """Degrees, specialties, departments and the rest - one table, keyed by kind."""

    __tablename__ = "catalog_items"
    __table_args__ = (UniqueConstraint("kind", "label", name="uq_catalog_kind_label"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
