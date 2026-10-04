"""About and tags: the parts of a profile other workers read and search."""

import pytest

from tests.conftest_onboarding import DOCTOR, auth, sign_in


@pytest.fixture
def token(client) -> str:
    return sign_in(client)


def save(client, token, **extra):
    return client.put(
        "/onboarding/profile?advance=false", json={**DOCTOR, **extra}, headers=auth(token)
    )


def test_about_and_tags_are_saved_trimmed_and_returned(client, token):
    response = save(client, token, about="  Emergency physician.  ", tags=[" trauma ", "ACLS instructor"])

    assert response.status_code == 200, response.text
    assert response.json()["about"] == "Emergency physician."
    assert response.json()["tags"] == ["trauma", "ACLS instructor"]


def test_duplicate_tags_ignoring_case_and_blank_tags_are_dropped(client, token):
    response = save(client, token, tags=["Trauma", "trauma", "  ", "TRAUMA", "Telugu"])

    assert response.json()["tags"] == ["Trauma", "Telugu"]


def test_a_blank_about_is_stored_as_none(client, token):
    assert save(client, token, about="   ").json()["about"] is None


@pytest.mark.parametrize(
    "extra",
    [
        {"about": "x" * 501},
        {"tags": [f"t{i}" for i in range(11)]},
        {"tags": ["x" * 31]},
    ],
    ids=["about-too-long", "eleven-tags", "tag-too-long"],
)
def test_extras_beyond_the_limits_are_refused(client, token, extra):
    response = save(client, token, **extra)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_profile"


def test_exactly_the_limits_are_accepted(client, token):
    response = save(client, token, about="x" * 500, tags=[f"tag{i}" for i in range(10)])

    assert response.status_code == 200


def test_extras_do_not_change_the_completion_percentage(client, token):
    save(client, token)
    before = client.get("/onboarding", headers=auth(token)).json()["completion"]["percent"]
    save(client, token, about="Hello", tags=["trauma"])

    after = client.get("/onboarding", headers=auth(token)).json()["completion"]["percent"]

    assert after == before
