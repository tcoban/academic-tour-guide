from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import asin, cos, inf, radians, sin, sqrt
from typing import Any

from app.models.entities import OpenSeminarWindow, Researcher, TripCluster


ZURICH_CITY = "Zurich"
ZURICH_COORDINATES = (47.3769, 8.5417)

CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "barcelona": (41.3851, 2.1734),
    "basel": (47.5596, 7.5886),
    "bocconi": (45.4507, 9.1899),
    "bonn": (50.7374, 7.0982),
    "boston": (42.3601, -71.0589),
    "cambridge, ma": (42.3736, -71.1097),
    "florence": (43.7696, 11.2558),
    "frankfurt": (50.1109, 8.6821),
    "london": (51.5072, -0.1276),
    "madrid": (40.4168, -3.7038),
    "mannheim": (49.4875, 8.4660),
    "milan": (45.4642, 9.1900),
    "munich": (48.1351, 11.5820),
    "new haven": (41.3083, -72.9279),
    "new york": (40.7128, -74.0060),
    "oxford": (51.7520, -1.2577),
    "paris": (48.8566, 2.3522),
    "princeton": (40.3573, -74.6672),
    "toulouse": (43.6047, 1.4442),
    "zurich": ZURICH_COORDINATES,
}

HOME_CITY_HINTS: dict[str, str] = {
    "bocconi": "Milan",
    "boston": "Boston",
    "boston university": "Boston",
    "columbia": "New York",
    "eth": "Zurich",
    "goethe": "Frankfurt",
    "harvard": "Boston",
    "lmu": "Munich",
    "ludwig maximilians": "Munich",
    "ludwig-maximilians": "Munich",
    "mannheim": "Mannheim",
    "mit": "Boston",
    "munich": "Munich",
    "new york university": "New York",
    "nyu": "New York",
    "princeton": "Princeton",
    "university of bonn": "Bonn",
    "university of zurich": "Zurich",
    "uzh": "Zurich",
    "yale": "New Haven",
}

TRANSATLANTIC_HOME_HINTS = {
    "boston",
    "cambridge",
    "columbia",
    "harvard",
    "mit",
    "new haven",
    "new york",
    "new york university",
    "nyu",
    "princeton",
    "united states",
    "usa",
    "yale",
}


@dataclass(slots=True)
class OrderedStop:
    city: str
    starts_at: datetime
    title: str | None = None
    source_name: str | None = None
    coordinates: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "starts_at": self.starts_at.isoformat(),
            "title": self.title,
            "source_name": self.source_name,
        }


@dataclass(slots=True)
class TravelFitAssessment:
    score: int
    label: str
    severity: str
    summary: str
    rationale: list[str]
    warnings: list[str]
    home_city: str | None = None
    previous_stop: dict[str, Any] | None = None
    next_stop: dict[str, Any] | None = None
    rest_days_after_previous: int | None = None
    rest_days_before_next: int | None = None
    route_detour_km: int | None = None
    route_ratio: float | None = None
    transatlantic_arrival: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TravelPlanner:
    def assess_slot(
        self,
        cluster: TripCluster,
        researcher: Researcher,
        window: OpenSeminarWindow,
    ) -> TravelFitAssessment:
        stops = self.ordered_stops(cluster)
        if not stops:
            return TravelFitAssessment(
                score=0,
                label="Itinerary review needed",
                severity="review",
                summary="No dated itinerary stops are available for route planning.",
                rationale=["Roadshow can attach the slot, but a human should verify the travel sequence."],
                warnings=["Missing itinerary dates"],
                home_city=self.home_city(researcher.home_institution),
            )

        window_start = self._comparable_datetime(window.starts_at)
        previous_stops = [stop for stop in stops if self._comparable_datetime(stop.starts_at) < window_start]
        next_stops = [stop for stop in stops if self._comparable_datetime(stop.starts_at) >= window_start]
        previous_stop = previous_stops[-1] if previous_stops else None
        next_stop = next_stops[0] if next_stops else None
        home_city = self.home_city(researcher.home_institution)
        transatlantic_arrival = self.requires_long_haul_arrival(researcher.home_institution)

        score = 0
        rationale: list[str] = []
        warnings: list[str] = []
        route_detour_km: int | None = None
        route_ratio: float | None = None
        rest_after_previous: int | None = None
        rest_before_next: int | None = None

        if previous_stop and next_stop:
            rest_after_previous = (window_start.date() - previous_stop.starts_at.date()).days
            rest_before_next = (next_stop.starts_at.date() - window_start.date()).days
            score += 12
            rationale.append(f"Zurich sits between {previous_stop.city} and {next_stop.city} in the known route order.")

            detour = self._detour_via_zurich(previous_stop.city, next_stop.city)
            if detour:
                route_detour_km = round(detour["detour_km"])
                route_ratio = round(detour["ratio"], 2)
                if detour["detour_km"] <= 150 or detour["ratio"] <= 1.35:
                    score += 24
                    rationale.append(
                        f"Zurich is a low-detour bridge between {previous_stop.city} and {next_stop.city} "
                        f"(about {route_detour_km} km detour)."
                    )
                elif detour["detour_km"] <= 300 or detour["ratio"] <= 1.65:
                    score += 10
                    rationale.append(
                        f"Zurich is a plausible detour between {previous_stop.city} and {next_stop.city}, but the route should be checked."
                    )
                else:
                    score -= 18
                    warnings.append(
                        f"Zurich creates a large detour between {previous_stop.city} and {next_stop.city}."
                    )

            if rest_after_previous >= 1 and rest_before_next >= 1:
                score += 16
                rationale.append(
                    f"The slot leaves {rest_after_previous} day(s) after {previous_stop.city} and "
                    f"{rest_before_next} day(s) before {next_stop.city}."
                )
            elif rest_after_previous == 0 or rest_before_next == 0:
                score -= 24
                warnings.append("The slot creates same-day lecture or same-day transfer pressure.")
            else:
                score -= 8
                warnings.append("The slot has a tight rest buffer around adjacent stops.")

            if len(stops) >= 3:
                score += 4
                rationale.append("The tour already has multiple stops, so preserving route order is prioritized.")

        elif next_stop:
            rest_before_next = (next_stop.starts_at.date() - window_start.date()).days
            if transatlantic_arrival:
                if rest_before_next <= 1:
                    score -= 36
                    warnings.append(
                        f"The slot is {rest_before_next} day(s) before {next_stop.city} after a likely long-haul arrival."
                    )
                    rationale.append("Roadshow avoids asking speakers to fly long-haul, lecture, and transfer again immediately.")
                elif rest_before_next == 2:
                    score -= 8
                    warnings.append("The slot gives only a limited rest buffer after a likely long-haul arrival.")
                else:
                    score += 8
                    rationale.append("The slot gives a usable rest buffer before the first known European stop.")
            else:
                score += 6
                rationale.append(f"Zurich is before the first known stop in {next_stop.city}.")

            if self._distance_to_zurich(next_stop.city) <= 500:
                score += 6
                rationale.append(f"{next_stop.city} is close enough for a rail-style Zurich add-on.")

            if len(stops) >= 2:
                score -= 10
                warnings.append("This would add Zurich as a front-loaded extra stop rather than an in-route bridge.")

        elif previous_stop:
            rest_after_previous = (window_start.date() - previous_stop.starts_at.date()).days
            if rest_after_previous == 0:
                score -= 24
                warnings.append(f"The slot is on the same day as the known {previous_stop.city} stop.")
            elif rest_after_previous == 1:
                score += 10
                warnings.append("The slot is directly after a known stop; check whether travel and rest are realistic.")
            else:
                score += 10
                rationale.append(f"The slot leaves {rest_after_previous} day(s) after the {previous_stop.city} stop.")

            if transatlantic_arrival:
                score += 6
                rationale.append("As an end-of-trip Zurich stop, this avoids front-loading a lecture immediately after arrival from North America.")

            if self._distance_to_zurich(previous_stop.city) <= 500:
                score += 6
                rationale.append(f"{previous_stop.city} is close enough for a rail-style Zurich add-on.")

            if len(stops) >= 3:
                score -= 8
                warnings.append("This adds Zurich after an already multi-stop itinerary; confirm the speaker has stamina for another stop.")

        severity, label = self._classification(score, previous_stop, next_stop)
        summary = self._summary(
            label=label,
            previous_stop=previous_stop,
            next_stop=next_stop,
            rest_after_previous=rest_after_previous,
            rest_before_next=rest_before_next,
            warnings=warnings,
        )
        return TravelFitAssessment(
            score=score,
            label=label,
            severity=severity,
            summary=summary,
            rationale=rationale or ["No strong deterministic route signal found."],
            warnings=warnings,
            home_city=home_city,
            previous_stop=previous_stop.to_dict() if previous_stop else None,
            next_stop=next_stop.to_dict() if next_stop else None,
            rest_days_after_previous=rest_after_previous,
            rest_days_before_next=rest_before_next,
            route_detour_km=route_detour_km,
            route_ratio=route_ratio,
            transatlantic_arrival=transatlantic_arrival,
        )

    def ordered_stops(self, cluster: TripCluster) -> list[OrderedStop]:
        stops: list[OrderedStop] = []
        for item in cluster.itinerary or []:
            starts_at = self.parse_datetime(item.get("starts_at"))
            city = str(item.get("city") or "").strip()
            if not starts_at or not city:
                continue
            stops.append(
                OrderedStop(
                    city=city,
                    starts_at=starts_at,
                    title=str(item.get("title") or "") or None,
                    source_name=str(item.get("source_name") or "") or None,
                    coordinates=self.coordinates_for_city(city),
                )
            )
        return sorted(stops, key=lambda stop: self._comparable_datetime(stop.starts_at))

    def home_city(self, home_institution: str | None) -> str | None:
        lowered = (home_institution or "").strip().lower()
        if not lowered:
            return None
        for hint, city in HOME_CITY_HINTS.items():
            if hint in lowered:
                return city
        return None

    def requires_long_haul_arrival(self, home_institution: str | None) -> bool:
        lowered = (home_institution or "").strip().lower()
        return any(hint in lowered for hint in TRANSATLANTIC_HOME_HINTS)

    def coordinates_for_city(self, city: str | None) -> tuple[float, float] | None:
        lowered = (city or "").strip().lower()
        if not lowered:
            return None
        for key, coordinates in CITY_COORDINATES.items():
            if key in lowered or lowered in key:
                return coordinates
        return None

    def parse_datetime(self, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def distance_between_cities(self, from_city: str | None, to_city: str | None) -> float | None:
        from_coordinates = self.coordinates_for_city(from_city)
        to_coordinates = self.coordinates_for_city(to_city)
        if not from_coordinates or not to_coordinates:
            return None
        return haversine_km(from_coordinates[0], from_coordinates[1], to_coordinates[0], to_coordinates[1])

    def _distance_to_zurich(self, city: str) -> float:
        distance = self.distance_between_cities(city, ZURICH_CITY)
        return distance if distance is not None else inf

    def _detour_via_zurich(self, from_city: str, to_city: str) -> dict[str, float] | None:
        direct = self.distance_between_cities(from_city, to_city)
        first_leg = self.distance_between_cities(from_city, ZURICH_CITY)
        second_leg = self.distance_between_cities(ZURICH_CITY, to_city)
        if not direct or first_leg is None or second_leg is None:
            return None
        via = first_leg + second_leg
        return {
            "direct_km": direct,
            "via_zurich_km": via,
            "detour_km": max(0.0, via - direct),
            "ratio": via / direct if direct else inf,
        }

    def _classification(self, score: int, previous_stop: OrderedStop | None, next_stop: OrderedStop | None) -> tuple[str, str]:
        if score >= 40 and previous_stop and next_stop:
            return "strong", "In-route Zurich stop"
        if score >= 22:
            return "good", "Practical Zurich stop"
        if score >= 0:
            return "review", "Route review advised"
        return "risky", "Travel-rest risk"

    def _summary(
        self,
        label: str,
        previous_stop: OrderedStop | None,
        next_stop: OrderedStop | None,
        rest_after_previous: int | None,
        rest_before_next: int | None,
        warnings: list[str],
    ) -> str:
        if previous_stop and next_stop:
            return (
                f"{label}: Zurich fits between {previous_stop.city} and {next_stop.city} "
                f"with {rest_after_previous} day(s) after the prior stop and {rest_before_next} day(s) before the next stop."
            )
        if next_stop:
            base = f"{label}: Zurich is before the first known stop in {next_stop.city}."
        elif previous_stop:
            base = f"{label}: Zurich is after the known stop in {previous_stop.city}."
        else:
            base = f"{label}: route position needs manual review."
        if warnings:
            return f"{base} Main caution: {warnings[0]}"
        return base

    def _comparable_datetime(self, value: datetime) -> datetime:
        return value.replace(tzinfo=None)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_km * asin(sqrt(a))
