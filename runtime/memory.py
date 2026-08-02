# -*- coding: utf-8 -*-
"""轻量本地记忆：用户画像 / 调参偏好 / 30 天历史结论。

禁止用记忆覆盖本次 API 定相；仅影响阈值与措辞。
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

DEFAULT_PATH = pathlib.Path(__file__).resolve().parent / "memory" / "store.json"


class MemoryStore:
    def __init__(self, path: Optional[pathlib.Path] = None):
        self.path = pathlib.Path(path) if path else DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {
            "user_profile": {},
            "tuning_prefs": {"pe_pct_max": 60, "drawdown_tol": 0.15},
            "history": [],
        }
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        self._expire_history()

    def save(self) -> None:
        self._expire_history()
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _expire_history(self) -> None:
        cutoff = datetime.utcnow() - timedelta(days=30)
        hist: List[Dict[str, Any]] = self._data.get("history", [])
        kept = []
        for item in hist:
            try:
                ts = datetime.fromisoformat(item.get("ts", ""))
            except Exception:
                continue
            if ts >= cutoff:
                kept.append(item)
        self._data["history"] = kept

    @property
    def tuning_prefs(self) -> Dict[str, Any]:
        return dict(self._data.get("tuning_prefs", {}))

    @property
    def user_profile(self) -> Dict[str, Any]:
        return dict(self._data.get("user_profile", {}))

    def update_profile(self, **kwargs) -> None:
        self._data.setdefault("user_profile", {}).update(kwargs)
        self.save()

    def update_tuning(self, **kwargs) -> None:
        self._data.setdefault("tuning_prefs", {}).update(kwargs)
        self.save()

    def append_conclusion(self, phase: str, summary: str, query: str = "") -> None:
        self._data.setdefault("history", []).append({
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "phase": phase,
            "summary": summary,
            "query": query,
        })
        self.save()
