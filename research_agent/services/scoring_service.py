from __future__ import annotations

from difflib import SequenceMatcher
import re

from research_agent.config import Settings
from research_agent.models import CandidatePaper, QueryProfile, RelevanceResult


class ScoringService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def score(self, query: QueryProfile, candidate: CandidatePaper) -> RelevanceResult:
        dimensions = {
            "topic_score": (query.topics, candidate.topics + candidate.fields_of_study),
            "task_score": (query.tasks, candidate.tasks),
            "method_score": (query.methods, candidate.methods),
            "domain_score": (query.domains, candidate.domains + candidate.fields_of_study),
            "dataset_score": (query.datasets, candidate.datasets),
            "keyword_score": (query.keywords, candidate.keywords + candidate.topics),
        }
        scores: dict[str, float] = {}
        weighted_sum = 0.0
        effective_weight = 0.0
        for name, (query_items, candidate_items) in dimensions.items():
            similarity = self._list_similarity(query_items, candidate_items)
            scores[name] = round(similarity or 0.0, 3)
            if similarity is not None:
                weight = self.settings.score_weights[name]
                weighted_sum += similarity * weight
                effective_weight += weight
        score = weighted_sum / effective_weight if effective_weight else 0.0
        title_similarity = self._phrase_similarity(query.title, candidate.title)
        if title_similarity is not None and title_similarity >= 0.45:
            score = min(1.0, score * 0.9 + title_similarity * 0.1)
        score = round(score, 4)
        level = self._map_level(score)
        confidence = self._confidence(query, candidate, scores)
        return RelevanceResult(
            paper_id=candidate.paper_id,
            relevance_score=score,
            relevance_level=level,
            relevance_label=self.settings.level_labels[level],
            confidence=confidence,
            dimension_scores=scores,
            reason_tags=[],
            reason_text="",
        )

    def _map_level(self, score: float) -> str:
        thresholds = self.settings.level_thresholds
        if score >= thresholds["A"]:
            return "A"
        if score >= thresholds["B"]:
            return "B"
        if score >= thresholds["C"]:
            return "C"
        return "D"

    def _confidence(
        self,
        query: QueryProfile,
        candidate: CandidatePaper,
        scores: dict[str, float],
    ) -> float:
        query_completeness = query.non_empty_dimension_count() / 6
        candidate_completeness = sum(
            1
            for item in [
                candidate.topics,
                candidate.tasks,
                candidate.methods,
                candidate.domains,
                candidate.datasets,
                candidate.keywords,
            ]
            if item
        ) / 6
        agreement = min(len(candidate.recall_sources), 3) / 3
        score_support = sum(1 for value in scores.values() if value >= 0.45) / 6
        confidence = 0.3
        confidence += 0.25 * query_completeness
        confidence += 0.2 * candidate_completeness
        confidence += 0.15 * agreement
        confidence += 0.1 * score_support
        return round(min(confidence, 0.95), 4)

    def _list_similarity(
        self,
        query_items: list[str],
        candidate_items: list[str],
    ) -> float | None:
        if not query_items or not candidate_items:
            return None
        best_scores: list[float] = []
        for query_item in query_items:
            best = 0.0
            for candidate_item in candidate_items:
                best = max(best, self._phrase_similarity(query_item, candidate_item) or 0.0)
            best_scores.append(best)
        if not best_scores:
            return None
        return sum(best_scores) / len(best_scores)

    def _phrase_similarity(self, left: str, right: str) -> float | None:
        left_tokens = self._tokenize(left)
        right_tokens = self._tokenize(right)
        if not left_tokens or not right_tokens:
            return None
        left_set = set(left_tokens)
        right_set = set(right_tokens)
        token_overlap = len(left_set & right_set) / len(left_set | right_set)
        raw_left = " ".join(left_tokens)
        raw_right = " ".join(right_tokens)
        sequence_score = SequenceMatcher(None, raw_left, raw_right).ratio()
        if raw_left in raw_right or raw_right in raw_left:
            return max(token_overlap, sequence_score, 0.8)
        return max(token_overlap, sequence_score * 0.85)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9][a-z0-9\-+]{1,}", text.lower())
