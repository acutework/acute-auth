import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import (
    build_auth_service,
    build_catalog_repository,
    build_onboarding_service,
    get_auth_service,
    get_catalog_repository,
    get_onboarding_service,
)
from app.main import app

NEW_MOBILE = "918888888888"
EXISTING_MOBILE = "919999999999"  # seeded by app.users.memory.demo_users


def make_settings(**overrides) -> Settings:
    """Settings for a test, ignoring any local .env.

    Without `_env_file=None` a developer's own OTP_PROVIDER or DATABASE_URL
    would leak into the suite and change what it asserts.
    """
    defaults = {
        "jwt_secret": "test-secret",
        "otp_provider": "fake",
        "database_url": "",
        "redis_url": "",
        "places_provider": "",
        "google_places_api_key": "",
        "otp_send_limit": 100,
        "otp_verify_limit": 100,
    }
    return Settings(_env_file=None, **{**defaults, **overrides})


@pytest.fixture
def settings() -> Settings:
    """In-memory everything, with limits high enough not to trip a test."""
    return make_settings()


@pytest.fixture
def client(settings: Settings) -> TestClient:
    """The real app, with every service built fresh for this test.

    Fresh services mean no user, OTP, rate-limit, revocation or onboarding
    state leaks between tests.
    """
    auth = build_auth_service(settings)
    onboarding = build_onboarding_service(settings)
    catalog = build_catalog_repository(settings)

    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_onboarding_service] = lambda: onboarding
    app.dependency_overrides[get_catalog_repository] = lambda: catalog
    yield TestClient(app)
    app.dependency_overrides.clear()


def send_otp(client: TestClient, mobile: str) -> tuple[str, str]:
    """Request an OTP and return (request_id, code)."""
    response = client.post("/auth/otp/request", json={"mobile": mobile})
    assert response.status_code == 200, response.text
    body = response.json()
    return body["request_id"], body["debug_code"]
