# -*- coding: utf-8 -*-
"""另类高频景气 Nowcast（runtime live 用）。

流程：get_macro_detail 定码 → get_macro_* 拉序列 → 同比/环比约定打分。
无特色类目映射的行业：用近 20 日价格动量代理（明确标注）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from industry_codes import (
    PREFERRED_ALT_SYMBOLS,
    alt_categories,
    price_feed,
)
from panda_client import fetch_ohlc_chunked, get_panda_data, to_ymd

# category → method
_CAT_METHOD = {
    "EC": "get_macro_ec",
    "MD": "get_macro_md",
    "EH": "get_macro_eh",
    "AD": "get_macro_ad",
    "HA": "get_macro_ha",
    "OF": "get_macro_of",
    "RB": "get_macro_rb",
    "RE": "get_macro_re",
    "ED": "get_macro_ed",
    "EP": "get_macro_ep",
}

_DETAIL_CACHE: Dict[str, pd.DataFrame] = {}
_EPS = 0.005  # 0.5% 视为持平


def _dir(change: float) -> int:
    if change > _EPS:
        return 1
    if change < -_EPS:
        return -1
    return 0


def score_from_dirs(yoy_dir: int, mom_dir: int) -> float:
    """指南约定：双升+1 / 双降-1 / 单升平+0.5 / 单降平-0.5 / 其它 0。"""
    if yoy_dir == 1 and mom_dir == 1:
        return 1.0
    if yoy_dir == -1 and mom_dir == -1:
        return -1.0
    if (yoy_dir == 1 and mom_dir == 0) or (yoy_dir == 0 and mom_dir == 1):
        return 0.5
    if (yoy_dir == -1 and mom_dir == 0) or (yoy_dir == 0 and mom_dir == -1):
        return -0.5
    return 0.0


def _already_yoy(stat_type: str) -> bool:
    s = str(stat_type or "")
    return "同比" in s


def _lag_for_yoy(frequency: str) -> int:
    f = str(frequency or "")
    if "周" in f or "week" in f.lower():
        return 52
    if "日" in f or "day" in f.lower():
        return 252
    return 12  # 月/季等默认按月对齐近似


def _parse_period(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str).str.replace("-", "").str[:8], format="%Y%m%d")


def score_series(
    df: pd.DataFrame,
    *,
    stat_type: str = "",
    frequency: str = "",
) -> Tuple[float, str, Dict[str, Any]]:
    """对单条特色序列打分。返回 (score, period, meta)。"""
    if df is None or len(df) == 0:
        raise ValueError("空序列")
    work = df.copy()
    work["period"] = _parse_period(work["period_date"])
    work = work.sort_values("period")
    vals = work["data_value"].astype(float).values
    periods = work["period"]
    latest_period = periods.iloc[-1].strftime("%Y-%m-%d")
    n = len(vals)
    if n < 2:
        return 0.0, latest_period, {"note": "样本过短", "n": n}

    mom_dir = _dir(float(vals[-1] / vals[-2] - 1.0)) if vals[-2] != 0 else 0

    if _already_yoy(stat_type):
        # 已是同比：水平符号作同比方向，相邻差分作环比动能
        yoy_dir = 1 if vals[-1] > _EPS else (-1 if vals[-1] < -_EPS else 0)
        score = score_from_dirs(yoy_dir, mom_dir)
        return score, latest_period, {
            "stat_type": stat_type,
            "yoy_dir": yoy_dir,
            "mom_dir": mom_dir,
            "mode": "published_yoy",
        }

    lag = _lag_for_yoy(frequency)
    if n > lag and vals[-1 - lag] != 0:
        yoy_dir = _dir(float(vals[-1] / vals[-1 - lag] - 1.0))
    else:
        # 不足一年：用近半样本趋势近似同比方向
        mid = max(1, n // 2)
        yoy_dir = _dir(float(vals[-1] / vals[-1 - mid] - 1.0)) if vals[-1 - mid] != 0 else 0

    score = score_from_dirs(yoy_dir, mom_dir)
    return score, latest_period, {
        "stat_type": stat_type,
        "yoy_dir": yoy_dir,
        "mom_dir": mom_dir,
        "mode": "level_diff",
        "lag": lag,
    }


def _detail(pd_mod: Any, category: str) -> pd.DataFrame:
    if category not in _DETAIL_CACHE:
        df = pd_mod.get_macro_detail(category=category)
        if df is None or len(df) == 0:
            _DETAIL_CACHE[category] = pd.DataFrame()
        else:
            _DETAIL_CACHE[category] = df.copy()
    return _DETAIL_CACHE[category]


def _pick_symbols(
    detail: pd.DataFrame,
    industry: str,
    max_n: int = 3,
) -> List[Dict[str, Any]]:
    if detail is None or len(detail) == 0:
        return []
    d = detail.copy()
    d["end_date"] = d["end_date"].astype(str)
    # 覆盖尽量新
    cutoff = (datetime.today() - timedelta(days=540)).strftime("%Y%m%d")
    d = d[d["end_date"] >= cutoff]
    if d.empty:
        d = detail.copy()
        d["end_date"] = d["end_date"].astype(str)

    # 跳过累计值优先用原始/期末
    st = d["stat_type"].astype(str)
    d["_cum"] = st.str.contains("累计", na=False).astype(int)
    name = d["name"].astype(str)
    # 名称启发
    boost = (
        name.str.contains("总指数|销售指数|销量|销售额|价格指数:总", na=False).astype(int) * 3
        + name.str.contains("总|整体|行业", na=False).astype(int)
        - name.str.contains("股份|有限公司|\\[停\\]", na=False).astype(int) * 5
    )
    pref = set(PREFERRED_ALT_SYMBOLS.get(industry, []))
    d["_pref"] = d["symbol"].astype(str).isin(pref).astype(int) * 10
    d["_score"] = d["_pref"] + boost - d["_cum"]
    d = d.sort_values(["_score", "end_date"], ascending=[False, False])
    rows = []
    for _, r in d.head(max_n * 3).iterrows():
        rows.append({
            "symbol": str(r["symbol"]),
            "name": str(r.get("name", "")),
            "stat_type": str(r.get("stat_type", "")),
            "frequency": str(r.get("frequency", "")),
            "unit": str(r.get("unit", "")),
        })
        if len(rows) >= max_n:
            break
    return rows


# 黄金 ETF 近窗常空，按序尝试（商品黄金优先）
_GOLD_FEED_FALLBACKS = [
    ("518880.SH", "fund"),  # 华安易富黄金
    ("518800.SH", "fund"),  # 国泰黄金
    ("159934.SZ", "fund"),  # 易方达黄金
    ("518850.SH", "fund"),  # 华安黄金易
]


def _price_feed_candidates(industry: str) -> List[Tuple[str, str]]:
    code, feed = price_feed(industry)
    out: List[Tuple[str, str]] = []
    if code:
        out.append((code, feed))
    if industry == "黄金":
        for c, f in _GOLD_FEED_FALLBACKS:
            if (c, f) not in out:
                out.append((c, f))
    return out


def _fetch_price_momentum(pd_mod: Any, industry: str) -> Dict[str, Any]:
    """无另类类目时的动量代理，归一化到 [-1, 1]。"""
    candidates = _price_feed_candidates(industry)
    if not candidates:
        raise ValueError(f"无行情代理码: {industry}")
    end = datetime.today()
    start = end - timedelta(days=120)
    last_err: Optional[Exception] = None
    closes = None
    feed_used = "fund"
    code_used = ""
    for code, feed in candidates:
        try:
            closes, feed_used = fetch_ohlc_chunked(
                pd_mod,
                code,
                feed,
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
                fallback_years=4,
            )
            code_used = code
            break
        except Exception as e:
            last_err = e
            continue
    if closes is None or len(closes) == 0:
        raise ValueError(f"动量代理失败 {industry}（{last_err}）")
    window = min(20, len(closes) - 1)
    if window < 5:
        raise ValueError(f"行情样本过短 {industry}")
    ret = float(closes.iloc[-1] / closes.iloc[-1 - window] - 1.0)
    score = float(max(-1.0, min(1.0, ret / 0.10)))
    score = round(score * 2) / 2.0
    period = closes.index[-1].strftime("%Y-%m-%d")
    lag_days = (end.date() - closes.index[-1].date()).days
    note = "无另类特色类目映射，20日动量代理（另类样本≠官方）"
    if lag_days > 45:
        note += f"；行情近窗稀疏，已用历史段（asof={period}，滞后约{lag_days}天）"
    if code_used != candidates[0][0]:
        note += f"；主代理无数据，改用 {code_used}"
    return {
        "industry": industry,
        "score": score,
        "period": period,
        "source": "price_momentum_proxy",
        "method": "get_fund_daily" if feed_used == "fund" else "get_index_daily",
        "symbol": code_used,
        "note": note,
    }


def fetch_prosperity_for_industries(
    industries: List[Dict[str, Any]],
    *,
    lookback_days: int = 540,
    pd_mod: Any = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """对初筛行业计算景气分数。返回 (rows, degradations)。"""
    deg: List[str] = []
    if not industries:
        return [], ["景气: 无初筛行业"]

    try:
        pd_mod = pd_mod or get_panda_data(require_token=True)
    except Exception as e:
        return [], [f"景气层失败：panda_data 不可用（{e}）"]

    end = datetime.today()
    start = end - timedelta(days=lookback_days)
    start_s, end_s = to_ymd(start.strftime("%Y-%m-%d")), to_ymd(end.strftime("%Y-%m-%d"))

    out: List[Dict[str, Any]] = []
    for item in industries:
        name = item.get("name") or ""
        cats = alt_categories(name)
        if not cats:
            try:
                out.append(_fetch_price_momentum(pd_mod, name))
            except Exception as e:
                deg.append(f"景气 {name}: 动量代理失败（{e}）")
            continue

        scores: List[float] = []
        meta_bits: List[str] = []
        period = ""
        method_used = ""
        for cat in cats:
            method = _CAT_METHOD.get(cat)
            if not method or not hasattr(pd_mod, method):
                deg.append(f"景气 {name}: 无方法 {cat}")
                continue
            try:
                detail = _detail(pd_mod, cat)
            except Exception as e:
                deg.append(f"景气 {name}: get_macro_detail({cat}) 失败（{e}）")
                continue
            if detail is None or len(detail) == 0:
                deg.append(f"景气 {name}: get_macro_detail({cat}) 空表")
                continue
            picks = _pick_symbols(detail, name, max_n=3)
            fn = getattr(pd_mod, method)
            for pick in picks:
                try:
                    raw = fn(symbol=pick["symbol"], start_date=start_s, end_date=end_s)
                    sc, per, meta = score_series(
                        raw, stat_type=pick["stat_type"], frequency=pick["frequency"]
                    )
                    scores.append(sc)
                    period = per or period
                    method_used = method
                    meta_bits.append(f"{pick['symbol']}:{pick['name'][:24]}={sc}")
                except Exception as e:
                    deg.append(f"景气 {name}/{pick['symbol']}: {e}")
            if scores:
                break  # 一个类目够用则不再扩 OF 等

        if not scores:
            try:
                out.append(_fetch_price_momentum(pd_mod, name))
                deg.append(f"景气 {name}: 特色序列无可用点，已降级为动量代理")
            except Exception as e:
                deg.append(f"景气 {name}: 无可用另类/动量数据（{e}）")
            continue

        agg = float(np.mean(scores))
        # 量化到 0.5 档
        agg = round(agg * 2) / 2.0
        out.append({
            "industry": name,
            "score": agg,
            "period": period,
            "source": "macro-altdata-nowcast",
            "method": method_used,
            "note": "另类/及时样本 Nowcast（非官方统计）；" + "; ".join(meta_bits[:3]),
        })

    if not out:
        deg.append("景气层：全部行业无分数")
    return out, deg
