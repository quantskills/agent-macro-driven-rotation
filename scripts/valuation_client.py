# -*- coding: utf-8 -*-
"""行业估值分位 + 动量（runtime live 用）。

优先 get_index_indicator(pe_ttm) 历史分位；无估值字段时用价格分位代理。
动量：20/60/120 日收益，用于辅助过筛（至少一个窗口为正更佳，但不强制）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from industry_codes import price_feed
from panda_client import fetch_ohlc_chunked, get_panda_data, parse_period_series, to_ymd


def _percentile_of_latest(hist: pd.Series) -> float:
    hist = hist.dropna().astype(float)
    if len(hist) < 20:
        raise ValueError("历史样本不足 20")
    cur = float(hist.iloc[-1])
    return round(float((hist < cur).mean() * 100), 1)


def _load_indicator_field(
    pd_mod: Any, symbol: str, start: str, end: str, field: str
) -> Optional[pd.Series]:
    try:
        df = pd_mod.get_index_indicator(symbol=symbol, start_date=start, end_date=end)
    except Exception:
        return None
    if df is None or len(df) == 0 or field not in df.columns:
        return None
    work = df.copy()
    work["_dt"] = parse_period_series(work["date"])
    work = work.sort_values("_dt")
    s = work.set_index("_dt")[field].astype(float)
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]
    return s if len(s) >= 20 else None


def _load_pe_ttm(pd_mod: Any, symbol: str, start: str, end: str) -> Optional[pd.Series]:
    return _load_indicator_field(pd_mod, symbol, start, end, "pe_ttm")


def _load_pb_ttm(pd_mod: Any, symbol: str, start: str, end: str) -> Optional[pd.Series]:
    return _load_indicator_field(pd_mod, symbol, start, end, "pb_ttm")


def _load_close(pd_mod: Any, symbol: str, feed: str, start: str, end: str) -> pd.Series:
    s, _ = fetch_ohlc_chunked(pd_mod, symbol, feed, start, end)
    if len(s) < 20:
        raise ValueError(f"行情过短 {symbol}")
    return s


def _momentum(closes: pd.Series) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {"mom_20": None, "mom_60": None, "mom_120": None}
    for w, key in ((20, "mom_20"), (60, "mom_60"), (120, "mom_120")):
        if len(closes) > w and float(closes.iloc[-1 - w]) != 0:
            out[key] = round(float(closes.iloc[-1] / closes.iloc[-1 - w] - 1.0) * 100, 2)
    return out


def fetch_valuation_for_industries(
    industries: List[Dict[str, Any]],
    *,
    pe_pct_max: float = 60.0,
    lookback_years: int = 5,
    pd_mod: Any = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """返回估值行与降级说明。"""
    deg: List[str] = []
    if not industries:
        return [], ["估值: 无初筛行业"]

    try:
        pd_mod = pd_mod or get_panda_data(require_token=True)
    except Exception as e:
        return [], [f"估值层失败：panda_data 不可用（{e}）"]

    end = datetime.today()
    start = end - timedelta(days=365 * lookback_years + 30)
    start_s, end_s = to_ymd(start.strftime("%Y-%m-%d")), to_ymd(end.strftime("%Y-%m-%d"))

    out: List[Dict[str, Any]] = []
    for item in industries:
        name = item.get("name") or ""
        code = item.get("code") or ""
        feed_code, feed = price_feed(name)
        symbol = code or feed_code
        if not symbol:
            deg.append(f"估值 {name}: 无代理码")
            continue
        try:
            pe_s = pb_s = None
            if feed != "fund":
                pe_s = _load_pe_ttm(pd_mod, symbol, start_s, end_s)
                pb_s = _load_pb_ttm(pd_mod, symbol, start_s, end_s)
            closes = _load_close(pd_mod, symbol, feed, start_s, end_s)
            moms = _momentum(closes)

            pb_pct: Optional[float] = None
            if pb_s is not None:
                try:
                    pb_pct = _percentile_of_latest(pb_s)
                except Exception:
                    pb_pct = None

            if pe_s is not None:
                pe_pct = _percentile_of_latest(pe_s)
                metric = "pe_ttm"
                source = "index-valuation-rotation"
                method = "get_index_indicator"
                period = pe_s.index[-1].strftime("%Y-%m-%d")
                note = f"PE_TTM 历史分位（窗口约{lookback_years}年）"
                if pb_pct is not None:
                    note += f"；PB_TTM分位={pb_pct}"
            else:
                pe_pct = _percentile_of_latest(closes)
                metric = "price_pct"
                source = "index-valuation-rotation"
                method = "get_fund_daily" if feed == "fund" else "get_index_daily"
                period = closes.index[-1].strftime("%Y-%m-%d")
                note = "无 PE 字段，价格历史分位代理（非官方 PE）"
                deg.append(f"估值 {name}: 无 pe_ttm，已用价格分位代理")

            # 过筛：主分位（PE 或价格代理）低于阈值
            mom_vals = [v for v in moms.values() if v is not None]
            momentum_ok = any(v > 0 for v in mom_vals) if mom_vals else True
            pass_filter = bool(pe_pct < float(pe_pct_max))

            out.append({
                "industry": name,
                "code": symbol,
                "pe_pct": pe_pct,
                "pb_pct": pb_pct,
                "metric": metric,
                "pass_filter": pass_filter,
                "momentum_ok": momentum_ok,
                "mom_20": moms["mom_20"],
                "mom_60": moms["mom_60"],
                "mom_120": moms["mom_120"],
                "period": period,
                "source": source,
                "method": method,
                "note": note,
            })
        except Exception as e:
            deg.append(f"估值 {name}({symbol}): {e}")

    if not out:
        deg.append("估值层：全部行业无分位")
    return out, deg
