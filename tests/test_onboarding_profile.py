"""Screens 1 and 2: role choice and the per-role profile rules.

Every credential here is self-declared. These tests check that required fields
are present - never that anything was verified, because nothing ever is.
"""

import pytest

from tests.conftest_onboarding import DOCTOR, NURSE, auth, sign_in


@pytest.fixture
def token(client) -> str:
    return sign_in(client)


def test_a_new_user_starts_at_the_first_step(client, token):
    response = client.get("/onboarding", headers=auth(token))

    assert response.status_code == 200
    state = response.json()["state"]
    assert state["current_step"] == "role"
    assert state["step_number"] == 1
    assert state["is_complete"] is False
    assert response.json()["profile"] is None


def test_a_complete_doctor_profile_is_accepted(client, token):
    response = client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["degrees"] == ["MBBS", "MD"]
    assert body["medical_council_reg_no"] == "MCI-12345"
    # Nothing is ever verified, and the response says so explicitly.
    assert body["is_verified"] is False


def test_saving_a_profile_advances_to_the_workplace_step(client, token):
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))

    state = client.get("/onboarding", headers=auth(token)).json()["state"]

    assert state["current_step"] == "workplace"
    assert state["step_number"] == 3


@pytest.mark.parametrize(
    "missing_field, expected",
    [
        ("degrees", "degree"),
        ("specialties", "specialty"),
        ("medical_council_reg_no", "medical council"),
    ],
)
def test_a_doctor_is_blocked_without_each_required_field(
    client, token, missing_field, expected
):
    payload = {**DOCTOR}
    payload[missing_field] = [] if isinstance(payload[missing_field], list) else ""

    response = client.put("/onboarding/profile", json=payload, headers=auth(token))

    assert response.status_code == 422
    assert response.json()["code"] == "onboarding_incomplete"
    assert expected in response.json()["message"]


@pytest.mark.parametrize(
    "missing_field", ["nursing_qualifications", "specialties", "nursing_council_reg_no"]
)
def test_a_nurse_is_blocked_without_each_required_field(client, token, missing_field):
    payload = {**NURSE}
    payload[missing_field] = [] if isinstance(payload[missing_field], list) else ""

    response = client.put("/onboarding/profile", json=payload, headers=auth(token))

    assert response.status_code == 422


def test_a_paramedic_needs_a_certification_level(client, token):
    payload = {"display_name": "Ravi Kumar", "role": "paramedic"}

    assert client.put(
        "/onboarding/profile", json=payload, headers=auth(token)
    ).status_code == 422

    payload["certification_level"] = "Advanced EMT"
    assert client.put(
        "/onboarding/profile", json=payload, headers=auth(token)
    ).status_code == 200


def test_other_staff_must_describe_their_role(client, token):
    payload = {"display_name": "Sam", "role": "other"}

    assert client.put(
        "/onboarding/profile", json=payload, headers=auth(token)
    ).status_code == 422

    payload["role_description"] = "Ward attendant"
    assert client.put(
        "/onboarding/profile", json=payload, headers=auth(token)
    ).status_code == 200


@pytest.mark.parametrize("role", ["front_desk", "security"])
def test_front_desk_and_security_need_only_a_name(client, token, role):
    response = client.put(
        "/onboarding/profile",
        json={"display_name": "Kiran", "role": role},
        headers=auth(token),
    )

    assert response.status_code == 200


def test_changing_role_replaces_the_previous_answers(client, token):
    """Screen 2's "Change" link goes back to Screen 1; the old role's fields go too."""
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(token))

    client.put("/onboarding/profile", json=NURSE, headers=auth(token))

    profile = client.get("/onboarding", headers=auth(token)).json()["profile"]
    assert profile["role"] == "nurse"
    assert profile["degrees"] == []
    assert profile["medical_council_reg_no"] is None


def test_onboarding_requires_a_signed_in_user(client):
    assert client.get("/onboarding").status_code == 401
    assert client.put("/onboarding/profile", json=DOCTOR).status_code == 401
