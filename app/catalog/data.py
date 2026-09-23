"""The option lists the onboarding pickers show.

Served from the database so a specialty can be added without an app release.
This module is the seed: the migration writes these rows, and the in-memory
repository returns them directly.
"""

from enum import StrEnum


class CatalogKind(StrEnum):
    DEGREE = "degree"
    SPECIALTY = "specialty"
    NURSING_QUALIFICATION = "nursing_qualification"
    CERTIFICATION_LEVEL = "certification_level"
    DEPARTMENT = "department"


CATALOGS: dict[CatalogKind, list[str]] = {
    CatalogKind.DEGREE: [
        "MBBS", "MD", "MS", "DNB", "DM", "MCh", "Diploma",
    ],
    CatalogKind.SPECIALTY: [
        "Emergency Medicine", "Critical care", "Cardiology", "Paediatrics",
        "Oncology", "Midwifery", "General Medicine", "General Surgery",
        "Orthopaedics", "Anaesthesiology", "Obstetrics and Gynaecology",
        "Radiology", "Psychiatry", "Dermatology",
    ],
    CatalogKind.NURSING_QUALIFICATION: [
        "GNM", "ANM", "B.Sc Nursing", "Post-basic B.Sc", "M.Sc Nursing",
    ],
    CatalogKind.CERTIFICATION_LEVEL: [
        "EMT-Basic", "Advanced EMT", "Paramedic",
    ],
    CatalogKind.DEPARTMENT: [
        "Emergency Department", "Intensive Care Unit", "Operation Theatre",
        "Outpatient Department", "Inpatient Ward", "Maternity", "Paediatrics",
        "Radiology", "Laboratory", "Pharmacy", "Reception", "Security",
    ],
}
