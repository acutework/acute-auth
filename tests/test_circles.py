"""Circles, over the in-memory repository through the real API.

The rule these tests exist to protect: being invited is not being a
responder. Nobody is alerted until they accept.
"""

import pytest
from fastapi.testclient import TestClient

from app.circles.models import InviteDelivery
from app.circles.notifier import InviteNotifier
from app.deps import (
    build_auth_service,
    build_circles_service,
    build_user_repository,
    get_auth_service,
    get_circles_service,
)
from app.main import app
from tests.conftest import EXISTING_MOBILE, make_settings
from tests.conftest_onboarding import auth, sign_in

OWNER_MOBILE = EXISTING_MOBILE
FRIEND_MOBILE = "918888888888"
STRANGER_MOBILE = "917777777777"


class RecordingNotifier(InviteNotifier):
    """Counts what was actually messaged, so cost rules can be asserted."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def notify(
        self, *, mobile: str, circle_name: str, inviter_name: str, join_url: str
    ) -> InviteDelivery:
        self.sent.append(mobile)
        return InviteDelivery.PUSH


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_in(client, OWNER_MOBILE)


def create_circle(client: TestClient, token: str, **overrides) -> dict:
    payload = {"name": "Family", "include_in_sos_alerts": True, "invitees": [], **overrides}
    response = client.post("/circles", json=payload, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def member_for(circle: dict, mobile: str) -> dict:
    return next(m for m in circle["members"] if m["mobile"] == mobile)


class TestCreating:
    def test_a_circle_is_created_with_the_people_it_invites(self, client, token):
        circle = create_circle(
            client,
            token,
            name="Ward team",
            invitees=[
                {"mobile": FRIEND_MOBILE, "display_name": "Asha"},
                {"mobile": STRANGER_MOBILE},
            ],
        )

        assert circle["name"] == "Ward team"
        assert circle["include_in_sos_alerts"] is True
        assert {m["mobile"] for m in circle["members"]} == {
            OWNER_MOBILE,
            FRIEND_MOBILE,
            STRANGER_MOBILE,
        }
        assert member_for(circle, FRIEND_MOBILE)["display_name"] == "Asha"

    def test_the_creator_is_an_accepted_owner_from_the_start(self, client, token):
        circle = create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])

        owner = member_for(circle, OWNER_MOBILE)
        assert owner["is_owner"] is True
        assert owner["status"] == "accepted"
        assert circle["is_owner"] is True

    def test_an_invitee_is_pending_rather_than_a_responder(self, client, token):
        circle = create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])

        assert member_for(circle, FRIEND_MOBILE)["status"] == "invited"
        assert circle["accepted_count"] == 1
        assert circle["pending_count"] == 1

    def test_inviting_your_own_number_is_rejected(self, client, token):
        response = client.post(
            "/circles",
            json={"name": "Family", "invitees": [{"mobile": OWNER_MOBILE}]},
            headers=auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "cannot_invite_self"

    def test_the_same_number_cannot_be_invited_twice_in_one_request(
        self, client, token
    ):
        response = client.post(
            "/circles",
            json={
                "name": "Family",
                "invitees": [{"mobile": FRIEND_MOBILE}, {"mobile": FRIEND_MOBILE}],
            },
            headers=auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "already_member"

    def test_a_number_already_in_the_circle_cannot_be_added_again(self, client, token):
        circle = create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])

        response = client.post(
            f"/circles/{circle['id']}/members",
            json={"mobile": FRIEND_MOBILE},
            headers=auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "already_member"

    def test_a_mobile_number_is_stored_in_its_canonical_form(self, client, token):
        circle = create_circle(client, token, invitees=[{"mobile": "+91 88888 88888"}])

        assert member_for(circle, FRIEND_MOBILE)["mobile"] == FRIEND_MOBILE


class TestOwnership:
    @pytest.fixture
    def circle(self, client, token) -> dict:
        return create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])

    @pytest.fixture
    def outsider(self, client) -> str:
        return sign_in(client, STRANGER_MOBILE)

    def test_the_owner_can_rename_a_circle(self, client, token, circle):
        response = client.patch(
            f"/circles/{circle['id']}", json={"name": "Home"}, headers=auth(token)
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Home"

    def test_the_owner_can_switch_a_circle_out_of_sos_alerts(
        self, client, token, circle
    ):
        response = client.patch(
            f"/circles/{circle['id']}",
            json={"include_in_sos_alerts": False},
            headers=auth(token),
        )

        assert response.json()["include_in_sos_alerts"] is False
        assert response.json()["name"] == "Family"

    def test_someone_who_is_not_the_owner_cannot_rename_it(
        self, client, circle, outsider
    ):
        response = client.patch(
            f"/circles/{circle['id']}", json={"name": "Mine now"}, headers=auth(outsider)
        )

        assert response.status_code == 403
        assert response.json()["code"] == "not_circle_owner"

    def test_someone_who_is_not_the_owner_cannot_delete_it(
        self, client, circle, outsider
    ):
        assert (
            client.delete(
                f"/circles/{circle['id']}", headers=auth(outsider)
            ).status_code
            == 403
        )

    def test_someone_who_is_not_the_owner_cannot_add_a_member(
        self, client, circle, outsider
    ):
        response = client.post(
            f"/circles/{circle['id']}/members",
            json={"mobile": "916666666666"},
            headers=auth(outsider),
        )

        assert response.status_code == 403

    def test_someone_who_is_not_the_owner_cannot_remove_a_member(
        self, client, circle, outsider
    ):
        member = member_for(circle, FRIEND_MOBILE)

        response = client.delete(
            f"/circles/{circle['id']}/members/{member['id']}", headers=auth(outsider)
        )

        assert response.status_code == 403

    def test_the_owner_can_remove_a_member(self, client, token, circle):
        member = member_for(circle, FRIEND_MOBILE)

        response = client.delete(
            f"/circles/{circle['id']}/members/{member['id']}", headers=auth(token)
        )

        assert response.status_code == 204
        remaining = client.get(
            f"/circles/{circle['id']}", headers=auth(token)
        ).json()["members"]
        assert [m["mobile"] for m in remaining] == [OWNER_MOBILE]

    def test_deleting_a_circle_removes_it_for_everyone(self, client, token, circle):
        assert (
            client.delete(f"/circles/{circle['id']}", headers=auth(token)).status_code
            == 204
        )
        assert client.get("/circles", headers=auth(token)).json() == []


class TestListing:
    def test_listing_shows_the_circles_i_own(self, client, token):
        create_circle(client, token, name="Family")
        create_circle(client, token, name="Ward team")

        names = [c["name"] for c in client.get("/circles", headers=auth(token)).json()]

        assert names == ["Family", "Ward team"]

    def test_a_circle_someone_else_owns_is_not_mine_until_i_accept(
        self, client, token
    ):
        create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])
        friend = sign_in(client, FRIEND_MOBILE)

        assert client.get("/circles", headers=auth(friend)).json() == []

    def test_invitations_lists_circles_waiting_on_my_answer(self, client, token):
        create_circle(client, token, name="Family", invitees=[{"mobile": FRIEND_MOBILE}])
        friend = sign_in(client, FRIEND_MOBILE)

        invitations = client.get("/circles/invitations", headers=auth(friend)).json()

        assert [c["name"] for c in invitations] == ["Family"]
        assert invitations[0]["is_owner"] is False

    def test_an_answered_invitation_leaves_the_invitations_list(self, client, token):
        circle = create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])
        friend = sign_in(client, FRIEND_MOBILE)

        client.post(f"/circles/{circle['id']}/accept", headers=auth(friend))

        assert client.get("/circles/invitations", headers=auth(friend)).json() == []

    def test_a_circle_i_have_nothing_to_do_with_is_not_found(self, client, token):
        circle = create_circle(client, token)
        outsider = sign_in(client, STRANGER_MOBILE)

        response = client.get(f"/circles/{circle['id']}", headers=auth(outsider))

        assert response.status_code == 404
        assert response.json()["code"] == "circle_not_found"


class TestResponding:
    @pytest.fixture
    def circle(self, client, token) -> dict:
        return create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])

    def test_accepting_makes_me_a_responder_in_that_circle(self, client, circle):
        friend = sign_in(client, FRIEND_MOBILE)

        response = client.post(f"/circles/{circle['id']}/accept", headers=auth(friend))

        assert response.status_code == 200
        assert member_for(response.json(), FRIEND_MOBILE)["status"] == "accepted"
        assert member_for(response.json(), FRIEND_MOBILE)["responded_at"] is not None
        assert [c["id"] for c in client.get("/circles", headers=auth(friend)).json()] == [
            circle["id"]
        ]

    def test_accepting_an_invitation_i_was_never_sent_is_refused(self, client, circle):
        outsider = sign_in(client, STRANGER_MOBILE)

        response = client.post(
            f"/circles/{circle['id']}/accept", headers=auth(outsider)
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invite_invalid"

    def test_declining_leaves_me_out_of_the_circle(self, client, token, circle):
        friend = sign_in(client, FRIEND_MOBILE)

        assert (
            client.post(
                f"/circles/{circle['id']}/decline", headers=auth(friend)
            ).status_code
            == 204
        )
        assert client.get("/circles", headers=auth(friend)).json() == []
        owners_view = client.get(f"/circles/{circle['id']}", headers=auth(token)).json()
        assert member_for(owners_view, FRIEND_MOBILE)["status"] == "declined"

    def test_someone_who_declined_can_be_invited_again(self, client, token, circle):
        friend = sign_in(client, FRIEND_MOBILE)
        client.post(f"/circles/{circle['id']}/decline", headers=auth(friend))

        response = client.post(
            f"/circles/{circle['id']}/members",
            json={"mobile": FRIEND_MOBILE},
            headers=auth(token),
        )

        assert response.status_code == 201
        assert response.json()["status"] == "invited"
        assert [
            c["id"] for c in client.get("/circles/invitations", headers=auth(friend)).json()
        ] == [circle["id"]]


class TestJoiningByLink:
    @pytest.fixture
    def circle(self, client, token) -> dict:
        return create_circle(client, token)

    def link(self, client, token, circle) -> dict:
        response = client.post(
            f"/circles/{circle['id']}/invite-link", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_a_link_carries_a_token_and_a_url_to_open(self, client, token, circle):
        link = self.link(client, token, circle)

        assert link["token"]
        assert link["url"].endswith(link["token"])
        assert link["url"].startswith("https://acutework.app/join")
        assert link["expires_in"] > 0

    def test_a_stranger_with_the_token_joins_as_an_accepted_member(
        self, client, token, circle
    ):
        link = self.link(client, token, circle)
        stranger = sign_in(client, STRANGER_MOBILE)

        response = client.post(
            "/circles/join", json={"token": link["token"]}, headers=auth(stranger)
        )

        assert response.status_code == 200
        assert member_for(response.json(), STRANGER_MOBILE)["status"] == "accepted"

    def test_someone_already_invited_accepts_their_own_row_rather_than_a_second_one(
        self, client, token, circle
    ):
        client.post(
            f"/circles/{circle['id']}/members",
            json={"mobile": FRIEND_MOBILE},
            headers=auth(token),
        )
        link = self.link(client, token, circle)
        friend = sign_in(client, FRIEND_MOBILE)

        joined = client.post(
            "/circles/join", json={"token": link["token"]}, headers=auth(friend)
        ).json()

        assert [m["mobile"] for m in joined["members"]].count(FRIEND_MOBILE) == 1
        assert member_for(joined, FRIEND_MOBILE)["status"] == "accepted"

    def test_an_unknown_token_is_refused(self, client):
        stranger = sign_in(client, STRANGER_MOBILE)

        response = client.post(
            "/circles/join", json={"token": "not-a-real-token"}, headers=auth(stranger)
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invite_invalid"


class TestExpiredLink:
    @pytest.fixture
    def settings(self):
        """Every link is already expired by the time it is used."""
        return make_settings(invite_link_ttl_seconds=-1)

    def test_an_expired_token_is_refused(self, client, token):
        circle = create_circle(client, token)
        link = client.post(
            f"/circles/{circle['id']}/invite-link", headers=auth(token)
        ).json()
        stranger = sign_in(client, STRANGER_MOBILE)

        response = client.post(
            "/circles/join", json={"token": link["token"]}, headers=auth(stranger)
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invite_invalid"


class TestInviteCost:
    """An invitation to a stranger costs an SMS, so sends are budgeted."""

    @pytest.fixture
    def notifier(self) -> RecordingNotifier:
        return RecordingNotifier()

    @pytest.fixture
    def settings(self):
        return make_settings(invite_send_limit=2, invite_send_window_seconds=3600)

    @pytest.fixture
    def client(self, settings, notifier) -> TestClient:
        users = build_user_repository(settings)
        auth_service = build_auth_service(settings, users=users)
        circles = build_circles_service(settings, users=users, notifier=notifier)

        app.dependency_overrides[get_auth_service] = lambda: auth_service
        app.dependency_overrides[get_circles_service] = lambda: circles
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_passing_the_invite_limit_is_refused(self, client, token, notifier):
        create_circle(
            client,
            token,
            invitees=[{"mobile": FRIEND_MOBILE}, {"mobile": STRANGER_MOBILE}],
        )
        circle = create_circle(client, token, name="Ward team")

        response = client.post(
            f"/circles/{circle['id']}/members",
            json={"mobile": "916666666666"},
            headers=auth(token),
        )

        assert response.status_code == 429
        assert response.json()["code"] == "too_many_requests"
        assert "916666666666" not in notifier.sent

    def test_the_budget_is_spent_before_a_circle_is_written(
        self, client, token, notifier
    ):
        response = client.post(
            "/circles",
            json={
                "name": "Too many",
                "invitees": [
                    {"mobile": FRIEND_MOBILE},
                    {"mobile": STRANGER_MOBILE},
                    {"mobile": "916666666666"},
                ],
            },
            headers=auth(token),
        )

        assert response.status_code == 429
        assert notifier.sent == []
        assert client.get("/circles", headers=auth(token)).json() == []

    def test_the_same_number_is_never_messaged_twice_for_one_circle(
        self, client, token, notifier
    ):
        circle = create_circle(client, token, invitees=[{"mobile": FRIEND_MOBILE}])

        client.post(
            f"/circles/{circle['id']}/members",
            json={"mobile": FRIEND_MOBILE},
            headers=auth(token),
        )

        assert notifier.sent == [FRIEND_MOBILE]
