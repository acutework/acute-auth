"""Invitation delivery, behind a contract.

Two ways an invitation reaches someone, and exactly one place decides which:
[InviteDispatcher]. Somebody who already has an account gets a push; a
stranger gets an SMS, which costs money and is therefore rate limited by the
service before it gets here.

Nothing in this module ever raises on a delivery failure. An invitation that
could not be sent is reported as [InviteDelivery.NONE] and the circle is
created regardless - losing a circle because one number was unreachable would
be far worse than an invitation the owner has to chase.
"""

import logging
from abc import ABC, abstractmethod

import httpx

from app.circles.models import InviteDelivery
from app.users.repository import UserRepository

logger = logging.getLogger(__name__)


class InviteNotifier(ABC):
    @abstractmethod
    async def notify(
        self, *, mobile: str, circle_name: str, inviter_name: str, join_url: str
    ) -> InviteDelivery:
        """Tell `mobile` they were invited, and report how it was delivered."""

    async def aclose(self) -> None:
        """Release any held resources (HTTP clients). Default: nothing."""


class PushInviteNotifier(InviteNotifier):
    """For a mobile that already has an account."""

    async def notify(
        self, *, mobile: str, circle_name: str, inviter_name: str, join_url: str
    ) -> InviteDelivery:
        # NOT YET REAL DELIVERY. Nothing is sent: this logs and reports PUSH so
        # the rest of the flow is complete and testable. Making it real needs a
        # device-token table on users (written at sign-in from the app's FCM
        # token), Firebase credentials in settings, and an FCM send here.
        # Until then an invited user sees the invitation only when the app
        # calls GET /circles/invitations.
        logger.info(
            "Circle invite for %s to %r from %s would be pushed (%s)",
            mobile,
            circle_name,
            inviter_name,
            join_url,
        )
        return InviteDelivery.PUSH


class SmsInviteNotifier(InviteNotifier):
    """For a mobile with no account yet, over MSG91's flow API.

    Flow (as opposed to OTP) sends an arbitrary approved template, which is
    what an invitation is. A blank template id is a legitimate configuration:
    it means invitations by SMS are switched off, not that they failed.
    """

    def __init__(
        self,
        *,
        authkey: str,
        template_id: str,
        flow_url: str = "https://control.msg91.com/api/v5/flow/",
        client: httpx.AsyncClient | None = None,
    ):
        self._authkey = authkey
        self._template_id = template_id
        self._flow_url = flow_url
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def notify(
        self, *, mobile: str, circle_name: str, inviter_name: str, join_url: str
    ) -> InviteDelivery:
        if not self._template_id or not self._authkey:
            logger.info(
                "No MSG91 invite template configured; not sending an SMS to %s", mobile
            )
            return InviteDelivery.NONE

        try:
            response = await self._client.post(
                self._flow_url,
                headers={"authkey": self._authkey, "accept": "application/json"},
                json={
                    "template_id": self._template_id,
                    "recipients": [
                        {
                            "mobiles": mobile,
                            "circle": circle_name,
                            "inviter": inviter_name,
                            "url": join_url,
                        }
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("MSG91 could not deliver a circle invite: %r", exc)
            return InviteDelivery.NONE

        if data.get("type") != "success":
            logger.warning(
                "MSG91 refused a circle invite: %s", data.get("message") or data
            )
            return InviteDelivery.NONE
        return InviteDelivery.SMS

    async def aclose(self) -> None:
        await self._client.aclose()


class InviteDispatcher(InviteNotifier):
    """The only place that decides push or SMS."""

    def __init__(
        self,
        *,
        users: UserRepository,
        push: InviteNotifier,
        sms: InviteNotifier,
    ):
        self._users = users
        self._push = push
        self._sms = sms

    async def notify(
        self, *, mobile: str, circle_name: str, inviter_name: str, join_url: str
    ) -> InviteDelivery:
        known = await self._users.get_by_mobile(mobile)
        notifier = self._push if known else self._sms
        return await notifier.notify(
            mobile=mobile,
            circle_name=circle_name,
            inviter_name=inviter_name,
            join_url=join_url,
        )

    async def aclose(self) -> None:
        await self._push.aclose()
        await self._sms.aclose()
