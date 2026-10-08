"""第一层记录循环主入口：QueryLogger。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from evolution.case_store import CaseStore
from evolution.generator import Generator
from evolution.retriever import BaseRetriever
from evolution.schemas import CaseLabel, GenerationRecord, QueryCase, RetrievalResult
from evolution.selector import ResultSelector


class QueryLogger:
    """记录一次完整查询链路的主类。

    使用方式：
        logger = QueryLogger.from_config("evolution/config.yaml")
        case = logger.log("宫颈癌的病理诊断要点是什么？")
        print(case.case_id)
    """

    def __init__(
        self,
        cfg: Dict[str, Any],
        retriever: Optional[BaseRetriever] = None,
        selector: Optional[ResultSelector] = None,
        generator: Optional[Generator] = None,
        store: Optional[CaseStore] = None,
    ):
        self.cfg = cfg
        self.retriever = retriever or BaseRetriever(cfg)
        self.selector = selector or ResultSelector(cfg)
        self.generator = generator or Generator(cfg)
        self.store = store or self._build_store(cfg)
        self.auto_save = cfg.get("logging", {}).get("auto_save", True)
        self.default_label = cfg.get("logging", {}).get("default_label", "auto")
        self.verbose = cfg.get("logging", {}).get("verbose", True)

    @classmethod
    def from_config(cls, config_path: Path | str) -> "QueryLogger":
        """从 YAML 配置文件加载。"""
        config_path = Path(config_path).expanduser().resolve()
        with config_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cls(cfg)

    def _build_store(self, cfg: Dict[str, Any]) -> CaseStore:
        cases_dir = cfg.get("paths", {}).get("query_cases_dir", "./data/query_cases")
        # 支持相对 evolution/ 目录的路径
        if not Path(cases_dir).is_absolute():
            base = Path(__file__).resolve().parent
            cases_dir = base / cases_dir
        return CaseStore(cases_dir)

    def log(
        self,
        query: str,
        label: Optional[CaseLabel] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> QueryCase:
        """记录一次完整查询链路。"""
        record_topk = self.cfg.get("retrieval", {}).get("record_topk", 30)
        select_topk = self.cfg.get("retrieval", {}).get("select_topk", 5)

        # 1. 检索
        t0 = time.perf_counter()
        results = self.retriever.search(query, topk=record_topk)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        # 2. 选择最终文段
        selected = self.selector.select(results, select_topk=select_topk)
        selected_ids = [r.pk for r in selected]

        # 3. 生成回答
        generation = self.generator.generate(query, selected)

        # 4. 组装 QueryCase
        case = QueryCase.create(
            query=query,
            retrieval_results=results,
            selected_chunks=selected_ids,
            generation=generation,
            topk=record_topk,
        )
        case.label = label if label is not None else CaseLabel(self.default_label)
        case.tags = tags or []
        case.notes = notes
        case.retrieval["latency_ms"] = retrieval_ms

        # 5. 保存
        if self.auto_save:
            self.store.save(case)

        if self.verbose:
            self._print_summary(case)

        return case

    def label_case(
        self,
        case_id: str,
        label: CaseLabel,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        is_satisfactory: Optional[bool] = None,
        has_hallucination: Optional[bool] = None,
    ) -> QueryCase:
        """为已有 case 打标签（通常由研究者人工调用）。"""
        case = self.store.load(case_id)
        case.label = label
        if tags is not None:
            case.tags = tags
        if notes is not None:
            case.notes = notes
        if case.generation:
            if is_satisfactory is not None:
                case.generation.is_satisfactory = is_satisfactory
            if has_hallucination is not None:
                case.generation.has_hallucination = has_hallucination
        self.store.save(case)
        return case

    def list_cases(self) -> List[str]:
        """列出所有已记录的 case_id。"""
        return self.store.list_cases()

    def load_case(self, case_id: str) -> QueryCase:
        """加载指定 case。"""
        return self.store.load(case_id)

    def _print_summary(self, case: QueryCase) -> None:
        print(f"\n[QueryLogger] Case recorded: {case.case_id}")
        print(f"  query: {case.query}")
        print(f"  topk recorded: {case.retrieval.get('topk')}")
        print(f"  selected chunks: {case.selected_chunks}")
        print(f"  label: {case.label.value}")
        if case.generation:
            print(f"  generation model: {case.generation.model}")
            print(f"  generation latency: {case.generation.latency_ms:.1f} ms")
        print(f"  saved to: {self.store.cases_dir / f'{case.case_id}.json'}")
