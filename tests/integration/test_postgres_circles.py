"""PostgresCirclesRepository against a real database.

These cover what only a real Postgres can show: the (circle_id, mobile) unique
constraint, the foreign keys, and members disappearing with their circle.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.circles.models import (
    Circle,
    CircleInvite,
    CircleMember,
    InviteDelivery,
    MemberStatus,
)

pytestmark = pytest.mark.integration


async def add_user(engine, mobile: str) -> str:
    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO users (id, mobile, name) VALUES (:id, :mobile, :name)"),
            {"id": user_id, "mobile": mobile, "name": "T"},
        )
    return str(user_id)


async def make_circle(circles_repo, owner_id: str, name: str = "Family") -> Circle:
    return await circles_repo.create_circle(
        Circle(id="", owner_user_id=owner_id, name=name)
    )


class TestCircles:
    async def test_a_circle_round_trips(self, circles_repo, seeded_user):
        circle = await make_circle(circles_repo, seeded_user, "Ward team")

        stored = await circles_repo.get_circle(circle.id)

        assert stored.name == "Ward team"
        assert stored.owner_user_id == seeded_user
        assert stored.include_in_sos_alerts is True

    async def test_the_sos_toggle_survives_a_save(self, circles_repo, seeded_user):
        circle = await make_circle(circles_repo, seeded_user)

        circle.include_in_sos_alerts = False
        await circles_repo.save_circle(circle)

        assert (await circles_repo.get_circle(circle.id)).include_in_sos_alerts is False

    async def test_a_malformed_circle_id_is_simply_not_found(self, circles_repo):
        assert await circles_repo.get_circle("not-a-uuid") is None


class TestMembers:
    async def test_a_member_round_trips_with_its_delivery_and_status(
        self, circles_repo, seeded_user
    ):
        circle = await make_circle(circles_repo, seeded_user)

        await circles_repo.save_member(
            CircleMember(
                id="",
                circle_id=circle.id,
                mobile="918888888888",
                display_name="Asha",
                delivery=InviteDelivery.SMS,
            )
        )

        member = await circles_repo.find_member_by_mobile(circle.id, "918888888888")
        assert member.display_name == "Asha"
        assert member.status is MemberStatus.INVITED
        assert member.delivery is InviteDelivery.SMS
        assert member.user_id is None

    async def test_accepting_links_the_member_to_the_accepting_account(
        self, circles_repo, seeded_user, engine
    ):
        circle = await make_circle(circles_repo, seeded_user)
        joiner = await add_user(engine, "918888888888")
        member = await circles_repo.save_member(
            CircleMember(id="", circle_id=circle.id, mobile="918888888888")
        )

        member.user_id = joiner
        member.status = MemberStatus.ACCEPTED
        member.responded_at = datetime.now(timezone.utc)
        await circles_repo.save_member(member)

        stored = await circles_repo.get_member(circle.id, member.id)
        assert stored.user_id == joiner
        assert stored.responded_at is not None
        assert [c.id for c in await circles_repo.list_circles_for_user(joiner)] == [
            circle.id
        ]

    async def test_the_same_number_cannot_be_stored_twice_in_one_circle(
        self, circles_repo, seeded_user
    ):
        circle = await make_circle(circles_repo, seeded_user)
        await circles_repo.save_member(
            CircleMember(id="", circle_id=circle.id, mobile="918888888888")
        )

        with pytest.raises(IntegrityError):
            await circles_repo.save_member(
                CircleMember(id="", circle_id=circle.id, mobile="918888888888")
            )

    async def test_the_same_number_may_be_in_two_different_circles(
        self, circles_repo, seeded_user
    ):
        family = await make_circle(circles_repo, seeded_user, "Family")
        ward = await make_circle(circles_repo, seeded_user, "Ward team")

        for circle in (family, ward):
            await circles_repo.save_member(
                CircleMember(id="", circle_id=circle.id, mobile="918888888888")
            )

        assert len(await circles_repo.list_circles_inviting("918888888888")) == 2

    async def test_deleting_a_circle_deletes_its_members_and_invites(
        self, circles_repo, seeded_user
    ):
        circle = await make_circle(circles_repo, seeded_user)
        await circles_repo.save_member(
            CircleMember(id="", circle_id=circle.id, mobile="918888888888")
        )
        await circles_repo.create_invite(
            CircleInvite(
                id="",
                circle_id=circle.id,
                token="tok-cascade",
                created_by_user_id=seeded_user,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )

        assert await circles_repo.delete_circle(circle.id) is True

        assert await circles_repo.list_members(circle.id) == []
        assert await circles_repo.get_invite_by_token("tok-cascade") is None


class TestInvites:
    async def test_an_invite_round_trips_with_an_aware_expiry(
        self, circles_repo, seeded_user
    ):
        circle = await make_circle(circles_repo, seeded_user)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        await circles_repo.create_invite(
            CircleInvite(
                id="",
                circle_id=circle.id,
                token="tok-abc",
                created_by_user_id=seeded_user,
                expires_at=expires_at,
            )
        )

        stored = await circles_repo.get_invite_by_token("tok-abc")
        assert stored.circle_id == circle.id
        # Timezone-aware, or the service's expiry comparison would raise.
        assert stored.expires_at.tzinfo is not None
        assert stored.expires_at > datetime.now(timezone.utc)

    async def test_an_unknown_token_is_not_found(self, circles_repo):
        assert await circles_repo.get_invite_by_token("nope") is None
