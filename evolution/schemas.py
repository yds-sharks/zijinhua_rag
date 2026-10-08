"""第一层记录循环的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class CaseLabel(str, Enum):
    """查询 case 的人工/自动标签。"""
    SUCCESS = "success"       # 检索与生成均满意
    FAILED = "failed"         # 检索或生成不满意
    PENDING = "pending"       # 待分析
    AUTO = "auto"             # 仅自动记录，未人工 review


class ConfusionCategory(str, Enum):
    """top30 中文段与用户意图的混淆分类。"""
    HIT_TOP = "hit_top"           # 检索对了，排序靠前
    HIT_BOTTOM = "hit_bottom"     # 检索对了，排序靠后
    FALSE_TOP = "false_top"       # 检索错了，排序靠前
    FALSE_BOTTOM = "false_bottom" # 检索错了，排序靠后
    UNKNOWN = "unknown"           # 尚未分析


class RewriteStrategy(str, Enum):
    """改造策略（第二层）。"""
    SPLIT = "SPLIT"                     # 拆分主题混杂
    CONTEXTUALIZE = "CONTEXTUALIZE"     # 补全疾病主体
    ANCHOR = "ANCHOR"                   # 增加诊断锚点
    RETIRE = "RETIRE"                   # 抑制重复竞争


class OverlayStatus(str, Enum):
    """OverlayUnit 生命周期状态。"""
    PENDING = "pending"       # 待裁决
    ACCEPTED = "accepted"     # 裁决通过，参与检索
    REJECTED = "rejected"     # 裁决拒绝
    DISABLED = "disabled"     # 人工停用（可回滚）


@dataclass
class RetrievalResult:
    """单条检索结果。"""
    rank: int
    pk: int
    score: float
    dense: Optional[float] = None
    sparse: Optional[float] = None
    file_name: Optional[str] = None
    text: Optional[str] = None
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_relevant: Optional[bool] = None
    confusion_category: ConfusionCategory = ConfusionCategory.UNKNOWN
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confusion_category"] = self.confusion_category.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievalResult":
        data = dict(data)
        data["confusion_category"] = ConfusionCategory(
            data.get("confusion_category", "unknown")
        )
        return cls(**data)


@dataclass
class GenerationRecord:
    """生成模型输出记录。"""
    model: str
    output: str
    prompt: Optional[str] = None
    has_hallucination: Optional[bool] = None
    is_satisfactory: Optional[bool] = None
    latency_ms: Optional[float] = None


@dataclass
class OverlayUnit:
    """PatchOverlay 单元：对 BaseIndex 已有文段的优化检索表达。"""
    overlay_id: str
    source_pk: int
    source_file_name: Optional[str]
    source_text: str
    trigger_case_id: str
    trigger_query: str
    strategy: RewriteStrategy
    strategy_reason: str
    rewritten_text: str
    status: OverlayStatus = OverlayStatus.PENDING
    judge_report_id: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OverlayUnit":
        data = dict(data)
        data["strategy"] = RewriteStrategy(data.get("strategy", "ANCHOR"))
        data["status"] = OverlayStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class JudgeReport:
    """自动裁决报告。"""
    judge_id: str
    overlay_id: str
    target_case_id: str
    target_query: str
    metrics_before: Dict[str, Any] = field(default_factory=dict)
    metrics_after: Dict[str, Any] = field(default_factory=dict)
    global_regression: bool = False
    conflict_detected: bool = False
    passed: bool = False
    reason: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QueryCase:
    """一次查询的完整记录档案。"""
    case_id: str
    query: str
    timestamp: str
    retrieval: Dict[str, Any] = field(default_factory=dict)
    selected_chunks: List[int] = field(default_factory=list)
    generation: Optional[GenerationRecord] = None
    label: CaseLabel = CaseLabel.AUTO
    tags: List[str] = field(default_factory=list)
    related_overlay_ids: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    triage: Optional[str] = None  # ok | overlay_rewrite | knowledge_injection

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["label"] = self.label.value
        if self.generation:
            d["generation"] = asdict(self.generation)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueryCase":
        data = dict(data)
        data["label"] = CaseLabel(data.get("label", "auto"))
        gen = data.pop("generation", None)
        if gen:
            data["generation"] = GenerationRecord(**gen)
        if "retrieval" in data and "results" in data["retrieval"]:
            data["retrieval"]["results"] = [
                RetrievalResult.from_dict(r) for r in data["retrieval"]["results"]
            ]
        return cls(**data)

    @classmethod
    def create(
        cls,
        query: str,
        retrieval_results: List[RetrievalResult],
        selected_chunks: List[int],
        generation: Optional[GenerationRecord] = None,
        topk: int = 30,
    ) -> "QueryCase":
        timestamp = datetime.now(timezone.utc).isoformat()
        case_id = f"case_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        return cls(
            case_id=case_id,
            query=query,
            timestamp=timestamp,
            retrieval={
                "topk": topk,
                "results": [r.to_dict() for r in retrieval_results],
            },
            selected_chunks=selected_chunks,
            generation=generation,
        )
