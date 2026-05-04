from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import TravelPriceCheck, TourLeg
from app.services.scoring import DEFAULT_COORDINATES, haversine_km


CITY_COORDINATES: dict[str, tuple[float, float]] = {
    **DEFAULT_COORDINATES,
    "basel": (47.5596, 7.5886),
    "bern": (46.9480, 7.4474),
    "bonn": (50.7374, 7.0982),
    "frankfurt": (50.1109, 8.6821),
    "geneva": (46.2044, 6.1432),
    "lausanne": (46.5197, 6.6323),
    "lucerne": (47.0502, 8.3093),
    "lugano": (46.0037, 8.9511),
    "milan": (45.4642, 9.1900),
    "munich": (48.1351, 11.5820),
    "st. gallen": (47.4245, 9.3767),
    "winterthur": (47.4988, 8.7237),
    "zurich": (47.3769, 8.5417),
}
SWISS_CITIES = {"basel", "bern", "geneva", "lausanne", "lucerne", "lugano", "st. gallen", "winterthur", "zurich"}
SBB_SOURCE_URL = "https://www.sbb.ch/en"
RAIL_EUROPE_SOURCE_URL = "https://www.raileurope.com/"
OPENTRANSPORTDATA_OJP_FARE_URL = "https://api.opentransportdata.swiss/ojpfare"


@dataclass(slots=True)
class PriceQuoteRequest:
    origin_city: str
    destination_city: str
    departure_at: datetime | None = None
    travel_class: str = "first"
    fare_policy: str = "full_fare"
    tour_leg_id: str | None = None
    force_refresh: bool = False
    ojp_trip_context: dict[str, Any] | None = None


@dataclass(slots=True)
class PriceQuote:
    provider: str
    status: str
    origin_city: str
    destination_city: str
    departure_at: datetime | None
    travel_class: str
    fare_policy: str
    amount: float | None
    currency: str
    amount_chf: int
    confidence: float
    source_url: str | None
    action_href: str | None
    raw_summary: dict[str, Any]
    error: str | None = None


class FareProvider(Protocol):
    provider_name: str

    def quote(self, request: PriceQuoteRequest) -> PriceQuote | None:
        ...


class OpenTransportDataOjpFareProvider:
    provider_name = "opentransportdata_ojp_fare"

    def quote(self, request: PriceQuoteRequest) -> PriceQuote | None:
        token = settings.opentransportdata_api_token
        if not token or not request.ojp_trip_context or not self._is_swiss_public_transport_route(request):
            return None
        payload = request.ojp_trip_context
        try:
            response = httpx.post(
                OPENTRANSPORTDATA_OJP_FARE_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            amount, currency = _extract_amount(data)
            if amount is None:
                return None
            return PriceQuote(
                provider=self.provider_name,
                status="live",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_at=request.departure_at,
                travel_class=request.travel_class,
                fare_policy=request.fare_policy,
                amount=amount,
                currency=currency,
                amount_chf=_normalize_to_chf(amount, currency),
                confidence=0.9,
                source_url="https://api-manager.opentransportdata.swiss/portal/catalogue-products/tedp_ojpfare-1",
                action_href=SBB_SOURCE_URL,
                raw_summary={"provider": self.provider_name, "response": _summarize_payload(data)},
            )
        except Exception as error:  # pragma: no cover - real provider failures are environment-dependent.
            return PriceQuote(
                provider=self.provider_name,
                status="failed",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_at=request.departure_at,
                travel_class=request.travel_class,
                fare_policy=request.fare_policy,
                amount=None,
                currency="CHF",
                amount_chf=0,
                confidence=0.0,
                source_url="https://api-manager.opentransportdata.swiss/portal/catalogue-products/tedp_ojpfare-1",
                action_href=SBB_SOURCE_URL,
                raw_summary={"provider": self.provider_name, "request": payload},
                error=str(error),
            )

    def _is_swiss_public_transport_route(self, request: PriceQuoteRequest) -> bool:
        return _city_key(request.origin_city) in SWISS_CITIES and _city_key(request.destination_city) in SWISS_CITIES


class RailEuropeEraProvider:
    provider_name = "rail_europe_era"

    def quote(self, request: PriceQuoteRequest) -> PriceQuote | None:
        token = settings.rail_europe_api_token
        base_url = settings.rail_europe_api_base_url
        if not token or not base_url:
            return None
        payload = {
            "origin": request.origin_city,
            "destination": request.destination_city,
            "departure_at": request.departure_at.isoformat() if request.departure_at else None,
            "travel_class": request.travel_class,
            "fare_policy": request.fare_policy,
            "passengers": [{"type": "adult"}],
        }
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/fare-quotes",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            amount, currency = _extract_amount(data)
            if amount is None:
                return None
            return PriceQuote(
                provider=self.provider_name,
                status="live",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_at=request.departure_at,
                travel_class=request.travel_class,
                fare_policy=request.fare_policy,
                amount=amount,
                currency=currency,
                amount_chf=_normalize_to_chf(amount, currency),
                confidence=0.85,
                source_url="https://raileurope.github.io/era-api/",
                action_href=RAIL_EUROPE_SOURCE_URL,
                raw_summary={"provider": self.provider_name, "response": _summarize_payload(data)},
            )
        except Exception as error:  # pragma: no cover - real provider failures are environment-dependent.
            return PriceQuote(
                provider=self.provider_name,
                status="failed",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_at=request.departure_at,
                travel_class=request.travel_class,
                fare_policy=request.fare_policy,
                amount=None,
                currency="CHF",
                amount_chf=0,
                confidence=0.0,
                source_url="https://raileurope.github.io/era-api/",
                action_href=RAIL_EUROPE_SOURCE_URL,
                raw_summary={"provider": self.provider_name, "request": payload},
                error=str(error),
            )


class FallbackRailEstimateProvider:
    provider_name = "fallback_first_class_estimate"

    def quote(self, request: PriceQuoteRequest) -> PriceQuote:
        distance_km = _route_distance_km(request.origin_city, request.destination_city)
        if distance_km is None:
            amount_chf = 220
            confidence = 0.25
            route_note = "No route coordinates available; using conservative manual-review floor."
        elif distance_km <= 30:
            amount_chf = 40
            confidence = 0.45
            route_note = "Short Swiss local segment, first-class policy floor applied."
        elif distance_km <= 500:
            amount_chf = _round_to_nearest_10(max(100, 95 + distance_km * 0.35))
            confidence = 0.45
            route_note = "Conservative first-class rail estimate for a regional European segment."
        elif distance_km <= 900:
            amount_chf = _round_to_nearest_10(max(180, 130 + distance_km * 0.45))
            confidence = 0.4
            route_note = "Longer rail estimate; manual fare review recommended."
        else:
            amount_chf = _round_to_nearest_10(260 + distance_km * 0.3)
            confidence = 0.3
            route_note = "Very long segment; verify mode and fare manually."
        source_url = SBB_SOURCE_URL if _route_touches_swiss_city(request) else RAIL_EUROPE_SOURCE_URL
        return PriceQuote(
            provider=self.provider_name,
            status="estimate_requires_review",
            origin_city=request.origin_city,
            destination_city=request.destination_city,
            departure_at=request.departure_at,
            travel_class=request.travel_class,
            fare_policy=request.fare_policy,
            amount=float(amount_chf),
            currency="CHF",
            amount_chf=amount_chf,
            confidence=confidence,
            source_url=source_url,
            action_href=source_url,
            raw_summary={
                "provider": self.provider_name,
                "distance_km": round(distance_km) if distance_km is not None else None,
                "note": route_note,
                "policy": "Conservative estimate until an authorized fare API returns a quote.",
            },
        )


class TravelPriceChecker:
    def __init__(self, session: Session, providers: list[FareProvider] | None = None) -> None:
        self.session = session
        self.providers = providers or [
            OpenTransportDataOjpFareProvider(),
            RailEuropeEraProvider(),
            FallbackRailEstimateProvider(),
        ]

    def quote(self, request: PriceQuoteRequest) -> TravelPriceCheck:
        request = PriceQuoteRequest(
            origin_city=request.origin_city.strip(),
            destination_city=request.destination_city.strip(),
            departure_at=request.departure_at,
            travel_class=request.travel_class or settings.rail_class,
            fare_policy=request.fare_policy or settings.rail_fare_policy,
            tour_leg_id=request.tour_leg_id,
            force_refresh=request.force_refresh,
            ojp_trip_context=request.ojp_trip_context,
        )
        cache_key = self.cache_key(request)
        cached = None if request.force_refresh else self._cached(cache_key)
        if cached:
            if request.tour_leg_id and cached.tour_leg_id != request.tour_leg_id:
                cloned = self._clone_cached(cached, request.tour_leg_id)
                self.session.add(cloned)
                self.session.flush()
                return cloned
            return cached

        provider_errors: list[dict[str, str]] = []
        quote: PriceQuote | None = None
        for provider in self.providers:
            quote = provider.quote(request)
            if not quote:
                continue
            if quote.status == "failed":
                provider_errors.append({"provider": quote.provider, "error": quote.error or "Provider failed."})
                quote = None
                continue
            break
        if not quote:
            quote = FallbackRailEstimateProvider().quote(request)
        if provider_errors:
            quote.raw_summary = {**quote.raw_summary, "provider_errors": provider_errors}

        record = self._record_from_quote(quote, request.tour_leg_id, cache_key)
        self.session.add(record)
        self.session.flush()
        return record

    def refresh_tour_leg(self, tour_leg: TourLeg, force: bool = True) -> TourLeg:
        cost_split = dict(tour_leg.cost_split_json or {})
        components = [dict(component) for component in cost_split.get("components") or []]
        if not components:
            return tour_leg
        departure_at = _parse_datetime(cost_split.get("slot_starts_at"))
        for component in components:
            if not _is_rail_component(component):
                _mark_non_rail_component(component)
                continue
            cities = _route_cities(str(component.get("route") or ""))
            if not cities:
                _mark_unresolved_component(component)
                continue
            check = self.quote(
                PriceQuoteRequest(
                    origin_city=cities[0],
                    destination_city=cities[1],
                    departure_at=departure_at,
                    travel_class=settings.rail_class,
                    fare_policy=settings.rail_fare_policy,
                    tour_leg_id=tour_leg.id,
                    force_refresh=force,
                )
            )
            self._apply_check_to_component(component, check)

        cost_split["components"] = components
        self._recalculate_cost_split(cost_split)
        tour_leg.cost_split_json = cost_split
        tour_leg.estimated_travel_total_chf = int(cost_split.get("modeled_total_chf") or 0)
        self._sync_stop_shares(tour_leg, cost_split)
        tour_leg.updated_at = datetime.now(UTC)
        self.session.add(tour_leg)
        return tour_leg

    def cache_key(self, request: PriceQuoteRequest) -> str:
        date_key = request.departure_at.date().isoformat() if request.departure_at else "date-pending"
        normalized = "|".join(
            [
                _city_key(request.origin_city),
                _city_key(request.destination_city),
                date_key,
                request.travel_class.lower(),
                request.fare_policy.lower(),
            ]
        )
        return sha256(normalized.encode("utf-8")).hexdigest()

    def _cached(self, cache_key: str) -> TravelPriceCheck | None:
        now = datetime.now(UTC)
        return self.session.scalar(
            select(TravelPriceCheck)
            .where(
                TravelPriceCheck.cache_key == cache_key,
                TravelPriceCheck.expires_at > now,
                TravelPriceCheck.status.in_(["live", "cached", "estimate_requires_review"]),
            )
            .order_by(desc(TravelPriceCheck.fetched_at))
            .limit(1)
        )

    def _clone_cached(self, cached: TravelPriceCheck, tour_leg_id: str) -> TravelPriceCheck:
        return TravelPriceCheck(
            tour_leg_id=tour_leg_id,
            cache_key=cached.cache_key,
            origin_city=cached.origin_city,
            destination_city=cached.destination_city,
            departure_at=cached.departure_at,
            travel_class=cached.travel_class,
            fare_policy=cached.fare_policy,
            provider=cached.provider,
            status="cached",
            amount=cached.amount,
            currency=cached.currency,
            amount_chf=cached.amount_chf,
            confidence=cached.confidence,
            source_url=cached.source_url,
            action_href=cached.action_href,
            raw_summary={**dict(cached.raw_summary or {}), "cached_from_id": cached.id},
            error=cached.error,
            fetched_at=datetime.now(UTC),
            expires_at=cached.expires_at,
        )

    def _record_from_quote(self, quote: PriceQuote, tour_leg_id: str | None, cache_key: str) -> TravelPriceCheck:
        now = datetime.now(UTC)
        return TravelPriceCheck(
            tour_leg_id=tour_leg_id,
            cache_key=cache_key,
            origin_city=quote.origin_city,
            destination_city=quote.destination_city,
            departure_at=quote.departure_at,
            travel_class=quote.travel_class,
            fare_policy=quote.fare_policy,
            provider=quote.provider,
            status=quote.status,
            amount=quote.amount,
            currency=quote.currency,
            amount_chf=quote.amount_chf,
            confidence=quote.confidence,
            source_url=quote.source_url,
            action_href=quote.action_href,
            raw_summary=quote.raw_summary,
            error=quote.error,
            fetched_at=now,
            expires_at=now + timedelta(hours=settings.rail_price_cache_hours),
        )

    def _apply_check_to_component(self, component: dict[str, Any], check: TravelPriceCheck) -> None:
        component["amount_chf"] = int(check.amount_chf)
        component["price_source"] = check.source_url or check.provider
        component["price_status"] = check.status
        component["fare_class"] = check.travel_class
        component["fare_policy"] = check.fare_policy
        component["provider"] = check.provider
        component["last_checked_at"] = check.fetched_at.isoformat()
        component["price_check_id"] = check.id
        component["confidence"] = check.confidence
        component["action_href"] = check.action_href

    def _recalculate_cost_split(self, cost_split: dict[str, Any]) -> None:
        components = list(cost_split.get("components") or [])
        hospitality = sum(
            int(component.get("amount_chf") or 0)
            for component in components
            if component.get("category") == "zurich_hospitality"
        )
        kof_travel = sum(
            int(component.get("amount_chf") or 0)
            for component in components
            if component.get("payer") == "KOF" and component.get("category") != "zurich_hospitality"
        )
        partner_travel = sum(
            int(component.get("amount_chf") or 0)
            for component in components
            if component.get("payer") != "KOF" and component.get("category") != "zurich_hospitality"
        )
        cost_split["kof_hospitality_chf"] = hospitality
        cost_split["kof_travel_chf"] = kof_travel
        cost_split["kof_total_chf"] = hospitality + kof_travel
        cost_split["partner_travel_chf"] = partner_travel
        cost_split["partner_total_chf"] = partner_travel
        cost_split["modeled_total_chf"] = hospitality + kof_travel + partner_travel
        cost_split["estimated_travel_total_chf"] = cost_split["modeled_total_chf"]
        external_leg_shares: dict[str, int] = {}
        for component in components:
            if component.get("payer") == "KOF" or component.get("category") == "zurich_hospitality":
                continue
            cities = _route_cities(str(component.get("route") or ""))
            if cities:
                non_zurich = cities[0] if _city_key(cities[1]) == "zurich" else cities[1]
                external_leg_shares[_city_key(non_zurich)] = int(component.get("amount_chf") or 0)
        cost_split["external_leg_shares"] = external_leg_shares

    def _sync_stop_shares(self, tour_leg: TourLeg, cost_split: dict[str, Any]) -> None:
        external_leg_shares = {
            str(city).lower(): int(amount)
            for city, amount in dict(cost_split.get("external_leg_shares") or {}).items()
        }
        external_city = str(cost_split.get("external_city") or "").lower()
        for stop in tour_leg.stops:
            if stop.format == "kof_seminar":
                stop.travel_share_chf = int(cost_split.get("kof_total_chf") or 0)
                stop.metadata_json = {
                    **dict(stop.metadata_json or {}),
                    "hospitality_chf": int(cost_split.get("kof_hospitality_chf") or 0),
                    "travel_chf": int(cost_split.get("kof_travel_chf") or 0),
                }
                self.session.add(stop)
                continue
            city_key = str(stop.city or "").lower()
            share = external_leg_shares.get(city_key)
            if share is None and city_key == external_city:
                share = int(cost_split.get("partner_total_chf") or 0)
            if share is not None:
                stop.travel_share_chf = share
                stop.metadata_json = {
                    **dict(stop.metadata_json or {}),
                    "cost_responsibility": "external_host" if share else "not_modeled",
                }
                self.session.add(stop)


def _is_rail_component(component: dict[str, Any]) -> bool:
    if component.get("category") == "zurich_hospitality":
        return False
    mode = str(component.get("mode") or "").lower()
    if mode in {"rail", "review", ""}:
        return "->" in str(component.get("route") or "")
    return False


def _mark_non_rail_component(component: dict[str, Any]) -> None:
    if component.get("category") == "zurich_hospitality":
        component["price_source"] = "roadshow_defaults"
        component["price_status"] = "hospitality_estimate"
        component["provider"] = "kof_hospitality_defaults"
        component["component_type"] = "hospitality"
        return
    component.setdefault("price_status", "not_rail_priced")


def _mark_unresolved_component(component: dict[str, Any]) -> None:
    component["price_source"] = "manual_review"
    component["price_status"] = "estimate_requires_review"
    component["fare_class"] = settings.rail_class
    component["fare_policy"] = settings.rail_fare_policy
    component["provider"] = "manual_review"
    component["action_href"] = RAIL_EUROPE_SOURCE_URL


def _route_cities(route: str) -> tuple[str, str] | None:
    if "->" not in route:
        return None
    origin, destination = [part.strip() for part in route.split("->", 1)]
    if not origin or not destination:
        return None
    return origin, destination


def _route_distance_km(origin_city: str, destination_city: str) -> float | None:
    origin = _coordinates_for_city(origin_city)
    destination = _coordinates_for_city(destination_city)
    if not origin or not destination:
        return None
    return haversine_km(origin[0], origin[1], destination[0], destination[1])


def _coordinates_for_city(city: str) -> tuple[float, float] | None:
    lowered = _city_key(city)
    for key, coordinates in CITY_COORDINATES.items():
        if key in lowered or lowered in key:
            return coordinates
    return None


def _route_touches_swiss_city(request: PriceQuoteRequest) -> bool:
    return _city_key(request.origin_city) in SWISS_CITIES or _city_key(request.destination_city) in SWISS_CITIES


def _city_key(city: str) -> str:
    return city.strip().lower()


def _round_to_nearest_10(value: float) -> int:
    return int(round(value / 10) * 10)


def _normalize_to_chf(amount: float, currency: str) -> int:
    if currency.upper() == "CHF":
        return round(amount)
    if currency.upper() == "EUR":
        return round(amount * settings.eur_chf_rate)
    return round(amount)


def _extract_amount(payload: Any) -> tuple[float | None, str]:
    if isinstance(payload, dict):
        currency = str(payload.get("currency") or payload.get("currencyCode") or "CHF")
        for key in ("amount", "price", "total", "total_amount", "value"):
            value = payload.get(key)
            if isinstance(value, int | float):
                return float(value), currency
            if isinstance(value, dict):
                nested_amount, nested_currency = _extract_amount(value)
                if nested_amount is not None:
                    return nested_amount, nested_currency or currency
        for key in ("fare", "bestFare", "totalPrice", "price"):
            nested_amount, nested_currency = _extract_amount(payload.get(key))
            if nested_amount is not None:
                return nested_amount, nested_currency or currency
        offers = payload.get("offers") or payload.get("results") or payload.get("fares")
        if isinstance(offers, list):
            amounts = [_extract_amount(item) for item in offers]
            valid = [(amount, curr) for amount, curr in amounts if amount is not None]
            if valid:
                return min(valid, key=lambda item: item[0])[0], valid[0][1] or currency
    if isinstance(payload, list):
        valid = [_extract_amount(item) for item in payload]
        valid = [(amount, currency) for amount, currency in valid if amount is not None]
        if valid:
            return min(valid, key=lambda item: item[0])[0], valid[0][1] or "CHF"
    return None, "CHF"


def _summarize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        summary: dict[str, Any] = {}
        for key in ("id", "currency", "amount", "price", "total", "offers", "fares", "status"):
            if key in payload:
                value = payload[key]
                summary[key] = value[:3] if isinstance(value, list) else value
        return summary or {"keys": sorted(str(key) for key in payload.keys())[:20]}
    return payload


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
