from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from research_agent.models import CandidatePaper


class BasePaperAdapter(ABC):
    name = "base"

    @abstractmethod
    def lookup_paper(self, identifier: str) -> CandidatePaper | None:
        raise NotImplementedError

    @abstractmethod
    def match_title(self, title: str) -> CandidatePaper | None:
        raise NotImplementedError

    @abstractmethod
    def search_ranked(self, query: str, limit: int) -> list[CandidatePaper]:
        raise NotImplementedError

    @abstractmethod
    def search_bulk(self, query: str, limit: int) -> list[CandidatePaper]:
        raise NotImplementedError

    @abstractmethod
    def search_bulk_all(
        self,
        query: str,
        max_items: int | None = None,
    ) -> tuple[list[CandidatePaper], dict[str, Any]]:
        raise NotImplementedError
