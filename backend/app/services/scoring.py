from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Institution, OpenSeminarWindow, Researcher, TripCluster
from app.services.enrichment import best_fact


DEFAULT_COORDINATES: dict[str, tuple[float, float]] = {
    "zurich": (47.3769, 8.5417),
    "eth zurich": (47.3769, 8.5417),
    "university of zurich": (47.3744, 8.5481),
    "mannheim": (49.4875, 8.4660),
    "munich": (48.1351, 11.5820),
    "milan": (45.4642, 9.1900),
    "bocconi": (45.4507, 9.1899),
    "bonn": (50.7374, 7.0982),
    "basel": (47.5596, 7.5886),
    "frankfurt": (50.1109, 8.6821),
    "mannheim university": (49.4833, 8.4628),
}

US_KEYWORDS = {
    "mit",
    "harvard",
    "yale",
    "princeton",
    "stanford",
    "northwestern",
    "berkeley",
    "chicago",
    "columbia",
    "new york university",
    "university of california",
    "university of michigan",
    "usa",
    "united states",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_km * asin(sqrt(a))


def normalize_place(value: str) -> str:
    return value.strip().lower()


def ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=ZoneInfo(settings.default_timezone))


def is_us_institution(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(keyword in lowered for keyword in US_KEYWORDS)


@dataclass(slots=True)
class ScoreResult:
    score: int
    rationale: list[dict]


class Scorer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def score_cluster(self, cluster: TripCluster, researcher: Researcher) -> ScoreResult:
        score = 0
        rationale: list[dict] = []
        phd_fact = best_fact(researcher, "phd_institution")
        nationality_fact = best_fact(researcher, "nationality")
        phd_distance = self._distance_to_zurich(phd_fact.value) if phd_fact else None
        if phd_distance is not None and phd_distance <= 300:
            score += 30
            rationale.append({"label": "Alumni Loop", "points": 30, "detail": phd_fact.value})

        if nationality_fact and nationality_fact.value.lower() in {"german", "austrian", "swiss"} and is_us_institution(
            researcher.home_institution
        ):
            score += 25
            rationale.append({"label": "DACH Link", "points": 25, "detail": nationality_fact.value})

        itinerary_cities = {item["city"].lower() for item in cluster.itinerary}
        if "milan" in itinerary_cities or "munich" in itinerary_cities:
            score += 20
            rationale.append({"label": "Hub Proximity", "points": 20, "detail": ", ".join(sorted(itinerary_cities))})

        if self._has_dense_window(cluster):
            score += 10
            rationale.append({"label": "Travel Density", "points": 10, "detail": "Two or more appearances within 14 days"})

        if self._has_slot_fit(cluster):
            score += 15
            rationale.append({"label": "Slot Fit", "points": 15, "detail": "An open KOF slot overlaps the trip window"})

        cluster.opportunity_score = score
        cluster.rationale = rationale
        self.session.add(cluster)
        return ScoreResult(score=score, rationale=rationale)

    def score_all_clusters(self) -> list[TripCluster]:
        clusters = self.session.scalars(select(TripCluster)).all()
        for cluster in clusters:
            researcher = self.session.get(Researcher, cluster.researcher_id)
            if researcher:
                self.score_cluster(cluster, researcher)
        self.session.flush()
        return clusters

    def _distance_to_zurich(self, institution_name: str) -> float | None:
        coordinates = self._coordinates_for_place(institution_name)
        zurich = DEFAULT_COORDINATES["zurich"]
        if not coordinates:
            return None
        return haversine_km(coordinates[0], coordinates[1], zurich[0], zurich[1])

    def _coordinates_for_place(self, institution_name: str) -> tuple[float, float] | None:
        normalized = normalize_place(institution_name)
        institution = self.session.scalar(select(Institution).where(Institution.name.ilike(f"%{institution_name}%")))
        if institution and institution.latitude is not None and institution.longitude is not None:
            return (institution.latitude, institution.longitude)
        for key, coordinates in DEFAULT_COORDINATES.items():
            if key in normalized:
                return coordinates
        return None

    def _has_dense_window(self, cluster: TripCluster) -> bool:
        starts = [datetime.fromisoformat(item["starts_at"]) for item in cluster.itinerary]
        for index, first in enumerate(starts):
            for second in starts[index + 1 :]:
                if abs((second.date() - first.date()).days) <= settings.cluster_gap_days:
                    return True
        return False

    def _has_slot_fit(self, cluster: TripCluster) -> bool:
        cluster_start = ensure_timezone(datetime.combine(cluster.start_date, datetime.min.time(), tzinfo=starts_tz(cluster)))
        cluster_end = ensure_timezone(datetime.combine(cluster.end_date, datetime.max.time(), tzinfo=starts_tz(cluster)))
        windows = self.session.scalars(select(OpenSeminarWindow)).all()
        for window in windows:
            window_start = ensure_timezone(window.starts_at)
            window_end = ensure_timezone(window.ends_at)
            if window_start <= cluster_end + timedelta(days=settings.slot_match_buffer_days) and window_end >= cluster_start - timedelta(
                days=settings.slot_match_buffer_days
            ):
                return True
        return False


def starts_tz(cluster: TripCluster):
    if cluster.itinerary:
        first = datetime.fromisoformat(cluster.itinerary[0]["starts_at"])
        return first.tzinfo
    return None
