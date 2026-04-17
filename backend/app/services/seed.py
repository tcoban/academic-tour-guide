from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Institution


REFERENCE_INSTITUTIONS = [
    ("ETH Zurich", "Zurich", "Switzerland", 47.3769, 8.5417),
    ("University of Zurich", "Zurich", "Switzerland", 47.3744, 8.5481),
    ("University of Mannheim", "Mannheim", "Germany", 49.4875, 8.4660),
    ("LMU Munich", "Munich", "Germany", 48.1508, 11.5805),
    ("Bocconi University", "Milan", "Italy", 45.4507, 9.1899),
    ("University of Bonn", "Bonn", "Germany", 50.7374, 7.0982),
    ("ECB", "Frankfurt", "Germany", 50.1109, 8.6821),
    ("BIS", "Basel", "Switzerland", 47.5596, 7.5886),
]


def seed_reference_data(session: Session) -> None:
    for name, city, country, latitude, longitude in REFERENCE_INSTITUTIONS:
        exists = session.scalar(select(Institution).where(Institution.name == name))
        if exists:
            continue
        session.add(
            Institution(
                name=name,
                city=city,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        )
    session.flush()

