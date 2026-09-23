"""Screen 3: workplace choice and saved places."""

import pytest

from tests.conftest_onboarding import DOCTOR, auth, sign_in


@pytest.fixture
def token(client) -> str:
    token = sign_in(client)
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))
    return token


def add_place(client, token, **overrides):
    payload = {
        "label": "Example City Hospital",
        "address_line": "Building A, Floor 2",
        **overrides,
    }
    return client.post("/places", json=payload, headers=auth(token))


class TestJoinMode:
    def test_joining_creates_a_pending_membership(self, client, token):
        response = client.put(
            "/onboarding/workplace",
            json={
                "mode": "join_organisation",
                "invite_code": "ECH-4X2K",
                "department": "Emergency Department",
                "employee_id": "E-1042",
            },
            headers=auth(token),
        )

        assert response.status_code == 200
        # Only the organisation can approve; we never mark it approved ourselves.
        assert response.json()["status"] == "pending"
        assert response.json()["department"] == "Emergency Department"

    def test_joining_needs_a_code_and_a_department(self, client, token):
        response = client.put(
            "/onboarding/workplace",
            json={"mode": "join_organisation"},
            headers=auth(token),
        )

        assert response.status_code == 422
        assert "invite_code" in response.json()["message"]
        assert "department" in response.json()["message"]

    def test_joining_does_not_require_a_saved_place(self, client, token):
        response = client.put(
            "/onboarding/workplace",
            json={
                "mode": "join_organisation",
                "invite_code": "ECH-4X2K",
                "department": "Emergency Department",
            },
            headers=auth(token),
        )

        assert response.status_code == 200


class TestIndividualMode:
    def test_an_individual_needs_at_least_one_place(self, client, token):
        response = client.put(
            "/onboarding/workplace", json={"mode": "individual"}, headers=auth(token)
        )

        assert response.status_code == 422
        assert "place" in response.json()["message"]

    def test_an_individual_with_a_place_may_continue(self, client, token):
        add_place(client, token)

        response = client.put(
            "/onboarding/workplace", json={"mode": "individual"}, headers=auth(token)
        )

        assert response.status_code == 200

    def test_individual_mode_discards_any_organisation_fields(self, client, token):
        add_place(client, token)

        response = client.put(
            "/onboarding/workplace",
            json={"mode": "individual", "invite_code": "ECH-4X2K",
                  "department": "Emergency Department"},
            headers=auth(token),
        )

        assert response.json()["invite_code"] is None
        assert response.json()["department"] is None


class TestPlaces:
    def test_the_first_place_becomes_the_default(self, client, token):
        """An SOS needs something to suggest; one place means that is it."""
        body = add_place(client, token).json()

        assert body["is_default"] is True

    def test_a_later_place_is_not_default_unless_asked(self, client, token):
        add_place(client, token)

        second = add_place(client, token, label="Home").json()

        assert second["is_default"] is False

    def test_setting_a_new_default_clears_the_old_one(self, client, token):
        first = add_place(client, token).json()
        second = add_place(client, token, label="Home", is_default=True).json()

        places = {p["id"]: p for p in client.get("/places", headers=auth(token)).json()}

        assert places[second["id"]]["is_default"] is True
        assert places[first["id"]]["is_default"] is False

    def test_coordinates_are_stored_for_later_sos_matching(self, client, token):
        body = add_place(
            client, token,
            latitude=19.0760, longitude=72.8777,
            provider="google", provider_place_id="ChIJ-abc",
        ).json()

        stored = client.get("/places", headers=auth(token)).json()[0]
        assert stored["latitude"] == pytest.approx(19.0760)
        assert stored["longitude"] == pytest.approx(72.8777)
        assert stored["provider"] == "google"
        assert stored["provider_place_id"] == "ChIJ-abc"

    def test_a_place_can_be_edited(self, client, token):
        place = add_place(client, token).json()

        response = client.put(
            f"/places/{place['id']}",
            json={"label": "Clinic", "address_line": "New address"},
            headers=auth(token),
        )

        assert response.status_code == 200
        assert response.json()["label"] == "Clinic"

    def test_deleting_the_default_promotes_another_place(self, client, token):
        first = add_place(client, token).json()
        add_place(client, token, label="Home")

        client.delete(f"/places/{first['id']}", headers=auth(token))

        remaining = client.get("/places", headers=auth(token)).json()
        assert len(remaining) == 1
        assert remaining[0]["is_default"] is True

    def test_deleting_an_unknown_place_is_a_404(self, client, token):
        response = client.delete("/places/does-not-exist", headers=auth(token))

        assert response.status_code == 404

    def test_places_are_private_to_their_owner(self, client, token):
        add_place(client, token)
        other_token = sign_in(client, "917777777777")

        assert client.get("/places", headers=auth(other_token)).json() == []

    def test_a_place_needs_a_label_and_an_address(self, client, token):
        assert client.post(
            "/places", json={"label": "", "address_line": "x"}, headers=auth(token)
        ).status_code == 422


class TestOrdering:
    def test_a_workplace_cannot_be_saved_before_a_profile(self, client):
        token = sign_in(client)

        response = client.put(
            "/onboarding/workplace", json={"mode": "individual"}, headers=auth(token)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "profile_required"
