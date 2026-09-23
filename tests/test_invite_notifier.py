"""Invitation delivery: who gets a push, who gets an SMS, and what happens
when neither works.

The invariant under test is that no delivery problem ever reaches the caller:
an unreachable number costs an invitation, never the circle.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.circles.models import InviteDelivery
from app.circles.notifier import InviteDispatcher, PushInviteNotifier, SmsInviteNotifier
from app.deps import (
    build_auth_service,
    build_circles_service,
    build_user_repository,
    get_auth_service,
    get_circles_service,
)
from app.main import app
from app.users.memory import InMemoryUserRepository
from app.users.models import User
from tests.conftest_onboarding import auth, sign_in

KNOWN_MOBILE = "919999999999"
UNKNOWN_MOBILE = "918888888888"

INVITE = {
    "circle_name": "Ward team",
    "inviter_name": "Dr Priya Sharma",
    "join_url": "https://acutework.app/join/abc123",
}


def make_sms(handler, *, template_id: str = "invite-template") -> SmsInviteNotifier:
    return SmsInviteNotifier(
        authkey="test-authkey",
        template_id=template_id,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def responder(payload: dict, status_code: int = 200):
    """A handler that records the request it saw and returns `payload`."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status_code, json=payload)

    return handler, seen


def make_dispatcher(sms: SmsInviteNotifier) -> InviteDispatcher:
    return InviteDispatcher(
        users=InMemoryUserRepository(
            seed=[User(id="u1", mobile=KNOWN_MOBILE, name="Known")]
        ),
        push=PushInviteNotifier(),
        sms=sms,
    )


class TestChoosingHowToDeliver:
    async def test_a_number_with_an_account_is_pushed_rather_than_messaged(self):
        handler, seen = responder({"type": "success"})
        dispatcher = make_dispatcher(make_sms(handler))

        delivery = await dispatcher.notify(mobile=KNOWN_MOBILE, **INVITE)

        assert delivery is InviteDelivery.PUSH
        # An SMS to someone who already has the app is money wasted.
        assert seen == []

    async def test_a_number_with_no_account_is_sent_an_sms(self):
        handler, seen = responder({"type": "success"})
        dispatcher = make_dispatcher(make_sms(handler))

        delivery = await dispatcher.notify(mobile=UNKNOWN_MOBILE, **INVITE)

        assert delivery is InviteDelivery.SMS
        assert len(seen) == 1
        assert seen[0].url.path == "/api/v5/flow/"
        assert seen[0].headers["authkey"] == "test-authkey"


class TestSmsDelivery:
    async def test_the_flow_request_carries_the_circle_and_the_join_link(self):
        import json

        handler, seen = responder({"type": "success"})

        await make_sms(handler).notify(mobile=UNKNOWN_MOBILE, **INVITE)

        body = json.loads(seen[0].content)
        assert body["template_id"] == "invite-template"
        assert body["recipients"] == [
            {
                "mobiles": UNKNOWN_MOBILE,
                "circle": "Ward team",
                "inviter": "Dr Priya Sharma",
                "url": "https://acutework.app/join/abc123",
            }
        ]

    async def test_a_blank_template_id_sends_nothing_and_does_not_raise(self):
        handler, seen = responder({"type": "success"})

        delivery = await make_sms(handler, template_id="").notify(
            mobile=UNKNOWN_MOBILE, **INVITE
        )

        assert delivery is InviteDelivery.NONE
        assert seen == []

    async def test_a_transport_failure_is_reported_as_undelivered(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        assert (
            await make_sms(handler).notify(mobile=UNKNOWN_MOBILE, **INVITE)
            is InviteDelivery.NONE
        )

    async def test_a_refusal_from_msg91_is_reported_as_undelivered(self):
        handler, _ = responder({"type": "error", "message": "invalid template_id"})

        assert (
            await make_sms(handler).notify(mobile=UNKNOWN_MOBILE, **INVITE)
            is InviteDelivery.NONE
        )

    async def test_a_5xx_is_reported_as_undelivered(self):
        handler, _ = responder({"type": "error"}, status_code=503)

        assert (
            await make_sms(handler).notify(mobile=UNKNOWN_MOBILE, **INVITE)
            is InviteDelivery.NONE
        )


class TestUndeliverableInvitesNeverFailACircle:
    @pytest.fixture
    def client(self, settings):
        """The real app, with MSG91 wired to a transport that never answers."""

        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        users = build_user_repository(settings)
        auth_service = build_auth_service(settings, users=users)
        circles = build_circles_service(
            settings,
            users=users,
            notifier=InviteDispatcher(
                users=users, push=PushInviteNotifier(), sms=make_sms(unreachable)
            ),
        )

        app.dependency_overrides[get_auth_service] = lambda: auth_service
        app.dependency_overrides[get_circles_service] = lambda: circles
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_a_circle_is_still_created_when_the_sms_cannot_be_sent(self, client):
        token = sign_in(client, KNOWN_MOBILE)

        response = client.post(
            "/circles",
            json={"name": "Ward team", "invitees": [{"mobile": UNKNOWN_MOBILE}]},
            headers=auth(token),
        )

        assert response.status_code == 201
        invited = next(
            m for m in response.json()["members"] if m["mobile"] == UNKNOWN_MOBILE
        )
        # The invitation is recorded as undelivered, so the owner can chase it.
        assert invited["delivery"] == "none"
        assert invited["status"] == "invited"
