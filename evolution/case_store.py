"""QueryCase 的读写管理。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from evolution.schemas import QueryCase


class CaseStore:
    """管理 QueryCase 的持久化存储。

    每个 case 保存为一个 JSON 文件，文件名即 case_id。
    """

    def __init__(self, cases_dir: Path | str):
        self.cases_dir = Path(cases_dir).expanduser().resolve()
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def save(self, case: QueryCase) -> Path:
        """保存一个 QueryCase，返回文件路径。"""
        path = self.cases_dir / f"{case.case_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(case.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, case_id: str) -> QueryCase:
        """加载指定 case_id 的 QueryCase。"""
        path = self.cases_dir / f"{case_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Case not found: {case_id}")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return QueryCase.from_dict(data)

    def list_cases(self) -> List[str]:
        """返回所有 case_id 列表（按文件名排序）。"""
        return sorted(
            p.stem for p in self.cases_dir.glob("*.json") if p.is_file()
        )

    def load_all(self) -> List[QueryCase]:
        """加载所有 QueryCase。"""
        cases = []
        for case_id in self.list_cases():
            try:
                cases.append(self.load(case_id))
            except Exception:
                # 跳过损坏文件，避免一次坏文件影响全部加载
                continue
        return cases

    def update(self, case_id: str, updates: Dict[str, Any]) -> QueryCase:
        """更新指定 case 的字段并保存。"""
        case = self.load(case_id)
        for key, value in updates.items():
            if hasattr(case, key):
                setattr(case, key, value)
            else:
                raise AttributeError(f"QueryCase has no attribute: {key}")
        self.save(case)
        return case
