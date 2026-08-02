# -*- coding: utf-8 -*-
"""
backtest.py - 宏观阶段回测脚本（改进版美林时钟有效性验证）

功能：
  1. 基于历史宏观数据（CPI/PMI/M2/社融/政策代理）按改进版美林时钟四维规则判定历史阶段
  2. 统计各宏观阶段下行业指数的超额收益、胜率、最大回撤
  3. 输出各阶段胜率、平均超额收益、最大回撤汇总表
  4. 支持时间窗口参数（--start_date / --end_date）
  5. 可选：将阶段判定结果保存为 CSV，供后续分析使用

使用方式：
  # 使用 Pandadata 自动判定历史阶段（需要 pandadata 环境和凭证）：
  python scripts/backtest.py --start_date 2015-01-01 --end_date 2026-07-01

  # 使用预存阶段 CSV（无需 Pandadata）：
  python scripts/backtest.py --phase_file macro_phases.csv --start_date 2015-01-01

  # 无 API 时仅允许显式模拟（禁止静默模拟）：
  python scripts/backtest.py --allow-simulate --start_date 2022-01-01 --end_date 2023-12-31

数据来源（回测写死代码；定码日期 2026-07-28，对话路径仍须先 get_macro_detail）：
  - 制造业 PMI：get_macro_ci(CI0000007)
  - CPI 同比：get_macro_pi(PI0000003)
  - M2 同比：get_macro_mb(MB0000002)
  - 社融存量同比：get_macro_fs(FS0042573)
  - 政策预期差代理：PMI 新订单−库存（CI0000010 − CI0000017；不可用则 policy_gap 置空）
  - 行业行情：get_index_daily
  - 已废弃方法名：get_macro_pm / get_macro_fi（勿再使用）

改进版美林时钟阶段判定规则（四维）：
  增长维度：制造业 PMI > 50 且环比上行 → 扩张；否则收缩
  通胀维度：CPI 同比 > 2.0% → 高通胀；否则低通胀
  流动性维度：M2 同比 > 8% 或 社融增速 > 10% → 宽松；否则收紧
  政策预期差：新订单−库存（>0 偏积极）
  判定结果：
    扩张 + 低通胀 + 宽松 → 复苏期
    扩张 + 低通胀 + 未宽松 → 复苏期（phase_note=扩张低通胀但流动性未宽松）
    扩张 + 高通胀         → 过热期（loose_liquidity 写入辅助列）
    收缩 + 高通胀         → 滞胀期
    收缩 + 低通胀         → 衰退期；若已宽松 → phase_note=衰退末期/政策托底
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from industry_codes import CODE_VERIFIED_DATE, all_phase_codes
from macro_catalog import (  # noqa: E402
    CODE_VERIFIED_DATE as MACRO_CODE_DATE,
    MACRO_SERIES,
    policy_gap_symbols,
)
from phase_rules import determine_phase_from_macro  # 四维判定纯逻辑

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="宏观轮动策略回测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--start_date",
        default="2015-01-01",
        help="回测起始日期，格式 YYYY-MM-DD（默认 2015-01-01）",
    )
    p.add_argument(
        "--end_date",
        default=datetime.today().strftime("%Y-%m-%d"),
        help="回测结束日期，格式 YYYY-MM-DD（默认今日）",
    )
    p.add_argument(
        "--benchmark",
        default="000300.SH",
        help="基准指数代码（默认 000300.SH 沪深300）",
    )
    p.add_argument(
        "--phase_file",
        default="",
        help="宏观阶段判定 CSV 文件路径（不填则自动从 pandadata 获取宏观数据判定）",
    )
    p.add_argument(
        "--output_dir",
        default="backtest_output",
        help="输出目录（默认 backtest_output/）",
    )
    p.add_argument(
        "--allow-simulate",
        action="store_true",
        help="允许在 panda_data 不可用或行情加载失败时使用模拟数据；默认禁止静默模拟",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_phase_file(path: str) -> pd.DataFrame:
    """加载宏观阶段判定 CSV。

    期望字段：date, macro_phase, recommended_industries
    """
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[ERROR] 宏观阶段文件不存在：{path}", file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(p, parse_dates=["date"])
    required = {"date", "macro_phase", "recommended_industries"}
    missing = required - set(df.columns)
    if missing:
        print(f"[ERROR] phase_file 缺少字段：{missing}", file=sys.stderr)
        sys.exit(1)
    df = df.sort_values("date").reset_index(drop=True)
    return df


# 各宏观阶段推荐行业指数（来自 industry_codes，定码日期见 CODE_VERIFIED_DATE）
PHASE_INDUSTRIES: Dict[str, List[str]] = all_phase_codes()


def load_macro_and_determine_phases(
    start: str,
    end: str,
    allow_simulate: bool = False,
) -> pd.DataFrame:
    """通过 pandadata API 加载历史宏观数据并自动判定每月宏观阶段。

    返回 DataFrame: date, macro_phase, recommended_industries, pmi, cpi_yoy, m2_yoy,
                    sf_yoy, loose_liquidity, policy_gap, phase_note
    """
    try:
        import panda_data as _pd_mod
        import os as _os
        _u = _os.environ.get("PANDA_DATA_USERNAME", "")
        _p = _os.environ.get("PANDA_DATA_PASSWORD", "")
        if _u and _p:
            _pd_mod.init_token(username=_u, password=_p)
        print("  [INFO] 从 panda_data 加载宏观数据...")
        print(f"  [INFO] 宏观定码日期：{MACRO_CODE_DATE}")

        def _to_series(df, value_name: str):
            out = df.rename(columns={"data_value": value_name, "period_date": "date"})
            out["date"] = pd.to_datetime(out["date"].astype(str), format="%Y%m%d")
            return out.set_index("date")[value_name].sort_index()

        series_map: Dict[str, pd.Series] = {}
        col_map = {"pmi": "pmi", "cpi": "cpi_yoy", "m2": "m2_yoy", "sf": "sf_yoy"}
        for field, meta in MACRO_SERIES.items():
            fn = getattr(_pd_mod, meta["method"])
            raw = fn(symbol=meta["symbol"], start_date=start, end_date=end)
            series_map[field] = _to_series(raw, col_map[field])

        pmi_df = series_map["pmi"]
        cpi_df = series_map["cpi"]
        m2_df = series_map["m2"]
        sf_df = series_map["sf"]

        # 政策预期差代理：新订单 − 库存
        policy_gap_s = None
        try:
            sym_no, sym_inv = policy_gap_symbols()
            new_orders = _pd_mod.get_macro_ci(symbol=sym_no, start_date=start, end_date=end)
            inventory = _pd_mod.get_macro_ci(symbol=sym_inv, start_date=start, end_date=end)
            new_orders = new_orders.rename(columns={"data_value": "v", "period_date": "date"})
            inventory = inventory.rename(columns={"data_value": "v", "period_date": "date"})
            new_orders["date"] = pd.to_datetime(new_orders["date"].astype(str), format="%Y%m%d")
            inventory["date"] = pd.to_datetime(inventory["date"].astype(str), format="%Y%m%d")
            no_s = new_orders.set_index("date")["v"].sort_index()
            inv_s = inventory.set_index("date")["v"].sort_index()
            policy_gap_s = (no_s - inv_s).rename("policy_gap")
            print(f"  [INFO] 政策预期差代理 = PMI新订单({sym_no}) − 库存({sym_inv})")
        except Exception as pe:
            print(f"  [WARN] 政策预期差代理不可用（{pe}），policy_gap 置空")

    except (ImportError, Exception) as e:
        if not allow_simulate:
            print(
                f"[ERROR] panda_data 宏观数据加载失败（{e}）。"
                f"默认禁止静默模拟；如需结构验证请加 --allow-simulate。",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  [WARN] panda_data 不可用（{e}），--allow-simulate 已启用，使用模拟宏观数据。")
        return _simulate_macro_phases(start, end)

    # 对齐到月度，填充缺失值
    months = pd.date_range(start, end, freq="MS")
    macro = pd.DataFrame(index=months)
    macro["pmi"] = pmi_df.reindex(months, method="ffill")
    macro["cpi_yoy"] = cpi_df.reindex(months, method="ffill")
    macro["m2_yoy"] = m2_df.reindex(months, method="ffill")
    macro["sf_yoy"] = sf_df.reindex(months, method="ffill")
    if policy_gap_s is not None:
        macro["policy_gap"] = policy_gap_s.reindex(months, method="ffill")
    else:
        macro["policy_gap"] = np.nan
    macro = macro.ffill().dropna(subset=["pmi", "cpi_yoy", "m2_yoy", "sf_yoy"])

    rows = []
    for i, (dt, row) in enumerate(macro.iterrows()):
        pmi_prev = macro["pmi"].iloc[i - 1] if i > 0 else row["pmi"]
        pg = row["policy_gap"]
        pg_val = None if pd.isna(pg) else float(pg)
        result = determine_phase_from_macro(
            pmi=row["pmi"],
            pmi_prev=pmi_prev,
            cpi_yoy=row["cpi_yoy"],
            m2_yoy=row["m2_yoy"],
            sf_yoy=row["sf_yoy"],
            policy_gap=pg_val,
        )
        phase = result["macro_phase"]
        industries = ",".join(PHASE_INDUSTRIES.get(phase, []))
        rows.append({
            "date": dt,
            "macro_phase": phase,
            "recommended_industries": industries,
            "pmi": row["pmi"],
            "cpi_yoy": row["cpi_yoy"],
            "m2_yoy": row["m2_yoy"],
            "sf_yoy": row["sf_yoy"],
            "loose_liquidity": result["loose_liquidity"],
            "policy_gap": pg_val,
            "phase_note": result["phase_note"],
            "code_verified_date": CODE_VERIFIED_DATE,
        })

    return pd.DataFrame(rows)


def _simulate_macro_phases(start: str, end: str) -> pd.DataFrame:
    """无 pandadata 时，生成模拟宏观阶段（仅 --allow-simulate）。"""
    months = pd.date_range(start, end, freq="MS")
    phases = ["复苏期", "过热期", "滞胀期", "衰退期"]
    rows = []
    for i, dt in enumerate(months):
        phase = phases[i % 4]
        industries = ",".join(PHASE_INDUSTRIES.get(phase, []))
        rows.append({
            "date": dt,
            "macro_phase": phase,
            "recommended_industries": industries,
            "pmi": 50.0 + (i % 3 - 1) * 0.5,
            "cpi_yoy": 1.5 + (i % 4) * 0.3,
            "m2_yoy": 8.5,
            "sf_yoy": 10.5,
            "loose_liquidity": True,
            "policy_gap": 1.0,
            "phase_note": "simulated",
            "code_verified_date": CODE_VERIFIED_DATE,
        })
    return pd.DataFrame(rows)


def calc_phase_stats(
    phase_df: pd.DataFrame,
    strategy_ret: pd.Series,
    benchmark_ret: pd.Series,
) -> pd.DataFrame:
    """统计各宏观阶段的超额收益、胜率、最大回撤。

    覆盖月数 = phase_df 中该 macro_phase 的月数（禁止用日收益 resample 长度充当）。
    日收益序列仅用于：月均超额、胜率、阶段最大回撤。
    无行情月份仍计入覆盖月数，超额/胜率/回撤在无日收益时记为 NaN。
    """
    rows = []
    phases = phase_df["macro_phase"].unique()
    for phase in phases:
        phase_rows = phase_df[phase_df["macro_phase"] == phase]
        cover_months = len(phase_rows)
        phase_dates = phase_rows["date"]

        mask = pd.Series(False, index=strategy_ret.index)
        for dt in phase_dates:
            month_mask = (strategy_ret.index.year == dt.year) & (
                strategy_ret.index.month == dt.month
            )
            mask = mask | month_mask

        s_ret = strategy_ret[mask]
        b_ret = benchmark_ret.reindex(s_ret.index).fillna(0.0)
        active = s_ret - b_ret

        if len(s_ret) == 0:
            rows.append({
                "宏观阶段": phase,
                "覆盖月数": cover_months,
                "月均超额收益(%)": None,
                "超额月胜率(%)": None,
                "阶段最大回撤(%)": None,
            })
            continue

        monthly_active = active.resample("ME").sum()
        win_rate = (
            (monthly_active > 0).sum() / len(monthly_active)
            if len(monthly_active) > 0
            else 0.0
        )
        avg_excess = active.mean() * 21
        cum = (1 + s_ret).cumprod()
        max_dd = ((cum - cum.cummax()) / cum.cummax()).min() if len(cum) > 0 else 0.0

        rows.append({
            "宏观阶段": phase,
            "覆盖月数": cover_months,
            "月均超额收益(%)": round(avg_excess * 100, 2),
            "超额月胜率(%)": round(win_rate * 100, 1),
            "阶段最大回撤(%)": round(max_dd * 100, 2),
        })

    return pd.DataFrame(rows)


def assert_phase_month_consistency(phase_df: pd.DataFrame, phase_stats: pd.DataFrame) -> None:
    """断言 sum(覆盖月数) == len(macro_phases)，失败则非 0 退出。"""
    if phase_stats.empty:
        print("[ERROR] phase_stats 为空，无法校验覆盖月数。", file=sys.stderr)
        sys.exit(1)
    total_cover = int(phase_stats["覆盖月数"].sum())
    n_phases = len(phase_df)
    if total_cover != n_phases:
        print(
            f"[ERROR] 覆盖月数合计({total_cover}) != macro_phases 行数({n_phases})，"
            f"绩效口径不可信。",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"  [OK] 覆盖月数合计={total_cover} 与 macro_phases 行数一致")


def load_index_daily(
    index_codes: list,
    start: str,
    end: str,
    allow_simulate: bool = False,
) -> pd.DataFrame:
    """通过 pandadata get_index_daily 接口加载行业指数日行情。

    返回 DataFrame，columns=[code, date, close]。
    默认禁止静默模拟；单码失败会列出失败码，全部失败且无 --allow-simulate 则退出。
    """
    try:
        import panda_data
        import os
        username = os.environ.get("PANDA_DATA_USERNAME", "")
        password = os.environ.get("PANDA_DATA_PASSWORD", "")
        if username and password:
            panda_data.init_token(username=username, password=password)
        get_index_daily = panda_data.get_index_daily
    except ImportError as e:
        if not allow_simulate:
            print(
                f"[ERROR] panda_data 未安装（{e}）。默认禁止静默模拟；"
                f"请安装 panda-data 或加 --allow-simulate。",
                file=sys.stderr,
            )
            sys.exit(1)
        print("[WARN] panda_data 未安装，--allow-simulate 已启用，使用随机数据模拟。", file=sys.stderr)
        return _simulate_index_daily(index_codes, start, end)

    frames = []
    failed: List[str] = []
    fund_codes = {
        sym for sym, kind in (
            (v[0], v[1]) for v in __import__("industry_codes", fromlist=["INDUSTRY_PRICE_FEEDS"]).INDUSTRY_PRICE_FEEDS.values()
        ) if kind == "fund"
    }
    for code in index_codes:
        try:
            df = None
            if code in fund_codes and hasattr(panda_data, "get_fund_daily"):
                df = panda_data.get_fund_daily(symbol=code, start_date=start, end_date=end)
            if df is None or (hasattr(df, "__len__") and len(df) == 0):
                df = get_index_daily(symbol=code, start_date=start, end_date=end)
            if df is None or len(df) == 0:
                raise ValueError("空行情表")
            df = df.copy()
            df["code"] = code
            date_col = "date" if "date" in df.columns else "period_date"
            close_col = "close" if "close" in df.columns else ("unit_nav" if "unit_nav" in df.columns else "nav")
            df["date"] = pd.to_datetime(df[date_col].astype(str).str.replace("-", "").str[:8], format="%Y%m%d")
            df["close"] = df[close_col].astype(float)
            frames.append(df[["code", "date", "close"]])
        except Exception as e:
            failed.append(code)
            print(f"[WARN] 加载 {code} 行情失败：{e}", file=sys.stderr)

    if failed:
        print(f"[WARN] 以下指数代码加载失败：{failed}", file=sys.stderr)

    if not frames:
        if not allow_simulate:
            print(
                f"[ERROR] 全部行业/基准行情加载失败（失败码：{failed or index_codes}）。"
                f"默认禁止用随机行情冒充实盘；请核验代码或加 --allow-simulate。",
                file=sys.stderr,
            )
            sys.exit(1)
        print("[WARN] 行情全部失败，--allow-simulate 已启用，使用随机模拟。", file=sys.stderr)
        return _simulate_index_daily(index_codes, start, end)

    return pd.concat(frames, ignore_index=True)


def _simulate_index_daily(codes: list, start: str, end: str) -> pd.DataFrame:
    """无 API 时生成模拟行情数据（仅 --allow-simulate）。"""
    dates = pd.date_range(start, end, freq="B")
    rng = np.random.default_rng(42)
    frames = []
    for code in codes:
        prices = 1000 * np.cumprod(1 + rng.normal(0.0003, 0.015, len(dates)))
        df = pd.DataFrame({"code": code, "date": dates, "close": prices})
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["code", "date", "close"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 策略构建
# ---------------------------------------------------------------------------

def build_strategy_returns(
    phase_df: pd.DataFrame,
    price_df: pd.DataFrame,
    start: str,
    end: str,
) -> Union[pd.Series, pd.DataFrame]:
    """按宏观阶段持有推荐行业等权组合，月度换仓。"""
    if price_df.empty:
        print("[WARN] 行情数据为空，无法计算策略收益。")
        return pd.DataFrame()

    price_df = price_df.copy()
    price_df["date"] = pd.to_datetime(price_df["date"])
    pivot = price_df.pivot(index="date", columns="code", values="close").sort_index()
    daily_ret = pivot.pct_change()

    phase_df = phase_df.copy()
    phase_df["date"] = pd.to_datetime(phase_df["date"])
    phase_df = phase_df.set_index("date").sort_index()

    dates = pd.date_range(start, end, freq="B")
    weights_series = pd.Series(index=dates, dtype=object)

    for dt in dates:
        prior = phase_df[phase_df.index <= dt]
        if prior.empty:
            weights_series[dt] = {}
            continue
        row = prior.iloc[-1]
        industries = [x.strip() for x in str(row["recommended_industries"]).split(",") if x.strip()]
        valid = [x for x in industries if x in daily_ret.columns]
        if not valid:
            weights_series[dt] = {}
            continue
        w = {code: 1.0 / len(valid) for code in valid}
        weights_series[dt] = w

    strategy_ret = pd.Series(index=dates, dtype=float)
    for dt in dates:
        w = weights_series.get(dt, {})
        if not w or dt not in daily_ret.index:
            strategy_ret[dt] = 0.0
            continue
        r = sum(daily_ret.loc[dt].get(code, 0.0) * weight for code, weight in w.items())
        strategy_ret[dt] = r

    return strategy_ret.fillna(0.0)


# ---------------------------------------------------------------------------
# 回测指标计算
# ---------------------------------------------------------------------------

def calc_metrics(returns: pd.Series, benchmark_returns: pd.Series, rf: float = 0.02) -> dict:
    """计算回测指标。"""
    if returns.empty:
        return {}

    total = (1 + returns).prod()
    years = len(returns) / 252
    annual_return = total ** (1 / years) - 1 if years > 0 else 0.0

    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    excess_ret = returns - rf / 252
    sharpe = (excess_ret.mean() / excess_ret.std() * np.sqrt(252)) if excess_ret.std() > 0 else 0.0

    active_ret = returns - benchmark_returns.reindex(returns.index).fillna(0)
    info_ratio = (active_ret.mean() / active_ret.std() * np.sqrt(252)) if active_ret.std() > 0 else 0.0

    monthly_strategy = (1 + returns).resample("ME").prod() - 1
    monthly_bench = (1 + benchmark_returns.reindex(returns.index).fillna(0)).resample("ME").prod() - 1
    beats = (monthly_strategy > monthly_bench).sum()
    win_rate = beats / len(monthly_strategy) if len(monthly_strategy) > 0 else 0.0

    return {
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "info_ratio": info_ratio,
        "win_rate": win_rate,
    }


def print_metrics(metrics: dict, label: str = "策略"):
    print(f"\n{'='*50}")
    print(f"  {label} 回测指标")
    print(f"{'='*50}")
    if not metrics:
        print("  [无数据]")
        return
    print(f"  年化收益率   : {metrics['annual_return']*100:.2f}%")
    print(f"  最大回撤     : {metrics['max_drawdown']*100:.2f}%")
    print(f"  夏普比率     : {metrics['sharpe']:.3f}")
    print(f"  信息比率     : {metrics['info_ratio']:.3f}")
    print(f"  月度胜率     : {metrics['win_rate']*100:.1f}%")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# 可视化
# ---------------------------------------------------------------------------

def plot_nav(
    strategy_ret: pd.Series,
    benchmark_ret: pd.Series,
    output_dir: pathlib.Path,
):
    """绘制净值曲线并保存为 PNG + HTML。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib import font_manager as _fm
        _cand = ["SimHei", "Microsoft YaHei", "STHeiti"]
        _avail = {x.name for x in _fm.fontManager.ttflist}
        for _fn in _cand:
            if _fn in _avail:
                matplotlib.rcParams["font.family"] = [_fn]
                matplotlib.rcParams["axes.unicode_minus"] = False
                break
    except ImportError:
        print("[WARN] matplotlib 未安装，跳过 PNG 输出。")
        strategy_ret = None

    strategy_nav = (1 + strategy_ret).cumprod() if strategy_ret is not None else None
    benchmark_nav = (1 + benchmark_ret).cumprod()

    output_dir.mkdir(parents=True, exist_ok=True)

    if strategy_nav is not None:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(strategy_nav.index, strategy_nav.values, label="策略净值", linewidth=1.5)
        ax.plot(benchmark_nav.index, benchmark_nav.values, label="基准净值", linewidth=1.5, linestyle="--")
        ax.set_title("宏观驱动行业轮动策略 vs 基准")
        ax.set_ylabel("净值")
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()
        png_path = output_dir / "nav_curve.png"
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  [OK] 净值曲线已保存：{png_path}")

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        if strategy_nav is not None:
            fig.add_trace(go.Scatter(
                x=strategy_nav.index, y=strategy_nav.values,
                name="策略净值", line=dict(width=2),
            ))
        fig.add_trace(go.Scatter(
            x=benchmark_nav.index, y=benchmark_nav.values,
            name="基准净值", line=dict(width=2, dash="dash"),
        ))
        fig.update_layout(
            title="宏观驱动行业轮动策略净值曲线",
            yaxis_title="净值",
            xaxis_title="日期",
            hovermode="x unified",
        )
        html_path = output_dir / "nav_curve.html"
        fig.write_html(str(html_path))
        print(f"  [OK] 交互净值曲线已保存：{html_path}")
    except ImportError:
        print("[WARN] plotly 未安装，跳过 HTML 输出。")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  宏观驱动行业轮动策略回测（改进版美林时钟有效性验证）")
    print(f"  起始日期：{args.start_date}")
    print(f"  结束日期：{args.end_date}")
    print(f"  基准指数：{args.benchmark}")
    print(f"  行业码定码日期：{CODE_VERIFIED_DATE}")
    print(f"  允许模拟：{args.allow_simulate}")
    print(f"{'='*60}")

    if args.phase_file:
        print(f"\n  [INFO] 从 CSV 加载宏观阶段：{args.phase_file}")
        phase_df = load_phase_file(args.phase_file)
    else:
        print("\n  [INFO] 自动从 pandadata 获取宏观数据并判定历史阶段...")
        phase_df = load_macro_and_determine_phases(
            args.start_date, args.end_date, allow_simulate=args.allow_simulate
        )

    print(f"  [OK] 宏观阶段记录 {len(phase_df)} 条")
    print(f"  阶段分布：\n{phase_df['macro_phase'].value_counts().to_string()}")

    phase_out = output_dir / "macro_phases.csv"
    phase_df.to_csv(phase_out, index=False, encoding="utf-8-sig")
    print(f"  [OK] 阶段判定结果已保存：{phase_out}")

    all_industries = set()
    for _, row in phase_df.iterrows():
        for ind in str(row["recommended_industries"]).split(","):
            ind = ind.strip()
            if ind:
                all_industries.add(ind)
    all_codes = list(all_industries | {args.benchmark})

    print(f"\n  [INFO] 加载行情数据（{len(all_codes)} 个标的）...")
    price_df = load_index_daily(
        all_codes, args.start_date, args.end_date, allow_simulate=args.allow_simulate
    )
    if not price_df.empty:
        print(f"  [OK] 行情加载完成，{len(price_df)} 行")

    strategy_ret = build_strategy_returns(phase_df, price_df, args.start_date, args.end_date)
    if isinstance(strategy_ret, pd.DataFrame) and strategy_ret.empty:
        print("[ERROR] 策略收益为空，请检查行情数据和阶段文件。")
        sys.exit(1)

    if not price_df.empty and args.benchmark in price_df["code"].values:
        bench_price = price_df[price_df["code"] == args.benchmark].set_index("date")["close"].sort_index()
    else:
        if not args.allow_simulate:
            print(
                f"[ERROR] 基准 {args.benchmark} 不在已加载行情中，禁止静默模拟。"
                f"请核验代码或加 --allow-simulate。",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[WARN] 基准缺失，--allow-simulate 已启用，模拟基准行情。", file=sys.stderr)
        bench_price = _simulate_index_daily([args.benchmark], args.start_date, args.end_date)
        bench_price = bench_price.set_index("date")["close"].sort_index()
    benchmark_ret = bench_price.pct_change().fillna(0.0)

    print("\n  [INFO] 统计各宏观阶段超额收益...")
    phase_stats = calc_phase_stats(phase_df, strategy_ret, benchmark_ret)
    if not phase_stats.empty:
        print(f"\n{'='*60}")
        print("  各宏观阶段超额收益汇总")
        print(f"{'='*60}")
        print(phase_stats.to_string(index=False))
        assert_phase_month_consistency(phase_df, phase_stats)
        stats_out = output_dir / "phase_stats.csv"
        phase_stats.to_csv(stats_out, index=False, encoding="utf-8-sig")
        print(f"\n  [OK] 阶段统计已保存：{stats_out}")

    strategy_metrics = calc_metrics(strategy_ret, benchmark_ret)
    bench_metrics = calc_metrics(benchmark_ret, benchmark_ret)
    print_metrics(strategy_metrics, "宏观轮动策略（全周期）")
    print_metrics(bench_metrics, f"基准（{args.benchmark}）（全周期）")

    plot_nav(strategy_ret, benchmark_ret, output_dir)
    print(f"\n  [完成] 回测结果已输出至：{output_dir}")


if __name__ == "__main__":
    main()
