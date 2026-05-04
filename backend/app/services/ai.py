from __future__ import annotations

import os
from dataclasses import dataclass

import vertexai
from vertexai.generative_models import GenerativeModel


DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


@dataclass(slots=True)
class GeminiGenerationResult:
    text: str
    model_name: str


def build_gemini_model(model_name: str | None = None) -> GenerativeModel:
    vertexai.init(project="kof-gcloud", location="europe-west6")
    return GenerativeModel(model_name or os.getenv("ROADSHOW_VERTEX_MODEL", DEFAULT_GEMINI_MODEL))


class VertexGeminiClient:
    def generate_text(self, prompt: str, model_name: str | None = None) -> GeminiGenerationResult:
        selected_model = model_name or os.getenv("ROADSHOW_VERTEX_MODEL", DEFAULT_GEMINI_MODEL)
        response = build_gemini_model(selected_model).generate_content(prompt)
        return GeminiGenerationResult(text=getattr(response, "text", "") or "", model_name=selected_model)
