from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
from typing import Any

from research_agent.adapters.base import BasePaperAdapter
from research_agent.config import Settings
from research_agent.models import CandidatePaper, ClusterSummary, QueryInput, RankedPaper, SearchResponse
from research_agent.services.explanation_service import ExplanationService
from research_agent.services.profile_service import ProfileService
from research_agent.services.result_service import ResultService
from research_agent.services.scoring_service import ScoringService


@dataclass
class SearchCacheEntry:
    session_id: str
    query_type: str
    query_summary: dict[str, Any]
    ranked_results: list[RankedPaper]
    clusters: list[ClusterSummary]
    overview_summary: str
    warnings: list[str]
    meta: dict[str, Any]
    created_at: float
    exhaustive_search: bool
    complete: bool


class SearchService:
    _cache: dict[str, SearchCacheEntry] = {}

    def __init__(
        self,
        settings: Settings,
        adapter: BasePaperAdapter,
        profile_service: ProfileService,
        scoring_service: ScoringService,
        explanation_service: ExplanationService,
        result_service: ResultService,
    ) -> None:
        self.settings = settings
        self.adapter = adapter
        self.profile_service = profile_service
        self.scoring_service = scoring_service
        self.explanation_service = explanation_service
        self.result_service = result_service

    def search(self, query_input: QueryInput) -> SearchResponse:
        self._prune_cache()
        page_size = self._clamp_requested_limit(query_input.result_limit)
        requested_page = max(1, query_input.page)

        if query_input.search_session_id:
            cached_entry = self._cache.get(query_input.search_session_id)
            if cached_entry:
                return self._paginate_entry(cached_entry, requested_page, page_size, cache_hit=True)
            if not query_input.has_any_content():
                raise ValueError("搜索会话已过期，请重新发起检索。")

        session_id = self._build_session_id(query_input)
        cached_entry = self._cache.get(session_id)
        minimum_results_needed = requested_page * page_size
        if cached_entry and (cached_entry.complete or len(cached_entry.ranked_results) >= minimum_results_needed):
            return self._paginate_entry(cached_entry, requested_page, page_size, cache_hit=True)

        entry = self._build_cache_entry(query_input, session_id, minimum_results_needed)
        self._cache[session_id] = entry
        return self._paginate_entry(entry, requested_page, page_size, cache_hit=False)

    def _build_cache_entry(
        self,
        query_input: QueryInput,
        session_id: str,
        minimum_results_needed: int,
    ) -> SearchCacheEntry:
        warnings: list[str] = []
        resolved_paper = self._resolve_query_paper(query_input, warnings)
        profile = self.profile_service.build_query_profile(query_input, resolved_paper)
        warnings.extend(profile.warnings)

        if query_input.exhaustive_search:
            candidates, retrieval_meta = self._retrieve_exhaustive_candidates(query_input, profile, resolved_paper, warnings)
            complete = bool(retrieval_meta.get("exhaustive_completed", False))
        else:
            candidate_target = min(max(minimum_results_needed * 2, 50), self.settings.max_search_limit)
            candidates = self._retrieve_candidates(profile, resolved_paper, warnings, candidate_target)
            retrieval_meta = {
                "candidate_count": len(candidates),
                "exhaustive_completed": False,
                "bulk_pages_fetched": 0,
                "api_total_hint": len(candidates),
            }
            complete = False

        ranked_results = self._rank_candidates(profile, candidates)
        clusters = self.result_service.cluster_results(ranked_results)
        overview = self.result_service.build_overview_summary(
            profile,
            ranked_results[: min(len(ranked_results), max(20, query_input.result_limit))],
            clusters,
        )
        return SearchCacheEntry(
            session_id=session_id,
            query_type=profile.query_type,
            query_summary={
                "title": profile.title,
                "topics": profile.topics,
                "tasks": profile.tasks,
                "methods": profile.methods,
                "domains": profile.domains,
                "datasets": profile.datasets,
                "keywords": profile.keywords,
            },
            ranked_results=ranked_results,
            clusters=clusters,
            overview_summary=overview,
            warnings=self._dedupe(warnings),
            meta={
                "candidate_count": len(candidates),
                "source": self.adapter.name,
                "resolved_query_paper": resolved_paper.paper_id if resolved_paper else "",
                "search_mode": "exhaustive" if query_input.exhaustive_search else "standard",
                "bulk_pages_fetched": retrieval_meta.get("bulk_pages_fetched", 0),
                "api_total_hint": retrieval_meta.get("api_total_hint", len(candidates)),
                "exhaustive_completed": retrieval_meta.get("exhaustive_completed", False),
            },
            created_at=time.time(),
            exhaustive_search=query_input.exhaustive_search,
            complete=complete,
        )

    def _paginate_entry(
        self,
        entry: SearchCacheEntry,
        requested_page: int,
        page_size: int,
        cache_hit: bool,
    ) -> SearchResponse:
        total_results = len(entry.ranked_results)
        total_pages = max(1, math.ceil(total_results / page_size)) if page_size else 1
        page = min(max(1, requested_page), total_pages)
        start = (page - 1) * page_size
        end = start + page_size
        page_results = entry.ranked_results[start:end]
        meta = {
            **entry.meta,
            "search_session_id": entry.session_id,
            "requested_count": page_size,
            "returned_count": len(page_results),
            "page": page,
            "page_size": page_size,
            "total_results": total_results,
            "total_pages": total_pages,
            "has_next_page": page < total_pages,
            "has_prev_page": page > 1,
            "cache_hit": cache_hit,
            "cache_ttl_seconds": self.settings.cache_ttl_seconds,
        }
        return SearchResponse(
            query_type=entry.query_type,
            query_summary=entry.query_summary,
            results=page_results,
            clusters=entry.clusters,
            overview_summary=entry.overview_summary,
            warnings=entry.warnings,
            meta=meta,
        )

    def _rank_candidates(self, profile, candidates: list[CandidatePaper]) -> list[RankedPaper]:
        ranked_results: list[RankedPaper] = []
        for candidate in candidates:
            enriched = self.profile_service.enrich_candidate(candidate)
            relevance = self.scoring_service.score(profile, enriched)
            reason_tags, reason_text, comparison = self.explanation_service.explain(
                profile,
                enriched,
                relevance,
            )
            ranked_results.append(
                RankedPaper(
                    paper_id=enriched.paper_id,
                    title=enriched.title,
                    authors=enriched.authors,
                    year=enriched.year,
                    venue=enriched.venue,
                    abstract=enriched.abstract,
                    keywords=enriched.keywords,
                    topics=enriched.topics,
                    tasks=enriched.tasks,
                    methods=enriched.methods,
                    domains=enriched.domains,
                    datasets=enriched.datasets,
                    fields_of_study=enriched.fields_of_study,
                    publication_types=enriched.publication_types,
                    citation_count=enriched.citation_count,
                    source_name=enriched.source_name,
                    source_url=enriched.source_url,
                    open_access_pdf=enriched.open_access_pdf,
                    recall_sources=sorted(set(enriched.recall_sources)),
                    relevance_score=relevance.relevance_score,
                    relevance_level=relevance.relevance_level,
                    relevance_label=relevance.relevance_label,
                    confidence=relevance.confidence,
                    dimension_scores=relevance.dimension_scores,
                    reason_tags=reason_tags,
                    reason_text=reason_text,
                    comparison=comparison,
                )
            )
        return self.result_service.sort_results(ranked_results)

    def _retrieve_exhaustive_candidates(
        self,
        query_input: QueryInput,
        profile,
        resolved_paper: CandidatePaper | None,
        warnings: list[str],
    ) -> tuple[list[CandidatePaper], dict[str, Any]]:
        warnings.append("已启用全量检索，系统会通过 bulk 分页抓取更多候选论文，耗时会明显高于普通模式。")
        if not self.settings.semantic_scholar_api_key:
            warnings.append("当前使用公用 Semantic Scholar API，全量检索时更容易遇到速率限制，建议配置专用 API Key。")
        merged: dict[str, CandidatePaper] = {}
        attempted_queries: set[str] = set()
        max_items = self.settings.exhaustive_max_items or None
        strategies = [
            ("raw_exhaustive", self._build_raw_query(query_input, profile)),
            ("title_exhaustive", resolved_paper.title if resolved_paper else profile.title),
            ("context_exhaustive", self._build_context_query(profile)),
            ("keyword_exhaustive", self._build_keyword_query(profile)),
        ]
        total_pages_fetched = 0
        api_total_hint = 0
        exhaustive_completed = True
        for strategy_name, query in strategies:
            cleaned_query = query.strip() if query else ""
            if not cleaned_query or cleaned_query.lower() in attempted_queries:
                continue
            attempted_queries.add(cleaned_query.lower())
            try:
                items, info = self.adapter.search_bulk_all(cleaned_query, max_items=max_items)
            except Exception as exc:
                warnings.append(f"全量召回策略 {strategy_name} 执行失败：{exc}")
                exhaustive_completed = False
                continue
            total_pages_fetched += int(info.get("pages_fetched") or 0)
            api_total_hint = max(api_total_hint, int(info.get("total_available") or 0))
            exhaustive_completed = exhaustive_completed and bool(info.get("completed", True))
            for item in items:
                item.recall_sources.append(strategy_name)
                if self._is_same_as_query(item, profile, resolved_paper):
                    continue
                key = item.paper_id or self._normalize_title(item.title)
                if not key:
                    continue
                if key not in merged:
                    merged[key] = item
                else:
                    merged[key] = self._merge_papers(merged[key], item)
        if not merged:
            warnings.append("全量检索没有召回到候选论文，建议缩小范围或补充更明确的主题词。")
        return list(merged.values()), {
            "candidate_count": len(merged),
            "bulk_pages_fetched": total_pages_fetched,
            "api_total_hint": api_total_hint or len(merged),
            "exhaustive_completed": exhaustive_completed,
        }

    def _retrieve_candidates(
        self,
        profile,
        resolved_paper: CandidatePaper | None,
        warnings: list[str],
        candidate_target: int,
    ) -> list[CandidatePaper]:
        merged: dict[str, CandidatePaper] = {}
        attempted_queries: set[tuple[str, str]] = set()
        ranked_primary_limit = min(
            max(candidate_target // 4, self.settings.ranked_search_limit),
            self.settings.max_ranked_page_size,
        )
        bulk_primary_limit = min(
            max(candidate_target, self.settings.bulk_search_limit),
            self.settings.max_bulk_page_size,
        )
        primary_strategies = [
            ("title_focus", (resolved_paper.title if resolved_paper else profile.title), "ranked", ranked_primary_limit),
            ("keyword_focus", self._build_keyword_query(profile), "ranked", ranked_primary_limit),
            ("context_focus", self._build_context_query(profile), "bulk", bulk_primary_limit),
        ]
        self._execute_strategies(primary_strategies, attempted_queries, merged, profile, resolved_paper, warnings)

        if len(merged) < candidate_target:
            fallback_ranked_limit = min(max(candidate_target // 5, 12), self.settings.max_ranked_page_size)
            fallback_bulk_limit = min(max(candidate_target // 2, 30), self.settings.max_bulk_page_size)
            fallback_strategies = [
                ("domain_task_fallback", self._join_parts(profile.domains[:2] + profile.tasks[:1]), "ranked", fallback_ranked_limit),
                ("method_task_fallback", self._join_parts(profile.methods[:2] + profile.tasks[:1]), "ranked", fallback_ranked_limit),
                ("topic_fallback", self._join_parts(profile.topics[:4]), "ranked", fallback_ranked_limit),
                ("keyword_fallback", self._join_parts(profile.keywords[:6]), "bulk", fallback_bulk_limit),
            ]
            self._execute_strategies(fallback_strategies, attempted_queries, merged, profile, resolved_paper, warnings)

        if len(merged) < candidate_target:
            warnings.append(f"当前共召回 {len(merged)} 篇候选论文，少于目标返回规模 {candidate_target}，说明该主题在当前 API 结果中较窄或接口存在限流。")
        return list(merged.values())

    def _execute_strategies(
        self,
        strategies,
        attempted_queries: set[tuple[str, str]],
        merged: dict[str, CandidatePaper],
        profile,
        resolved_paper: CandidatePaper | None,
        warnings: list[str],
    ) -> None:
        for strategy_name, query, mode, limit in strategies:
            if not query:
                continue
            normalized_key = (mode, query.lower())
            if normalized_key in attempted_queries:
                continue
            attempted_queries.add(normalized_key)
            try:
                items = self.adapter.search_bulk(query, limit) if mode == "bulk" else self.adapter.search_ranked(query, limit)
            except Exception as exc:
                warnings.append(f"召回策略 {strategy_name} 执行失败：{exc}")
                continue
            for item in items:
                item.recall_sources.append(strategy_name)
                if self._is_same_as_query(item, profile, resolved_paper):
                    continue
                key = item.paper_id or self._normalize_title(item.title)
                if not key:
                    continue
                if key not in merged:
                    merged[key] = item
                else:
                    merged[key] = self._merge_papers(merged[key], item)

    def _resolve_query_paper(self, query_input: QueryInput, warnings: list[str]) -> CandidatePaper | None:
        try:
            if query_input.doi:
                paper = self.adapter.lookup_paper(f"DOI:{query_input.doi}")
                if not paper:
                    warnings.append("DOI 未能在 Semantic Scholar 中解析到论文，将回退为文本检索。")
                return paper
            if query_input.arxiv_id:
                paper = self.adapter.lookup_paper(f"ARXIV:{query_input.arxiv_id}")
                if not paper:
                    warnings.append("arXiv ID 未能在 Semantic Scholar 中解析到论文，将回退为文本检索。")
                return paper
            if query_input.title:
                return self.adapter.match_title(query_input.title)
        except Exception as exc:
            warnings.append(f"查询论文解析失败，已回退为普通检索：{exc}")
        return None

    def _build_raw_query(self, query_input: QueryInput, profile) -> str:
        if query_input.topic_text.strip():
            return query_input.topic_text.strip()
        if query_input.title.strip() and query_input.abstract.strip():
            return f"{query_input.title.strip()} {query_input.abstract.strip()[:400]}".strip()
        if query_input.title.strip():
            return query_input.title.strip()
        return profile.raw_text[:600].strip()

    def _build_keyword_query(self, profile) -> str:
        parts = self._dedupe(profile.keywords[:8] + profile.topics[:5] + profile.tasks[:3] + profile.methods[:3])
        return self._join_parts(parts[:14])

    def _build_context_query(self, profile) -> str:
        parts = self._dedupe(
            ([profile.title] if profile.title else [])
            + profile.topics[:4]
            + profile.methods[:4]
            + profile.domains[:4]
            + profile.datasets[:3]
            + profile.tasks[:3]
        )
        return self._join_parts(parts[:16])

    def _join_parts(self, parts: list[str]) -> str:
        return " ".join(self._dedupe(parts)[:16])

    def _is_same_as_query(self, candidate: CandidatePaper, profile, resolved_paper: CandidatePaper | None) -> bool:
        if resolved_paper and resolved_paper.paper_id and candidate.paper_id == resolved_paper.paper_id:
            return True
        if profile.title and self._normalize_title(candidate.title) == self._normalize_title(profile.title):
            return True
        return False

    def _merge_papers(self, existing: CandidatePaper, new_item: CandidatePaper) -> CandidatePaper:
        existing.recall_sources = self._dedupe(existing.recall_sources + new_item.recall_sources)
        if not existing.abstract and new_item.abstract:
            existing.abstract = new_item.abstract
        if not existing.venue and new_item.venue:
            existing.venue = new_item.venue
        if not existing.source_url and new_item.source_url:
            existing.source_url = new_item.source_url
        if not existing.open_access_pdf and new_item.open_access_pdf:
            existing.open_access_pdf = new_item.open_access_pdf
        existing.fields_of_study = self._dedupe(existing.fields_of_study + new_item.fields_of_study)
        existing.publication_types = self._dedupe(existing.publication_types + new_item.publication_types)
        return existing

    def _build_session_id(self, query_input: QueryInput) -> str:
        payload = {
            "title": query_input.title.strip(),
            "abstract": query_input.abstract.strip(),
            "keywords": [item.strip().lower() for item in query_input.keywords],
            "doi": query_input.doi.strip().lower(),
            "arxiv_id": query_input.arxiv_id.strip().lower(),
            "topic_text": query_input.topic_text.strip(),
            "pdf_filename": query_input.pdf_filename.strip(),
            "pdf_hash": hashlib.sha256(query_input.pdf_text.encode("utf-8")).hexdigest() if query_input.pdf_text else "",
            "exhaustive_search": query_input.exhaustive_search,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    def _prune_cache(self) -> None:
        now = time.time()
        expired = [key for key, entry in self._cache.items() if now - entry.created_at > self.settings.cache_ttl_seconds]
        for key in expired:
            self._cache.pop(key, None)

    def _clamp_requested_limit(self, requested_limit: int) -> int:
        return max(1, min(requested_limit, self.settings.max_search_limit))

    def _normalize_title(self, value: str) -> str:
        return re.sub(r"\W+", "", value.lower())

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            cleaned = item.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(cleaned)
        return result



