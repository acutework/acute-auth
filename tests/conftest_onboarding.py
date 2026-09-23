"""Shared helpers for onboarding tests."""

from fastapi.testclient import TestClient

from tests.conftest import EXISTING_MOBILE, send_otp


def sign_in(client: TestClient, mobile: str = EXISTING_MOBILE) -> str:
    """Complete the OTP flow and return an access token."""
    request_id, code = send_otp(client, mobile)
    body = client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": mobile, "code": code},
    ).json()

    if body["is_new_user"]:
        body = client.post(
            "/auth/register",
            json={"name": "Test User"},
            headers={"Authorization": f"Bearer {body['registration_token']}"},
        ).json()
    return body["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


DOCTOR = {
    "display_name": "Dr Priya Sharma",
    "role": "doctor",
    "degrees": ["MBBS", "MD"],
    "specialties": ["Emergency Medicine"],
    "medical_council_reg_no": "MCI-12345",
}

NURSE = {
    "display_name": "Anjali Rao",
    "role": "nurse",
    "nursing_qualifications": ["B.Sc Nursing"],
    "specialties": ["Critical care"],
    "nursing_council_reg_no": "INC-9988",
}
