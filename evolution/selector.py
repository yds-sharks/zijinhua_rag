"""从检索结果中选择最终喂给生成模型的文段。"""

from __future__ import annotations

from typing import Any, Dict, List

from evolution.schemas import RetrievalResult


class ResultSelector:
    """根据配置策略，从 top-k 检索结果中选出最终用于生成的文段。"""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        selection_cfg = cfg.get("selection", {})
        self.strategy = selection_cfg.get("strategy", "topk")
        self.min_score = float(selection_cfg.get("min_score", 0.0))
        self.default_select_topk = cfg.get("retrieval", {}).get("select_topk", 5)

    def select(self, results: List[RetrievalResult], select_topk: int | None = None) -> List[RetrievalResult]:
        """根据策略返回选中的 RetrievalResult 列表。"""
        if not results:
            return []

        k = select_topk if select_topk is not None else self.default_select_topk

        if self.strategy == "topk":
            return results[:k]

        if self.strategy == "threshold":
            filtered = [r for r in results if r.score >= self.min_score]
            return filtered[:k]

        raise ValueError(f"Unsupported selection strategy: {self.strategy}")

    def select_chunk_ids(self, results: List[RetrievalResult], select_topk: int | None = None) -> List[int]:
        """返回选中的文段 pk 列表。"""
        selected = self.select(results, select_topk)
        return [r.pk for r in selected]
