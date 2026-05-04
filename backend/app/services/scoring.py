from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Institution, OpenSeminarWindow, Researcher, ResearcherIdentity, TripCluster
from app.services.enrichment import best_available_fact
from app.services.tenancy import get_session_tenant, tenant_scope
from app.services.travel_planning import TravelPlanner


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

KOF_RESEARCH_AREAS: dict[str, tuple[str, ...]] = {
    "Business Tendency Surveys": (
        "business tendency",
        "survey",
        "expectations",
        "sentiment",
        "leading indicator",
        "indicator",
    ),
    "Macroeconomic Forecasting and Data Science": (
        "macroeconomic",
        "macroeconomics",
        "macro",
        "forecast",
        "forecasting",
        "nowcast",
        "nowcasting",
        "business cycle",
        "inflation",
        "monetary",
        "time series",
        "macroeconometric",
        "data science",
        "statistical model",
    ),
    "Innovation Economics": (
        "innovation",
        "productivity",
        "technology",
        "structural change",
        "firm dynamics",
        "firm-level",
        "r&d",
        "patent",
        "digitalization",
    ),
    "Swiss Labour Market": (
        "labour",
        "labor",
        "employment",
        "unemployment",
        "wage",
        "wages",
        "immigration",
        "migration",
        "discrimination",
        "education gap",
        "digital labour",
        "digital labor",
        "causal inference",
        "machine learning",
        "policy evaluation",
    ),
    "KOF Lab": (
        "income",
        "wealth",
        "distribution",
        "inequality",
        "randomised controlled trial",
        "randomized controlled trial",
        "rct",
        "social policy",
        "long-term scenario",
        "trade",
        "data centre",
        "data center",
    ),
    "Applied Macroeconomics": (
        "political economy",
        "international macro",
        "international monetary",
        "monetary economics",
        "economic policy",
        "policy",
        "household",
        "firm",
        "corruption",
        "business cycle",
        "economic forecasting",
    ),
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
        self.tenant = get_session_tenant(session)

    def score_cluster(self, cluster: TripCluster, researcher: Researcher) -> ScoreResult:
        score = 0
        rationale: list[dict] = []
        uses_unreviewed_evidence = False
        phd_fact = best_available_fact(researcher, "phd_institution", tenant_id=self.tenant.id)
        nationality_fact = best_available_fact(researcher, "nationality", tenant_id=self.tenant.id)
        phd_distance = self._distance_to_host(phd_fact.value) if phd_fact else None
        if phd_distance is not None and phd_distance <= 300:
            score += 30
            rationale.append({"label": "Alumni Loop", "points": 30, "detail": self._fact_detail(phd_fact)})
            uses_unreviewed_evidence = uses_unreviewed_evidence or not phd_fact.approved

        if nationality_fact and nationality_fact.value.lower() in {"german", "austrian", "swiss"} and is_us_institution(
            researcher.home_institution
        ):
            score += 25
            rationale.append({"label": "DACH Link", "points": 25, "detail": self._fact_detail(nationality_fact)})
            uses_unreviewed_evidence = uses_unreviewed_evidence or not nationality_fact.approved

        itinerary_cities = {item["city"].lower() for item in cluster.itinerary}
        if "milan" in itinerary_cities or "munich" in itinerary_cities:
            score += 20
            rationale.append({"label": "Hub Proximity", "points": 20, "detail": ", ".join(sorted(itinerary_cities))})

        if self._has_dense_window(cluster):
            score += 10
            rationale.append({"label": "Travel Density", "points": 10, "detail": "Two or more appearances within 14 days"})

        slot_fit = self._slot_fit_signal(cluster, researcher)
        if slot_fit:
            score += 15
            rationale.append({"label": "Slot Fit", "points": 15, "detail": slot_fit.detail})

        research_fit = self._research_fit(cluster, researcher)
        if research_fit.points > 0:
            score += research_fit.points
            host_label = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
            rationale.append({"label": f"{host_label} Research Fit", "points": research_fit.points, "detail": research_fit.detail})

        superstar = self._superstar_priority(researcher)
        if superstar.points > 0:
            score += superstar.points
            rationale.append({"label": "Superstar Priority", "points": superstar.points, "detail": superstar.detail})

        if uses_unreviewed_evidence:
            rationale.append(
                {
                    "label": "Review Flag",
                    "points": 0,
                    "detail": "One or more biographic signals are still pending human approval.",
                }
            )

        cluster.opportunity_score = score
        cluster.uses_unreviewed_evidence = uses_unreviewed_evidence
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

    def _distance_to_host(self, institution_name: str) -> float | None:
        coordinates = self._coordinates_for_place(institution_name)
        host = self._host_coordinates()
        if not coordinates:
            return None
        return haversine_km(coordinates[0], coordinates[1], host[0], host[1])

    def _host_coordinates(self) -> tuple[float, float]:
        if self.tenant.latitude is not None and self.tenant.longitude is not None:
            return (self.tenant.latitude, self.tenant.longitude)
        return DEFAULT_COORDINATES["zurich"]

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

    def _slot_fit_signal(self, cluster: TripCluster, researcher: Researcher) -> "_FitSignal | None":
        cluster_start = ensure_timezone(datetime.combine(cluster.start_date, datetime.min.time(), tzinfo=starts_tz(cluster)))
        cluster_end = ensure_timezone(datetime.combine(cluster.end_date, datetime.max.time(), tzinfo=starts_tz(cluster)))
        windows = self.session.scalars(
            select(OpenSeminarWindow).where(tenant_scope(OpenSeminarWindow, self.tenant))
        ).all()
        planner = TravelPlanner()
        best_detail = ""
        best_score = -999
        for window in windows:
            window_start = ensure_timezone(window.starts_at)
            window_end = ensure_timezone(window.ends_at)
            if window_start <= cluster_end + timedelta(days=settings.slot_match_buffer_days) and window_end >= cluster_start - timedelta(
                days=settings.slot_match_buffer_days
            ):
                travel_fit = planner.assess_slot(cluster, researcher, window)
                if travel_fit.score > best_score:
                    best_score = travel_fit.score
                    best_detail = travel_fit.summary
        if best_score == -999:
            return None
        host_label = (self.tenant.branding_json or {}).get("short_name") or self.tenant.name
        return _FitSignal(points=15, detail=best_detail or f"An open {host_label} slot is close enough to the trip window.")

    def _fact_detail(self, fact) -> str:
        detail = fact.value
        if not fact.approved:
            detail += " (pending review)"
        return detail

    def _research_fit(self, cluster: TripCluster, researcher: Researcher) -> "_FitSignal":
        text = self._research_text(cluster, researcher)
        if not text:
            return _FitSignal(points=0, detail="")

        focus_terms = list((self.tenant.settings.research_focuses if self.tenant.settings else []) or [])
        focus_areas: dict[str, tuple[str, ...]] = {
            "Tenant research priorities": tuple(focus_terms),
            **KOF_RESEARCH_AREAS,
        }
        matches_by_area: dict[str, list[str]] = {}
        for area, terms in focus_areas.items():
            matched_terms = [term for term in terms if _term_matches(text, term)]
            if matched_terms:
                matches_by_area[area] = matched_terms

        if not matches_by_area:
            return _FitSignal(points=0, detail="No deterministic host topic match found.")

        unique_term_count = len({term for terms in matches_by_area.values() for term in terms})
        points = min(15, 5 + unique_term_count * 2 + max(0, len(matches_by_area) - 1))
        detail = "; ".join(
            f"{area}: {', '.join(terms[:4])}"
            for area, terms in sorted(matches_by_area.items(), key=lambda item: (-len(item[1]), item[0]))[:3]
        )
        return _FitSignal(points=points, detail=detail)

    def _research_text(self, cluster: TripCluster, researcher: Researcher) -> str:
        parts: list[str] = [researcher.name, researcher.home_institution or ""]
        for item in cluster.itinerary:
            parts.extend(
                [
                    str(item.get("title") or ""),
                    str(item.get("city") or ""),
                    str(item.get("source_name") or ""),
                ]
            )
        if researcher.speaker_profile:
            parts.extend(researcher.speaker_profile.topics or [])
            parts.append(researcher.speaker_profile.availability_notes or "")
        for fact in researcher.facts:
            if fact.fact_type in {"research_topic", "field", "home_institution"}:
                parts.append(fact.value)
        return " ".join(part for part in parts if part).lower()

    def _superstar_priority(self, researcher: Researcher) -> "_FitSignal":
        rank = self._best_repec_rank(researcher)
        percentile = self._best_repec_percentile(researcher)
        if rank is not None:
            if rank <= 25:
                return _FitSignal(points=25, detail=f"RePEc worldwide rank #{rank}")
            if rank <= 100:
                return _FitSignal(points=18, detail=f"RePEc worldwide rank #{rank}")
            if rank <= 200:
                return _FitSignal(points=12, detail=f"RePEc worldwide rank #{rank}")
        if percentile is None:
            return _FitSignal(points=0, detail="")
        if percentile <= 0.05:
            return _FitSignal(points=25, detail=f"RePEc top {percentile:.3g}%")
        if percentile <= 0.15:
            return _FitSignal(points=18, detail=f"RePEc top {percentile:.3g}%")
        if percentile <= 0.3:
            return _FitSignal(points=12, detail=f"RePEc top {percentile:.3g}%")
        if percentile <= 5:
            return _FitSignal(points=6, detail=f"RePEc top {percentile:.3g}%")
        return _FitSignal(points=0, detail="")

    def _best_repec_rank(self, researcher: Researcher) -> int | None:
        ranks: list[int] = []
        for identity in self._repec_identities(researcher):
            rank = (identity.metadata_json or {}).get("rank")
            if isinstance(rank, int):
                ranks.append(rank)
            elif isinstance(rank, str) and rank.isdigit():
                ranks.append(int(rank))
        return min(ranks) if ranks else None

    def _best_repec_percentile(self, researcher: Researcher) -> float | None:
        percentiles = [researcher.repec_rank] if researcher.repec_rank is not None else []
        percentiles.extend(
            identity.ranking_percentile
            for identity in self._repec_identities(researcher)
            if identity.ranking_percentile is not None
        )
        return min(percentiles) if percentiles else None

    def _repec_identities(self, researcher: Researcher) -> list[ResearcherIdentity]:
        return [identity for identity in researcher.identities if identity.provider == "repec"]


@dataclass(slots=True)
class _FitSignal:
    points: int
    detail: str


def _term_matches(text: str, term: str) -> bool:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text))


def starts_tz(cluster: TripCluster):
    if cluster.itinerary:
        first = datetime.fromisoformat(cluster.itinerary[0]["starts_at"])
        return first.tzinfo
    return None
