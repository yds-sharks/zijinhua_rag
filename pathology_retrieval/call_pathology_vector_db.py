#!/usr/bin/env python3
"""Call the local pathology hybrid vector database.

This script is intentionally placed in the pathology RAG project root:
  /mnt/data_1/yds/RAG/Hybrid_milvus/总版

It uses the local config by default:
  insert/config.yaml

Confirmed default target from that config:
  Milvus Lite DB: 数据库/bm25.db
  Collection:     cervix_v3
"""

import argparse
import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "insert" / "config.yaml"
PACKAGE_ROOT = PROJECT_ROOT / "insert"


if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from bm25_bge_vectorstore_v2.retrieval_service import HybridRetriever  # noqa: E402


DEFAULT_SERVER_URL = os.environ.get("PATHOLOGY_VECTOR_DB_URL", "http://127.0.0.1:8765")


def load_config(config_path: Path, topk: int | None = None) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    if topk is not None:
        cfg["retrieval"]["topk"] = int(topk)
    return cfg


def _call_with_debug_to_stderr(func, *args, **kwargs):
    """Keep retrieval debug prints away from JSON stdout."""
    with contextlib.redirect_stdout(sys.stderr):
        return func(*args, **kwargs)


def build_retriever(config_path: Path = DEFAULT_CONFIG, topk: int | None = None) -> HybridRetriever:
    cfg = load_config(config_path, topk=topk)
    return _call_with_debug_to_stderr(HybridRetriever, cfg)


def search(query: str, *, topk: int = 5, config_path: Path = DEFAULT_CONFIG) -> Dict[str, Any]:
    retriever = build_retriever(config_path=config_path, topk=topk)
    return _call_with_debug_to_stderr(retriever.search, query)


def batch_search(
    queries: List[str],
    *,
    topk: int = 5,
    config_path: Path = DEFAULT_CONFIG,
) -> List[Dict[str, Any]]:
    retriever = build_retriever(config_path=config_path, topk=topk)
    return _call_with_debug_to_stderr(retriever.search_batch, queries, topk=topk)


def search_via_server(
    query: str,
    *,
    topk: int = 5,
    server_url: str = DEFAULT_SERVER_URL,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    url = server_url.rstrip("/") + "/search"
    body = json.dumps({"query": query, "topk": int(topk)}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the local pathology hybrid vector database")
    parser.add_argument("query", nargs="?", default="宫颈癌的病理诊断要点是什么？")
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--json", action="store_true", help="Print full JSON output")
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SERVER_URL,
        help="Resident retrieval service URL. Defaults to PATHOLOGY_VECTOR_DB_URL or http://127.0.0.1:8765",
    )
    parser.add_argument("--no-server", action="store_true", help="Bypass resident service and load Milvus locally")
    parser.add_argument("--strict-server", action="store_true", help="Fail instead of falling back when service is unavailable")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout when using the resident service")
    parser.add_argument(
        "--light-output",
        action="store_true",
        help="Return only IDs from Milvus internals. Useful for load/search debugging, not for final evidence text.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.light_output:
        os.environ["MILVUS_LIGHT_OUTPUT"] = "1"

    if args.no_server:
        output = search(args.query, topk=args.topk, config_path=args.config)
    else:
        try:
            output = search_via_server(args.query, topk=args.topk, server_url=args.server_url, timeout=args.timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            if args.strict_server:
                raise SystemExit(f"Resident service unavailable: {exc}") from exc
            print(
                f"[WARN] resident service unavailable ({exc}); falling back to direct Milvus load.",
                file=sys.stderr,
            )
            output = search(args.query, topk=args.topk, config_path=args.config)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    print(f"query: {output.get('query')}")
    print(f"lang: {output.get('lang')}")
    print(f"fusion: {output.get('fusion')}")
    for rank, row in enumerate(output.get("results", []), start=1):
        print(
            f"[{rank}] score={row.get('score', 0.0):.4f} "
            f"dense={row.get('dense', 0.0):.4f} "
            f"sparse={row.get('sparse', 0.0):.4f} "
            f"file={row.get('file_name')}"
        )
        text = str(row.get("text") or "").replace("\n", " ")
        if text:
            print(f"    {text[:240]}")


if __name__ == "__main__":
    main()
