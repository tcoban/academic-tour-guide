from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class Settings:
    app_name: str = "Academic Tour Guide"
    api_prefix: str = "/api"
    default_timezone: str = "Europe/Zurich"
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    cluster_gap_days: int = 14
    slot_match_buffer_days: int = 7
    opportunity_horizon_days: int = 120
    evidence_confidence_threshold: float = 0.6

    @property
    def access_token(self) -> str | None:
        return os.getenv("ATG_API_ACCESS_TOKEN") or None

    @property
    def database_url(self) -> str:
        configured = os.getenv("DATABASE_URL")
        if configured:
            return configured
        db_path = Path(__file__).resolve().parents[2] / "academic_tour_guide.db"
        return f"sqlite+pysqlite:///{db_path.as_posix()}"


settings = Settings()
