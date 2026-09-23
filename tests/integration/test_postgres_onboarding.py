"""PostgresOnboardingRepository against a real database.

These cover what only a real Postgres can show: the foreign keys, the JSON
columns round-tripping, and coordinates surviving as floats.
"""

import pytest

from app.onboarding.models import (
    MembershipStatus,
    OnboardingState,
    OnboardingStep,
    SavedPlace,
    WorkerProfile,
    WorkerRole,
    WorkplaceMembership,
    WorkplaceMode,
)

pytestmark = pytest.mark.integration


class TestProfile:
    async def test_a_profile_round_trips_with_its_lists(
        self, onboarding_repo, seeded_user
    ):
        await onboarding_repo.save_profile(
            WorkerProfile(
                user_id=seeded_user,
                display_name="Dr Priya Sharma",
                role=WorkerRole.DOCTOR,
                degrees=["MBBS", "MD"],
                specialties=["Emergency Medicine", "Critical care"],
                medical_council_reg_no="MCI-12345",
            )
        )

        stored = await onboarding_repo.get_profile(seeded_user)

        assert stored.role is WorkerRole.DOCTOR
        assert stored.degrees == ["MBBS", "MD"]
        assert stored.specialties == ["Emergency Medicine", "Critical care"]

    async def test_saving_twice_updates_rather_than_duplicates(
        self, onboarding_repo, seeded_user
    ):
        base = WorkerProfile(
            user_id=seeded_user, display_name="A", role=WorkerRole.FRONT_DESK
        )
        await onboarding_repo.save_profile(base)

        base.display_name = "B"
        await onboarding_repo.save_profile(base)

        assert (await onboarding_repo.get_profile(seeded_user)).display_name == "B"

    async def test_an_unknown_user_has_no_profile(self, onboarding_repo):
        assert await onboarding_repo.get_profile("not-a-uuid") is None


class TestPlaces:
    async def test_coordinates_survive_the_round_trip(
        self, onboarding_repo, seeded_user
    ):
        await onboarding_repo.save_place(
            SavedPlace(
                id="",
                user_id=seeded_user,
                label="Lilavati Hospital",
                address_line="Bandra West, Mumbai",
                latitude=19.0510043,
                longitude=72.8293225,
                provider="google",
                provider_place_id="ChIJ-abc",
                is_default=True,
            )
        )

        [stored] = await onboarding_repo.list_places(seeded_user)

        assert stored.latitude == pytest.approx(19.0510043)
        assert stored.longitude == pytest.approx(72.8293225)
        assert stored.provider == "google"

    async def test_the_default_place_sorts_first(self, onboarding_repo, seeded_user):
        await onboarding_repo.save_place(
            SavedPlace(id="", user_id=seeded_user, label="A clinic", address_line="x")
        )
        await onboarding_repo.save_place(
            SavedPlace(
                id="", user_id=seeded_user, label="Z hospital",
                address_line="y", is_default=True,
            )
        )

        places = await onboarding_repo.list_places(seeded_user)

        assert places[0].label == "Z hospital"

    async def test_clearing_the_default_leaves_only_one(
        self, onboarding_repo, seeded_user
    ):
        first = await onboarding_repo.save_place(
            SavedPlace(
                id="", user_id=seeded_user, label="A",
                address_line="x", is_default=True,
            )
        )
        second = await onboarding_repo.save_place(
            SavedPlace(
                id="", user_id=seeded_user, label="B",
                address_line="y", is_default=True,
            )
        )

        await onboarding_repo.clear_default_place(seeded_user, except_id=second.id)

        places = {p.id: p for p in await onboarding_repo.list_places(seeded_user)}
        assert places[second.id].is_default is True
        assert places[first.id].is_default is False

    async def test_a_place_cannot_be_read_by_another_user(
        self, onboarding_repo, seeded_user
    ):
        place = await onboarding_repo.save_place(
            SavedPlace(id="", user_id=seeded_user, label="A", address_line="x")
        )

        import uuid

        assert await onboarding_repo.get_place(str(uuid.uuid4()), place.id) is None

    async def test_deleting_an_unknown_place_reports_false(
        self, onboarding_repo, seeded_user
    ):
        import uuid

        assert await onboarding_repo.delete_place(seeded_user, str(uuid.uuid4())) is False


class TestMembershipAndState:
    async def test_a_membership_round_trips(self, onboarding_repo, seeded_user):
        await onboarding_repo.save_membership(
            WorkplaceMembership(
                user_id=seeded_user,
                mode=WorkplaceMode.JOIN_ORGANISATION,
                status=MembershipStatus.PENDING,
                invite_code="ECH-4X2K",
                department="Emergency Department",
            )
        )

        stored = await onboarding_repo.get_membership(seeded_user)

        assert stored.mode is WorkplaceMode.JOIN_ORGANISATION
        assert stored.status is MembershipStatus.PENDING
        assert stored.invite_code == "ECH-4X2K"

    async def test_state_defaults_to_the_first_step(self, onboarding_repo, seeded_user):
        state = await onboarding_repo.get_state(seeded_user)

        assert state.current_step is OnboardingStep.ROLE
        assert state.is_complete is False

    async def test_completion_is_recorded(self, onboarding_repo, seeded_user):
        await onboarding_repo.save_state(
            OnboardingState(
                user_id=seeded_user,
                current_step=OnboardingStep.DONE,
                is_complete=True,
            )
        )

        stored = await onboarding_repo.get_state(seeded_user)

        assert stored.is_complete is True
        assert stored.current_step is OnboardingStep.DONE


class TestCatalog:
    async def test_the_migration_seeded_the_catalogs(self, engine):
        from app.catalog.repository import PostgresCatalogRepository
        from app.db.session import create_session_factory

        repo = PostgresCatalogRepository(create_session_factory(engine))

        catalogs = await repo.list_all()

        assert "MBBS" in catalogs["degree"]
        assert "Emergency Department" in catalogs["department"]
        assert "B.Sc Nursing" in catalogs["nursing_qualification"]
