from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    AuditEvent,
    FeedbackSignal,
    Institution,
    InstitutionProfile,
    OpenSeminarWindow,
    RelationshipBrief,
    Researcher,
    SpeakerProfile,
    TourLeg,
    TourStop,
    TripCluster,
    WishlistAlert,
    WishlistEntry,
)
from app.services.enrichment import normalize_name
from app.services.logistics import CostSharingCalculator
from app.services.opportunities import OpportunityWorkbench
from app.services.travel_prices import TravelPriceChecker


KOF_INSTITUTION_NAME = "KOF Swiss Economic Institute"


class RoadshowService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cost_sharing = CostSharingCalculator()

    def ensure_kof_institution(self) -> Institution:
        institution = self.session.scalar(select(Institution).where(Institution.name == KOF_INSTITUTION_NAME))
        if institution:
            return institution
        institution = Institution(
            name=KOF_INSTITUTION_NAME,
            city="Zurich",
            country="Switzerland",
            latitude=47.3769,
            longitude=8.5417,
            metadata_json={"tenant": "kof", "roadshow_role": "anchor_host"},
        )
        self.session.add(institution)
        self.session.flush()
        return institution

    def ensure_speaker_profile(self, researcher: Researcher) -> SpeakerProfile:
        if researcher.speaker_profile:
            return researcher.speaker_profile
        profile = SpeakerProfile(
            researcher_id=researcher.id,
            topics=[],
            travel_preferences={},
            rider={},
            communication_preferences={},
        )
        researcher.speaker_profile = profile
        self.session.add(profile)
        self.session.flush()
        return profile

    def update_speaker_profile(self, researcher: Researcher, values: dict[str, Any]) -> SpeakerProfile:
        profile = self.ensure_speaker_profile(researcher)
        for field, value in values.items():
            setattr(profile, field, value)
        profile.updated_at = datetime.now(UTC)
        self.session.add(profile)
        self.record_event(
            event_type="speaker_profile.updated",
            entity_type="speaker_profile",
            entity_id=profile.id,
            payload={"researcher_id": researcher.id, "fields": sorted(values)},
        )
        return profile

    def ensure_institution_profile(self, institution: Institution) -> InstitutionProfile:
        if institution.roadshow_profile:
            return institution.roadshow_profile
        profile = InstitutionProfile(
            institution_id=institution.id,
            wishlist_topics=[],
            coordinator_contacts=[],
        )
        institution.roadshow_profile = profile
        self.session.add(profile)
        self.session.flush()
        return profile

    def update_institution_profile(self, institution: Institution, values: dict[str, Any]) -> InstitutionProfile:
        profile = self.ensure_institution_profile(institution)
        for field, value in values.items():
            setattr(profile, field, value)
        profile.updated_at = datetime.now(UTC)
        self.session.add(profile)
        self.record_event(
            event_type="institution_profile.updated",
            entity_type="institution_profile",
            entity_id=profile.id,
            payload={"institution_id": institution.id, "fields": sorted(values)},
        )
        return profile

    def create_wishlist_entry(self, values: dict[str, Any]) -> WishlistEntry:
        entry = WishlistEntry(**values)
        self.session.add(entry)
        self.session.flush()
        self.record_event(
            event_type="wishlist_entry.created",
            entity_type="wishlist_entry",
            entity_id=entry.id,
            payload=self._wishlist_payload(entry),
        )
        self.refresh_wishlist_alerts()
        return entry

    def update_wishlist_entry(self, entry: WishlistEntry, values: dict[str, Any]) -> WishlistEntry:
        for field, value in values.items():
            setattr(entry, field, value)
        entry.updated_at = datetime.now(UTC)
        self.session.add(entry)
        self.record_event(
            event_type="wishlist_entry.updated",
            entity_type="wishlist_entry",
            entity_id=entry.id,
            payload={"fields": sorted(values), **self._wishlist_payload(entry)},
        )
        self.refresh_wishlist_alerts()
        return entry

    def delete_wishlist_entry(self, entry: WishlistEntry) -> None:
        self.record_event(
            event_type="wishlist_entry.deleted",
            entity_type="wishlist_entry",
            entity_id=entry.id,
            payload=self._wishlist_payload(entry),
        )
        self.session.delete(entry)

    def refresh_wishlist_alerts(self) -> list[WishlistAlert]:
        entries = self.session.scalars(
            select(WishlistEntry)
            .where(WishlistEntry.status == "active")
            .options(selectinload(WishlistEntry.researcher), selectinload(WishlistEntry.institution))
        ).all()
        clusters = self.session.scalars(
            select(TripCluster)
            .options(
                selectinload(TripCluster.researcher).selectinload(Researcher.speaker_profile),
                selectinload(TripCluster.researcher).selectinload(Researcher.facts),
            )
            .order_by(desc(TripCluster.opportunity_score))
        ).all()
        created: list[WishlistAlert] = []
        for entry in entries:
            for cluster in clusters:
                if not cluster.researcher:
                    continue
                reason = self._wishlist_match_reason(entry, cluster)
                if not reason:
                    continue
                existing = self.session.scalar(
                    select(WishlistAlert).where(
                        WishlistAlert.wishlist_entry_id == entry.id,
                        WishlistAlert.trip_cluster_id == cluster.id,
                    )
                )
                if existing:
                    continue
                alert = WishlistAlert(
                    wishlist_entry_id=entry.id,
                    researcher_id=cluster.researcher_id,
                    trip_cluster_id=cluster.id,
                    match_reason=reason,
                    score=min(100, int(cluster.opportunity_score) + min(20, max(0, entry.priority // 5))),
                    metadata_json={
                        "itinerary_cities": [item.get("city") for item in cluster.itinerary],
                        "institution_name": entry.institution.name if entry.institution else None,
                    },
                )
                self.session.add(alert)
                created.append(alert)
        self.session.flush()
        for alert in created:
            self.record_event(
                event_type="wishlist_alert.created",
                entity_type="wishlist_alert",
                entity_id=alert.id,
                payload={"wishlist_entry_id": alert.wishlist_entry_id, "trip_cluster_id": alert.trip_cluster_id},
            )
        return created

    def propose_tour_leg(self, cluster: TripCluster, fee_per_stop_chf: int | None = None) -> TourLeg:
        if not cluster.researcher:
            raise ValueError("Trip cluster must be linked to a researcher before a tour leg can be proposed.")

        kof = self.ensure_kof_institution()
        profile = self.ensure_speaker_profile(cluster.researcher)
        explicit_fee = profile.fee_floor_chf if profile.fee_floor_chf is not None else fee_per_stop_chf
        fee = explicit_fee or 0
        fee_source = "speaker_profile" if profile.fee_floor_chf is not None else ("request_override" if fee_per_stop_chf else "not_assumed")
        match = OpportunityWorkbench(self.session).best_window_for_cluster(cluster)
        travel_plan = self.cost_sharing.tour_leg_cost_plan(cluster, cluster.researcher, match.window if match else None)
        itinerary_stops = list(cluster.itinerary or [])
        stop_count = max(1, len(itinerary_stops) + (1 if match else 0))
        cost_split = {
            **travel_plan,
            "deterministic": True,
            "source": "negotiator_lite",
            "co_booking_stop_count": stop_count,
            "speaker_fee_chf": fee,
            "speaker_fee_source": fee_source,
            "modeled_total_travel_chf": int(travel_plan["modeled_total_chf"]),
            "per_stop_travel_share_chf": int(travel_plan["modeled_total_chf"] / stop_count) if stop_count else 0,
            "assumption_notes": [
                *travel_plan["assumption_notes"],
                "Speaker fee or honorarium is included only when it is explicitly configured on the speaker profile or request.",
                "Contracts, payments, and travel booking remain manual/off-platform in this phase.",
            ],
        }
        tour_leg = TourLeg(
            researcher_id=cluster.researcher_id,
            trip_cluster_id=cluster.id,
            title=f"{cluster.researcher.name} Roadshow leg",
            status="proposed",
            start_date=cluster.start_date,
            end_date=cluster.end_date,
            estimated_fee_total_chf=fee,
            estimated_travel_total_chf=int(travel_plan["modeled_total_chf"]),
            cost_split_json=cost_split,
            rationale=[
                {"label": "Scout cluster", "detail": "Built from scraped European appearances."},
                {
                    "label": "Adjacent-leg split",
                    "detail": self._cost_split_rationale(cost_split),
                },
            ],
        )
        self.session.add(tour_leg)
        self.session.flush()

        stop_specs: list[dict[str, Any]] = []
        external_leg_shares = {
            str(city).lower(): int(amount)
            for city, amount in dict(cost_split.get("external_leg_shares") or {}).items()
        }
        for item in itinerary_stops:
            city = str(item.get("city") or "Unknown")
            external_share = external_leg_shares.get(city.lower(), 0)
            if not external_leg_shares and city.lower() == str(cost_split.get("external_city") or "").lower():
                external_share = int(cost_split["partner_total_chf"])
            stop_specs.append(
                {
                    "starts_at": self._parse_datetime(item.get("starts_at")),
                    "stop": TourStop(
                        tour_leg_id=tour_leg.id,
                        sequence=0,
                        city=city,
                        country=item.get("country"),
                        starts_at=self._parse_datetime(item.get("starts_at")),
                        format="external_appearance",
                        fee_chf=0,
                        travel_share_chf=external_share,
                        status="known",
                        metadata_json={
                            "title": item.get("title"),
                            "source_name": item.get("source_name"),
                            "url": item.get("url"),
                            "cost_responsibility": "external_host" if external_share else "not_modeled",
                        },
                    ),
                }
            )
        if match:
            stop_specs.append(
                {
                    "starts_at": match.window.starts_at,
                    "stop": TourStop(
                        tour_leg_id=tour_leg.id,
                        institution_id=kof.id,
                        open_window_id=match.window.id,
                        sequence=0,
                        city="Zurich",
                        country="Switzerland",
                        starts_at=match.window.starts_at,
                        format="kof_seminar",
                        fee_chf=fee,
                        travel_share_chf=int(cost_split["kof_total_chf"]),
                        status="candidate",
                        metadata_json={
                            "slot_fit": match.fit_type,
                            "distance_days": match.distance_days,
                            "cost_responsibility": "kof",
                            "hospitality_chf": cost_split["kof_hospitality_chf"],
                            "travel_chf": cost_split["kof_travel_chf"],
                            "speaker_fee_source": fee_source,
                        },
                    ),
                }
            )
        stop_specs.sort(key=lambda item: self._sort_datetime(item["starts_at"]))
        stops: list[TourStop] = []
        for index, item in enumerate(stop_specs, start=1):
            stop = item["stop"]
            stop.sequence = index
            stops.append(stop)
        self.session.add_all(stops)
        self.session.flush()
        TravelPriceChecker(self.session).refresh_tour_leg(tour_leg, force=False)
        tour_leg.rationale = [
            {"label": "Scout cluster", "detail": "Built from scraped European appearances."},
            {
                "label": "Adjacent-leg split",
                "detail": self._cost_split_rationale(tour_leg.cost_split_json),
            },
        ]
        self.session.add(tour_leg)
        self.record_event(
            event_type="tour_leg.proposed",
            entity_type="tour_leg",
            entity_id=tour_leg.id,
            payload={
                "researcher_id": cluster.researcher_id,
                "trip_cluster_id": cluster.id,
                "stop_count": stop_count,
                "cost_split": tour_leg.cost_split_json,
            },
        )
        return tour_leg

    def _cost_split_rationale(self, cost_split: dict[str, Any]) -> str:
        if cost_split.get("zurich_stop_position") == "between_external_stops":
            return (
                f"Zurich is inserted between {cost_split.get('previous_city') or 'the previous stop'} and "
                f"{cost_split.get('next_city') or 'the next stop'}; KOF covers Zurich hospitality, while adjacent hosts "
                f"cover CHF {cost_split.get('partner_total_chf', 0)} modeled inbound/outbound travel."
            )
        return (
            f"KOF covers {cost_split['kof_travel_chf']} CHF travel plus Zurich hospitality; "
            f"{cost_split['external_host_label']} covers {cost_split['partner_travel_chf']} CHF adjacent travel."
        )

    def ensure_relationship_brief(self, researcher_id: str, institution_id: str) -> RelationshipBrief:
        brief = self.session.scalar(
            select(RelationshipBrief).where(
                RelationshipBrief.researcher_id == researcher_id,
                RelationshipBrief.institution_id == institution_id,
            )
        )
        if brief:
            return brief
        brief = RelationshipBrief(
            researcher_id=researcher_id,
            institution_id=institution_id,
            summary="No prior Roadshow relationship memory yet.",
            communication_preferences={},
            decision_patterns={},
            relationship_history=[],
            operational_memory={},
            forward_signals={},
        )
        self.session.add(brief)
        self.session.flush()
        return brief

    def update_relationship_brief(self, brief: RelationshipBrief, values: dict[str, Any]) -> RelationshipBrief:
        for field, value in values.items():
            setattr(brief, field, value)
        brief.updated_at = datetime.now(UTC)
        self.session.add(brief)
        self.record_event(
            event_type="relationship_brief.updated",
            entity_type="relationship_brief",
            entity_id=brief.id,
            payload={"researcher_id": brief.researcher_id, "institution_id": brief.institution_id, "fields": sorted(values)},
        )
        return brief

    def create_feedback_signal(self, values: dict[str, Any]) -> FeedbackSignal:
        signal = FeedbackSignal(**values)
        self.session.add(signal)
        self.session.flush()
        brief = self.ensure_relationship_brief(signal.researcher_id, signal.institution_id)
        history = list(brief.relationship_history or [])
        history.append(
            {
                "type": "feedback_signal",
                "party": signal.party,
                "signal_type": signal.signal_type,
                "value": signal.value,
                "created_at": signal.created_at.isoformat(),
            }
        )
        brief.relationship_history = history[-20:]
        forward_signals = dict(brief.forward_signals or {})
        forward_signals[signal.signal_type] = signal.value
        brief.forward_signals = forward_signals
        brief.updated_at = datetime.now(UTC)
        self.record_event(
            event_type="feedback_signal.created",
            entity_type="feedback_signal",
            entity_id=signal.id,
            payload={
                "researcher_id": signal.researcher_id,
                "institution_id": signal.institution_id,
                "tour_leg_id": signal.tour_leg_id,
                "signal_type": signal.signal_type,
            },
        )
        return signal

    def record_event(self, event_type: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            actor_type="system",
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        self.session.add(event)
        return event

    def _wishlist_match_reason(self, entry: WishlistEntry, cluster: TripCluster) -> str | None:
        researcher = cluster.researcher
        if not researcher:
            return None
        if entry.researcher_id and entry.researcher_id == researcher.id:
            return f"{researcher.name} is explicitly on the KOF Roadshow wishlist."
        if entry.speaker_name and normalize_name(entry.speaker_name) == researcher.normalized_name:
            return f"Speaker-name wishlist match for {entry.speaker_name}."
        if entry.topic:
            topic = entry.topic.lower()
            profile_topics = [str(item).lower() for item in (researcher.speaker_profile.topics if researcher.speaker_profile else [])]
            titles = [str(item.get("title") or "").lower() for item in cluster.itinerary]
            if any(topic in candidate or candidate in topic for candidate in profile_topics) or any(topic in title for title in titles):
                return f"Topic wishlist match for {entry.topic}."
        return None

    def _wishlist_payload(self, entry: WishlistEntry) -> dict[str, Any]:
        return {
            "institution_id": entry.institution_id,
            "researcher_id": entry.researcher_id,
            "speaker_name": entry.speaker_name,
            "topic": entry.topic,
            "priority": entry.priority,
            "status": entry.status,
        }

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _sort_datetime(self, value: datetime | None) -> datetime:
        return value.replace(tzinfo=None) if value else datetime.max
