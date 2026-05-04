from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import inf

from app.models.entities import OpenSeminarWindow, Researcher, TripCluster
from app.services.scoring import DEFAULT_COORDINATES, haversine_km, is_us_institution
from app.services.travel_planning import TravelPlanner


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
    "boston": (42.3601, -71.0589),
    "florence": (43.7696, 11.2558),
    "london": (51.5072, -0.1276),
    "madrid": (40.4168, -3.7038),
    "new haven": (41.3083, -72.9279),
    "new york": (40.7128, -74.0060),
    "oxford": (51.7520, -1.2577),
    "paris": (48.8566, 2.3522),
    "princeton": (40.3573, -74.6672),
    "toulouse": (43.6047, 1.4442),
}

HOME_CITY_HINTS = {
    "boston": "Boston",
    "boston university": "Boston",
    "lmu": "Munich",
    "ludwig-maximilians": "Munich",
    "ludwig maximilians": "Munich",
    "munich": "Munich",
    "bocconi": "Milan",
    "columbia": "New York",
    "universita commerciale luigi bocconi": "Milan",
    "goethe": "Frankfurt",
    "frankfurt": "Frankfurt",
    "harvard": "Boston",
    "mannheim": "Mannheim",
    "mit": "Boston",
    "new york university": "New York",
    "nyu": "New York",
    "princeton": "Princeton",
    "bonn": "Bonn",
    "eth": "Zurich",
    "uzh": "Zurich",
    "university of zurich": "Zurich",
    "yale": "New Haven",
}

ZURICH_HOSPITALITY_DEFAULTS = {
    "hotel_chf": 220,
    "dinner_chf": 90,
    "local_transport_chf": 30,
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

    def tour_leg_cost_plan(
        self,
        cluster: TripCluster,
        researcher: Researcher,
        matching_window: OpenSeminarWindow | None = None,
    ) -> dict:
        route_fit = TravelPlanner().assess_slot(cluster, researcher, matching_window) if matching_window else None
        if route_fit and route_fit.previous_stop and route_fit.next_stop:
            return self._between_stops_cost_plan(cluster, matching_window, route_fit)

        home_city = self._home_city(researcher.home_institution)
        adjacent_stop = self._adjacent_itinerary_stop(cluster, matching_window)
        adjacent_city = str((adjacent_stop or {}).get("city") or "").strip() or None
        adjacent_host = self._host_label(adjacent_stop)
        hospitality_total = sum(ZURICH_HOSPITALITY_DEFAULTS.values())
        home_leg_cost = self._one_way_city_cost(home_city, "Zurich") if home_city else None
        partner_leg_cost = self._one_way_city_cost("Zurich", adjacent_city) if adjacent_city else None
        direction = self._zurich_stop_position(adjacent_stop, matching_window)

        if direction == "before_external":
            kof_route = f"{home_city or 'home city'} -> Zurich"
            partner_route = f"Zurich -> {adjacent_city or 'external host city'}"
        else:
            kof_route = f"Zurich -> {home_city or 'home city'}"
            partner_route = f"{adjacent_city or 'external host city'} -> Zurich"

        kof_travel = home_leg_cost if home_leg_cost is not None else int((self.estimate(cluster, researcher, matching_window) or {}).get("multi_city_incremental_chf") or 0)
        partner_travel = partner_leg_cost or 0
        kof_total = kof_travel + hospitality_total
        modeled_total = kof_total + partner_travel
        components = [
            {
                "payer": "KOF",
                "category": "home_zurich_travel",
                "route": kof_route,
                "amount_chf": kof_travel,
                "mode": self._recommended_mode_for_cities(home_city, "Zurich"),
                "responsibility": "KOF covers the leg that makes Zurich possible from/to the speaker home base.",
            },
            {
                "payer": "KOF",
                "category": "zurich_hospitality",
                "route": "Zurich stay and dinner",
                "amount_chf": hospitality_total,
                "items": ZURICH_HOSPITALITY_DEFAULTS,
                "responsibility": "KOF hosts the Zurich seminar day, including overnight stay if needed and dinner.",
            },
            {
                "payer": adjacent_host,
                "category": "zurich_external_travel",
                "route": partner_route,
                "amount_chf": partner_travel,
                "mode": self._recommended_mode_for_cities("Zurich", adjacent_city),
                "responsibility": f"{adjacent_host} covers the adjacent leg between Zurich and its stop.",
            },
        ]
        return {
            "deterministic": True,
            "source": "adjacent_leg_split",
            "home_city": home_city,
            "zurich_city": "Zurich",
            "external_city": adjacent_city,
            "external_host_label": adjacent_host,
            "zurich_stop_position": direction,
            "kof_travel_chf": kof_travel,
            "kof_hospitality_chf": hospitality_total,
            "kof_total_chf": kof_total,
            "partner_travel_chf": partner_travel,
            "partner_total_chf": partner_travel,
            "modeled_total_chf": modeled_total,
            "external_leg_shares": {adjacent_city.lower(): partner_travel} if adjacent_city else {},
            "components": components,
            "assumption_notes": [
                "Roadshow splits only the incremental logistics around the Zurich stop; it does not invent a speaker fee.",
                "KOF covers the Munich/home-base to Zurich side, plus Zurich stay and dinner.",
                "The external host covers the Zurich to external-city side of the itinerary.",
                "Amounts are deterministic screening estimates, not live fare quotes or bookings.",
            ],
            "slot_starts_at": matching_window.starts_at.isoformat() if matching_window else None,
        }

    def _between_stops_cost_plan(
        self,
        cluster: TripCluster,
        matching_window: OpenSeminarWindow | None,
        route_fit,
    ) -> dict:
        previous_stop = route_fit.previous_stop or {}
        next_stop = route_fit.next_stop or {}
        previous_city = str(previous_stop.get("city") or "").strip() or None
        next_city = str(next_stop.get("city") or "").strip() or None
        previous_host = self._host_label(previous_stop)
        next_host = self._host_label(next_stop)
        hospitality_total = sum(ZURICH_HOSPITALITY_DEFAULTS.values())
        previous_leg_cost = self._one_way_city_cost(previous_city, "Zurich") or 0
        next_leg_cost = self._one_way_city_cost("Zurich", next_city) or 0
        modeled_total = hospitality_total + previous_leg_cost + next_leg_cost
        components = [
            {
                "payer": previous_host,
                "category": "previous_external_zurich_travel",
                "route": f"{previous_city or 'previous host city'} -> Zurich",
                "amount_chf": previous_leg_cost,
                "mode": self._recommended_mode_for_cities(previous_city, "Zurich"),
                "responsibility": f"{previous_host} covers the adjacent leg from its stop into Zurich.",
            },
            {
                "payer": "KOF",
                "category": "zurich_hospitality",
                "route": "Zurich stay and dinner",
                "amount_chf": hospitality_total,
                "items": ZURICH_HOSPITALITY_DEFAULTS,
                "responsibility": "KOF hosts the Zurich seminar day, including overnight stay if needed and dinner.",
            },
            {
                "payer": next_host,
                "category": "zurich_next_external_travel",
                "route": f"Zurich -> {next_city or 'next host city'}",
                "amount_chf": next_leg_cost,
                "mode": self._recommended_mode_for_cities("Zurich", next_city),
                "responsibility": f"{next_host} covers the adjacent leg from Zurich to its stop.",
            },
        ]
        external_leg_shares = {
            city.lower(): amount
            for city, amount in [(previous_city, previous_leg_cost), (next_city, next_leg_cost)]
            if city
        }
        return {
            "deterministic": True,
            "source": "in_route_between_stops_split",
            "home_city": None,
            "zurich_city": "Zurich",
            "previous_city": previous_city,
            "external_city": next_city,
            "next_city": next_city,
            "previous_host_label": previous_host,
            "external_host_label": next_host,
            "zurich_stop_position": "between_external_stops",
            "kof_travel_chf": 0,
            "kof_hospitality_chf": hospitality_total,
            "kof_total_chf": hospitality_total,
            "previous_partner_travel_chf": previous_leg_cost,
            "partner_travel_chf": next_leg_cost,
            "partner_total_chf": previous_leg_cost + next_leg_cost,
            "modeled_total_chf": modeled_total,
            "external_leg_shares": external_leg_shares,
            "components": components,
            "route_fit": route_fit.to_dict(),
            "assumption_notes": [
                "Zurich is modeled as an in-route European stop between two known appearances, not as a replacement transatlantic arrival.",
                "KOF covers the Zurich stay and dinner; adjacent external hosts cover their own inbound/outbound Zurich legs.",
                "Amounts are deterministic screening estimates, not live fare quotes or bookings.",
            ],
            "slot_starts_at": matching_window.starts_at.isoformat() if matching_window else None,
        }

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

    def _home_city(self, home_institution: str | None) -> str | None:
        lowered = (home_institution or "").strip().lower()
        if not lowered:
            return None
        for hint, city in HOME_CITY_HINTS.items():
            if hint in lowered:
                return city
        return None

    def _adjacent_itinerary_stop(
        self,
        cluster: TripCluster,
        matching_window: OpenSeminarWindow | None,
    ) -> dict | None:
        stops = [stop for stop in cluster.itinerary if self._coordinates_for_city(str(stop.get("city") or ""))]
        if not stops:
            return None
        if not matching_window:
            nearest_city, _ = self._nearest_itinerary_city(cluster)
            return next((stop for stop in stops if str(stop.get("city") or "") == nearest_city), stops[0])

        window_start = self._comparable_datetime(matching_window.starts_at)
        parsed: list[tuple[datetime, dict]] = []
        for stop in stops:
            starts_at = self._parse_datetime(stop.get("starts_at"))
            if starts_at:
                parsed.append((self._comparable_datetime(starts_at), stop))
        if not parsed:
            return stops[0]

        after = [(starts_at, stop) for starts_at, stop in parsed if starts_at >= window_start]
        if after:
            return min(after, key=lambda item: abs((item[0] - window_start).total_seconds()))[1]
        return min(parsed, key=lambda item: abs((item[0] - window_start).total_seconds()))[1]

    def _zurich_stop_position(self, adjacent_stop: dict | None, matching_window: OpenSeminarWindow | None) -> str:
        if not adjacent_stop or not matching_window:
            return "after_external"
        starts_at = self._parse_datetime(adjacent_stop.get("starts_at"))
        if starts_at and self._comparable_datetime(starts_at) >= self._comparable_datetime(matching_window.starts_at):
            return "before_external"
        return "after_external"

    def _parse_datetime(self, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _comparable_datetime(self, value: datetime) -> datetime:
        return value.replace(tzinfo=None)

    def _host_label(self, stop: dict | None) -> str:
        if not stop:
            return "External host"
        source_name = str(stop.get("source_name") or "").strip()
        city = str(stop.get("city") or "").strip()
        if source_name:
            return f"{source_name.upper()} host" if len(source_name) <= 4 else f"{source_name.title()} host"
        return f"{city} host" if city else "External host"

    def _one_way_city_cost(self, from_city: str | None, to_city: str | None) -> int | None:
        if not from_city or not to_city:
            return None
        from_coordinates = self._coordinates_for_city(from_city)
        to_coordinates = self._coordinates_for_city(to_city)
        if not from_coordinates or not to_coordinates:
            return None
        distance_km = haversine_km(from_coordinates[0], from_coordinates[1], to_coordinates[0], to_coordinates[1])
        if distance_km <= 30:
            return 20
        if distance_km <= 500:
            return self._round_to_nearest_10(45 + distance_km * 0.22)
        return self._round_to_nearest_10(120 + distance_km * 0.13)

    def _recommended_mode_for_cities(self, from_city: str | None, to_city: str | None) -> str:
        if not from_city or not to_city:
            return "review"
        from_coordinates = self._coordinates_for_city(from_city)
        to_coordinates = self._coordinates_for_city(to_city)
        if not from_coordinates or not to_coordinates:
            return "review"
        distance_km = haversine_km(from_coordinates[0], from_coordinates[1], to_coordinates[0], to_coordinates[1])
        return self._recommended_mode(distance_km)

    def _round_to_nearest_10(self, value: float) -> int:
        return int(round(value / 10) * 10)

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
