"""How complete a worker's profile is, as a percentage.

Onboarding already forces everything a role *requires*, so those fields are not
counted - they are true by the time anyone sees this. What is counted is the
optional detail that makes a responder's job easier, and which the person can
finish on their own. Nothing here waits on an organisation's approval, so the
ring can always be driven to 100%.
"""

from dataclasses import dataclass, field

from app.onboarding.models import SavedPlace, WorkerProfile, WorkplaceMembership, WorkplaceMode


@dataclass(frozen=True)
class CompletionItem:
    key: str
    label: str
    is_done: bool


@dataclass
class ProfileCompletion:
    percent: int
    items: list[CompletionItem] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.percent >= 100

    @property
    def missing(self) -> list[str]:
        return [item.label for item in self.items if not item.is_done]


def compute_completion(
    profile: WorkerProfile | None,
    membership: WorkplaceMembership | None,
    places: list[SavedPlace],
) -> ProfileCompletion:
    """Percentage of the optional extras that are filled in.

    No profile at all means 0% - onboarding has not started.
    """
    if profile is None:
        return ProfileCompletion(percent=0)

    items = [
        CompletionItem(
            key="email",
            label="Add an email address",
            is_done=bool((profile.email or "").strip()),
        ),
        # One place is enough to send an SOS; a second means the suggestion is
        # still right when they are not at their usual site.
        CompletionItem(
            key="second_place",
            label="Save a second place",
            is_done=len(places) >= 2,
        ),
    ]

    # Only asked of people who joined an organisation - an individual has no
    # employer to issue one, so counting it would strand them below 100%.
    if membership is not None and membership.mode is WorkplaceMode.JOIN_ORGANISATION:
        items.append(
            CompletionItem(
                key="employee_id",
                label="Add your employee ID",
                is_done=bool((membership.employee_id or "").strip()),
            )
        )

    done = sum(1 for item in items if item.is_done)
    return ProfileCompletion(
        percent=round(done / len(items) * 100) if items else 100,
        items=items,
    )
