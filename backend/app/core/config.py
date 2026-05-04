from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class Settings:
    app_name: str = "Roadshow"
    api_prefix: str = "/api"
    default_timezone: str = "Europe/Zurich"
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    cluster_gap_days: int = 14
    slot_match_buffer_days: int = 7
    opportunity_horizon_days: int = 120
    evidence_confidence_threshold: float = 0.6

    @property
    def roadshow_env(self) -> str:
        return os.getenv("ROADSHOW_ENV", "development").lower()

    @property
    def is_production(self) -> bool:
        return self.roadshow_env == "production"

    @property
    def demo_tools_enabled(self) -> bool:
        return os.getenv("ROADSHOW_ENABLE_DEMO_TOOLS", "").lower() in {"1", "true", "yes", "on"}

    def _flag(self, name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "on"}

    @property
    def ai_enabled(self) -> bool:
        return self._flag("ROADSHOW_AI_ENABLED")

    @property
    def ai_evidence_enabled(self) -> bool:
        return self.ai_enabled and self._flag("ROADSHOW_AI_EVIDENCE_ENABLED", default=True)

    @property
    def ai_fit_enabled(self) -> bool:
        return self.ai_enabled and self._flag("ROADSHOW_AI_FIT_ENABLED", default=True)

    @property
    def ai_draft_enabled(self) -> bool:
        return self.ai_enabled and self._flag("ROADSHOW_AI_DRAFT_ENABLED", default=True)

    @property
    def ai_autopilot_enabled(self) -> bool:
        return self.ai_enabled and self._flag("ROADSHOW_AI_AUTOPILOT_ENABLED", default=True)

    @property
    def vertex_model(self) -> str:
        return os.getenv("ROADSHOW_VERTEX_MODEL", "gemini-1.5-flash")

    @property
    def ai_timeout_seconds(self) -> int:
        try:
            return max(1, int(os.getenv("ROADSHOW_AI_TIMEOUT_SECONDS", "45")))
        except ValueError:
            return 45

    @property
    def frontend_password(self) -> str | None:
        return os.getenv("ROADSHOW_APP_PASSWORD") or os.getenv("ATG_APP_PASSWORD") or None

    @property
    def access_token(self) -> str | None:
        return os.getenv("ROADSHOW_API_ACCESS_TOKEN") or os.getenv("ATG_API_ACCESS_TOKEN") or None

    @property
    def rail_class(self) -> str:
        return os.getenv("ROADSHOW_RAIL_CLASS", "first").lower()

    @property
    def rail_fare_policy(self) -> str:
        return os.getenv("ROADSHOW_RAIL_FARE_POLICY", "full_fare").lower()

    @property
    def opentransportdata_api_token(self) -> str | None:
        return os.getenv("OPENTRANSPORTDATA_API_TOKEN") or None

    @property
    def rail_europe_api_token(self) -> str | None:
        return os.getenv("RAIL_EUROPE_API_TOKEN") or None

    @property
    def rail_europe_api_base_url(self) -> str | None:
        return os.getenv("RAIL_EUROPE_API_BASE_URL") or None

    @property
    def rail_price_cache_hours(self) -> int:
        try:
            return max(1, int(os.getenv("RAIL_PRICE_CACHE_HOURS", "24")))
        except ValueError:
            return 24

    @property
    def eur_chf_rate(self) -> float:
        try:
            return float(os.getenv("ROADSHOW_EUR_CHF_RATE", "0.95"))
        except ValueError:
            return 0.95

    def production_validation_errors(self) -> list[str]:
        if not self.is_production:
            return []
        return []

    def ensure_production_ready(self) -> None:
        errors = self.production_validation_errors()
        if errors:
            raise RuntimeError(" ".join(errors))

    @property
    def database_url(self) -> str:
        configured = os.getenv("DATABASE_URL")
        if configured:
            return configured
        db_path = Path(__file__).resolve().parents[2] / "academic_tour_guide.db"
        return f"sqlite+pysqlite:///{db_path.as_posix()}"


settings = Settings()
