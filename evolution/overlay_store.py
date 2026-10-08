"""PatchOverlay 存储：OverlayUnit 的 JSON 持久化与状态管理。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from evolution.schemas import OverlayStatus, OverlayUnit


class OverlayStore:
    """管理 overlay_units/ 目录下的 JSON 文件，文件名即 overlay_id。"""

    def __init__(self, overlay_dir: Path | str):
        self.overlay_dir = Path(overlay_dir).expanduser().resolve()
        self.overlay_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 基础 CRUD ----------

    def save(self, unit: OverlayUnit) -> Path:
        path = self.overlay_dir / f"{unit.overlay_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(unit.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, overlay_id: str) -> OverlayUnit:
        path = self.overlay_dir / f"{overlay_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"OverlayUnit not found: {overlay_id}")
        with path.open("r", encoding="utf-8") as f:
            return OverlayUnit.from_dict(json.load(f))

    def list_all(self) -> List[OverlayUnit]:
        units = []
        for p in sorted(self.overlay_dir.glob("*.json")):
            try:
                with p.open("r", encoding="utf-8") as f:
                    units.append(OverlayUnit.from_dict(json.load(f)))
            except Exception:
                continue  # 跳过损坏文件
        return units

    def list_by_status(self, status: OverlayStatus) -> List[OverlayUnit]:
        return [u for u in self.list_all() if u.status == status]

    # ---------- 状态流转 ----------

    def set_status(self, overlay_id: str, status: OverlayStatus,
                   judge_report_id: Optional[str] = None) -> OverlayUnit:
        unit = self.load(overlay_id)
        unit.status = status
        if judge_report_id is not None:
            unit.judge_report_id = judge_report_id
        self.save(unit)
        return unit

    def accepted_units(self) -> List[OverlayUnit]:
        """参与检索扩展的全部生效单元。"""
        return self.list_by_status(OverlayStatus.ACCEPTED)

    # ---------- 冲突检测辅助 ----------

    def find_conflicts(self, rewritten_text: str, exclude_id: Optional[str] = None,
                       top_n: int = 3) -> List[tuple]:
        """粗暴的字符重叠冲突预检：返回 (overlay_id, 重叠度) 列表。

        首版用字符 bigram Jaccard 相似度；后续可升级为 embedding 相似度。
        """
        def bigrams(s: str) -> set:
            s = "".join(s.split())
            return {s[i:i + 2] for i in range(len(s) - 1)}

        target = bigrams(rewritten_text)
        hits = []
        for u in self.list_all():
            if u.overlay_id == exclude_id or u.status != OverlayStatus.ACCEPTED:
                continue
            other = bigrams(u.rewritten_text)
            if not target or not other:
                continue
            jaccard = len(target & other) / len(target | other)
            if jaccard > 0.3:
                hits.append((u.overlay_id, round(jaccard, 4)))
        hits.sort(key=lambda x: -x[1])
        return hits[:top_n]


def new_overlay_id() -> str:
    return f"ovl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
