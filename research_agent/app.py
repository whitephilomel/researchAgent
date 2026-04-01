from __future__ import annotations

from flask import Flask, jsonify, make_response, render_template, request

from research_agent.adapters import SemanticScholarAdapter
from research_agent.config import Settings
from research_agent.services.explanation_service import ExplanationService
from research_agent.services.export_service import ExportService
from research_agent.services.input_service import InputService
from research_agent.services.profile_service import ProfileService
from research_agent.services.result_service import ResultService
from research_agent.services.scoring_service import ScoringService
from research_agent.services.search_service import SearchService


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = settings.secret_key

    input_service = InputService(settings)
    profile_service = ProfileService()
    adapter = SemanticScholarAdapter(settings)
    scoring_service = ScoringService(settings)
    explanation_service = ExplanationService()
    result_service = ResultService()
    export_service = ExportService()
    search_service = SearchService(
        settings=settings,
        adapter=adapter,
        profile_service=profile_service,
        scoring_service=scoring_service,
        explanation_service=explanation_service,
        result_service=result_service,
    )

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            search_limit=settings.search_limit,
            max_search_limit=settings.max_search_limit,
            level_labels=settings.level_labels,
        )

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok", "service": settings.app_name}, 200

    @app.post("/api/search")
    def api_search():
        try:
            query_input = input_service.parse_http_request(request)
            response = search_service.search(query_input)
            return jsonify(response.to_dict())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"搜索失败: {exc}"}), 500

    @app.post("/api/export")
    def api_export():
        payload = request.get_json(silent=True) or {}
        export_format = str(payload.get("format", "json"))
        search_response = payload.get("search_response")
        if not search_response:
            return jsonify({"error": "导出失败：缺少 search_response。"}), 400
        try:
            content, mimetype, extension = export_service.export(export_format, search_response)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        response = make_response(content)
        response.headers["Content-Type"] = mimetype
        response.headers["Content-Disposition"] = (
            f"attachment; filename=research_results.{extension}"
        )
        return response

    return app
