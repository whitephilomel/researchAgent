from __future__ import annotations

from research_agent.models import CandidatePaper, QueryProfile, RelevanceResult


class ExplanationService:
    def explain(
        self,
        query: QueryProfile,
        candidate: CandidatePaper,
        relevance: RelevanceResult,
    ) -> tuple[list[str], str, dict[str, list[str] | str]]:
        scores = relevance.dimension_scores
        reason_tags: list[str] = []
        if scores.get("topic_score", 0.0) >= 0.55:
            reason_tags.append("同研究主题")
        if scores.get("task_score", 0.0) >= 0.5:
            reason_tags.append("同研究任务")
        if scores.get("method_score", 0.0) >= 0.5:
            reason_tags.append("同方法路线")
        if scores.get("domain_score", 0.0) >= 0.45:
            reason_tags.append("同应用领域")
        if scores.get("dataset_score", 0.0) >= 0.45:
            reason_tags.append("使用相同数据集")
        if scores.get("keyword_score", 0.0) >= 0.55:
            reason_tags.append("关键术语高度重合")
        if not reason_tags and "Review" in candidate.publication_types:
            reason_tags.append("背景/综述价值高")
        if not reason_tags and candidate.citation_count >= 100:
            reason_tags.append("高引用背景论文")
        if not reason_tags:
            reason_tags.append("同领域背景材料")

        reason_text = (
            f"该论文被判定为{relevance.relevance_label}（{relevance.relevance_level}级），"
            f"主要依据是{ '、'.join(reason_tags[:3]) }。"
        )
        if relevance.confidence < 0.55:
            reason_text += "当前输入或候选元数据不够完整，建议结合摘要与原文进一步核验。"
        elif candidate.citation_count:
            reason_text += f" 该论文当前引用量约为 {candidate.citation_count}，可作为进一步追踪的重要线索。"

        comparison = self._build_comparison(query, candidate, scores)
        return reason_tags, reason_text, comparison

    def _build_comparison(
        self,
        query: QueryProfile,
        candidate: CandidatePaper,
        scores: dict[str, float],
    ) -> dict[str, list[str] | str]:
        similarities: list[str] = []
        differences: list[str] = []
        self._compare_dimension(
            "研究主题",
            query.topics,
            candidate.topics or candidate.fields_of_study,
            scores.get("topic_score", 0.0),
            similarities,
            differences,
        )
        self._compare_dimension(
            "研究任务",
            query.tasks,
            candidate.tasks,
            scores.get("task_score", 0.0),
            similarities,
            differences,
        )
        self._compare_dimension(
            "方法",
            query.methods,
            candidate.methods,
            scores.get("method_score", 0.0),
            similarities,
            differences,
        )
        self._compare_dimension(
            "数据集",
            query.datasets,
            candidate.datasets,
            scores.get("dataset_score", 0.0),
            similarities,
            differences,
        )
        self._compare_dimension(
            "应用领域",
            query.domains,
            candidate.domains,
            scores.get("domain_score", 0.0),
            similarities,
            differences,
        )
        if not similarities:
            similarities.append("与查询存在一定主题或术语关联，但直接重合点有限。")
        if not differences:
            differences.append("未发现明显冲突维度，更适合作为补充阅读。")
        summary = f"相似点 {len(similarities)} 项，差异点 {len(differences)} 项。"
        return {
            "similarities": similarities,
            "differences": differences,
            "summary": summary,
        }

    def _compare_dimension(
        self,
        label: str,
        query_items: list[str],
        candidate_items: list[str],
        score: float,
        similarities: list[str],
        differences: list[str],
    ) -> None:
        query_set = {item.lower() for item in query_items}
        candidate_set = {item.lower() for item in candidate_items}
        overlap = sorted(query_set & candidate_set)
        if score >= 0.5 and overlap:
            similarities.append(f"{label}重合：{', '.join(overlap[:3])}")
        elif score >= 0.5:
            similarities.append(f"{label}整体相近。")
        elif query_items and candidate_items and score <= 0.2:
            differences.append(
                f"{label}差异较大：查询侧为 {', '.join(query_items[:2])}，候选侧为 {', '.join(candidate_items[:2])}。"
            )
