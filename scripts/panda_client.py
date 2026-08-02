# -*- coding: utf-8 -*-
"""panda_data 初始化与通用工具（runtime / 脚本共用）。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple

import pandas as pd


def get_panda_data(require_token: bool = True) -> Any:
    """返回已 init_token 的 panda_data 模块。凭证来自环境变量。"""
    import panda_data

    u = os.environ.get("PANDA_DATA_USERNAME", "")
    p = os.environ.get("PANDA_DATA_PASSWORD", "")
    if u and p:
        panda_data.init_token(username=u, password=p)
    elif require_token:
        raise RuntimeError(
            "客户端未初始化：请先设置 PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD "
            "并调用 panda_data.init_token()"
        )
    return panda_data


def to_ymd(date_str: str) -> str:
    """统一为 YYYY-MM-DD。"""
    s = str(date_str).replace("-", "")[:8]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def to_ymd_compact(date_str: str) -> str:
    return str(date_str).replace("-", "")[:8]


def parse_period_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str).str.replace("-", "").str[:8], format="%Y%m%d")


def normalize_close_series(df: pd.DataFrame) -> pd.Series:
    """从 index/fund 日行情表提取收盘价序列。"""
    if df is None or len(df) == 0:
        raise ValueError("空行情表")
    date_col = "date" if "date" in df.columns else "period_date"
    close_col = "close" if "close" in df.columns else None
    if close_col is None:
        for c in ("nav", "unit_nav", "adj_nav", "price"):
            if c in df.columns:
                close_col = c
                break
    if close_col is None:
        raise ValueError("无收盘价字段")
    work = df.copy()
    work["_dt"] = parse_period_series(work[date_col])
    work = work.sort_values("_dt")
    s = work.set_index("_dt")[close_col].astype(float)
    s = s[~s.index.duplicated(keep="last")].dropna()
    if s.empty:
        raise ValueError("收盘价序列为空")
    return s


def _fetch_one_chunk(
    pd_mod: Any, symbol: str, feed: str, start_dt: datetime, end_dt: datetime
) -> Tuple[Optional[pd.DataFrame], str]:
    """单段拉取；基金优先 compact 日期，失败再试带连字符。"""
    s_c, e_c = start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")
    s_d, e_d = to_ymd(s_c), to_ymd(e_c)
    feed_used = feed
    df = None
    if feed == "fund":
        for a, b in ((s_c, e_c), (s_d, e_d)):
            try:
                df = pd_mod.get_fund_daily(symbol=symbol, start_date=a, end_date=b)
                if df is not None and len(df) > 0:
                    break
            except Exception:
                df = None
    else:
        try:
            df = pd_mod.get_index_daily(symbol=symbol, start_date=s_d, end_date=e_d)
        except Exception:
            df = None
        if (df is None or len(df) == 0) and hasattr(pd_mod, "get_fund_daily"):
            try:
                df = pd_mod.get_fund_daily(symbol=symbol, start_date=s_c, end_date=e_c)
                if df is not None and len(df) > 0:
                    feed_used = "fund"
            except Exception:
                pass
    return df, feed_used


def fetch_ohlc_chunked(
    pd_mod: Any,
    symbol: str,
    feed: str,
    start: str,
    end: str,
    *,
    fallback_years: int = 3,
) -> Tuple[pd.Series, str]:
    """按年分段拉取（基金接口常限制单次 ≤1 年）。

    若近窗全空（基金数据常滞后），自动向历史回退最多 fallback_years 年取最近可用段。
    """
    start_dt = datetime.strptime(to_ymd(start), "%Y-%m-%d")
    end_dt = datetime.strptime(to_ymd(end), "%Y-%m-%d")

    def _pull(a: datetime, b: datetime) -> Tuple[List[pd.Series], str]:
        pieces: List[pd.Series] = []
        feed_used = feed
        cur = a
        while cur <= b:
            chunk_end = min(datetime(cur.year, 12, 31), b)
            if (chunk_end - cur).days > 360:
                chunk_end = cur + timedelta(days=360)
            df, feed_used = _fetch_one_chunk(pd_mod, symbol, feed_used, cur, chunk_end)
            if df is not None and len(df) > 0:
                try:
                    pieces.append(normalize_close_series(df))
                except Exception:
                    pass
            cur = chunk_end + timedelta(days=1)
        return pieces, feed_used

    pieces, feed_used = _pull(start_dt, end_dt)
    # 近窗空：整段向历史滑动，直到拿到数据
    if not pieces and fallback_years > 0:
        for back in range(1, fallback_years * 4 + 1):  # 按季回退
            shift = timedelta(days=90 * back)
            a2, b2 = start_dt - shift, end_dt - shift
            pieces, feed_used = _pull(a2, b2)
            if pieces:
                break
    if not pieces:
        raise ValueError(f"分段拉取仍为空 {symbol}/{feed}")
    s_all = pd.concat(pieces).sort_index()
    s_all = s_all[~s_all.index.duplicated(keep="last")]
    return s_all, feed_used
