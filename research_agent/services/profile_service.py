from __future__ import annotations

from collections import Counter
import re

from research_agent.constants import (
    CHINESE_HINTS,
    DATASET_HINTS,
    DOMAIN_LEXICON,
    METHOD_LEXICON,
    STOPWORDS,
    TASK_LEXICON,
)
from research_agent.models import CandidatePaper, QueryInput, QueryProfile


class ProfileService:
    def build_query_profile(
        self,
        query_input: QueryInput,
        resolved_paper: CandidatePaper | None = None,
    ) -> QueryProfile:
        title = query_input.title or (resolved_paper.title if resolved_paper else "")
        abstract = query_input.abstract or (resolved_paper.abstract if resolved_paper else "")
        raw_text = "\n".join(
            part
            for part in [
                title,
                abstract,
                query_input.topic_text,
                " ".join(query_input.keywords),
                query_input.pdf_text,
                " ".join(resolved_paper.fields_of_study) if resolved_paper else "",
            ]
            if part
        )
        keywords = self._dedupe(
            query_input.keywords
            + (resolved_paper.keywords if resolved_paper else [])
            + self.extract_keywords(raw_text)
        )
        topics = self._dedupe(
            (resolved_paper.fields_of_study if resolved_paper else [])
            + self.extract_topics("\n".join([title, abstract, query_input.topic_text]))
        )
        tasks = self.match_lexicon(raw_text, TASK_LEXICON)
        methods = self.match_lexicon(raw_text, METHOD_LEXICON)
        domains = self.match_lexicon(raw_text, DOMAIN_LEXICON)
        datasets = self.match_lexicon(raw_text, DATASET_HINTS)
        query_type = self._infer_query_type(query_input)
        warnings = [query_input.pdf_parse_warning] if query_input.pdf_parse_warning else []
        return QueryProfile(
            query_type=query_type,
            title=title,
            abstract=abstract,
            topics=topics,
            tasks=tasks,
            methods=methods,
            domains=domains,
            datasets=datasets,
            keywords=keywords,
            raw_text=raw_text,
            warnings=warnings,
        )

    def enrich_candidate(self, paper: CandidatePaper) -> CandidatePaper:
        combined = "\n".join(
            part
            for part in [paper.title, paper.abstract, " ".join(paper.fields_of_study)]
            if part
        )
        paper.keywords = self._dedupe(paper.keywords + self.extract_keywords(combined))
        paper.topics = self._dedupe(paper.fields_of_study + self.extract_topics(combined))
        paper.tasks = self.match_lexicon(combined, TASK_LEXICON)
        paper.methods = self.match_lexicon(combined, METHOD_LEXICON)
        paper.domains = self.match_lexicon(combined, DOMAIN_LEXICON)
        paper.datasets = self.match_lexicon(combined, DATASET_HINTS)
        return paper

    def extract_keywords(self, text: str, limit: int = 12) -> list[str]:
        expanded = self._expand_chinese_hints(text)
        tokens = [token for token in self._tokenize(expanded) if token not in STOPWORDS]
        unigram_counts = Counter(token for token in tokens if len(token) > 2)
        bigram_counts = Counter()
        for left, right in zip(tokens, tokens[1:]):
            if left in STOPWORDS or right in STOPWORDS:
                continue
            if len(left) <= 2 or len(right) <= 2:
                continue
            bigram_counts[f"{left} {right}"] += 1
        phrases = [item for item, _ in bigram_counts.most_common(limit // 2)]
        singles = [item for item, _ in unigram_counts.most_common(limit)]
        return self._dedupe(phrases + singles)[:limit]

    def extract_topics(self, text: str, limit: int = 8) -> list[str]:
        expanded = self._expand_chinese_hints(text)
        candidates = self.match_lexicon(expanded, DOMAIN_LEXICON)
        candidates += self.match_lexicon(expanded, METHOD_LEXICON)
        candidates += self.extract_keywords(expanded, limit=limit)
        return self._dedupe(candidates)[:limit]

    def match_lexicon(
        self,
        text: str,
        lexicon: dict[str, list[str]],
    ) -> list[str]:
        haystack = self._expand_chinese_hints(text).lower()
        hits: list[str] = []
        for canonical, synonyms in lexicon.items():
            for synonym in synonyms:
                if synonym.lower() in haystack:
                    hits.append(canonical)
                    break
        return self._dedupe(hits)

    def _infer_query_type(self, query_input: QueryInput) -> str:
        if query_input.pdf_filename:
            return "paper_pdf"
        if query_input.doi:
            return "doi"
        if query_input.arxiv_id:
            return "arxiv"
        if query_input.title and query_input.abstract:
            return "paper_text"
        if query_input.title:
            return "title"
        if query_input.abstract:
            return "abstract"
        return "topic_text"

    def _expand_chinese_hints(self, text: str) -> str:
        hints = [english for chinese, english in CHINESE_HINTS.items() if chinese in text]
        if not hints:
            return text
        return text + " " + " ".join(hints)

    def _tokenize(self, text: str) -> list[str]:
        normalized = text.lower()
        return re.findall(r"[a-z0-9][a-z0-9\-+]{1,}", normalized)

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
        return result
