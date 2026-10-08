"""混淆自动分类器：相关性 × rank 位置 → 四分类（纯规则）。

并负责失败 case 的自动分流：
- top-k 内无相关文段            → knowledge_injection（第三层：知识缺口）
- 相关文段被埋没 / 误排文段靠前 → overlay_rewrite（第二层：表达问题）
- 其余                          → ok
"""

from __future__ import annotations

from typing import Any, Dict, List

from evolution.schemas import ConfusionCategory, QueryCase, RetrievalResult

# 默认"靠前"阈值：前 5 名视为靠前（对应 select_topk 的默认值）
DEFAULT_HIT_K = 5

TriageDecision = str  # "ok" | "overlay_rewrite" | "knowledge_injection"


def classify(rank: int, is_relevant: bool | None, hit_k: int = DEFAULT_HIT_K) -> ConfusionCategory:
    """单条文段的混淆分类。is_relevant 未知时返回 unknown。"""
    if is_relevant is None:
        return ConfusionCategory.UNKNOWN
    front = rank <= hit_k
    if is_relevant and front:
        return ConfusionCategory.HIT_TOP
    if is_relevant and not front:
        return ConfusionCategory.HIT_BOTTOM
    if not is_relevant and front:
        return ConfusionCategory.FALSE_TOP
    return ConfusionCategory.FALSE_BOTTOM


def apply_case(case: QueryCase, hit_k: int = DEFAULT_HIT_K) -> QueryCase:
    """对一条 case 的全部检索结果做混淆分类，并写回 confusion_category。"""
    for r in case.retrieval.get("results", []):
        r.confusion_category = classify(r.rank, r.is_relevant, hit_k)
    return case


def analyze(case: QueryCase, hit_k: int = DEFAULT_HIT_K) -> Dict[str, Any]:
    """分类 + 统计 + 分流结论。不修改 case，返回分析报告。"""
    apply_case(case, hit_k)
    results: List[RetrievalResult] = case.retrieval.get("results", [])

    counts = {c.value: 0 for c in ConfusionCategory}
    relevant_in_topk = 0
    for r in results:
        counts[r.confusion_category.value] += 1
        if r.is_relevant and r.rank <= hit_k:
            relevant_in_topk += 1

    decision = triage(counts, relevant_in_topk)
    return {
        "case_id": case.case_id,
        "category_counts": counts,
        "relevant_in_topk": relevant_in_topk,
        "decision": decision,
        "reason": _reason(counts, relevant_in_topk),
    }


def triage(counts: Dict[str, int], relevant_in_topk: int) -> TriageDecision:
    """根据混淆分布决定走第二层改造还是第三层注入。"""
    if relevant_in_topk == 0 and counts.get("unknown", 0) == 0:
        # top-k 内没有任何相关文段：库里没有能回答的知识
        return "knowledge_injection"
    if counts.get("hit_bottom", 0) > 0 or counts.get("false_top", 0) > 0:
        # 有知识但表达/排序有问题：需要改造
        return "overlay_rewrite"
    return "ok"


def _reason(counts: Dict[str, int], relevant_in_topk: int) -> str:
    if relevant_in_topk == 0 and counts.get("unknown", 0) == 0:
        return "top-k 内无相关文段，疑似知识缺口，建议走第三层外部注入。"
    if counts.get("hit_bottom", 0) > 0 and counts.get("false_top", 0) > 0:
        return "存在被埋没的相关文段和误排靠前的不相关文段，建议改造两类文段。"
    if counts.get("hit_bottom", 0) > 0:
        return "存在相关文段被埋没，建议 ANCHOR/CONTEXTUALIZE 提升。"
    if counts.get("false_top", 0) > 0:
        return "存在不相关文段误排靠前，建议 RETIRE/SPLIT 抑制。"
    return "检索分布正常。"
