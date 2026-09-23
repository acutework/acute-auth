"""Circle domain types.

A circle is a named group of people one worker chooses to alert. Being
invited is not the same as being a responder: nobody is alerted until they
accept, so an SOS never fires at a number that never agreed to it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class MemberStatus(StrEnum):
    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REMOVED = "removed"


class InviteDelivery(StrEnum):
    """How the invitation actually went out, as reported by the notifier."""

    PUSH = "push"
    SMS = "sms"
    NONE = "none"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Circle:
    id: str
    owner_user_id: str
    name: str
    include_in_sos_alerts: bool = True
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class CircleMember:
    """One person in a circle, keyed by mobile number rather than user id.

    Someone can be invited long before they have an account, so the mobile is
    the identity until they accept and `user_id` is filled in.
    """

    id: str
    circle_id: str
    mobile: str
    user_id: str | None = None
    display_name: str | None = None
    status: MemberStatus = MemberStatus.INVITED
    is_owner: bool = False
    delivery: InviteDelivery | None = None
    invited_at: datetime = field(default_factory=_now)
    responded_at: datetime | None = None


@dataclass
class CircleInvite:
    """The shareable link's token."""

    id: str
    circle_id: str
    token: str
    created_by_user_id: str
    expires_at: datetime
    created_at: datetime = field(default_factory=_now)
