from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "ResearchAgent"
    secret_key: str = os.getenv("FLASK_SECRET_KEY", "research-agent-dev")
    semantic_scholar_api_key: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    semantic_scholar_base_url: str = os.getenv(
        "SEMANTIC_SCHOLAR_BASE_URL",
        "https://api.semanticscholar.org/graph/v1",
    )
    semantic_scholar_timeout_seconds: int = _int_env(
        "SEMANTIC_SCHOLAR_TIMEOUT_SECONDS",
        20,
    )
    search_limit: int = _int_env("SEARCH_LIMIT", 20)
    ranked_search_limit: int = _int_env("RANKED_SEARCH_LIMIT", 15)
    bulk_search_limit: int = _int_env("BULK_SEARCH_LIMIT", 25)
    max_pdf_size_bytes: int = _int_env("MAX_PDF_SIZE_MB", 15) * 1024 * 1024
    max_context_chars: int = 6000
    allowed_export_formats: tuple[str, ...] = ("json", "csv", "md")
    paper_fields: tuple[str, ...] = (
        "paperId",
        "title",
        "authors",
        "year",
        "venue",
        "abstract",
        "citationCount",
        "url",
        "fieldsOfStudy",
        "externalIds",
        "openAccessPdf",
        "publicationTypes",
    )
    score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "topic_score": 0.30,
            "task_score": 0.20,
            "method_score": 0.20,
            "domain_score": 0.15,
            "dataset_score": 0.10,
            "keyword_score": 0.05,
        }
    )
    level_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "A": 0.85,
            "B": 0.70,
            "C": 0.50,
            "D": 0.00,
        }
    )
    level_labels: dict[str, str] = field(
        default_factory=lambda: {
            "A": "严格相关",
            "B": "高度相关",
            "C": "扩展相关",
            "D": "背景相关",
        }
    )

    @property
    def paper_fields_query(self) -> str:
        return ",".join(self.paper_fields)
