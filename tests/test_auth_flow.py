"""End-to-end tests over the HTTP API."""

from tests.conftest import EXISTING_MOBILE, NEW_MOBILE, send_otp


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_existing_user_gets_tokens(client):
    request_id, code = send_otp(client, EXISTING_MOBILE)

    response = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is False
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["mobile"] == EXISTING_MOBILE
    assert body["registration_token"] is None


def test_new_user_gets_a_registration_token(client):
    request_id, code = send_otp(client, NEW_MOBILE)

    response = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": NEW_MOBILE, "code": code},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert body["registration_token"]
    assert body["access_token"] is None


def test_new_user_can_register_and_then_sign_in(client):
    request_id, code = send_otp(client, NEW_MOBILE)
    registration_token = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": NEW_MOBILE, "code": code},
    ).json()["registration_token"]

    response = client.post(
        "/auth/register",
        json={"name": "Asha"},
        headers={"Authorization": f"Bearer {registration_token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["name"] == "Asha"
    assert body["user"]["mobile"] == NEW_MOBILE

    # The number is now a known user, so the next OTP returns tokens directly.
    request_id, code = send_otp(client, NEW_MOBILE)
    second = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": NEW_MOBILE, "code": code},
    ).json()
    assert second["is_new_user"] is False


def test_registering_twice_is_rejected(client):
    request_id, code = send_otp(client, NEW_MOBILE)
    token = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": NEW_MOBILE, "code": code},
    ).json()["registration_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/auth/register", json={"name": "Asha"}, headers=headers)

    response = client.post("/auth/register", json={"name": "Asha"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "user_already_exists"


def test_wrong_code_is_rejected(client):
    request_id, _ = send_otp(client, EXISTING_MOBILE)

    response = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": "000000"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_otp"


def test_attempt_limit_burns_the_challenge(client):
    request_id, code = send_otp(client, EXISTING_MOBILE)
    payload = {"request_id": request_id, "mobile": EXISTING_MOBILE, "code": "000000"}

    for _ in range(2):
        assert client.post("/auth/otp/verify", json=payload).status_code == 400
    assert client.post("/auth/otp/verify", json=payload).status_code == 429

    payload["code"] = code
    assert client.post("/auth/otp/verify", json=payload).status_code == 404


def test_me_returns_the_signed_in_user(client):
    request_id, code = send_otp(client, EXISTING_MOBILE)
    access = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    ).json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})

    assert response.status_code == 200
    assert response.json()["mobile"] == EXISTING_MOBILE


def test_refresh_returns_a_new_pair(client):
    request_id, code = send_otp(client, EXISTING_MOBILE)
    refresh_token = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    ).json()["refresh_token"]

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_a_refresh_token_is_not_an_access_token(client):
    request_id, code = send_otp(client, EXISTING_MOBILE)
    refresh_token = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    ).json()["refresh_token"]

    response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )

    assert response.status_code == 401


def test_me_without_a_token_is_rejected(client):
    assert client.get("/auth/me").status_code == 401


def test_resend_is_accepted_by_a_provider_that_supports_it(client):
    request_id, _ = send_otp(client, EXISTING_MOBILE)

    response = client.post(
        "/auth/otp/resend",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "voice": True},
    )

    assert response.status_code == 202
    assert response.json() == {"sent": True}


def test_a_mobile_with_a_plus_is_normalised(client):
    """'+91...' and '91...' are the same user."""
    response = client.post("/auth/otp/request", json={"mobile": f"+{EXISTING_MOBILE}"})
    assert response.status_code == 200
    body = response.json()

    verified = client.post(
        "/auth/otp/verify",
        json={
            "request_id": body["request_id"],
            "mobile": f"+{EXISTING_MOBILE}",
            "code": body["debug_code"],
        },
    ).json()

    assert verified["is_new_user"] is False
    assert verified["user"]["mobile"] == EXISTING_MOBILE


def test_an_unusable_mobile_is_rejected(client):
    response = client.post("/auth/otp/request", json={"mobile": "0919999999999"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_mobile"
