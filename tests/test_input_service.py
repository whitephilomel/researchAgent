import unittest

from research_agent.config import Settings
from research_agent.services.input_service import InputService


class InputServiceTest(unittest.TestCase):
    def test_parse_result_limit_from_payload(self) -> None:
        service = InputService(Settings())
        query = service._from_payload({
            "topic_text": "graph neural network for recommendation",
            "result_limit": 250,
        })
        self.assertEqual(query.result_limit, 250)

    def test_validate_rejects_result_limit_above_cap(self) -> None:
        service = InputService(Settings())
        with self.assertRaises(ValueError):
            service._from_payload({
                "topic_text": "transformer retrieval",
                "result_limit": 1001,
            })

    def test_parse_session_paging_payload(self) -> None:
        service = InputService(Settings())
        query = service._from_payload({
            "search_session_id": "abc123",
            "page": 3,
            "result_limit": 50,
        })
        self.assertEqual(query.search_session_id, "abc123")
        self.assertEqual(query.page, 3)
        self.assertEqual(query.result_limit, 50)


if __name__ == "__main__":
    unittest.main()
