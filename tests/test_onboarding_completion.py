"""Screens 4 and 5: permissions and finishing."""

import pytest

from tests.conftest_onboarding import DOCTOR, auth, sign_in

JOIN = {
    "mode": "join_organisation",
    "invite_code": "ECH-4X2K",
    "department": "Emergency Department",
}


@pytest.fixture
def token(client) -> str:
    token = sign_in(client)
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))
    client.put("/onboarding/workplace", json=JOIN, headers=auth(token))
    return token


def test_permissions_advance_without_granting_anything(client, token):
    """Screen 4 must never be a gate - an SOS never waits on a permission."""
    response = client.post("/onboarding/permissions-seen", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["current_step"] == "first_setup"
    assert response.json()["step_number"] == 5


def test_finishing_marks_onboarding_complete(client, token):
    client.post("/onboarding/permissions-seen", headers=auth(token))

    response = client.post("/onboarding/complete", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["is_complete"] is True
    assert response.json()["current_step"] == "done"


def test_skipping_the_practice_sos_still_completes(client, token):
    """"Skip practice for now" lands on the same endpoint as "Finish setup"."""
    response = client.post("/onboarding/complete", headers=auth(token))

    assert response.json()["is_complete"] is True


def test_a_completed_user_reads_back_as_complete(client, token):
    client.post("/onboarding/complete", headers=auth(token))

    snapshot = client.get("/onboarding", headers=auth(token)).json()

    assert snapshot["state"]["is_complete"] is True
    assert snapshot["profile"]["display_name"] == "Dr Priya Sharma"
    assert snapshot["workplace"]["status"] == "pending"


def test_completing_without_a_profile_is_refused(client):
    token = sign_in(client)

    response = client.post("/onboarding/complete", headers=auth(token))

    assert response.status_code == 409


def test_completing_without_a_workplace_choice_is_refused(client):
    token = sign_in(client)
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))

    response = client.post("/onboarding/complete", headers=auth(token))

    assert response.status_code == 422


def test_going_back_a_step_does_not_lose_progress(client, token):
    """Back navigation re-saves an earlier screen; the furthest step must stand."""
    client.post("/onboarding/permissions-seen", headers=auth(token))

    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))

    state = client.get("/onboarding", headers=auth(token)).json()["state"]
    assert state["current_step"] == "first_setup"


def test_a_returning_user_resumes_at_the_last_incomplete_step(client):
    """The server is the source of truth, so a reinstall resumes correctly."""
    token = sign_in(client)
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))

    # A second device signs in to the same account.
    again = sign_in(client)
    state = client.get("/onboarding", headers=auth(again)).json()["state"]

    assert state["current_step"] == "workplace"
    assert state["is_complete"] is False
