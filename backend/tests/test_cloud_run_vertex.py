from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vertex_adapter_uses_adc_initialization() -> None:
    source = (ROOT / "app" / "services" / "ai.py").read_text(encoding="utf-8")

    assert "import vertexai" in source
    assert "from vertexai.generative_models import GenerativeModel" in source
    assert 'vertexai.init(project="kof-gcloud", location="europe-west6")' in source


def test_backend_app_code_does_not_use_gemini_api_keys() -> None:
    forbidden = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "google.generativeai", "google.genai", "api_key=")
    for path in (ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{token} must not be used in {path.relative_to(ROOT)}"
