from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryInput(Serializable):
    title: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    arxiv_id: str = ""
    topic_text: str = ""
    pdf_filename: str = ""
    pdf_text: str = ""
    pdf_parse_warning: str = ""

    def has_any_content(self) -> bool:
        return any(
            [
                self.title.strip(),
                self.abstract.strip(),
                self.keywords,
                self.doi.strip(),
                self.arxiv_id.strip(),
                self.topic_text.strip(),
                self.pdf_text.strip(),
                self.pdf_filename.strip(),
            ]
        )


@dataclass
class QueryProfile(Serializable):
    query_id: str = field(default_factory=lambda: str(uuid4()))
    query_type: str = "topic_text"
    title: str = ""
    abstract: str = ""
    topics: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)

    def non_empty_dimension_count(self) -> int:
        dimensions = [
            self.topics,
            self.tasks,
            self.methods,
            self.domains,
            self.datasets,
            self.keywords,
        ]
        return sum(1 for item in dimensions if item)


@dataclass
class CandidatePaper(Serializable):
    paper_id: str = ""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    fields_of_study: list[str] = field(default_factory=list)
    publication_types: list[str] = field(default_factory=list)
    citation_count: int = 0
    source_name: str = ""
    source_url: str = ""
    open_access_pdf: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)
    recall_sources: list[str] = field(default_factory=list)


@dataclass
class RelevanceResult(Serializable):
    paper_id: str
    relevance_score: float
    relevance_level: str
    relevance_label: str
    confidence: float
    dimension_scores: dict[str, float]
    reason_tags: list[str]
    reason_text: str


@dataclass
class RankedPaper(Serializable):
    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str
    abstract: str
    keywords: list[str]
    topics: list[str]
    tasks: list[str]
    methods: list[str]
    domains: list[str]
    datasets: list[str]
    fields_of_study: list[str]
    publication_types: list[str]
    citation_count: int
    source_name: str
    source_url: str
    open_access_pdf: str
    recall_sources: list[str]
    relevance_score: float
    relevance_level: str
    relevance_label: str
    confidence: float
    dimension_scores: dict[str, float]
    reason_tags: list[str]
    reason_text: str
    comparison: dict[str, Any] = field(default_factory=dict)
    cluster_label: str = ""


@dataclass
class ClusterSummary(Serializable):
    label: str
    size: int
    paper_ids: list[str] = field(default_factory=list)


@dataclass
class SearchResponse(Serializable):
    query_type: str
    query_summary: dict[str, Any]
    results: list[RankedPaper]
    clusters: list[ClusterSummary]
    overview_summary: str
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=_utc_now_iso)
