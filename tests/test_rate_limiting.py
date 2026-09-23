"""Rate limiting is the guard that stops someone burning your SMS credits."""

import pytest

from app.deps import build_auth_service, get_auth_service
from app.main import app
from tests.conftest import EXISTING_MOBILE, make_settings, send_otp


@pytest.fixture
def strict_client():
    """Two sends and three verifies per window, so limits are quick to reach."""
    settings = make_settings(
        otp_send_limit=2,
        otp_send_window_seconds=3600,
        otp_verify_limit=3,
        otp_verify_window_seconds=900,
    )
    service = build_auth_service(settings)
    app.dependency_overrides[get_auth_service] = lambda: service
    from fastapi.testclient import TestClient

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_a_number_cannot_request_otps_without_limit(strict_client):
    for _ in range(2):
        assert strict_client.post(
            "/auth/otp/request", json={"mobile": EXISTING_MOBILE}
        ).status_code == 200

    response = strict_client.post("/auth/otp/request", json={"mobile": EXISTING_MOBILE})

    assert response.status_code == 429
    assert response.json()["code"] == "too_many_requests"


def test_resend_counts_against_the_same_send_budget(strict_client):
    request_id, _ = send_otp(strict_client, EXISTING_MOBILE)

    # One send used; a resend takes the second, the next is refused.
    body = {"request_id": request_id, "mobile": EXISTING_MOBILE, "voice": False}
    assert strict_client.post("/auth/otp/resend", json=body).status_code == 202
    assert strict_client.post("/auth/otp/resend", json=body).status_code == 429


def test_the_limit_is_per_number(strict_client):
    for _ in range(2):
        strict_client.post("/auth/otp/request", json={"mobile": EXISTING_MOBILE})

    other = strict_client.post("/auth/otp/request", json={"mobile": "917777777777"})

    assert other.status_code == 200


def test_guessing_is_capped_across_challenges(strict_client):
    """A per-challenge attempt counter can be reset by asking for a new OTP.

    The verify limit is what actually caps guessing, so it is checked before
    the OTP itself is.
    """
    request_id, _ = send_otp(strict_client, EXISTING_MOBILE)
    payload = {"request_id": request_id, "mobile": EXISTING_MOBILE, "code": "0000"}

    for _ in range(3):
        strict_client.post("/auth/otp/verify", json=payload)

    assert strict_client.post("/auth/otp/verify", json=payload).status_code == 429
