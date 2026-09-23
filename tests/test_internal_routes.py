"""The one question acute-core asks identity.

This endpoint exists so an invitation to someone who already has an account
goes by push instead of costing an SMS. It must stay exactly that narrow: a
boolean, behind a shared key, disclosing nothing else about the user table.
"""

from tests.conftest import EXISTING_MOBILE, make_settings
from tests.conftest_onboarding import sign_in

KEY = "internal-test-key"


def make_client(**overrides):
    from fastapi.testclient import TestClient

    from app.deps import (
        build_auth_service,
        build_catalog_repository,
        build_onboarding_service,
        get_auth_service,
        get_catalog_repository,
        get_onboarding_service,
        get_settings_dep,
    )
    from app.main import app

    settings = make_settings(**{'internal_api_key': KEY, **overrides})
    auth = build_auth_service(settings)
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_onboarding_service] = (
        lambda: build_onboarding_service(settings)
    )
    app.dependency_overrides[get_catalog_repository] = (
        lambda: build_catalog_repository(settings)
    )
    app.dependency_overrides[get_settings_dep] = lambda: settings
    return TestClient(app), auth


def teardown_function() -> None:
    from app.main import app

    app.dependency_overrides.clear()


class TestLookup:
    def test_a_registered_number_exists(self):
        client, _ = make_client()
        sign_in(client)  # registers EXISTING_MOBILE in the in-memory store

        response = client.get(
            "/internal/users/exists",
            params={"mobile": EXISTING_MOBILE},
            headers={"X-Internal-Key": KEY},
        )

        assert response.status_code == 200
        assert response.json() == {"exists": True}

    def test_an_unknown_number_does_not(self):
        client, _ = make_client()

        response = client.get(
            "/internal/users/exists",
            params={"mobile": "915555000111"},
            headers={"X-Internal-Key": KEY},
        )

        assert response.json() == {"exists": False}

    def test_a_number_is_canonicalised_before_lookup(self):
        """acute-core may pass '+91...'; the same person must be found."""
        client, _ = make_client()
        sign_in(client)

        response = client.get(
            "/internal/users/exists",
            params={"mobile": f"+{EXISTING_MOBILE}"},
            headers={"X-Internal-Key": KEY},
        )

        assert response.json() == {"exists": True}

    def test_an_unusable_number_is_answered_rather_than_erroring(self):
        client, _ = make_client()

        response = client.get(
            "/internal/users/exists",
            params={"mobile": "not-a-number"},
            headers={"X-Internal-Key": KEY},
        )

        assert response.status_code == 200
        assert response.json() == {"exists": False}

    def test_nothing_but_a_boolean_is_disclosed(self):
        """A leak here would turn an invite feature into a user-table oracle."""
        client, _ = make_client()
        sign_in(client)

        body = client.get(
            "/internal/users/exists",
            params={"mobile": EXISTING_MOBILE},
            headers={"X-Internal-Key": KEY},
        ).json()

        assert set(body) == {"exists"}


class TestAccess:
    def test_a_missing_key_is_refused(self):
        client, _ = make_client()

        response = client.get(
            "/internal/users/exists", params={"mobile": EXISTING_MOBILE}
        )

        assert response.status_code == 401
        assert response.json()["code"] == "internal_access_denied"

    def test_a_wrong_key_is_refused(self):
        client, _ = make_client()

        response = client.get(
            "/internal/users/exists",
            params={"mobile": EXISTING_MOBILE},
            headers={"X-Internal-Key": "wrong"},
        )

        assert response.status_code == 401

    def test_a_blank_configured_key_disables_the_endpoint(self):
        """A deployment that forgot to set the key fails closed, not open."""
        client, _ = make_client(internal_api_key="")

        response = client.get(
            "/internal/users/exists",
            params={"mobile": EXISTING_MOBILE},
            headers={"X-Internal-Key": ""},
        )

        assert response.status_code == 401

    def test_a_user_access_token_does_not_open_it(self):
        """This is service-to-service; a signed-in person is not a service."""
        client, _ = make_client()
        token = sign_in(client)

        response = client.get(
            "/internal/users/exists",
            params={"mobile": EXISTING_MOBILE},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 401


class TestVisibility:
    def test_it_is_absent_from_the_public_api_documentation(self):
        from app.main import app

        assert not any(
            path.startswith("/internal") for path in app.openapi()["paths"]
        )
