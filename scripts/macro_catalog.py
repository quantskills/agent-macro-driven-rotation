# -*- coding: utf-8 -*-
"""宏观指标目录（回测 / 动画 / L2 对账唯一数据源）。

定码日期 2026-07-30。对话路径仍须先 get_macro_detail；此处仅供脚本复现。
已废弃方法名：get_macro_pm / get_macro_fi（勿再使用）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

CODE_VERIFIED_DATE = "2026-07-30"

# key → 拉取与对账元数据
MACRO_SERIES: Dict[str, Dict[str, Any]] = {
    "pmi": {
        "label": "制造业PMI",
        "aliases": ["pmi", "制造业pmi", "制造业 pmi"],
        "method": "get_macro_ci",
        "symbol": "CI0000007",
        "tol": 0.05,
        "unit": "index",
    },
    "cpi": {
        "label": "CPI同比",
        "aliases": ["cpi同比", "cpi", "cpi yoy"],
        "method": "get_macro_pi",
        "symbol": "PI0000003",
        "tol": 0.05,
        "unit": "pct",
    },
    "m2": {
        "label": "M2同比",
        "aliases": ["m2同比", "m2", "m2 yoy"],
        "method": "get_macro_mb",
        "symbol": "MB0000002",
        "tol": 0.05,
        "unit": "pct",
    },
    "sf": {
        "label": "社融存量同比",
        "aliases": ["社融存量同比", "社融同比", "社融", "社会融资存量同比"],
        "method": "get_macro_fs",
        "symbol": "FS0042573",
        "tol": 0.05,
        "unit": "pct",
    },
}

# 政策预期差代理：新订单 − 库存（同属 get_macro_ci）
POLICY_GAP: Dict[str, Any] = {
    "label": "政策预期差(新订单−库存)",
    "aliases": ["政策预期差", "新订单−库存", "新订单-库存", "policy_gap", "新订单－库存"],
    "method": "get_macro_ci",
    "new_orders_symbol": "CI0000010",
    "inventory_symbol": "CI0000017",
    "symbol": "CI0000010-CI0000017",  # 对账复合键
    "tol": 0.15,
    "unit": "diff",
    "composite": True,
}

# 供 build_animation 使用的精简表：field → (method_suffix, symbol)
# method_suffix: ci/pi/mb/fs → get_macro_*
MACRO_SYMBOLS_ANIM: Dict[str, Tuple[str, str]] = {
    "pmi": ("ci", MACRO_SERIES["pmi"]["symbol"]),
    "cpi": ("pi", MACRO_SERIES["cpi"]["symbol"]),
    "m2": ("mb", MACRO_SERIES["m2"]["symbol"]),
    "sf": ("fs", MACRO_SERIES["sf"]["symbol"]),
}

# reconcile 用的完整目录（含 policy_gap）
MACRO_CATALOG: Dict[str, Dict[str, Any]] = {
    **{k: dict(v) for k, v in MACRO_SERIES.items()},
    "policy_gap": dict(POLICY_GAP),
}


def panda_method_name(method: str) -> str:
    """get_macro_ci → 属性名已是完整方法名。"""
    return method


def series_fetch_plan() -> List[Tuple[str, str, str]]:
    """返回 [(field, method, symbol), ...] 供 backtest 拉取。"""
    return [(k, v["method"], v["symbol"]) for k, v in MACRO_SERIES.items()]


def policy_gap_symbols() -> Tuple[str, str]:
    return POLICY_GAP["new_orders_symbol"], POLICY_GAP["inventory_symbol"]
