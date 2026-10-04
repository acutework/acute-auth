"""What every directory repository must do. Subclass with `directory` and `seed` fixtures:
`seed(name, **kwargs)` creates a worker (see seed_person) and returns their user id."""

from app.directory.models import GeoPoint, SearchQuery
from app.onboarding.models import PlaceVisibility, WorkerRole

PRIVATE, PRACTICE = PlaceVisibility.PRIVATE, PlaceVisibility.PRACTICE
HERE = GeoPoint(17.4300, 78.4100)
# 0.0899320364 degrees of latitude is 10.0 km on the rule's sphere.
TEN_KM_NORTH = (17.5199320364, 78.4100)


def names(people) -> list[str]:
    return [p.name for p in people]


async def everyone(directory, **query) -> list:
    return await directory.search(SearchQuery(**query), offset=0, limit=50)


class DirectoryContract:
    async def test_doctors_only_by_default_and_everyone_on_request(self, directory, seed):
        await seed("Dr Rao")
        await seed("Priya Nair", role=WorkerRole.NURSE, specialties=["Critical care"])

        assert names(await everyone(directory)) == ["Dr Rao"]
        assert names(await everyone(directory, roles=None)) == ["Dr Rao", "Priya Nair"]
        assert names(await everyone(directory, roles=frozenset({WorkerRole.NURSE}))) == ["Priya Nair"]

    async def test_a_worker_mid_onboarding_is_not_listed(self, directory, seed):
        hidden = await seed("Dr Halfway", complete=False)

        assert await everyone(directory) == []
        assert await directory.get_person(hidden) is None

    async def test_text_matches_part_of_a_name_specialty_or_tag_ignoring_case(self, directory, seed):
        await seed("Dr Anjali Rao", specialties=["Emergency Medicine"])
        await seed("Dr Vikram Mehta", specialties=["Cardiology"], tags=["ACLS instructor"])
        await seed("Dr Sneha Patil", tags=["తెలుగు"])

        assert names(await everyone(directory, text="anjali")) == ["Dr Anjali Rao"]
        assert names(await everyone(directory, text="CARDI")) == ["Dr Vikram Mehta"]
        assert names(await everyone(directory, text="acls")) == ["Dr Vikram Mehta"]
        assert names(await everyone(directory, text="తెలు")) == ["Dr Sneha Patil"]

    async def test_like_wildcards_in_the_text_are_literal(self, directory, seed):
        await seed("Dr Rao")

        assert await everyone(directory, text="%") == []
        assert await everyone(directory, text="_") == []

    async def test_a_specialty_filter_is_exact(self, directory, seed):
        await seed("Dr Heart", specialties=["Cardiology", "Critical care"])
        await seed("Dr Cardio", specialties=["Cardiology Fellow"])

        assert names(await everyone(directory, specialty="Cardiology")) == ["Dr Heart"]

    async def test_location_matches_any_practice_location_and_never_a_private_one(self, directory, seed):
        await seed("Dr Near", places=[("Far clinic", 28.6, 77.2, PRACTICE), ("Ward", HERE.lat, HERE.lng, PRACTICE)])
        await seed("Dr Home", places=[("Home", HERE.lat, HERE.lng, PRIVATE)])
        await seed("Dr Nowhere")

        found = await everyone(directory, near=HERE, radius_km=5)

        assert names(found) == ["Dr Near"]

    async def test_the_radius_edge_is_inside_and_just_past_it_is_not(self, directory, seed):
        await seed("Dr Edge", places=[("Edge", *TEN_KM_NORTH, PRACTICE)])

        assert names(await everyone(directory, near=HERE, radius_km=10)) == ["Dr Edge"]
        assert await everyone(directory, near=GeoPoint(HERE.lat - 0.0001, HERE.lng), radius_km=10) == []

    async def test_results_are_by_name_or_by_distance_when_located(self, directory, seed):
        await seed("Dr Zed", places=[("Z", HERE.lat + 0.01, HERE.lng, PRACTICE)])
        await seed("Dr Amy", places=[("A", HERE.lat + 0.05, HERE.lng, PRACTICE)])

        assert names(await everyone(directory)) == ["Dr Amy", "Dr Zed"]
        assert names(await everyone(directory, near=HERE, radius_km=50)) == ["Dr Zed", "Dr Amy"]

    async def test_pages_follow_the_same_order(self, directory, seed):
        for name in ("Dr A", "Dr B", "Dr C"):
            await seed(name)

        first = await directory.search(SearchQuery(), offset=0, limit=2)
        rest = await directory.search(SearchQuery(), offset=2, limit=2)

        assert names(first) + names(rest) == ["Dr A", "Dr B", "Dr C"]

    async def test_a_person_carries_practice_locations_only_and_their_profile(self, directory, seed):
        user = await seed(
            "Dr Rao",
            specialties=["Emergency Medicine"],
            tags=["trauma"],
            about="Emergency physician.",
            organisation="Apollo Hospital",
            places=[("Apollo", HERE.lat, HERE.lng, PRACTICE), ("Home", 17.5, 78.5, PRIVATE)],
        )

        person = await directory.get_person(user)

        assert person.name == "Dr Rao" and person.about == "Emergency physician."
        assert person.tags == ("trauma",) and person.organisation == "Apollo Hospital"
        assert [p.label for p in person.practice_locations] == ["Apollo"]

    async def test_an_unknown_person_is_none(self, directory):
        assert await directory.get_person("00000000-0000-0000-0000-000000000000") is None
        assert await directory.get_person("not-a-uuid") is None
