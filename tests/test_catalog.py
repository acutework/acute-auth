"""The option lists the pickers show."""

from tests.conftest_onboarding import auth, sign_in


def test_every_catalog_comes_back_in_one_call(client):
    response = client.get("/catalog")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "degree", "specialty", "nursing_qualification",
        "certification_level", "department",
    }
    assert "MBBS" in body["degree"]
    assert "Emergency Department" in body["department"]


def test_one_catalog_can_be_fetched_on_its_own(client):
    response = client.get("/catalog/nursing_qualification")

    assert response.status_code == 200
    assert "B.Sc Nursing" in response.json()["items"]


def test_an_unknown_catalog_kind_is_rejected(client):
    assert client.get("/catalog/hobbies").status_code == 422


def test_catalogs_are_readable_without_signing_in(client):
    """The pickers are needed during onboarding; gating them buys nothing."""
    assert client.get("/catalog").status_code == 200


def test_a_signed_in_user_sees_the_same_lists(client):
    token = sign_in(client)

    assert client.get("/catalog", headers=auth(token)).json() == client.get(
        "/catalog"
    ).json()
