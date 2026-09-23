"""Refresh-token revocation: what makes sign-out mean something."""

from tests.conftest import EXISTING_MOBILE, send_otp


def sign_in(client) -> dict:
    request_id, code = send_otp(client, EXISTING_MOBILE)
    return client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    ).json()


def test_logout_revokes_the_refresh_token(client):
    tokens = sign_in(client)

    assert client.post(
        "/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 204

    refused = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refused.status_code == 401
    assert refused.json()["code"] == "token_revoked"


def test_a_refresh_token_works_only_once(client):
    tokens = sign_in(client)

    first = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200

    replayed = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replayed.status_code == 401
    assert replayed.json()["code"] == "token_revoked"


def test_the_new_refresh_token_from_a_rotation_still_works(client):
    tokens = sign_in(client)

    rotated = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()

    assert client.post(
        "/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    ).status_code == 200


def test_logging_out_twice_is_refused_the_second_time(client):
    tokens = sign_in(client)
    body = {"refresh_token": tokens["refresh_token"]}

    assert client.post("/auth/logout", json=body).status_code == 204
    assert client.post("/auth/logout", json=body).status_code == 401


def test_signing_in_again_after_logout_works(client):
    tokens = sign_in(client)
    client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    fresh = sign_in(client)

    assert client.post(
        "/auth/refresh", json={"refresh_token": fresh["refresh_token"]}
    ).status_code == 200
