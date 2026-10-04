"""What the directory answers. No contact or licence fields exist here, by design."""

from pydantic import BaseModel


class SearchItemOut(BaseModel):
    user_id: str
    name: str
    role: str
    specialties: list[str]
    organisation: str | None
    nearest_place: str | None
    distance_km: float | None
    is_you: bool


class SearchPageOut(BaseModel):
    items: list[SearchItemOut]
    next_cursor: str | None


class PracticeLocationOut(BaseModel):
    label: str
    address_line: str
    lat: float
    lng: float
    distance_km: float | None


class PersonOut(BaseModel):
    user_id: str
    name: str
    role: str
    about: str | None
    tags: list[str]
    degrees: list[str]
    specialties: list[str]
    nursing_qualifications: list[str]
    certification_level: str | None
    role_description: str | None
    organisation: str | None
    department: str | None
    practice_locations: list[PracticeLocationOut]
    # Nothing in a profile is checked; the app says so.
    is_verified: bool = False
    is_you: bool
