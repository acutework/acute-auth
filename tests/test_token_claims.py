"""What other services learn about a worker from their access token.

acute-core cannot read the users table, so the Feed decides who may see a post
from these claims alone.
"""

from app.core.security import TokenService, TokenType
from tests.conftest import EXISTING_MOBILE, make_settings, send_otp
from tests.conftest_onboarding import DOCTOR, NURSE, auth


def tokens_for(client) -> dict:
    request_id, code = send_otp(client, EXISTING_MOBILE)
    body = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    ).json()
    if body["is_new_user"]:
        body = client.post(
            "/auth/register",
            json={"name": "Test User"},
            headers=auth(body["registration_token"]),
        ).json()
    return body


def claims_of(token: str) -> dict:
    return TokenService(make_settings()).decode(token, expected_type=TokenType.ACCESS)


def refreshed(client, tokens: dict) -> dict:
    return client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()


def test_a_worker_without_a_profile_has_no_role_and_no_specialties(client):
    claims = claims_of(tokens_for(client)["access_token"])

    assert claims["role"] is None
    assert claims["specialties"] == []


def test_a_refresh_after_saving_a_profile_carries_the_role_and_specialties(client):
    tokens = tokens_for(client)
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(tokens["access_token"]))

    claims = claims_of(refreshed(client, tokens)["access_token"])

    assert claims["role"] == "doctor"
    assert claims["specialties"] == ["Emergency Medicine"]


def test_a_changed_role_reaches_the_token_on_the_next_refresh(client):
    tokens = tokens_for(client)
    client.put("/onboarding/profile", json=DOCTOR, headers=auth(tokens["access_token"]))
    tokens = refreshed(client, tokens)
    client.put("/onboarding/profile", json=NURSE, headers=auth(tokens["access_token"]))

    claims = claims_of(refreshed(client, tokens)["access_token"])

    assert claims["role"] == "nurse"
    assert claims["specialties"] == ["Critical care"]


def test_signing_in_again_carries_the_saved_profile(client):
    first = tokens_for(client)
    client.put("/onboarding/profile", json=NURSE, headers=auth(first["access_token"]))

    claims = claims_of(tokens_for(client)["access_token"])

    assert claims["role"] == "nurse"
