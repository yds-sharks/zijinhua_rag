"""生成模型接口：支持 mock 模式，预留 api 模式。"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from evolution.schemas import GenerationRecord, RetrievalResult


class Generator:
    """生成模型包装器。

    当前支持：
    - mock: 返回固定格式模板，用于测试记录链路。
    - api: 预留接口，后续接入真实大模型。
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        gen_cfg = cfg.get("generation", {})
        self.mode = gen_cfg.get("mode", "mock")
        self.model_name = gen_cfg.get("model_name", "mock-model")
        self.mock_template = gen_cfg.get(
            "mock_template",
            "[MOCK] 基于检索到的 {num_chunks} 条文段，生成回答。",
        )

    def generate(self, query: str, selected_chunks: List[RetrievalResult]) -> GenerationRecord:
        """根据查询和选中文段生成回答。"""
        start = time.perf_counter()

        if self.mode == "mock":
            output = self._mock_generate(query, selected_chunks)
        elif self.mode == "api":
            output = self._api_generate(query, selected_chunks)
        else:
            raise ValueError(f"Unsupported generation mode: {self.mode}")

        latency_ms = (time.perf_counter() - start) * 1000
        return GenerationRecord(
            model=self.model_name,
            output=output,
            prompt=self._build_prompt(query, selected_chunks),
            latency_ms=latency_ms,
        )

    def _mock_generate(self, query: str, selected_chunks: List[RetrievalResult]) -> str:
        preview = "\n".join(
            f"[{i+1}] {r.text[:80]}..." if r.text else f"[{i+1}] (无文本)"
            for i, r in enumerate(selected_chunks)
        )
        return (
            self.mock_template.format(num_chunks=len(selected_chunks))
            + f"\n\n查询：{query}\n\n参考文段预览：\n{preview}"
        )

    def _api_generate(self, query: str, selected_chunks: List[RetrievalResult]) -> str:
        # 预留：接入真实大模型 API
        raise NotImplementedError("api 模式尚未实现，请先用 mock 模式测试记录链路。")

    def _build_prompt(self, query: str, selected_chunks: List[RetrievalResult]) -> str:
        context = "\n\n".join(
            f"文段 {i+1}（来源：{r.file_name or '未知'}）：\n{r.text or ''}"
            for i, r in enumerate(selected_chunks)
        )
        return f"请根据以下文段回答问题：{query}\n\n{context}"
