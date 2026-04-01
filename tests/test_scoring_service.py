import unittest

from research_agent.config import Settings
from research_agent.models import CandidatePaper, QueryProfile
from research_agent.services.scoring_service import ScoringService


class ScoringServiceTest(unittest.TestCase):
    def test_score_outputs_high_relevance_for_close_match(self) -> None:
        service = ScoringService(Settings())
        query = QueryProfile(
            title="Multimodal medical imaging report generation",
            topics=["medical imaging", "multimodal learning"],
            tasks=["report generation"],
            methods=["transformer", "retrieval augmented generation"],
            domains=["medical imaging"],
            datasets=["mimic-cxr"],
            keywords=["medical imaging", "report generation", "transformer"],
        )
        candidate = CandidatePaper(
            paper_id="paper-1",
            title="Retrieval augmented transformer for multimodal medical imaging report generation",
            topics=["medical imaging", "multimodal learning"],
            tasks=["report generation"],
            methods=["transformer", "retrieval augmented generation"],
            domains=["medical imaging"],
            datasets=["mimic-cxr"],
            keywords=["transformer", "report generation"],
            fields_of_study=["Computer Science"],
            recall_sources=["ranked_search", "context_focus"],
        )

        result = service.score(query, candidate)

        self.assertGreater(result.relevance_score, 0.75)
        self.assertIn(result.relevance_level, {"A", "B"})
        self.assertGreater(result.confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
