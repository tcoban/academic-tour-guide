from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil, radians, sin, cos, asin, sqrt
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Institution,
    InstitutionProfile,
    OutreachDraft,
    Researcher,
    SpeakerProfile,
    TourAssemblyProposal,
    TourLeg,
    TourStop,
    TripCluster,
    WishlistEntry,
    WishlistMatchGroup,
    WishlistMatchParticipant,
)
from app.services.enrichment import normalize_name
from app.services.logistics import CostSharingCalculator
from app.services.opportunities import OpportunityWorkbench
from app.services.outreach import DraftGenerator, ReviewRequiredError
from app.services.roadshow import KOF_INSTITUTION_NAME, RoadshowService


DEFAULT_MATCH_RADIUS_KM = 150
DEFAULT_FEE_FLOOR_CHF = 3500
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class TourAssemblyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cost_sharing = CostSharingCalculator()

    def refresh_wishlist_matches(self, radius_km: int = DEFAULT_MATCH_RADIUS_KM) -> list[WishlistMatchGroup]:
        entries = self.session.scalars(
            select(WishlistEntry)
            .where(WishlistEntry.status == "active")
            .options(
                selectinload(WishlistEntry.institution).selectinload(Institution.roadshow_profile),
                selectinload(WishlistEntry.researcher).selectinload(Researcher.speaker_profile),
            )
        ).all()
        researchers_by_normalized = {
            researcher.normalized_name: researcher
            for researcher in self.session.scalars(select(Researcher).options(selectinload(Researcher.speaker_profile))).all()
        }
        grouped: dict[str, dict[str, Any]] = {}
        for entry in entries:
            speaker = self._speaker_key(entry, researchers_by_normalized)
            if not speaker:
                continue
            bucket = grouped.setdefault(
                speaker["match_key"],
                {
                    "researcher": speaker["researcher"],
                    "normalized_speaker_name": speaker["normalized_speaker_name"],
                    "display_speaker_name": speaker["display_speaker_name"],
                    "entries_by_institution": {},
                },
            )
            current = bucket["entries_by_institution"].get(entry.institution_id)
            if current is None or entry.priority > current.priority:
                bucket["entries_by_institution"][entry.institution_id] = entry

        refreshed: list[WishlistMatchGroup] = []
        active_keys: set[str] = set()
        for match_key, bucket in grouped.items():
            entries_for_speaker = list(bucket["entries_by_institution"].values())
            participants = self._participants_within_radius(entries_for_speaker, radius_km)
            existing = self.session.scalar(select(WishlistMatchGroup).where(WishlistMatchGroup.match_key == match_key))
            if len(participants) < 2:
                if existing:
                    existing.status = "stale" if existing.status == "new" else existing.status
                    existing.updated_at = datetime.now(UTC)
                    for participant in list(existing.participants):
                        self.session.delete(participant)
                    self.session.add(existing)
                continue

            active_keys.add(match_key)
            group = existing or WishlistMatchGroup(
                researcher_id=bucket["researcher"].id if bucket["researcher"] else None,
                normalized_speaker_name=bucket["normalized_speaker_name"],
                display_speaker_name=bucket["display_speaker_name"],
                match_key=match_key,
                radius_km=radius_km,
            )
            group.researcher_id = bucket["researcher"].id if bucket["researcher"] else None
            group.normalized_speaker_name = bucket["normalized_speaker_name"]
            group.display_speaker_name = bucket["display_speaker_name"]
            group.radius_km = radius_km
            group.score = self._match_score(participants)
            group.rationale = [
                {
                    "label": "Shared speaker demand",
                    "detail": f"{len(participants)} distinct institutions wishlist the same speaker.",
                },
                {
                    "label": "Anonymized radius",
                    "detail": f"At least two institutions are within {radius_km} km or share the same city.",
                },
            ]
            group.metadata_json = {
                "source_wishlist_entry_count": len(entries_for_speaker),
                "matched_participant_count": len(participants),
                "refresh_rule": "speaker_specific_researcher_or_normalized_name",
                "latest_refreshed_at": datetime.now(UTC).isoformat(),
            }
            group.updated_at = datetime.now(UTC)
            self.session.add(group)
            self.session.flush()

            for participant in list(group.participants):
                self.session.delete(participant)
            self.session.flush()
            new_participants = [
                WishlistMatchParticipant(
                    match_group_id=group.id,
                    wishlist_entry_id=entry.id,
                    institution_id=entry.institution_id,
                    masked_label=self._masked_label(index, entry.institution),
                    distance_km=distance_km,
                    distance_band=self._distance_band(distance_km),
                    role="kof_anchor" if self._is_kof(entry.institution) else "co_host",
                    status="candidate",
                    budget_status="not_checked",
                    slot_status="not_checked",
                    metadata_json={
                        "city_region": self._city_region(entry.institution),
                        "wishlist_priority": entry.priority,
                    },
                )
                for index, (entry, distance_km) in enumerate(participants, start=1)
            ]
            group.participants = new_participants
            self.session.add_all(new_participants)
            self.session.flush()
            if not existing:
                RoadshowService(self.session).record_event(
                    event_type="wishlist_match_group.created",
                    entity_type="wishlist_match_group",
                    entity_id=group.id,
                    payload={"match_key": match_key, "participant_count": len(participants), "radius_km": radius_km},
                )
            refreshed.append(group)

        stale_groups = self.session.scalars(select(WishlistMatchGroup).where(WishlistMatchGroup.match_key.not_in(active_keys))).all()
        for group in stale_groups:
            if group.status == "new":
                group.status = "stale"
                group.updated_at = datetime.now(UTC)
                self.session.add(group)
        self.session.flush()
        return refreshed

    def update_match_status(self, group: WishlistMatchGroup, status: str, note: str | None = None) -> WishlistMatchGroup:
        old_status = group.status
        group.status = status
        group.updated_at = datetime.now(UTC)
        metadata = dict(group.metadata_json or {})
        if note:
            metadata["status_note"] = note
        group.metadata_json = metadata
        self.session.add(group)
        RoadshowService(self.session).record_event(
            event_type="wishlist_match_group.status_updated",
            entity_type="wishlist_match_group",
            entity_id=group.id,
            payload={"from": old_status, "to": status, "note": note},
        )
        return group

    def propose_assembly(self, match_group: WishlistMatchGroup) -> TourAssemblyProposal:
        match_group = self._load_group(match_group.id)
        if not match_group:
            raise ValueError("Wishlist match group not found.")
        participants = list(match_group.participants)
        if len({participant.institution_id for participant in participants}) < 2:
            raise ValueError("An anonymous tour assembly requires at least two distinct institutions.")

        researcher = match_group.researcher
        cluster = self._best_cluster(researcher.id) if researcher else None
        speaker_profile = self._speaker_profile(researcher.id) if researcher else None
        fee_floor = speaker_profile.fee_floor_chf if speaker_profile and speaker_profile.fee_floor_chf is not None else DEFAULT_FEE_FLOOR_CHF
        blockers: list[dict[str, Any]] = []
        if not researcher:
            blockers.append(
                {
                    "code": "researcher_identity_missing",
                    "detail": "The matched speaker name must be linked to a researcher record before a speaker-facing draft can be created.",
                }
            )
        if not speaker_profile or speaker_profile.fee_floor_chf is None:
            blockers.append(
                {
                    "code": "speaker_fee_floor_missing",
                    "detail": "Set a speaker fee floor before Roadshow can treat the budget as compatible.",
                }
            )
        if not cluster:
            blockers.append(
                {
                    "code": "trip_cluster_missing",
                    "detail": "No current Scout trip cluster is linked to this speaker, so dates remain review-only.",
                }
            )

        cost_share = self._cost_share(cluster, researcher) if cluster and researcher else None
        travel_total = int((cost_share or {}).get("baseline_round_trip_chf") or 900) + int(
            (cost_share or {}).get("multi_city_incremental_chf") or 0
        )
        host_count = max(1, len(participants))
        travel_share = ceil(travel_total / host_count)
        per_host_total = fee_floor + travel_share
        participant_summaries = []
        for participant in participants:
            profile = participant.institution.roadshow_profile if participant.institution else None
            budget_status = self._budget_status(profile, per_host_total)
            if budget_status == "missing_budget":
                blockers.append(
                    {
                        "code": "host_budget_missing",
                        "detail": f"{participant.masked_label} needs a PO threshold before compatibility is clear.",
                    }
                )
            elif budget_status == "below_required_estimate":
                blockers.append(
                    {
                        "code": "host_budget_below_estimate",
                        "detail": f"{participant.masked_label} PO threshold is below the CHF {per_host_total} per-host estimate.",
                    }
                )
            participant.budget_status = budget_status
            participant.slot_status = "review_required"
            participant.updated_at = datetime.now(UTC)
            participant.metadata_json = {
                **dict(participant.metadata_json or {}),
                "per_host_estimate_chf": per_host_total,
                "grant_code_support": bool(profile.grant_code_support) if profile else False,
            }
            participant_summaries.append(self._masked_participant_summary(participant))
            self.session.add(participant)

        start_date = cluster.start_date if cluster else (datetime.now(UTC).date() + timedelta(days=30))
        end_date = cluster.end_date if cluster else (start_date + timedelta(days=max(1, host_count - 1)))
        title = f"{match_group.display_speaker_name} anonymous Roadshow tour"
        term_sheet = {
            "title": title,
            "speaker_pitch": f"A {host_count}-stop European Roadshow with shared logistics and anonymized co-host coordination.",
            "anonymity_mode": match_group.anonymity_mode,
            "host_count": host_count,
            "target_window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "conditions": [
                "Roadshow coordinates term review internally before any external send.",
                "Institution identities remain masked in the review workflow until admins decide to disclose.",
                "Contracts, payments, and travel booking are not executed by Roadshow v1.",
            ],
        }
        budget_summary = {
            "deterministic": True,
            "fee_floor_chf": fee_floor,
            "host_count": host_count,
            "estimated_travel_total_chf": travel_total,
            "per_host_travel_share_chf": travel_share,
            "per_host_total_estimate_chf": per_host_total,
            "cost_share_source": "trip_cluster_estimate" if cost_share else "fallback_screening_estimate",
            "participants": participant_summaries,
        }
        masked_summary = {
            "speaker": match_group.display_speaker_name,
            "participant_count": host_count,
            "participants": participant_summaries,
            "ordered_stops": self._ordered_stop_summary(participants, start_date, fee_floor, travel_share),
        }

        tour_leg: TourLeg | None = None
        if researcher:
            tour_leg = TourLeg(
                researcher_id=researcher.id,
                trip_cluster_id=cluster.id if cluster else None,
                title=title,
                status="assembly_proposed",
                start_date=start_date,
                end_date=end_date,
                estimated_fee_total_chf=fee_floor * host_count,
                estimated_travel_total_chf=travel_total,
                cost_split_json={
                    "deterministic": True,
                    "source": "anonymous_tour_assembly",
                    "host_count": host_count,
                    "fee_floor_chf": fee_floor,
                    "per_host_travel_share_chf": travel_share,
                    "per_host_total_estimate_chf": per_host_total,
                    "assumption_notes": [
                        "Screening estimate only; no live fare quote, payment, or booking is executed.",
                        "Institution identities are stored internally but masked in default assembly responses.",
                    ],
                },
                rationale=[
                    {
                        "label": "Anonymous co-host match",
                        "detail": f"{host_count} institutions wishlist the same speaker within {match_group.radius_km} km.",
                    },
                    {
                        "label": "Budget screen",
                        "detail": "Compatibility uses PO threshold, grant-code support, fee floor, and travel-share estimate.",
                    },
                ],
            )
            self.session.add(tour_leg)
            self.session.flush()
            self.session.add_all(
                [
                    TourStop(
                        tour_leg_id=tour_leg.id,
                        institution_id=participant.institution_id,
                        sequence=index,
                        city=participant.institution.city or "Unknown",
                        country=participant.institution.country,
                        starts_at=datetime.combine(start_date + timedelta(days=index - 1), datetime.min.time(), tzinfo=ZURICH_TZ)
                        + timedelta(hours=16),
                        format="anonymous_host",
                        fee_chf=fee_floor,
                        travel_share_chf=travel_share,
                        status="candidate",
                        metadata_json={
                            "masked_label": participant.masked_label,
                            "distance_band": participant.distance_band,
                            "budget_status": participant.budget_status,
                        },
                    )
                    for index, participant in enumerate(participants, start=1)
                ]
            )
        proposal = TourAssemblyProposal(
            match_group_id=match_group.id,
            researcher_id=researcher.id if researcher else None,
            tour_leg_id=tour_leg.id if tour_leg else None,
            title=title,
            status="blocked" if blockers else "ready_for_review",
            term_sheet_json=term_sheet,
            budget_summary_json=budget_summary,
            blockers=blockers,
            masked_summary_json=masked_summary,
        )
        match_group.status = "converted"
        match_group.updated_at = datetime.now(UTC)
        self.session.add_all([proposal, match_group])
        self.session.flush()
        RoadshowService(self.session).record_event(
            event_type="tour_assembly.proposed",
            entity_type="tour_assembly_proposal",
            entity_id=proposal.id,
            payload={"match_group_id": match_group.id, "status": proposal.status, "blocker_count": len(blockers)},
        )
        return proposal

    def create_speaker_draft(self, proposal: TourAssemblyProposal) -> OutreachDraft:
        proposal = self._load_proposal(proposal.id)
        if not proposal:
            raise ValueError("Tour assembly proposal not found.")
        if proposal.speaker_draft_id:
            draft = self.session.get(OutreachDraft, proposal.speaker_draft_id)
            if draft:
                return draft
        if proposal.blockers:
            blocker_labels = ", ".join(str(item.get("code")) for item in proposal.blockers)
            raise ReviewRequiredError(f"Resolve tour assembly blockers before creating a speaker draft: {blocker_labels}.")
        if not proposal.researcher:
            raise ReviewRequiredError("Link this anonymous match to a researcher before creating a speaker draft.")
        if not proposal.tour_leg or not proposal.tour_leg.trip_cluster:
            raise ReviewRequiredError("A current Scout trip cluster is required before creating a speaker-facing tour draft.")

        context = {
            "proposal_id": proposal.id,
            "match_group_id": proposal.match_group_id,
            "host_count": int(proposal.budget_summary_json.get("host_count") or 0),
            "term_sheet": proposal.term_sheet_json,
            "budget_summary": proposal.budget_summary_json,
            "masked_summary": proposal.masked_summary_json,
        }
        draft = DraftGenerator(self.session).generate(
            proposal.researcher,
            proposal.tour_leg.trip_cluster,
            template_key="multi_host_tour",
            tour_assembly_context=context,
        )
        draft.metadata_json = {
            **dict(draft.metadata_json or {}),
            "tour_assembly_proposal_id": proposal.id,
            "tour_leg_id": proposal.tour_leg_id,
        }
        proposal.speaker_draft_id = draft.id
        proposal.status = "speaker_draft_ready"
        proposal.updated_at = datetime.now(UTC)
        self.session.add_all([draft, proposal])
        RoadshowService(self.session).record_event(
            event_type="tour_assembly.speaker_draft_created",
            entity_type="tour_assembly_proposal",
            entity_id=proposal.id,
            payload={"draft_id": draft.id, "tour_leg_id": proposal.tour_leg_id},
        )
        return draft

    def _speaker_key(self, entry: WishlistEntry, researchers_by_normalized: dict[str, Researcher]) -> dict[str, Any] | None:
        if entry.researcher:
            return {
                "match_key": f"researcher:{entry.researcher.id}",
                "researcher": entry.researcher,
                "normalized_speaker_name": entry.researcher.normalized_name,
                "display_speaker_name": entry.researcher.name,
            }
        if not entry.speaker_name:
            return None
        normalized = normalize_name(entry.speaker_name)
        if not normalized:
            return None
        researcher = researchers_by_normalized.get(normalized)
        if researcher:
            return {
                "match_key": f"researcher:{researcher.id}",
                "researcher": researcher,
                "normalized_speaker_name": normalized,
                "display_speaker_name": researcher.name,
            }
        return {
            "match_key": f"speaker:{normalized}",
            "researcher": None,
            "normalized_speaker_name": normalized,
            "display_speaker_name": entry.speaker_name,
        }

    def _participants_within_radius(self, entries: list[WishlistEntry], radius_km: int) -> list[tuple[WishlistEntry, float | None]]:
        matched: list[tuple[WishlistEntry, float | None]] = []
        for entry in entries:
            distances = [
                distance
                for other in entries
                if other.institution_id != entry.institution_id
                for distance in [self._distance_between(entry.institution, other.institution)]
                if distance is not None
            ]
            if not distances:
                continue
            nearest = min(distances)
            if nearest <= radius_km:
                matched.append((entry, nearest))
        return sorted(
            matched,
            key=lambda item: (
                0 if self._is_kof(item[0].institution) else 1,
                item[0].institution.city or "",
                item[0].institution.name,
            ),
        )

    def _distance_between(self, left: Institution | None, right: Institution | None) -> float | None:
        if not left or not right:
            return None
        if left.latitude is not None and left.longitude is not None and right.latitude is not None and right.longitude is not None:
            return self._haversine_km(left.latitude, left.longitude, right.latitude, right.longitude)
        if self._same_city(left, right):
            return 0.0
        return None

    def _same_city(self, left: Institution, right: Institution) -> bool:
        return bool(
            left.city
            and right.city
            and left.country
            and right.country
            and left.city.strip().lower() == right.city.strip().lower()
            and left.country.strip().lower() == right.country.strip().lower()
        )

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
        return 6371 * 2 * asin(sqrt(a))

    def _distance_band(self, distance_km: float | None) -> str:
        if distance_km is None:
            return "unknown"
        if distance_km == 0:
            return "same city"
        if distance_km <= 50:
            return "0-50 km"
        if distance_km <= 150:
            return "50-150 km"
        return "outside radius"

    def _masked_label(self, index: int, institution: Institution | None) -> str:
        if self._is_kof(institution):
            return "KOF anchor"
        return f"Nearby institution {index}"

    def _is_kof(self, institution: Institution | None) -> bool:
        return bool(
            institution
            and (
                institution.name == KOF_INSTITUTION_NAME
                or (institution.metadata_json or {}).get("roadshow_role") == "anchor_host"
            )
        )

    def _city_region(self, institution: Institution | None) -> str:
        if not institution:
            return "Region unavailable"
        return ", ".join(part for part in [institution.city, institution.country] if part) or "Region unavailable"

    def _match_score(self, participants: list[tuple[WishlistEntry, float | None]]) -> int:
        if not participants:
            return 0
        max_priority = max(entry.priority for entry, _ in participants)
        average_distance = sum(distance or 0 for _, distance in participants) / len(participants)
        proximity_boost = 20 if average_distance <= 50 else 10
        return min(100, 45 + len(participants) * 10 + int(max_priority * 0.2) + proximity_boost)

    def _speaker_profile(self, researcher_id: str) -> SpeakerProfile | None:
        return self.session.scalar(select(SpeakerProfile).where(SpeakerProfile.researcher_id == researcher_id))

    def _best_cluster(self, researcher_id: str) -> TripCluster | None:
        today = datetime.now(UTC).date()
        return self.session.scalar(
            select(TripCluster)
            .where(TripCluster.researcher_id == researcher_id, TripCluster.end_date >= today)
            .order_by(desc(TripCluster.opportunity_score), TripCluster.start_date)
            .limit(1)
        )

    def _cost_share(self, cluster: TripCluster, researcher: Researcher) -> dict[str, Any] | None:
        match = OpportunityWorkbench(self.session).best_window_for_cluster(cluster)
        return self.cost_sharing.estimate(cluster, researcher, match.window if match else None)

    def _budget_status(self, profile: InstitutionProfile | None, per_host_total: int) -> str:
        if not profile or profile.po_threshold_chf is None:
            return "missing_budget"
        if profile.po_threshold_chf < per_host_total:
            return "below_required_estimate"
        return "compatible"

    def _masked_participant_summary(self, participant: WishlistMatchParticipant) -> dict[str, Any]:
        return {
            "masked_label": participant.masked_label,
            "city_region": (participant.metadata_json or {}).get("city_region") or self._city_region(participant.institution),
            "distance_band": participant.distance_band,
            "role": participant.role,
            "budget_status": participant.budget_status,
            "slot_status": participant.slot_status,
            "grant_code_support": bool((participant.metadata_json or {}).get("grant_code_support")),
        }

    def _ordered_stop_summary(
        self,
        participants: list[WishlistMatchParticipant],
        start_date,
        fee_floor: int,
        travel_share: int,
    ) -> list[dict[str, Any]]:
        return [
            {
                "sequence": index,
                "masked_label": participant.masked_label,
                "city_region": (participant.metadata_json or {}).get("city_region") or self._city_region(participant.institution),
                "target_date": (start_date + timedelta(days=index - 1)).isoformat(),
                "fee_chf": fee_floor,
                "travel_share_chf": travel_share,
            }
            for index, participant in enumerate(participants, start=1)
        ]

    def _load_group(self, group_id: str) -> WishlistMatchGroup | None:
        return self.session.scalar(
            select(WishlistMatchGroup)
            .where(WishlistMatchGroup.id == group_id)
            .options(
                selectinload(WishlistMatchGroup.researcher).selectinload(Researcher.speaker_profile),
                selectinload(WishlistMatchGroup.participants)
                .selectinload(WishlistMatchParticipant.institution)
                .selectinload(Institution.roadshow_profile),
                selectinload(WishlistMatchGroup.participants)
                .selectinload(WishlistMatchParticipant.wishlist_entry)
                .selectinload(WishlistEntry.researcher),
            )
        )

    def _load_proposal(self, proposal_id: str) -> TourAssemblyProposal | None:
        return self.session.scalar(
            select(TourAssemblyProposal)
            .where(TourAssemblyProposal.id == proposal_id)
            .options(
                selectinload(TourAssemblyProposal.match_group).selectinload(WishlistMatchGroup.participants),
                selectinload(TourAssemblyProposal.researcher).selectinload(Researcher.facts),
                selectinload(TourAssemblyProposal.researcher).selectinload(Researcher.fact_candidates),
                selectinload(TourAssemblyProposal.researcher).selectinload(Researcher.speaker_profile),
                selectinload(TourAssemblyProposal.tour_leg).selectinload(TourLeg.trip_cluster),
            )
        )
