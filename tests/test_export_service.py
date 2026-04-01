import unittest

from research_agent.services.export_service import ExportService


class ExportServiceTest(unittest.TestCase):
    def test_export_generates_csv_and_markdown(self) -> None:
        service = ExportService()
        payload = {
            "query_type": "topic_text",
            "query_summary": {
                "topics": ["medical imaging"],
                "tasks": ["report generation"],
            },
            "results": [
                {
                    "relevance_level": "A",
                    "relevance_score": 0.91,
                    "confidence": 0.76,
                    "year": 2024,
                    "title": "Example Paper",
                    "authors": ["Alice", "Bob"],
                    "venue": "NeurIPS",
                    "citation_count": 123,
                    "reason_text": "Highly aligned with the query.",
                }
            ],
        }

        csv_content, _, _ = service.export("csv", payload)
        md_content, _, _ = service.export("md", payload)

        self.assertIn("Example Paper", csv_content)
        self.assertIn("# ResearchAgent Export", md_content)
        self.assertIn("Highly aligned with the query.", md_content)


if __name__ == "__main__":
    unittest.main()
