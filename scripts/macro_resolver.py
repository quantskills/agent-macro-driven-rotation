# -*- coding: utf-8 -*-
"""宏观官方指标自动定码。

策略（避免 get_macro_detail 全表超限额）：
  1. 按字段准备候选 symbol 池（短列表）
  2. get_macro_detail(category, symbol=候选) 取字典
  3. 按官方名称打分选最优，写回 macro_catalog 并缓存

缓存：scripts/.cache/resolved_macro.json
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

CACHE_PATH = pathlib.Path(__file__).resolve().parent / ".cache" / "resolved_macro.json"

# field → category, 候选码, 偏好完整名, 排除子串
_FIELD_CANDIDATES: Dict[str, Dict[str, Any]] = {
    "pmi": {
        "category": "CI",
        "candidates": ["CI0000007", "CI0000002"],
        "prefer_names": ["制造业PMI"],
        "exclude": ["生产", "新订单", "库存", "从业人员", "财新", "RatingDog", "预览", "[停]"],
        "method": "get_macro_ci",
    },
    "cpi": {
        "category": "PI",
        "candidates": ["PI0000047", "PI0000004", "PI0000003", "PI0000001"],
        "prefer_names": ["CPI:当月同比"],
        "exclude": ["居住", "翘尾", "城市", "农村", "环比", "累计", "[停]"],
        "method": "get_macro_pi",
    },
    "m2": {
        "category": "MB",
        "candidates": ["MB0000006", "MB0000034", "MB0000002", "MB0000005"],
        "prefer_names": ["货币供应量:M2:同比", "M2:同比"],
        "exclude": ["M0", "M1", "乘数", "[停]"],
        "method": "get_macro_mb",
    },
    "sf": {
        # 社融在 Pandadata 落在 MB 类，不是 FS
        "category": "MB",
        "candidates": ["MB0000091", "MB0000083", "MB0000044"],
        "prefer_names": ["社会融资规模存量增速"],
        "exclude": ["人民币贷款", "占比", "增量", "[停]"],
        "method": "get_macro_mb",
    },
}

_POLICY_CANDIDATES = {
    "new_orders": {
        "category": "CI",
        "candidates": ["CI0000009", "CI0000010"],
        "prefer_names": ["制造业PMI:新订单"],
        "exclude": ["出口", "在手", "[停]"],
    },
    "inventory": {
        "category": "CI",
        "candidates": ["CI0000012", "CI0000016", "CI0000017"],
        "prefer_names": ["制造业PMI:产成品库存"],
        "exclude": ["从业人员", "[停]"],
    },
}


def _load_cache() -> Dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(data: Dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _score(name: str, prefers: List[str], excludes: List[str]) -> int:
    n = str(name)
    if any(x in n for x in excludes):
        return -1000
    score = 0
    for i, kw in enumerate(prefers):
        if n == kw:
            score += 300 - i
        elif kw in n:
            score += 100 - i * 10
    score -= max(0, len(n) - len(prefers[0]) if prefers else 0)
    return score


def _pick(detail, prefers: List[str], excludes: List[str]) -> Optional[Tuple[str, str]]:
    if detail is None or len(detail) == 0:
        return None
    best_sym, best_name, best = None, "", -10**9
    for _, row in detail.iterrows():
        name = str(row.get("name", ""))
        sc = _score(name, prefers, excludes)
        # 覆盖越新越好（用完整 end_date 数值区分，避免同年仅取到 2 分）
        try:
            ed = int(str(row.get("end_date", "0"))[:8] or 0)
        except Exception:
            ed = 0
        sc += ed / 1_000_000.0
        if sc > best:
            best, best_sym, best_name = sc, str(row["symbol"]), name
    if best_sym and best > 0:
        return best_sym, best_name
    return None


def resolve_macro_symbols(pd_mod: Any = None, *, force: bool = False) -> Dict[str, Any]:
    import macro_catalog as cat
    from panda_client import get_panda_data

    cache = _load_cache()
    if not force and cache.get("series") and cache.get("policy_gap"):
        _apply_to_catalog(cat, cache)
        return cache

    pd_mod = pd_mod or get_panda_data(require_token=True)
    series_out: Dict[str, Any] = {}

    for field, spec in _FIELD_CANDIDATES.items():
        detail = pd_mod.get_macro_detail(
            category=spec["category"], symbol=spec["candidates"]
        )
        picked = _pick(detail, spec["prefer_names"], spec["exclude"])
        if picked:
            sym, name = picked
            series_out[field] = {
                "symbol": sym,
                "name": name,
                "method": spec["method"],
                "source": "get_macro_detail",
            }
        else:
            series_out[field] = {
                "symbol": cat.MACRO_SERIES[field]["symbol"],
                "name": cat.MACRO_SERIES[field]["label"],
                "method": cat.MACRO_SERIES[field]["method"],
                "source": "fallback_catalog",
            }

    # 政策预期差
    no_spec = _POLICY_CANDIDATES["new_orders"]
    inv_spec = _POLICY_CANDIDATES["inventory"]
    d_no = pd_mod.get_macro_detail(category="CI", symbol=no_spec["candidates"])
    d_inv = pd_mod.get_macro_detail(category="CI", symbol=inv_spec["candidates"])
    no = _pick(d_no, no_spec["prefer_names"], no_spec["exclude"])
    inv = _pick(d_inv, inv_spec["prefer_names"], inv_spec["exclude"])
    policy = {
        "new_orders_symbol": no[0] if no else cat.POLICY_GAP["new_orders_symbol"],
        "inventory_symbol": inv[0] if inv else cat.POLICY_GAP["inventory_symbol"],
        "new_orders_name": no[1] if no else "",
        "inventory_name": inv[1] if inv else "",
        "source": "get_macro_detail" if (no and inv) else "fallback_catalog",
    }
    policy["symbol"] = f"{policy['new_orders_symbol']}-{policy['inventory_symbol']}"

    out = {"series": series_out, "policy_gap": policy}
    _apply_to_catalog(cat, out)
    _save_cache(out)
    return out


def _apply_to_catalog(cat: Any, resolved: Dict[str, Any]) -> None:
    for field, meta in (resolved.get("series") or {}).items():
        if field not in cat.MACRO_SERIES:
            continue
        if meta.get("symbol"):
            cat.MACRO_SERIES[field]["symbol"] = meta["symbol"]
        if meta.get("method"):
            cat.MACRO_SERIES[field]["method"] = meta["method"]
        cat.MACRO_SERIES[field]["resolved_name"] = meta.get("name", "")
    pg = resolved.get("policy_gap") or {}
    if pg.get("new_orders_symbol"):
        cat.POLICY_GAP["new_orders_symbol"] = pg["new_orders_symbol"]
        cat.POLICY_GAP["inventory_symbol"] = pg["inventory_symbol"]
        cat.POLICY_GAP["symbol"] = pg.get(
            "symbol",
            f"{pg['new_orders_symbol']}-{pg['inventory_symbol']}",
        )
    cat.MACRO_SYMBOLS_ANIM = {
        "pmi": ("ci", cat.MACRO_SERIES["pmi"]["symbol"]),
        "cpi": ("pi", cat.MACRO_SERIES["cpi"]["symbol"]),
        "m2": ("mb", cat.MACRO_SERIES["m2"]["symbol"]),
        "sf": ("mb", cat.MACRO_SERIES["sf"]["symbol"]),  # 社融走 mb
    }
    cat.MACRO_CATALOG = {
        **{k: dict(v) for k, v in cat.MACRO_SERIES.items()},
        "policy_gap": dict(cat.POLICY_GAP),
    }
    cat.CODE_VERIFIED_DATE = datetime.today().strftime("%Y-%m-%d") + "(auto)"
