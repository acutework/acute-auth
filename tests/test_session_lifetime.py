"""Staying signed in, and the lever that ends it.

Every OTP costs an SMS, so the only things that should force a user back
through verification are their own logout and a deliberate forced sign-out.
"""

from app.core.security import TokenService, TokenType
from app.deps import get_auth_service
from app.main import app
from tests.conftest import EXISTING_MOBILE, make_settings, send_otp
from tests.conftest_onboarding import auth, sign_in


async def force_sign_out(mobile: str) -> None:
    """What an operator does for a lost phone, or a release-wide sign-out.

    In production this is one statement:
        UPDATE users SET token_version = token_version + 1;
    """
    service = app.dependency_overrides[get_auth_service]()
    user = await service._users.get_by_mobile(mobile)
    await service._users.bump_token_version(user.id)


def sign_in_tokens(client) -> dict:
    request_id, code = send_otp(client, EXISTING_MOBILE)
    return client.post(
        "/auth/otp/verify",
        json={"request_id": request_id, "mobile": EXISTING_MOBILE, "code": code},
    ).json()


class TestLifetime:
    def test_refresh_tokens_last_a_year_by_default(self):
        """Long enough that an active user never re-verifies."""
        assert make_settings().refresh_token_ttl_days == 365

    def test_refreshing_slides_the_window(self, client):
        """Each refresh issues a new year, so opening the app keeps it alive."""
        tokens = sign_in_tokens(client)
        service = TokenService(make_settings())

        rotated = client.post(
            "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()

        old = service.decode(tokens["refresh_token"], expected_type=TokenType.REFRESH)
        new = service.decode(rotated["refresh_token"], expected_type=TokenType.REFRESH)
        assert new["exp"] >= old["exp"]

    def test_a_session_survives_without_another_otp(self, client):
        """The whole point: no SMS is spent to stay signed in."""
        tokens = sign_in_tokens(client)

        for _ in range(3):
            tokens = client.post(
                "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            ).json()

        me = client.get("/auth/me", headers=auth(tokens["access_token"]))
        assert me.status_code == 200


class TestForcedSignOut:
    async def test_bumping_the_version_kills_an_access_token(self, client):
        tokens = sign_in_tokens(client)

        await force_sign_out(EXISTING_MOBILE)

        response = client.get("/auth/me", headers=auth(tokens["access_token"]))

        assert response.status_code == 401
        assert response.json()["code"] == "session_superseded"

    async def test_bumping_the_version_kills_the_refresh_token(self, client):
        tokens = sign_in_tokens(client)

        await force_sign_out(EXISTING_MOBILE)

        response = client.post(
            "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 401
        assert response.json()["code"] == "session_superseded"

    async def test_signing_in_again_after_a_forced_sign_out_works(self, client):
        sign_in_tokens(client)
        await force_sign_out(EXISTING_MOBILE)

        fresh = sign_in_tokens(client)

        assert client.get(
            "/auth/me", headers=auth(fresh["access_token"])
        ).status_code == 200

    async def test_one_user_being_signed_out_does_not_affect_another(self, client):
        other = sign_in(client, "917777777777")
        tokens = sign_in_tokens(client)

        await force_sign_out(EXISTING_MOBILE)

        assert client.get(
            "/auth/me", headers=auth(tokens["access_token"])
        ).status_code == 401
        assert client.get("/auth/me", headers=auth(other)).status_code == 200
