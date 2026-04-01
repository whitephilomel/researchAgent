from __future__ import annotations

import re

from research_agent.adapters.base import BasePaperAdapter
from research_agent.config import Settings
from research_agent.models import CandidatePaper, QueryInput, RankedPaper, SearchResponse
from research_agent.services.explanation_service import ExplanationService
from research_agent.services.profile_service import ProfileService
from research_agent.services.result_service import ResultService
from research_agent.services.scoring_service import ScoringService


class SearchService:
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
        warnings: list[str] = []
        resolved_paper = self._resolve_query_paper(query_input, warnings)
        profile = self.profile_service.build_query_profile(query_input, resolved_paper)
        warnings.extend(profile.warnings)
        candidates = self._retrieve_candidates(profile, resolved_paper, warnings)
        ranked_results: list[RankedPaper] = []
        for candidate in candidates[: max(self.settings.search_limit * 3, 30)]:
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
        ranked_results = self.result_service.sort_results(ranked_results)[: self.settings.search_limit]
        clusters = self.result_service.cluster_results(ranked_results)
        overview = self.result_service.build_overview_summary(profile, ranked_results, clusters)
        return SearchResponse(
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
            results=ranked_results,
            clusters=clusters,
            overview_summary=overview,
            warnings=self._dedupe(warnings),
            meta={
                "candidate_count": len(candidates),
                "returned_count": len(ranked_results),
                "source": self.adapter.name,
                "resolved_query_paper": resolved_paper.paper_id if resolved_paper else "",
            },
        )

    def _resolve_query_paper(
        self,
        query_input: QueryInput,
        warnings: list[str],
    ) -> CandidatePaper | None:
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

    def _retrieve_candidates(
        self,
        profile,
        resolved_paper: CandidatePaper | None,
        warnings: list[str],
    ) -> list[CandidatePaper]:
        merged: dict[str, CandidatePaper] = {}
        attempted_queries: set[tuple[str, str]] = set()

        primary_strategies = [
            ("title_focus", (resolved_paper.title if resolved_paper else profile.title), "ranked", self.settings.ranked_search_limit),
            ("keyword_focus", self._build_keyword_query(profile), "ranked", self.settings.ranked_search_limit),
            ("context_focus", self._build_context_query(profile), "bulk", self.settings.bulk_search_limit),
        ]
        self._execute_strategies(primary_strategies, attempted_queries, merged, profile, resolved_paper, warnings)

        if len(merged) < 10:
            fallback_strategies = [
                ("domain_task_fallback", self._join_parts(profile.domains[:2] + profile.tasks[:1]), "ranked", 12),
                ("method_task_fallback", self._join_parts(profile.methods[:2] + profile.tasks[:1]), "ranked", 12),
                ("topic_fallback", self._join_parts(profile.topics[:3]), "ranked", 12),
                ("keyword_fallback", self._join_parts(profile.keywords[:4]), "bulk", 15),
            ]
            self._execute_strategies(fallback_strategies, attempted_queries, merged, profile, resolved_paper, warnings)

        if len(merged) < 10:
            warnings.append("当前候选结果较少，建议补充更明确的摘要、关键词或领域约束。")
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
                if mode == "bulk":
                    items = self.adapter.search_bulk(query, limit)
                else:
                    items = self.adapter.search_ranked(query, limit)
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

    def _build_keyword_query(self, profile) -> str:
        parts = self._dedupe(
            profile.keywords[:6]
            + profile.topics[:4]
            + profile.tasks[:2]
            + profile.methods[:2]
        )
        return self._join_parts(parts[:12])

    def _build_context_query(self, profile) -> str:
        parts = self._dedupe(
            ([profile.title] if profile.title else [])
            + profile.topics[:3]
            + profile.methods[:3]
            + profile.domains[:3]
            + profile.datasets[:2]
            + profile.tasks[:2]
        )
        return self._join_parts(parts[:12])

    def _join_parts(self, parts: list[str]) -> str:
        cleaned = self._dedupe(parts)
        return " ".join(cleaned[:12])

    def _is_same_as_query(
        self,
        candidate: CandidatePaper,
        profile,
        resolved_paper: CandidatePaper | None,
    ) -> bool:
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
