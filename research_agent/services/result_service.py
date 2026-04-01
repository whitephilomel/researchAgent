from __future__ import annotations

from collections import Counter, defaultdict

from research_agent.models import ClusterSummary, QueryProfile, RankedPaper


class ResultService:
    def sort_results(
        self,
        results: list[RankedPaper],
        sort_by: str = "relevance_score",
    ) -> list[RankedPaper]:
        if sort_by == "year":
            return sorted(results, key=lambda item: (item.year or 0, item.relevance_score), reverse=True)
        if sort_by == "citation_count":
            return sorted(results, key=lambda item: (item.citation_count, item.relevance_score), reverse=True)
        return sorted(
            results,
            key=lambda item: (item.relevance_score, item.citation_count, item.year or 0),
            reverse=True,
        )

    def filter_results(
        self,
        results: list[RankedPaper],
        levels: set[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RankedPaper]:
        filtered: list[RankedPaper] = []
        for item in results:
            if levels and item.relevance_level not in levels:
                continue
            if year_from and (item.year or 0) < year_from:
                continue
            if year_to and (item.year or 0) > year_to:
                continue
            filtered.append(item)
        return filtered

    def cluster_results(self, results: list[RankedPaper]) -> list[ClusterSummary]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in results:
            label = self._cluster_label(item)
            item.cluster_label = label
            grouped[label].append(item.paper_id)
        clusters = [ClusterSummary(label=label, size=len(paper_ids), paper_ids=paper_ids) for label, paper_ids in grouped.items()]
        return sorted(clusters, key=lambda cluster: cluster.size, reverse=True)

    def build_overview_summary(
        self,
        query: QueryProfile,
        results: list[RankedPaper],
        clusters: list[ClusterSummary],
    ) -> str:
        if not results:
            return "当前未检索到合适的候选论文，建议补充摘要、关键词或更具体的研究问题。"
        cluster_text = "、".join(cluster.label for cluster in clusters[:3]) or "一个主要方向"
        method_counter = Counter(
            method
            for result in results[:10]
            for method in result.methods[:2]
        )
        common_methods = "、".join(method for method, _ in method_counter.most_common(3)) or "多种方法路线"
        representative = "；".join(result.title for result in results[:3])
        topic_text = "、".join(query.topics[:3] or query.keywords[:3]) or "当前查询主题"
        return (
            f"围绕 {topic_text}，结果主要聚集在 {cluster_text} 等方向。"
            f"高频方法包括 {common_methods}。"
            f"代表性论文有：{representative}。"
        )

    def _cluster_label(self, item: RankedPaper) -> str:
        if item.domains:
            return item.domains[0].title()
        if item.methods:
            return item.methods[0].title()
        if item.topics:
            return item.topics[0].title()
        return "General Background"
