"""Request and response bodies for circles."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.circles.models import InviteDelivery, MemberStatus


class InviteeIn(BaseModel):
    mobile: str = Field(min_length=6, max_length=20)
    display_name: str | None = Field(default=None, max_length=120)


class CircleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    include_in_sos_alerts: bool = True
    invitees: list[InviteeIn] = Field(default_factory=list)


class CirclePatch(BaseModel):
    """Only the fields present are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    include_in_sos_alerts: bool | None = None


class JoinIn(BaseModel):
    token: str = Field(min_length=1, max_length=64)


class CircleMemberOut(BaseModel):
    id: str
    mobile: str
    display_name: str | None = None
    status: MemberStatus
    is_owner: bool
    # None until an invitation has been attempted; "none" when it could not be
    # delivered at all.
    delivery: InviteDelivery | None = None
    invited_at: datetime
    responded_at: datetime | None = None


class CircleOut(BaseModel):
    id: str
    name: str
    include_in_sos_alerts: bool
    is_owner: bool
    accepted_count: int
    pending_count: int
    created_at: datetime
    members: list[CircleMemberOut] = Field(default_factory=list)


class InviteLinkOut(BaseModel):
    token: str
    url: str
    expires_in: int
