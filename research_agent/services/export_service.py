from __future__ import annotations

import csv
import io
import json
from typing import Any


class ExportService:
    def export(self, export_format: str, payload: dict[str, Any]) -> tuple[str, str, str]:
        normalized = export_format.lower()
        if normalized == "json":
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json; charset=utf-8", "json"
        if normalized == "csv":
            return self._to_csv(payload), "text/csv; charset=utf-8", "csv"
        if normalized == "md":
            return self._to_markdown(payload), "text/markdown; charset=utf-8", "md"
        raise ValueError("仅支持导出 JSON、CSV 或 Markdown。")

    def _to_csv(self, payload: dict[str, Any]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "relevance_level",
                "relevance_score",
                "confidence",
                "year",
                "title",
                "authors",
                "venue",
                "citation_count",
                "reason_text",
            ],
        )
        writer.writeheader()
        for item in payload.get("results", []):
            writer.writerow(
                {
                    "relevance_level": item.get("relevance_level", ""),
                    "relevance_score": item.get("relevance_score", ""),
                    "confidence": item.get("confidence", ""),
                    "year": item.get("year", ""),
                    "title": item.get("title", ""),
                    "authors": "; ".join(item.get("authors", [])),
                    "venue": item.get("venue", ""),
                    "citation_count": item.get("citation_count", 0),
                    "reason_text": item.get("reason_text", ""),
                }
            )
        return buffer.getvalue()

    def _to_markdown(self, payload: dict[str, Any]) -> str:
        lines = [
            "# ResearchAgent Export",
            "",
            "## Query Summary",
            f"- Query Type: {payload.get('query_type', '')}",
            f"- Topics: {', '.join(payload.get('query_summary', {}).get('topics', []))}",
            f"- Tasks: {', '.join(payload.get('query_summary', {}).get('tasks', []))}",
            "",
            "## Results",
            "| Level | Score | Year | Title | Venue | Reason |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in payload.get("results", []):
            reason = item.get("reason_text", "").replace("|", "/")
            title = item.get("title", "").replace("|", "/")
            venue = item.get("venue", "").replace("|", "/")
            lines.append(
                f"| {item.get('relevance_level', '')} | {item.get('relevance_score', '')} | {item.get('year', '')} | {title} | {venue} | {reason} |"
            )
        return "\n".join(lines)
