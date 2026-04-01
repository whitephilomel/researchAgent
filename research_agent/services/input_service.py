from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from werkzeug.datastructures import FileStorage

from research_agent.config import Settings
from research_agent.models import QueryInput

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


class InputService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def parse_http_request(self, flask_request: Any) -> QueryInput:
        if flask_request.is_json:
            payload = flask_request.get_json(silent=True) or {}
            return self._from_payload(payload)
        return self._from_form(flask_request.form, flask_request.files)

    def _from_payload(self, payload: dict[str, Any]) -> QueryInput:
        query = QueryInput(
            title=str(payload.get("title", "") or "").strip(),
            abstract=str(payload.get("abstract", "") or "").strip(),
            keywords=self._split_keywords(payload.get("keywords", [])),
            doi=self._normalize_doi(str(payload.get("doi", "") or "")),
            arxiv_id=self._normalize_arxiv_id(str(payload.get("arxiv_id", "") or "")),
            topic_text=str(payload.get("topic_text", "") or "").strip(),
            pdf_filename=str(payload.get("pdf_filename", "") or "").strip(),
            pdf_text=str(payload.get("pdf_text", "") or "").strip(),
            result_limit=self._parse_result_limit(payload.get("result_limit")),
            page=self._parse_page(payload.get("page")),
            exhaustive_search=self._parse_bool(payload.get("exhaustive_search")),
            search_session_id=str(payload.get("search_session_id", "") or "").strip(),
        )
        self.validate(query)
        return query

    def _from_form(self, form: Any, files: Any) -> QueryInput:
        query = QueryInput(
            title=str(form.get("title", "") or "").strip(),
            abstract=str(form.get("abstract", "") or "").strip(),
            keywords=self._split_keywords(form.get("keywords", "")),
            doi=self._normalize_doi(str(form.get("doi", "") or "")),
            arxiv_id=self._normalize_arxiv_id(str(form.get("arxiv_id", "") or "")),
            topic_text=str(form.get("topic_text", "") or "").strip(),
            result_limit=self._parse_result_limit(form.get("result_limit")),
            page=self._parse_page(form.get("page")),
            exhaustive_search=self._parse_bool(form.get("exhaustive_search")),
            search_session_id=str(form.get("search_session_id", "") or "").strip(),
        )
        uploaded = files.get("pdf_file") if files else None
        if uploaded and getattr(uploaded, "filename", ""):
            pdf_payload = self.parse_pdf_upload(uploaded)
            query.pdf_filename = pdf_payload["filename"]
            query.pdf_text = pdf_payload["text"]
            query.pdf_parse_warning = pdf_payload["warning"]
            if not query.title:
                query.title = pdf_payload["title"]
            if not query.doi and pdf_payload["doi"]:
                query.doi = pdf_payload["doi"]
            if not query.arxiv_id and pdf_payload["arxiv_id"]:
                query.arxiv_id = pdf_payload["arxiv_id"]
        self.validate(query)
        return query

    def validate(self, query: QueryInput) -> None:
        if not query.search_session_id and not query.has_any_content():
            raise ValueError("请至少提供标题、摘要、关键词、DOI、arXiv ID、研究描述或 PDF 文件。")
        if query.title and len(query.title) > 500:
            raise ValueError("标题长度不能超过 500 个字符。")
        if query.abstract and len(query.abstract) > 12000:
            raise ValueError("摘要长度不能超过 12000 个字符。")
        if query.topic_text and len(query.topic_text) > 12000:
            raise ValueError("研究描述长度不能超过 12000 个字符。")
        if query.doi and "/" not in query.doi:
            raise ValueError("DOI 格式无效，请检查后重试。")
        if not (1 <= query.result_limit <= self.settings.max_search_limit):
            raise ValueError(f"返回条数必须在 1 到 {self.settings.max_search_limit} 之间。")
        if query.page < 1:
            raise ValueError("页码必须大于等于 1。")

    def parse_pdf_upload(self, uploaded: FileStorage) -> dict[str, str]:
        filename = (uploaded.filename or "").strip()
        if not filename.lower().endswith(".pdf"):
            raise ValueError("仅支持 PDF 文件上传。")
        raw_bytes = uploaded.read()
        if len(raw_bytes) > self.settings.max_pdf_size_bytes:
            raise ValueError("PDF 文件过大，请控制在 15MB 以内。")
        if not raw_bytes:
            raise ValueError("上传的 PDF 文件为空。")
        raw_text = raw_bytes.decode("latin-1", errors="ignore")
        title = self._clean_filename_title(filename)
        doi = self._extract_doi(raw_text)
        arxiv_id = self._extract_arxiv_id(raw_text)
        text = ""
        warning = ""
        if PdfReader is not None:
            try:
                uploaded.stream.seek(0)
                reader = PdfReader(uploaded.stream)
                chunks: list[str] = []
                for page in reader.pages[:5]:
                    extracted = page.extract_text() or ""
                    if extracted:
                        chunks.append(extracted)
                text = "\n".join(chunks).strip()
                if text:
                    title = self._extract_title_from_text(text) or title
            except Exception:
                warning = "PDF 已上传，但正文解析失败，系统已回退为文件名/标识级检索。"
        else:
            warning = "当前环境未安装 pypdf，系统已回退为文件名/标识级检索。"
        uploaded.stream.seek(0)
        return {
            "filename": filename,
            "title": title,
            "text": text,
            "warning": warning,
            "doi": doi,
            "arxiv_id": arxiv_id,
        }

    def _parse_result_limit(self, value: Any) -> int:
        if value is None or str(value).strip() == "":
            return self.settings.search_limit
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError("返回条数必须是整数。")
        return parsed

    def _parse_page(self, value: Any) -> int:
        if value is None or str(value).strip() == "":
            return 1
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError("页码必须是整数。")
        return parsed

    def _parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _split_keywords(self, value: Any) -> list[str]:
        if isinstance(value, list):
            items = value
        else:
            items = re.split(r"[,;；、\n]+", str(value or ""))
        return [item.strip() for item in items if str(item).strip()]

    def _normalize_doi(self, doi: str) -> str:
        cleaned = doi.strip()
        cleaned = re.sub(r"^https?://doi.org/", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^doi:\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _normalize_arxiv_id(self, arxiv_id: str) -> str:
        cleaned = arxiv_id.strip()
        cleaned = re.sub(r"^arxiv:\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _extract_doi(self, text: str) -> str:
        match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, flags=re.IGNORECASE)
        return match.group(0).rstrip(".") if match else ""

    def _extract_arxiv_id(self, text: str) -> str:
        match = re.search(r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", text, flags=re.IGNORECASE)
        return match.group(1) if match else ""

    def _clean_filename_title(self, filename: str) -> str:
        stem = Path(filename).stem
        stem = re.sub(r"[_-]+", " ", stem)
        stem = re.sub(r"\s+", " ", stem)
        return stem.strip()

    def _extract_title_from_text(self, text: str) -> str:
        for line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", line).strip()
            if 12 <= len(cleaned) <= 200 and cleaned.lower() != "abstract":
                return cleaned
        return ""
