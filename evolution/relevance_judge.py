"""相关性裁判：LLM 零样本批量判定 top-k 文段与查询的相关性。

替代人工标注。判定结果写回 case.retrieval.results[i].is_relevant / notes。
"""

from __future__ import annotations

from typing import Any, Dict, List

from evolution.llm_client import LLMClient
from evolution.schemas import QueryCase

JUDGE_SYSTEM_PROMPT = """\
你是医学文献检索的相关性裁判。给定一个用户查询和若干检索文段，逐条判断该文段\
是否包含有助于回答查询的医学信息（诊断、机制、治疗、统计、分期、检查方法等）。

判定标准：
- relevant=true：文段直接或部分回答了查询的核心问题；
- relevant=false：文段与查询主题无关，或仅 superficial 相似（同词不同义）。

严格只输出 JSON，格式：
{"judgements": [{"rank": <编号>, "relevant": true/false, "reason": "<不超过30字>"}]}
"""


class RelevanceJudge:
    """LLM 相关性裁判。"""

    def __init__(self, cfg: Dict[str, Any], llm: "LLMClient | None" = None):
        self.cfg = cfg
        self.llm = llm or LLMClient(cfg)
        self.batch_size = int(cfg.get("second_layer", {}).get("judge_batch_size", 10))

    def judge_case(self, case: QueryCase) -> QueryCase:
        """判定一条 case 的全部检索结果，并写回 is_relevant/notes。"""
        results = case.retrieval.get("results", [])
        if not results:
            return case
        for start in range(0, len(results), self.batch_size):
            batch = results[start : start + self.batch_size]
            judgements = self._judge_batch(case.query, batch)
            self._write_back(batch, judgements)
        return case

    def _judge_batch(self, query: str, results: List) -> List[Dict[str, Any]]:
        lines = []
        for r in results:
            text = (r.text or "").replace("\n", " ")
            if len(text) > 300:
                text = text[:300] + "..."
            lines.append(f"[{r.rank}] {text}")
        user_prompt = f"查询：{query}\n\n待判定文段：\n" + "\n".join(lines)

        data = self.llm.chat_json(JUDGE_SYSTEM_PROMPT, user_prompt)
        judgements = data.get("judgements", []) if isinstance(data, dict) else []
        return judgements

    @staticmethod
    def _write_back(results: List, judgements: List[Dict[str, Any]]) -> None:
        by_rank = {}
        for j in judgements:
            try:
                by_rank[int(j.get("rank"))] = j
            except (TypeError, ValueError):
                continue
        for r in results:
            j = by_rank.get(r.rank)
            if j is None:
                # 裁判漏判时保持 None（unknown），不阻塞流水线
                continue
            r.is_relevant = bool(j.get("relevant"))
            r.notes = str(j.get("reason", ""))[:100]
