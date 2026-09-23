"""Importing this package registers every table on ``Base.metadata``.

Alembic's env.py imports it, so a new model only needs a line here to be
picked up by autogenerate.
"""

from app.models.onboarding import (  # noqa: F401
    CatalogItemRow,
    OnboardingStateRow,
    SavedPlaceRow,
    WorkerProfileRow,
    WorkplaceMembershipRow,
)
from app.models.user import User  # noqa: F401
