# -*- coding: utf-8 -*-
"""改进版美林时钟四维判定（纯逻辑，无 pandas 依赖）。

与 backtest.determine_phase_from_macro 保持同一口径；backtest 从此处再导出。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def determine_phase_from_macro(
    pmi: float,
    pmi_prev: float,
    cpi_yoy: float,
    m2_yoy: float,
    sf_yoy: float,
    policy_gap: Optional[float] = None,
) -> Dict[str, Any]:
    """基于改进版美林时钟四维规则判定宏观阶段。"""
    growth_up = (pmi > 50) and (pmi >= pmi_prev)
    high_inflation = cpi_yoy > 2.0
    loose_liquidity = (m2_yoy > 8.0) or (sf_yoy > 10.0)
    phase_note = ""

    if growth_up and not high_inflation and loose_liquidity:
        phase = "复苏期"
    elif growth_up and not high_inflation and not loose_liquidity:
        phase = "复苏期"
        phase_note = "扩张低通胀但流动性未宽松"
    elif growth_up and high_inflation:
        phase = "过热期"
        if loose_liquidity:
            phase_note = "过热且流动性仍宽松"
        else:
            phase_note = "过热且流动性收紧"
    elif (not growth_up) and high_inflation:
        phase = "滞胀期"
    else:
        phase = "衰退期"
        if loose_liquidity:
            phase_note = "衰退末期/政策托底"

    if policy_gap is not None and policy_gap > 0 and phase == "衰退期" and loose_liquidity:
        if phase_note:
            phase_note = phase_note + ";政策预期差偏积极"
        else:
            phase_note = "政策预期差偏积极"

    return {
        "macro_phase": phase,
        "loose_liquidity": bool(loose_liquidity),
        "policy_gap": policy_gap,
        "phase_note": phase_note,
        "growth_up": bool(growth_up),
        "high_inflation": bool(high_inflation),
    }
