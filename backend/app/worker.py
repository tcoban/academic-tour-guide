from __future__ import annotations

import argparse

from app.db.session import SessionLocal, init_db
from app.services.availability import AvailabilityBuilder
from app.services.clustering import TripClusterer
from app.services.enrichment import BiographerPipeline
from app.services.ingestion import IngestionService
from app.services.scoring import Scorer
from app.services.seed import seed_demo_data, seed_reference_data


def run(command: str) -> None:
    init_db()
    with SessionLocal() as session:
        seed_reference_data(session)
        if command == "ingest":
            IngestionService(session).ingest_sources()
        elif command == "sync-host":
            IngestionService(session).sync_host_calendar()
        elif command == "repec-sync":
            BiographerPipeline(session).sync_repec()
            Scorer(session).score_all_clusters()
        elif command == "biographer-refresh":
            BiographerPipeline(session).refresh()
            Scorer(session).score_all_clusters()
        elif command == "seed-demo":
            seed_demo_data(session)
        elif command == "rebuild":
            TripClusterer(session).rebuild_all()
            AvailabilityBuilder(session).rebuild_persisted()
            Scorer(session).score_all_clusters()
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Academic Tour Guide worker")
    parser.add_argument("command", choices=["ingest", "sync-host", "repec-sync", "biographer-refresh", "seed-demo", "rebuild"])
    args = parser.parse_args()
    run(args.command)


if __name__ == "__main__":
    main()
