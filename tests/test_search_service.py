import unittest

from research_agent.adapters.base import BasePaperAdapter
from research_agent.config import Settings
from research_agent.models import CandidatePaper, QueryInput
from research_agent.services.explanation_service import ExplanationService
from research_agent.services.profile_service import ProfileService
from research_agent.services.result_service import ResultService
from research_agent.services.scoring_service import ScoringService
from research_agent.services.search_service import SearchService


class FakeAdapter(BasePaperAdapter):
    name = "FakeAdapter"

    def lookup_paper(self, identifier: str):
        return None

    def match_title(self, title: str):
        return None

    def search_ranked(self, query: str, limit: int):
        return self._build_items(limit, prefix="ranked")

    def search_bulk(self, query: str, limit: int):
        return self._build_items(limit, prefix="bulk")

    def search_bulk_all(self, query: str, max_items=None):
        total = 45 if max_items is None else min(max_items, 45)
        return self._build_items(total, prefix="all"), {
            "pages_fetched": 2,
            "total_available": 45,
            "completed": True,
        }

    def _build_items(self, count: int, prefix: str):
        items = []
        for index in range(count):
            items.append(
                CandidatePaper(
                    paper_id=f"{prefix}-{index}",
                    title=f"Transformer medical imaging paper {index}",
                    authors=["Author A"],
                    year=2024 - (index % 3),
                    venue="TestConf",
                    abstract="Transformer for medical imaging report generation and retrieval.",
                    citation_count=200 - index,
                    source_name=self.name,
                    source_url=f"https://example.org/{prefix}-{index}",
                    recall_sources=[prefix],
                )
            )
        return items


class SearchServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        SearchService._cache.clear()
        self.service = SearchService(
            settings=Settings(),
            adapter=FakeAdapter(),
            profile_service=ProfileService(),
            scoring_service=ScoringService(Settings()),
            explanation_service=ExplanationService(),
            result_service=ResultService(),
        )

    def test_exhaustive_search_returns_pagination_meta(self) -> None:
        response = self.service.search(
            QueryInput(
                topic_text="transformer for medical imaging report generation",
                exhaustive_search=True,
                result_limit=10,
                page=1,
            )
        )
        self.assertEqual(response.meta["page"], 1)
        self.assertEqual(response.meta["page_size"], 10)
        self.assertGreaterEqual(response.meta["total_pages"], 2)
        self.assertTrue(response.meta["search_session_id"])
        self.assertEqual(response.meta["search_mode"], "exhaustive")

    def test_cached_session_can_fetch_second_page(self) -> None:
        first = self.service.search(
            QueryInput(
                topic_text="transformer for medical imaging report generation",
                exhaustive_search=True,
                result_limit=10,
                page=1,
            )
        )
        second = self.service.search(
            QueryInput(
                search_session_id=first.meta["search_session_id"],
                result_limit=10,
                page=2,
            )
        )
        self.assertEqual(second.meta["page"], 2)
        self.assertTrue(second.meta["cache_hit"])
        self.assertNotEqual(first.results[0].paper_id, second.results[0].paper_id)


if __name__ == "__main__":
    unittest.main()
