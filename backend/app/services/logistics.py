from __future__ import annotations

from dataclasses import asdict, dataclass
from math import inf

from app.models.entities import OpenSeminarWindow, Researcher, TripCluster
from app.services.scoring import DEFAULT_COORDINATES, haversine_km, is_us_institution


EUROPEAN_HOME_KEYWORDS = {
    "bocconi",
    "bonn",
    "eth",
    "eui",
    "frankfurt",
    "goethe",
    "lse",
    "mannheim",
    "munich",
    "oxford",
    "paris",
    "pse",
    "toulouse",
    "university of zurich",
    "uzh",
}

EXTRA_COORDINATES = {
    "barcelona": (41.3851, 2.1734),
    "florence": (43.7696, 11.2558),
    "london": (51.5072, -0.1276),
    "madrid": (40.4168, -3.7038),
    "oxford": (51.7520, -1.2577),
    "paris": (48.8566, 2.3522),
    "toulouse": (43.6047, 1.4442),
}


@dataclass(slots=True)
class CostShareEstimate:
    baseline_round_trip_chf: int
    multi_city_incremental_chf: int
    estimated_savings_chf: int
    roi_percent: int
    nearest_itinerary_city: str
    nearest_distance_km: int
    recommended_mode: str
    recommendation: str
    assumption_notes: list[str]
    slot_starts_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class CostSharingCalculator:
    def estimate(
        self,
        cluster: TripCluster,
        researcher: Researcher,
        matching_window: OpenSeminarWindow | None = None,
    ) -> dict | None:
        nearest_city, distance_km = self._nearest_itinerary_city(cluster)
        if not nearest_city or distance_km == inf:
            return None

        baseline = self._standalone_round_trip_cost(researcher.home_institution)
        incremental = self._multi_city_incremental_cost(distance_km)
        savings = max(0, baseline - incremental)
        roi_percent = round((savings / baseline) * 100) if baseline else 0
        mode = self._recommended_mode(distance_km)
        recommendation = self._recommendation(savings, roi_percent)
        notes = [
            "Baseline estimates a standalone KOF-funded Zurich round trip from the home institution region.",
            "Multi-city estimate prices Zurich as an add-on from the closest known European itinerary city.",
            "This is a screening estimate for admin negotiation, not a fare quote.",
        ]
        if matching_window:
            notes.append("The estimate is anchored to the same KOF slot selected by the opportunity workbench.")

        return CostShareEstimate(
            baseline_round_trip_chf=baseline,
            multi_city_incremental_chf=incremental,
            estimated_savings_chf=savings,
            roi_percent=roi_percent,
            nearest_itinerary_city=nearest_city,
            nearest_distance_km=round(distance_km),
            recommended_mode=mode,
            recommendation=recommendation,
            assumption_notes=notes,
            slot_starts_at=matching_window.starts_at.isoformat() if matching_window else None,
        ).to_dict()

    def _nearest_itinerary_city(self, cluster: TripCluster) -> tuple[str | None, float]:
        nearest_city: str | None = None
        nearest_distance = inf
        zurich_lat, zurich_lon = DEFAULT_COORDINATES["zurich"]
        for stop in cluster.itinerary:
            city = str(stop.get("city") or "").strip()
            coordinates = self._coordinates_for_city(city)
            if not coordinates:
                continue
            distance = haversine_km(coordinates[0], coordinates[1], zurich_lat, zurich_lon)
            if distance < nearest_distance:
                nearest_city = city
                nearest_distance = distance
        return nearest_city, nearest_distance

    def _coordinates_for_city(self, city: str) -> tuple[float, float] | None:
        lowered = city.strip().lower()
        coordinates = {**DEFAULT_COORDINATES, **EXTRA_COORDINATES}
        for key, value in coordinates.items():
            if key in lowered or lowered in key:
                return value
        return None

    def _standalone_round_trip_cost(self, home_institution: str | None) -> int:
        if is_us_institution(home_institution):
            return 1200
        lowered = (home_institution or "").lower()
        if any(keyword in lowered for keyword in EUROPEAN_HOME_KEYWORDS):
            return 450
        return 900

    def _multi_city_incremental_cost(self, distance_km: float) -> int:
        if distance_km <= 30:
            return 40
        if distance_km <= 500:
            return round(2 * (30 + distance_km * 0.16))
        return round(2 * (110 + distance_km * 0.10))

    def _recommended_mode(self, distance_km: float) -> str:
        if distance_km <= 30:
            return "local"
        if distance_km <= 500:
            return "rail"
        return "flight"

    def _recommendation(self, savings: int, roi_percent: int) -> str:
        if savings >= 400 or roi_percent >= 50:
            return "strong"
        if savings >= 150 or roi_percent >= 25:
            return "moderate"
        return "limited"
