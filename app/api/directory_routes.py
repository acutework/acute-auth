"""The worker directory. Any signed-in worker may search; nobody may be found by
their number, and nothing private is answered."""

from fastapi import APIRouter, Query

from app.api.directory_schemas import PersonOut, PracticeLocationOut, SearchItemOut, SearchPageOut
from app.deps import CurrentUserDep, DirectoryServiceDep

router = APIRouter(prefix="/directory", tags=["directory"])

ROLES = "^(all|doctor|nurse|paramedic|front_desk|security|other)$"


def _km(value: float | None) -> float | None:
    return float(round(value)) if value is not None else None


@router.get("/search", response_model=SearchPageOut)
async def search(
    user: CurrentUserDep,
    service: DirectoryServiceDep,
    q: str | None = Query(default=None, max_length=200),
    role: str = Query(default="doctor", pattern=ROLES),
    specialty: str | None = Query(default=None, max_length=80),
    lat: float | None = None,
    lng: float | None = None,
    radius_km: int | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> SearchPageOut:
    page = await service.search(
        text=q, role=role, specialty=specialty, lat=lat, lng=lng,
        radius_km=radius_km, cursor=cursor, limit=limit,
    )
    return SearchPageOut(
        items=[
            SearchItemOut(
                user_id=h.person.user_id,
                name=h.person.name,
                role=h.person.role.value,
                specialties=list(h.person.specialties),
                organisation=h.person.organisation,
                nearest_place=h.nearest_place,
                distance_km=_km(h.distance_km),
                is_you=h.person.user_id == user.id,
            )
            for h in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/people/{user_id}", response_model=PersonOut)
async def person(
    user_id: str,
    user: CurrentUserDep,
    service: DirectoryServiceDep,
    lat: float | None = None,
    lng: float | None = None,
) -> PersonOut:
    view = await service.person(user_id, lat=lat, lng=lng)
    p = view.person
    return PersonOut(
        user_id=p.user_id,
        name=p.name,
        role=p.role.value,
        about=p.about,
        tags=list(p.tags),
        degrees=list(p.degrees),
        specialties=list(p.specialties),
        nursing_qualifications=list(p.nursing_qualifications),
        certification_level=p.certification_level,
        role_description=p.role_description,
        organisation=p.organisation,
        department=p.department,
        practice_locations=[
            PracticeLocationOut(label=loc.label, address_line=loc.address_line, lat=loc.lat, lng=loc.lng, distance_km=_km(d))
            for loc, d in zip(p.practice_locations, view.distances)
        ],
        is_you=p.user_id == user.id,
    )
