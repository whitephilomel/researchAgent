import unittest

from research_agent.models import QueryInput
from research_agent.services.profile_service import ProfileService


class ProfileServiceTest(unittest.TestCase):
    def test_build_query_profile_extracts_core_dimensions(self) -> None:
        service = ProfileService()
        query_input = QueryInput(
            title="Transformer-based multimodal medical imaging report generation",
            abstract="We study multimodal medical imaging report generation with contrastive learning and retrieval augmented generation.",
            keywords=["medical imaging", "report generation"],
            topic_text="希望找到适合医学影像报告生成的多模态 Transformer 与 RAG 论文。",
        )

        profile = service.build_query_profile(query_input)

        self.assertIn("transformer", profile.methods)
        self.assertIn("report generation", profile.tasks)
        self.assertIn("medical imaging", profile.domains)
        self.assertTrue(profile.keywords)


if __name__ == "__main__":
    unittest.main()
