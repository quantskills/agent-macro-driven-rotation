# -*- coding: utf-8 -*-
"""
build_animation.py
──────────────────
从 Pandadata 拉取宏观 + 行业行情数据，生成供动态四象限网页使用的 JSON 快照文件。

用法：
    python scripts/build_animation.py \
        --start_date 2022-01-01 \
        --end_date   2026-07-25 \
        --output     animation_data/data.json

输出格式：
{
  "meta": {"start": "2022-01-01", "end": "2026-07-25", "generated": "2026-07-28T..."},
  "industries": ["电子", "消费", "医药", "资源", "周期", "银行",
                 "防御消费", "公用事业", "黄金", "债券"],
  "phases": {                              # 月度宏观阶段
    "2022-01": {"phase": "衰退期", "pmi": 49.6, "cpi": 0.9, "m2": 9.8, "sf": 10.2},
    ...
  },
  "daily": {                               # 每交易日快照（行情数据插值到月度宏观）
    "2022-01-04": {
      "phase": "衰退期",
      "growth_idx": 49.6,   # PMI（月度插值）
      "cpi":        0.9,    # CPI 同比（月度插值）
      "industries": {
        "电子":    {"close": 1234.5, "ret_1m": -2.3, "ret_ytd": -5.1,
                   "sentiment": 0.32, "valuation_pct": 45.0},
        ...
      }
    },
    ...
  }
}
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys, warnings
from datetime import datetime, timedelta

import numpy as np

# ── CLI ──────────────────────────────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(
        description="生成动态四象限网页所需的 JSON，并默认内嵌进 animation.html（打开即用，无需手动加载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--start_date", default="2022-01-01", help="开始日期 YYYY-MM-DD")
    p.add_argument("--end_date",   default="",           help="结束日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--output",     default="animation_data/data.json",
                   help="旁路 JSON 路径（默认 animation_data/data.json）")
    p.add_argument("--html",       default="animation.html",
                   help="要内嵌数据的 HTML 路径（默认仓库根目录 animation.html）")
    p.add_argument("--no-embed",   action="store_true",
                   help="只写 JSON，不改 HTML")
    p.add_argument("--username",   default="", help="Pandadata 用户名（优先用环境变量）")
    p.add_argument("--password",   default="", help="Pandadata 密码（优先用环境变量）")
    return p.parse_args()


# ── Pandadata 初始化 ─────────────────────────────────────────────────────────
def _init_panda(username: str, password: str):
    try:
        import panda_data
    except ImportError:
        print("[ERROR] panda_data 未安装。请执行：pip install panda-data", file=sys.stderr)
        sys.exit(1)
    u = os.environ.get("PANDA_DATA_USERNAME", username)
    pw = os.environ.get("PANDA_DATA_PASSWORD", password)
    if not u or not pw:
        print("[ERROR] 缺少 Pandadata 凭据。请设置环境变量 PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD",
              file=sys.stderr)
        sys.exit(1)
    panda_data.init_token(username=u, password=pw)
    print("  [OK] Pandadata 登录成功")
    return panda_data


# ── 宏观数据 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from macro_catalog import MACRO_SYMBOLS_ANIM  # noqa: E402

MACRO_SYMBOLS = MACRO_SYMBOLS_ANIM

def _load_macro(pd_mod, start: str, end: str) -> dict:
    """返回 {month_str: {pmi, cpi, m2, sf}} 月度字典"""
    import pandas as pd
    frames = {}
    fetch_map = {
        "ci": pd_mod.get_macro_ci,
        "pi": pd_mod.get_macro_pi,
        "mb": pd_mod.get_macro_mb,
        "fs": pd_mod.get_macro_fs,
    }
    for field, (cat, sym) in MACRO_SYMBOLS.items():
        try:
            df = fetch_map[cat](symbol=sym, start_date=start, end_date=end)
            df["date"] = pd.to_datetime(df["period_date"].astype(str), format="%Y%m%d")
            df = df.set_index("date")["data_value"].sort_index()
            frames[field] = df
            print(f"  [OK] 宏观数据 {field}（{sym}）：{len(df)} 条")
        except Exception as e:
            print(f"  [WARN] 宏观数据 {field} 加载失败：{e}", file=sys.stderr)
            frames[field] = None

    # 对齐到月度
    months = pd.date_range(start, end, freq="MS")
    result = {}
    for m in months:
        ms = m.strftime("%Y-%m")
        row = {}
        for field in MACRO_SYMBOLS:
            s = frames.get(field)
            if s is not None and not s.empty:
                # 找最近的月度值
                mask = s.index <= m + pd.offsets.MonthEnd(0)
                row[field] = float(s[mask].iloc[-1]) if mask.any() else None
            else:
                row[field] = None
        result[ms] = row
    return result


def _determine_phase(row: dict, pmi_prev: float | None = None) -> str:
    return _phase_from_macro_row(row, pmi_prev)


# ── 行情数据 ─────────────────────────────────────────────────────────────────
# 与 scripts/industry_codes.py 同源（SH/SZ 可拉代理；勿用空返回的 .SI）
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from industry_codes import (  # noqa: E402
    ANIMATION_INDUSTRIES,
    CODE_VERIFIED_DATE,
    INDUSTRY_PRICE_FEEDS,
    price_feed,
)
from phase_rules import determine_phase_from_macro  # noqa: E402


def _phase_from_macro_row(row: dict, pmi_prev: float | None = None) -> str:
    """与 backtest/runtime 同一套四维规则（禁止本地另写一套阈值）。"""
    pmi = float(row.get("pmi") or 50.0)
    prev = float(pmi_prev) if pmi_prev is not None else pmi
    cpi = float(row.get("cpi") or 1.0)
    m2 = float(row.get("m2") or 8.0)
    sf = float(row.get("sf") or 10.0)
    return determine_phase_from_macro(pmi, prev, cpi, m2, sf, policy_gap=None)["macro_phase"]


def _normalize_ohlc(df, code: str):
    import pandas as pd
    if df is None or len(df) == 0:
        raise ValueError(f"空行情表 {code}")
    date_col = "date" if "date" in df.columns else "period_date"
    close_col = "close" if "close" in df.columns else "nav"
    if close_col not in df.columns:
        # 基金常见字段
        for c in ("unit_nav", "adj_nav", "price"):
            if c in df.columns:
                close_col = c
                break
    out = df.copy()
    out["date"] = pd.to_datetime(out[date_col].astype(str).str.replace("-", "").str[:8], format="%Y%m%d")
    s = out.set_index("date")[close_col].sort_index().astype(float)
    if s.empty:
        raise ValueError(f"无收盘价序列 {code}")
    return s


def _fetch_ohlc_chunked(pd_mod, code: str, feed: str, start: str, end: str):
    """按年分段拉取（基金接口常限制单次 ≤1 年）。"""
    import pandas as pd

    start_dt = datetime.strptime(start[:10], "%Y-%m-%d")
    end_dt = datetime.strptime(end[:10], "%Y-%m-%d")
    pieces = []
    cur = start_dt
    while cur <= end_dt:
        chunk_end = min(datetime(cur.year, 12, 31), end_dt)
        s = cur.strftime("%Y%m%d")
        e = chunk_end.strftime("%Y%m%d")
        if feed == "fund":
            df = pd_mod.get_fund_daily(symbol=code, start_date=s, end_date=e)
        else:
            df = pd_mod.get_index_daily(symbol=code, start_date=s, end_date=e)
            if (df is None or len(df) == 0) and hasattr(pd_mod, "get_fund_daily"):
                try:
                    df = pd_mod.get_fund_daily(symbol=code, start_date=s, end_date=e)
                    feed = "fund"
                except Exception:
                    pass
        if df is not None and len(df) > 0:
            pieces.append(_normalize_ohlc(df, code))
        cur = chunk_end + timedelta(days=1)
    if not pieces:
        raise ValueError(f"分段拉取仍为空 {code}/{feed}")
    s_all = pd.concat(pieces).sort_index()
    s_all = s_all[~s_all.index.duplicated(keep="last")]
    return s_all, feed


def _load_industry_prices(pd_mod, start: str, end: str) -> dict:
    """返回 {industry_name: pd.Series(close, index=datetime)}"""
    result = {}
    for name in ANIMATION_INDUSTRIES:
        code, feed = price_feed(name)
        if not code:
            print(f"  [WARN] 行业行情 {name}：无代理码", file=sys.stderr)
            result[name] = None
            continue
        try:
            # 基金或超长窗口：统一分段，避免「间隔不能超过1年」
            span_days = (
                datetime.strptime(end[:10], "%Y-%m-%d")
                - datetime.strptime(start[:10], "%Y-%m-%d")
            ).days
            if feed == "fund" or span_days > 360:
                s, feed_used = _fetch_ohlc_chunked(pd_mod, code, feed, start, end)
            else:
                start_n = start.replace("-", "")
                end_n = end.replace("-", "")
                if feed == "fund":
                    df = pd_mod.get_fund_daily(symbol=code, start_date=start_n, end_date=end_n)
                else:
                    df = pd_mod.get_index_daily(symbol=code, start_date=start_n, end_date=end_n)
                s = _normalize_ohlc(df, code)
                feed_used = feed
            result[name] = s
            print(f"  [OK] 行业行情 {name}（{code}/{feed_used}）：{len(s)} 天")
        except Exception as e:
            print(f"  [WARN] 行业行情 {name}（{code}）加载失败：{e}", file=sys.stderr)
            result[name] = None
    ok_n = sum(1 for v in result.values() if v is not None and len(v) > 0)
    print(f"  [INFO] 行情加载成功 {ok_n}/{len(ANIMATION_INDUSTRIES)}；代理定码 {CODE_VERIFIED_DATE}")
    if ok_n < 3:
        print("  [WARN] 可用行业过少，动画将几乎静止；请检查指数代理码。", file=sys.stderr)
    return result


def _compute_sentiment(price_series, window: int = 20) -> float:
    """用近 window 日涨跌动量作为景气代理，归一化到 -1~+1"""
    if price_series is None or len(price_series) < window + 1:
        return 0.0
    recent = price_series.iloc[-window:]
    ret = float(recent.iloc[-1] / recent.iloc[0] - 1)
    # 简单截断归一化：±10% → ±1
    return max(-1.0, min(1.0, ret / 0.10))


def _compute_valuation_pct(price_series, lookback: int = 252) -> float:
    """用近 lookback 日 price/均值 分位替代 PE 分位（演示用）"""
    if price_series is None or len(price_series) < 20:
        return 50.0
    hist = price_series.iloc[-lookback:] if len(price_series) >= lookback else price_series
    cur = float(price_series.iloc[-1])
    pct = float((hist < cur).mean() * 100)
    return round(pct, 1)


# ── 构建每日快照 ─────────────────────────────────────────────────────────────
def _build_daily_snapshots(macro_monthly: dict, industry_prices: dict,
                            start: str, end: str) -> dict:
    import pandas as pd
    s_dt = datetime.strptime(start, "%Y-%m-%d")
    e_dt = datetime.strptime(end,   "%Y-%m-%d")

    # 所有交易日（用 000300.SH 价格的日期集合近似）
    all_dates = set()
    for s in industry_prices.values():
        if s is not None:
            all_dates.update(s.index)
    if not all_dates:
        # 回退：生成所有工作日
        all_dates = set(pd.bdate_range(start, end))

    trade_days = sorted(d for d in all_dates if s_dt <= d.to_pydatetime() <= e_dt)

    # 月序 PMI，供环比判定
    month_keys = sorted(macro_monthly.keys())
    pmi_by_month = {ms: macro_monthly[ms].get("pmi") for ms in month_keys}

    daily = {}
    for dt in trade_days:
        ds = dt.strftime("%Y-%m-%d")
        ms = dt.strftime("%Y-%m")

        macro_row = macro_monthly.get(ms, {})
        # 上月 PMI（无则用当月）
        prev_ms = None
        if ms in month_keys:
            i = month_keys.index(ms)
            if i > 0:
                prev_ms = month_keys[i - 1]
        pmi_prev = pmi_by_month.get(prev_ms) if prev_ms else macro_row.get("pmi")
        phase = _determine_phase(macro_row, pmi_prev=pmi_prev)
        growth_idx = macro_row.get("pmi") or 50.0
        cpi_val    = macro_row.get("cpi") or 1.0

        inds = {}
        for name, series in industry_prices.items():
            if series is None:
                inds[name] = {"close": None, "ret_1m": None, "ret_ytd": None,
                              "sentiment": 0.0, "valuation_pct": 50.0}
                continue
            # 截到当天
            s_cut = series[series.index <= dt]
            if s_cut.empty:
                inds[name] = {"close": None, "ret_1m": None, "ret_ytd": None,
                              "sentiment": 0.0, "valuation_pct": 50.0}
                continue
            close = float(s_cut.iloc[-1])
            # 近 1 个月收益
            s_1m = s_cut[s_cut.index >= dt - timedelta(days=31)]
            ret_1m = round((close / float(s_1m.iloc[0]) - 1) * 100, 2) if len(s_1m) > 1 else 0.0
            # 年初至今
            ytd_start = s_cut[s_cut.index >= pd.Timestamp(f"{dt.year}-01-01")]
            ret_ytd = round((close / float(ytd_start.iloc[0]) - 1) * 100, 2) if len(ytd_start) > 1 else 0.0
            sentiment     = _compute_sentiment(s_cut, window=20)
            valuation_pct = _compute_valuation_pct(s_cut, lookback=252)
            inds[name] = {
                "close":         round(close, 2),
                "ret_1m":        ret_1m,
                "ret_ytd":       ret_ytd,
                "sentiment":     round(sentiment, 3),
                "valuation_pct": valuation_pct,
            }

        daily[ds] = {
            "phase":      phase,
            "growth_idx": round(growth_idx, 2),
            "cpi":        round(cpi_val, 2),
            "industries": inds,
        }

    return daily


# ── 内嵌到 HTML ───────────────────────────────────────────────────────────────
_EMBED_BEGIN = "<!-- ANIMATION_EMBEDDED_DATA_BEGIN -->"
_EMBED_END = "<!-- ANIMATION_EMBEDDED_DATA_END -->"


def _embed_into_html(html_path: pathlib.Path, payload: dict) -> None:
    """把 JSON 写入 animation.html 的内嵌块，打开页面即可用，无需手动加载。"""
    if not html_path.exists():
        print(f"  [WARN] HTML 不存在，跳过内嵌：{html_path}", file=sys.stderr)
        return
    text = html_path.read_text(encoding="utf-8")
    if _EMBED_BEGIN not in text or _EMBED_END not in text:
        print(
            f"  [WARN] {html_path} 缺少内嵌标记 "
            f"{_EMBED_BEGIN} … {_EMBED_END}，跳过内嵌。",
            file=sys.stderr,
        )
        return
    # 转义 </script> 以免 JSON 字符串打断 HTML
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e")
    block = (
        f"{_EMBED_BEGIN}\n"
        f'<script type="application/json" id="animation-embedded-data">{raw}</script>\n'
        f"{_EMBED_END}"
    )
    import re
    pattern = re.compile(
        re.escape(_EMBED_BEGIN) + r".*?" + re.escape(_EMBED_END),
        re.DOTALL,
    )
    new_text, n = pattern.subn(block, text, count=1)
    if n != 1:
        print("  [WARN] 内嵌替换失败（未匹配到唯一标记块）", file=sys.stderr)
        return
    html_path.write_text(new_text, encoding="utf-8")
    print(f"  [OK] 已内嵌进页面：{html_path.resolve()}（打开即用，无需加载 JSON）")


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    args = _parse_args()
    start = args.start_date
    end   = args.end_date or datetime.now().strftime("%Y-%m-%d")
    root = pathlib.Path(__file__).resolve().parent.parent

    print("=" * 60)
    print(f"  build_animation.py")
    print(f"  起止日期：{start} → {end}")
    print(f"  JSON 路径：{args.output}")
    print(f"  内嵌 HTML：{'否' if args.no_embed else args.html}")
    print("=" * 60)

    pd_mod = _init_panda(args.username, args.password)

    print("\n[步骤 1] 加载宏观数据...")
    macro_monthly = _load_macro(pd_mod, start, end)
    print(f"  月度快照：{len(macro_monthly)} 个月")

    print("\n[步骤 2] 加载行业行情...")
    industry_prices = _load_industry_prices(pd_mod, start, end)

    print("\n[步骤 3] 构建每日快照...")
    daily = _build_daily_snapshots(macro_monthly, industry_prices, start, end)
    print(f"  每日快照：{len(daily)} 天")

    phases_out = {}
    month_keys = sorted(macro_monthly.keys())
    for i, ms in enumerate(month_keys):
        row = macro_monthly[ms]
        pmi_prev = macro_monthly[month_keys[i - 1]].get("pmi") if i > 0 else row.get("pmi")
        phases_out[ms] = {
            "phase": _determine_phase(row, pmi_prev=pmi_prev),
            "pmi":   row.get("pmi"),
            "cpi":   row.get("cpi"),
            "m2":    row.get("m2"),
            "sf":    row.get("sf"),
        }

    output = {
        "meta": {
            "start":     start,
            "end":       end,
            "generated": datetime.now().isoformat(),
            "source":    "build_animation.py",
            "note":      "页面内嵌；宏观月度定相 + SH/SZ/ETF 行情代理（非申万.SI；.SI 在 panda 常无日行情）",
            "code_verified_date": CODE_VERIFIED_DATE,
            "price_feeds": {k: {"symbol": v[0], "feed": v[1]} for k, v in INDUSTRY_PRICE_FEEDS.items() if k in ANIMATION_INDUSTRIES},
        },
        "industries": list(ANIMATION_INDUSTRIES),
        "phases":     phases_out,
        "daily":      daily,
    }

    out_path = pathlib.Path(args.output)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = out_path.stat().st_size / 1024
    print(f"\n  [完成] JSON 已写入：{out_path}（{size_kb:.1f} KB）")
    if daily:
        print(f"  日期范围：{min(daily)} ~ {max(daily)}")

    if not args.no_embed:
        html_path = pathlib.Path(args.html)
        if not html_path.is_absolute():
            html_path = root / html_path
        print("\n[步骤 4] 内嵌到 HTML...")
        _embed_into_html(html_path, output)


if __name__ == "__main__":
    main()
