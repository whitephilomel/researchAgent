from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import requests

from research_agent.adapters.base import BasePaperAdapter
from research_agent.config import Settings
from research_agent.models import CandidatePaper


class SemanticScholarAdapter(BasePaperAdapter):
    name = "Semantic Scholar"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "research-agent/1.0"})
        if settings.semantic_scholar_api_key:
            self.session.headers.update(
                {"x-api-key": settings.semantic_scholar_api_key}
            )

    def lookup_paper(self, identifier: str) -> CandidatePaper | None:
        safe_identifier = quote(identifier, safe=":/")
        payload = self._get(
            f"/paper/{safe_identifier}",
            params={"fields": self.settings.paper_fields_query},
            allow_not_found=True,
        )
        if not payload:
            return None
        return self._map_paper(payload, "query_lookup")

    def match_title(self, title: str) -> CandidatePaper | None:
        if not title.strip():
            return None
        payload = self._get(
            "/paper/search/match",
            params={
                "query": title,
                "fields": self.settings.paper_fields_query,
            },
            allow_not_found=True,
        )
        if not payload or not payload.get("data"):
            return None
        return self._map_paper(payload["data"][0], "title_match")

    def search_ranked(self, query: str, limit: int) -> list[CandidatePaper]:
        if not query.strip():
            return []
        payload = self._get(
            "/paper/search",
            params={
                "query": query,
                "limit": max(1, min(limit, 100)),
                "fields": self.settings.paper_fields_query,
            },
        )
        return self._map_many(payload.get("data", []), "ranked_search")

    def search_bulk(self, query: str, limit: int) -> list[CandidatePaper]:
        if not query.strip():
            return []
        payload = self._get(
            "/paper/search/bulk",
            params={
                "query": query,
                "limit": max(1, min(limit, 100)),
                "fields": self.settings.paper_fields_query,
            },
        )
        return self._map_many(payload.get("data", []), "bulk_search")

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        url = self.settings.semantic_scholar_base_url.rstrip("/") + path
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.settings.semantic_scholar_timeout_seconds,
                )
                if response.status_code == 404 and allow_not_found:
                    return None
                if response.status_code == 429 and attempt < 2:
                    time.sleep(1.0 + attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.75 + attempt)
                    continue
        if allow_not_found:
            return None
        raise RuntimeError(f"Semantic Scholar request failed: {last_error}")

    def _map_many(
        self,
        items: list[dict[str, Any]],
        recall_source: str,
    ) -> list[CandidatePaper]:
        return [self._map_paper(item, recall_source) for item in items]

    def _map_paper(
        self,
        payload: dict[str, Any],
        recall_source: str,
    ) -> CandidatePaper:
        authors = [
            author.get("name", "").strip()
            for author in payload.get("authors", [])
            if author.get("name")
        ]
        open_access_pdf = payload.get("openAccessPdf") or {}
        return CandidatePaper(
            paper_id=payload.get("paperId", "") or "",
            title=(payload.get("title") or "").strip(),
            authors=authors,
            year=payload.get("year"),
            venue=(payload.get("venue") or "").strip(),
            abstract=(payload.get("abstract") or "").strip(),
            fields_of_study=[
                field_name
                for field_name in payload.get("fieldsOfStudy", []) or []
                if field_name
            ],
            publication_types=[
                item
                for item in payload.get("publicationTypes", []) or []
                if item
            ],
            citation_count=int(payload.get("citationCount") or 0),
            source_name=self.name,
            source_url=(payload.get("url") or "").strip(),
            open_access_pdf=(open_access_pdf.get("url") or "").strip(),
            external_ids=payload.get("externalIds") or {},
            recall_sources=[recall_source],
        )
