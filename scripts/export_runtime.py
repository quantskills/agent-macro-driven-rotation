# -*- coding: utf-8 -*-
"""把 runtime AgentState 导出为 L5 CSV/XLSX（供 persist_and_report / CLI 调用）。"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from export_data import write_csv, write_xlsx


def state_to_payload(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    phase = state.get("macro_phase") or ""
    asof = state.get("macro_asof") or ""
    metrics = state.get("macro_metrics") or {}
    macro: List[Dict[str, Any]] = [
        {"metric": "宏观阶段", "value": phase, "period": asof, "source": "phase_rules"},
    ]
    for key, label, src in (
        ("pmi", "PMI", "get_macro_ci"),
        ("cpi_yoy", "CPI同比", "get_macro_pi"),
        ("m2_yoy", "M2同比", "get_macro_mb"),
        ("sf_yoy", "社融存量同比", "get_macro_mb"),
        ("policy_gap", "政策预期差", "get_macro_ci"),
        ("loose_liquidity", "loose_liquidity", "phase_rules"),
    ):
        if key in metrics and metrics[key] is not None:
            macro.append({
                "metric": label,
                "value": metrics[key],
                "period": asof,
                "source": src,
            })

    prosperity = []
    for p in state.get("prosperity") or []:
        prosperity.append({
            "industry": p.get("industry"),
            "score": p.get("score"),
            "period": p.get("period"),
            "source": p.get("source"),
            "method": p.get("method"),
            "note": p.get("note", ""),
        })

    valuation = []
    for v in state.get("valuation") or []:
        valuation.append({
            "industry": v.get("industry"),
            "code": v.get("code"),
            "pe_pct": v.get("pe_pct"),
            "pb_pct": v.get("pb_pct"),
            "metric": v.get("metric"),
            "pass_filter": v.get("pass_filter"),
            "mom_20": v.get("mom_20"),
            "period": v.get("period"),
            "source": v.get("source"),
            "method": v.get("method"),
        })

    prosp_map = {p["industry"]: p.get("score") for p in (state.get("prosperity") or [])}
    recommend = []
    for v in state.get("valuation") or []:
        if not v.get("pass_filter"):
            continue
        sc = prosp_map.get(v["industry"])
        if sc is not None and float(sc) < 0:
            continue
        recommend.append({
            "industry": v.get("industry"),
            "code": v.get("code"),
            "reason": "估值过筛且景气非负",
            "macro_phase": phase,
            "pe_pct": v.get("pe_pct"),
            "prosperity": sc,
        })

    return {
        "macro": macro,
        "prosperity": prosperity,
        "valuation": valuation,
        "recommend": recommend,
    }


def export_state(
    state: Dict[str, Any],
    output_dir: str,
    *,
    fmt: str = "both",
) -> Dict[str, str]:
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = state_to_payload(state)
    paths: Dict[str, str] = {}
    if fmt in ("csv", "both"):
        for name, rows in payload.items():
            p = out / f"{name}.csv"
            write_csv(p, rows)
            paths[name] = str(p)
    if fmt in ("xlsx", "both"):
        xlsx = out / "rotation_data.xlsx"
        write_xlsx(xlsx, payload)
        if xlsx.exists():
            paths["xlsx"] = str(xlsx)
    return paths
