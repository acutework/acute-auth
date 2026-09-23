"""Assembles the invitation dispatcher from settings.

Kept separate from app/deps.py for the same reason app/otp/registry.py is:
swapping how an invitation is delivered should touch one file.
"""

from app.circles.notifier import InviteDispatcher, PushInviteNotifier, SmsInviteNotifier
from app.config import Settings
from app.users.repository import UserRepository


def build_invite_dispatcher(
    settings: Settings, users: UserRepository
) -> InviteDispatcher:
    return InviteDispatcher(
        users=users,
        push=PushInviteNotifier(),
        sms=SmsInviteNotifier(
            authkey=settings.msg91_authkey,
            template_id=settings.msg91_invite_template_id,
            flow_url=settings.msg91_flow_url,
        ),
    )
