"""The percentage behind the ring on the profile avatar."""

import pytest

from app.onboarding.completion import compute_completion
from app.onboarding.models import (
    SavedPlace,
    WorkerProfile,
    WorkerRole,
    WorkplaceMembership,
    WorkplaceMode,
)
from tests.conftest_onboarding import DOCTOR, auth, sign_in

JOIN = {
    "mode": "join_organisation",
    "invite_code": "ECH-4X2K",
    "department": "Emergency Department",
}


def profile(**overrides) -> WorkerProfile:
    return WorkerProfile(
        user_id="u1", display_name="Dr Priya", role=WorkerRole.DOCTOR, **overrides
    )


def place(label: str) -> SavedPlace:
    return SavedPlace(id=label, user_id="u1", label=label, address_line="x")


class TestComputation:
    def test_no_profile_is_zero(self):
        assert compute_completion(None, None, []).percent == 0

    def test_an_individual_with_nothing_optional_filled(self):
        result = compute_completion(
            profile(),
            WorkplaceMembership(user_id="u1", mode=WorkplaceMode.INDIVIDUAL),
            [place("Clinic")],
        )

        assert result.percent == 0
        assert result.missing == ["Add an email address", "Save a second place"]

    def test_an_individual_can_reach_one_hundred(self):
        """Nothing counted may depend on an organisation approving anything."""
        result = compute_completion(
            profile(email="a@example.com"),
            WorkplaceMembership(user_id="u1", mode=WorkplaceMode.INDIVIDUAL),
            [place("Clinic"), place("Home")],
        )

        assert result.percent == 100
        assert result.is_complete
        assert result.missing == []

    def test_employee_id_is_asked_of_joiners_only(self):
        membership = WorkplaceMembership(
            user_id="u1", mode=WorkplaceMode.JOIN_ORGANISATION
        )

        joined = compute_completion(profile(), membership, [])
        individual = compute_completion(
            profile(), WorkplaceMembership(user_id="u1", mode=WorkplaceMode.INDIVIDUAL), []
        )

        assert "Add your employee ID" in joined.missing
        assert "Add your employee ID" not in individual.missing

    def test_a_joiner_reaches_one_hundred_with_all_three(self):
        result = compute_completion(
            profile(email="a@example.com"),
            WorkplaceMembership(
                user_id="u1",
                mode=WorkplaceMode.JOIN_ORGANISATION,
                employee_id="E-1042",
            ),
            [place("Clinic"), place("Home")],
        )

        assert result.percent == 100

    @pytest.mark.parametrize(
        "email, places, expected",
        [("", 1, 0), ("a@x.com", 1, 50), ("", 2, 50), ("a@x.com", 2, 100)],
    )
    def test_percentage_steps(self, email, places, expected):
        result = compute_completion(
            profile(email=email),
            WorkplaceMembership(user_id="u1", mode=WorkplaceMode.INDIVIDUAL),
            [place(str(i)) for i in range(places)],
        )

        assert result.percent == expected

    def test_blank_email_does_not_count(self):
        result = compute_completion(
            profile(email="   "),
            WorkplaceMembership(user_id="u1", mode=WorkplaceMode.INDIVIDUAL),
            [],
        )

        assert "Add an email address" in result.missing


class TestThroughTheApi:
    @pytest.fixture
    def token(self, client) -> str:
        token = sign_in(client)
        client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))
        client.put("/onboarding/workplace", json=JOIN, headers=auth(token))
        return token

    def test_the_snapshot_carries_the_completion(self, client, token):
        body = client.get("/onboarding", headers=auth(token)).json()

        assert body["completion"]["percent"] == 0
        keys = {item["key"] for item in body["completion"]["items"]}
        assert keys == {"email", "second_place", "employee_id"}

    def test_filling_details_raises_the_percentage(self, client, token):
        client.put(
            "/onboarding/profile",
            json={**DOCTOR, "email": "priya@example.com"},
            headers=auth(token),
        )

        body = client.get("/onboarding", headers=auth(token)).json()
        assert body["completion"]["percent"] == 33

    def test_an_edit_does_not_re_drive_onboarding(self, client, token):
        """Saving a detail later must not rewind the flow to step 3."""
        client.post("/onboarding/permissions-seen", headers=auth(token))
        client.post("/onboarding/complete", headers=auth(token))

        client.put(
            "/onboarding/profile?advance=false",
            json={**DOCTOR, "email": "priya@example.com"},
            headers=auth(token),
        )

        state = client.get("/onboarding", headers=auth(token)).json()["state"]
        assert state["is_complete"] is True
        assert state["current_step"] == "done"

    def test_a_user_with_no_profile_reads_zero(self, client):
        token = sign_in(client, "917777777777")

        body = client.get("/onboarding", headers=auth(token)).json()

        assert body["completion"]["percent"] == 0
        assert body["profile"] is None
