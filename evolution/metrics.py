"""检索评估指标：目标文段排名、Recall@k、MRR。"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from evolution.schemas import RetrievalResult


def target_best_rank(results: Sequence[RetrievalResult], target_pks: Iterable[int]) -> Optional[int]:
    """目标文段集合在结果中的最高（最小）排名；未命中返回 None。"""
    targets = set(target_pks)
    for r in results:
        if r.pk in targets:
            return r.rank
    return None


def recall_at_k(results: Sequence[RetrievalResult], relevant_pks: Iterable[int], k: int) -> float:
    """前 k 名中命中的相关文段比例。"""
    relevant = set(relevant_pks)
    if not relevant:
        return 0.0
    top_k = {r.pk for r in results[:k]}
    return len(top_k & relevant) / len(relevant)


def mrr(results: Sequence[RetrievalResult], relevant_pks: Iterable[int]) -> float:
    """首个相关文段排名的倒数（MRR）。"""
    relevant = set(relevant_pks)
    for r in results:
        if r.pk in relevant:
            return 1.0 / r.rank
    return 0.0


def category_counts(results: Sequence[RetrievalResult]) -> dict:
    """统计四类混淆分布。"""
    counts = {"hit_top": 0, "hit_bottom": 0, "false_top": 0, "false_bottom": 0, "unknown": 0}
    for r in results:
        counts[r.confusion_category.value] += 1
    return counts


def summarize(results: List[RetrievalResult], relevant_pks: Iterable[int], k: int = 5) -> dict:
    """一次评估的完整指标汇总。"""
    relevant = list(relevant_pks)
    return {
        "recall@k": recall_at_k(results, relevant, k),
        "k": k,
        "mrr": mrr(results, relevant),
        "target_best_rank": target_best_rank(results, relevant),
        "num_results": len(results),
        "category_counts": category_counts(results),
    }
