"""包装现有病理检索链路，为记录循环提供统一接口。"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

# 将 pathology_retrieval 加入路径，以便本地直连模式调用
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RETRIEVAL_ROOT = _PROJECT_ROOT / "pathology_retrieval"
if str(_RETRIEVAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ROOT))

from call_pathology_vector_db import search as local_search, search_via_server  # noqa: E402

from evolution.schemas import RetrievalResult


class BaseRetriever:
    """基于现有病理向量库的统一检索器。

    支持两种模式：
    - server: 调用常驻 HTTP 服务（推荐，避免重复加载模型）。
    - local: 本地直连 Milvus Lite（适合服务未启动时测试）。
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.mode = cfg.get("retrieval", {}).get("mode", "server")
        self.server_url = cfg.get("retrieval", {}).get("server_url", "http://127.0.0.1:8765")
        self.local_config = cfg.get("retrieval", {}).get("local_config", "../pathology_retrieval/insert/config.yaml")
        self.timeout = cfg.get("retrieval", {}).get("timeout", 120.0)

    def search(self, query: str, topk: int = 30) -> List[RetrievalResult]:
        """执行检索，返回 RetrievalResult 列表。"""
        if self.mode == "server":
            raw = self._search_via_server(query, topk)
        elif self.mode == "local":
            raw = self._search_local(query, topk)
        else:
            raise ValueError(f"Unsupported retrieval mode: {self.mode}")
        return self._parse_results(raw)

    def _search_via_server(self, query: str, topk: int) -> Dict[str, Any]:
        try:
            return search_via_server(query, topk=topk, server_url=self.server_url, timeout=self.timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"无法连接常驻检索服务 {self.server_url}。"
                f"请先启动服务：cd pathology_retrieval && python3 pathology_vector_db_server.py。"
                f"原始错误：{exc}"
            ) from exc

    def _search_local(self, query: str, topk: int) -> Dict[str, Any]:
        config_path = Path(self.local_config).expanduser().resolve()
        return local_search(query, topk=topk, config_path=config_path)

    def _parse_results(self, raw: Dict[str, Any]) -> List[RetrievalResult]:
        results = []
        for rank, row in enumerate(raw.get("results", []), start=1):
            results.append(
                RetrievalResult(
                    rank=rank,
                    pk=int(row.get("pk", 0)),
                    score=float(row.get("score", 0.0)),
                    dense=float(row.get("dense")) if row.get("dense") is not None else None,
                    sparse=float(row.get("sparse")) if row.get("sparse") is not None else None,
                    file_name=row.get("file_name"),
                    text=row.get("text"),
                    summary=row.get("summary"),
                    metadata=row.get("metadata", {}),
                )
            )
        return results
