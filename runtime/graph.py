# -*- coding: utf-8 -*-
"""最小编排图：定相 →（按需）初筛 → 景气 → 估值 → 出图 → 写记忆。

优先使用 langgraph；未安装时退化为顺序 pipeline（行为一致）。
工具失败走降级边：标注跳过，禁止编造数值。

intent 控制实际执行的步骤（不再空跑全链路）：
  macro      → 定相 + 时钟图（跳过景气/估值；行业池仅作阶段映射参考）
  prosperity → 定相 + 初筛 + 景气（跳过估值）
  valuation  → 定相 + 初筛 + 估值（跳过景气）
  full       → 全链路
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from industry_codes import PHASE_INDUSTRY_NAMES, name_code_pairs  # noqa: E402
from runtime.memory import MemoryStore  # noqa: E402


class AgentState(TypedDict, total=False):
    query: str
    intent: str
    macro_phase: str
    loose_liquidity: bool
    phase_note: str
    industries: List[Dict[str, Any]]
    prosperity: List[Dict[str, Any]]
    valuation: List[Dict[str, Any]]
    charts: Dict[str, Any]
    degradation: List[str]
    report_md: str
    output_dir: str
    mock: bool
    pe_pct_max: float
    macro_asof: str
    macro_metrics: Dict[str, Any]
    growth_series: Any
    inflation_series: Any
    export_paths: Dict[str, str]
    l4_rebuild: bool  # True 时 L4 重建历史动画内嵌（较慢）


def _intent(state: AgentState) -> str:
    return state.get("intent") or "full"


def wants_screen(intent: str) -> bool:
    return intent in ("full", "prosperity", "valuation", "macro")


def wants_nowcast(intent: str) -> bool:
    return intent in ("full", "prosperity")


def wants_valuation(intent: str) -> bool:
    return intent in ("full", "valuation")


def resolve_intent(state: AgentState) -> AgentState:
    q = (state.get("query") or "").lower()
    # 完整轮动优先于「美林/宏观」单关键词，避免「完整…美林…报告」被收成仅定相
    if any(k in q for k in ("轮动", "完整报告", "完整行业", "该买什么", "关注什么行业", "配置")):
        intent = "full"
    elif any(k in q for k in ("估值", "pe", "pb", "valuation")):
        intent = "valuation"
    elif any(k in q for k in ("景气", "nowcast", "高频")):
        intent = "prosperity"
    elif any(k in q for k in ("宏观", "阶段", "美林", "定相")):
        intent = "macro"
    else:
        intent = "full"
    return {**state, "intent": intent, "degradation": list(state.get("degradation") or [])}


def macro_phase_node(state: AgentState) -> AgentState:
    """宏观定相。mock 或 API 失败时标注降级，不编造未标注数值。"""
    deg = list(state.get("degradation") or [])
    if state.get("mock"):
        # 示意输入：扩张+低通胀+宽松 → 复苏（纯逻辑，不依赖 pandas）
        try:
            from phase_rules import determine_phase_from_macro
            import pandas as pd

            result = determine_phase_from_macro(50.8, 50.2, 0.3, 8.2, 10.5, policy_gap=1.2)
            dates = pd.date_range(end=datetime.today(), periods=12, freq="MS")
            growth = pd.Series([50.2 + i * 0.05 for i in range(12)], index=dates)
            inflation = pd.Series([0.3 + (i % 3) * 0.05 for i in range(12)], index=dates)
            return {
                **state,
                "macro_phase": result["macro_phase"],
                "loose_liquidity": result["loose_liquidity"],
                "phase_note": result["phase_note"],
                "macro_asof": datetime.today().strftime("%Y-%m-%d"),
                "macro_metrics": {
                    "pmi": 50.8,
                    "cpi_yoy": 0.3,
                    "m2_yoy": 8.2,
                    "sf_yoy": 10.5,
                    "policy_gap": 1.2,
                    "loose_liquidity": result["loose_liquidity"],
                },
                "growth_series": growth,
                "inflation_series": inflation,
                "degradation": deg + ["macro: mock 示意输入（非实时 API）"],
            }
        except Exception as e:
            deg.append(f"宏观定相数据缺失，已跳过宏观阶段判定（{e}）")
            return {**state, "macro_phase": "", "degradation": deg}

    try:
        from datetime import timedelta

        import pandas as pd

        from backtest import load_macro_and_determine_phases
        from macro_resolver import resolve_macro_symbols

        # 先自动定码（候选池 + get_macro_detail），再拉序列
        try:
            resolved = resolve_macro_symbols(force=False)
            deg.append(
                "宏观自动定码："
                + ", ".join(
                    f"{k}={v.get('symbol')}"
                    for k, v in (resolved.get("series") or {}).items()
                )
            )
        except Exception as re:
            deg.append(f"宏观自动定码失败，使用目录兜底（{re}）")

        # 官方宏观常滞后：向前多取约 24 个月，供增长-通胀轨迹图
        end_dt = datetime.today()
        start_dt = (end_dt.replace(day=1) - timedelta(days=750)).replace(day=1)
        end = end_dt.strftime("%Y-%m-%d")
        start = start_dt.strftime("%Y-%m-%d")
        df = load_macro_and_determine_phases(start, end, allow_simulate=False)
        if df is None or len(df) == 0:
            raise RuntimeError(f"宏观阶段表为空（窗口 {start}~{end}）")
        row = df.iloc[-1]
        work = df.copy()
        work["date"] = pd.to_datetime(work["date"])
        work = work.sort_values("date")
        growth = work.set_index("date")["pmi"].astype(float)
        inflation = work.set_index("date")["cpi_yoy"].astype(float)
        def _num(v, nd=4):
            try:
                if v is None or v != v:
                    return None
                return round(float(v), nd)
            except Exception:
                return None

        metrics = {
            "pmi": _num(row.get("pmi"), 2),
            "cpi_yoy": _num(row.get("cpi_yoy"), 2),
            "m2_yoy": _num(row.get("m2_yoy"), 2),
            "sf_yoy": _num(row.get("sf_yoy"), 2),
            "policy_gap": _num(row.get("policy_gap"), 2),
            "loose_liquidity": bool(row.get("loose_liquidity", False)),
        }
        return {
            **state,
            "macro_phase": str(row["macro_phase"]),
            "loose_liquidity": bool(row.get("loose_liquidity", False)),
            "phase_note": str(row.get("phase_note", "")),
            "macro_asof": str(row.get("date", ""))[:10],
            "macro_metrics": metrics,
            "growth_series": growth,
            "inflation_series": inflation,
            "degradation": deg,
        }
    except SystemExit:
        deg.append("宏观定相数据缺失，已跳过宏观阶段判定")
        return {**state, "macro_phase": "", "degradation": deg}
    except Exception as e:
        deg.append(f"宏观定相数据缺失，已跳过宏观阶段判定（{e}）")
        return {**state, "macro_phase": "", "degradation": deg}


def industry_screen(state: AgentState) -> AgentState:
    intent = _intent(state)
    if not wants_screen(intent):
        return {**state, "industries": []}
    phase = state.get("macro_phase") or ""
    if not phase:
        return {**state, "industries": []}

    deg = list(state.get("degradation") or [])
    # live：用 panda_data 自动匹配行情代理 / 申万码（失败则回退静态表）
    if not state.get("mock"):
        try:
            from industry_codes import refresh_codes_from_api

            notes = refresh_codes_from_api(force=False)
            bad = [f"{k}" for k, v in notes.items() if str(v).startswith("fallback:")]
            if bad:
                deg.append("行情代理自动匹配部分回退：" + "、".join(bad[:6]))
        except Exception as e:
            deg.append(f"行情代理自动匹配失败，已用静态兜底（{e}）")

    inds = [
        {"name": n, "code": c}
        for n, c in name_code_pairs(phase)
    ]
    if not inds:
        names = PHASE_INDUSTRY_NAMES.get(phase, [])
        inds = [{"name": n, "code": ""} for n in names]
    return {**state, "industries": inds, "degradation": deg}


def nowcast_node(state: AgentState) -> AgentState:
    deg = list(state.get("degradation") or [])
    intent = _intent(state)
    if not wants_nowcast(intent):
        deg.append(f"按 intent={intent} 跳过景气确认")
        return {**state, "prosperity": [], "degradation": deg}

    inds = state.get("industries") or []
    if state.get("mock"):
        prosperity = [
            {"industry": x["name"], "score": 0.5, "period": "mock", "source": "macro-altdata-nowcast"}
            for x in inds[:3]
        ]
        deg.append("景气: mock 示意分数（非实时 Nowcast；仅编排冒烟）")
        return {**state, "prosperity": prosperity, "degradation": deg}

    try:
        from nowcast_client import fetch_prosperity_for_industries

        prosperity, d2 = fetch_prosperity_for_industries(inds)
        deg.extend(d2)
        return {**state, "prosperity": prosperity, "degradation": deg}
    except Exception as e:
        deg.append(f"另类景气数据暂不可用（{e}）")
        return {**state, "prosperity": [], "degradation": deg}


def valuation_node(state: AgentState) -> AgentState:
    deg = list(state.get("degradation") or [])
    intent = _intent(state)
    if not wants_valuation(intent):
        deg.append(f"按 intent={intent} 跳过估值过滤")
        return {**state, "valuation": [], "degradation": deg}

    inds = state.get("industries") or []
    pe_max = float(state.get("pe_pct_max") or 60)
    if state.get("mock"):
        valuation = []
        for i, x in enumerate(inds):
            pe = 30 + i * 8
            valuation.append({
                "industry": x["name"],
                "code": x.get("code", ""),
                "pe_pct": pe,
                "pass_filter": pe < pe_max,
                "period": "mock",
                "source": "index-valuation-rotation",
            })
        deg.append("估值: mock 示意分位（非实时 API；仅编排冒烟）")
        return {**state, "valuation": valuation, "degradation": deg}

    try:
        from valuation_client import fetch_valuation_for_industries

        mem = MemoryStore()
        pe_max = float(mem.tuning_prefs.get("pe_pct_max", pe_max))
        # Step4：景气下行行业剔除后再估值；若全部下行则仍估全量并标注
        prosp = {p["industry"]: p.get("score") for p in (state.get("prosperity") or [])}
        screened = inds
        if prosp:
            kept = [
                x for x in inds
                if prosp.get(x.get("name")) is None or float(prosp[x["name"]]) >= 0
            ]
            kept_names = {x["name"] for x in kept}
            dropped = [x["name"] for x in inds if x.get("name") not in kept_names]
            if kept:
                screened = kept
                if dropped:
                    deg.append("估值前剔除景气下行：" + "、".join(dropped))
            else:
                deg.append("景气全为下行：仍对初筛行业做估值，供对照")
        valuation, d2 = fetch_valuation_for_industries(screened, pe_pct_max=pe_max)
        deg.extend(d2)
        return {**state, "valuation": valuation, "degradation": deg, "pe_pct_max": pe_max}
    except Exception as e:
        deg.append(f"估值数据暂不可用（{e}）")
        return {**state, "valuation": [], "degradation": deg}


def render_node(state: AgentState) -> AgentState:
    phase = state.get("macro_phase") or "未知"
    charts: Dict[str, Any] = {"degraded": False}
    out_dir = pathlib.Path(state.get("output_dir") or (ROOT / "reports" / "runtime_out"))
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    prosp = {p["industry"]: p.get("score", 0) for p in (state.get("prosperity") or [])}
    industries_data = []
    for v in state.get("valuation") or []:
        industries_data.append({
            "name": v["industry"],
            "sentiment": float(prosp.get(v["industry"], 0) or 0),
            "valuation_pct": float(v.get("pe_pct", 50) or 50),
            "phase_match": True,
        })
    # 仅有景气、无估值时也画点
    if not industries_data:
        for p in state.get("prosperity") or []:
            industries_data.append({
                "name": p["industry"],
                "sentiment": float(p.get("score", 0) or 0),
                "valuation_pct": 50.0,
                "phase_match": True,
            })

    try:
        from chart_writer import ascii_clock, ascii_valuation_chart, render_all

        phase_show = phase if phase not in ("未知", "") else "复苏期"
        charts["clock_ascii"] = ascii_clock(phase_show)
        if industries_data:
            charts["valuation_ascii"] = ascii_valuation_chart(industries_data)

        growth = state.get("growth_series")
        inflation = state.get("inflation_series")
        data_date = (state.get("macro_asof") or datetime.today().strftime("%Y-%m"))[:7]
        if growth is not None and inflation is not None:
            rendered = render_all(
                phase_show,
                growth,
                inflation,
                industries_data,
                output_dir=str(chart_dir),
                data_date=data_date,
            )
            files: Dict[str, str] = {}
            for key, pair in (rendered or {}).items():
                b64, path = pair if pair else (None, None)
                if path:
                    files[key] = str(path)
                if b64:
                    charts[f"{key}_b64"] = b64
            charts["files"] = files
            if not files:
                charts["degraded"] = True
                deg_note = "[图表降级：matplotlib 不可用或渲染失败]"
            else:
                deg_note = ""
            if deg_note:
                charts["note"] = deg_note
        else:
            charts["degraded"] = True
            charts["note"] = "[图表降级：缺少增长/通胀序列，仅 ASCII]"
    except Exception as e:
        charts["error"] = str(e)
        charts["degraded"] = True
        charts["note"] = f"[图表降级：{e}]"
        try:
            from chart_writer import ascii_clock, ascii_valuation_chart

            charts["clock_ascii"] = ascii_clock(phase if phase != "未知" else "复苏期")
            if industries_data:
                charts["valuation_ascii"] = ascii_valuation_chart(industries_data)
        except Exception:
            pass
    return {**state, "charts": charts}


def persist_and_report(state: AgentState) -> AgentState:
    phase = state.get("macro_phase") or "（宏观定相已跳过）"
    intent = _intent(state)
    deg = state.get("degradation") or []
    mem = MemoryStore()
    prefs = mem.tuning_prefs
    pe_max = prefs.get("pe_pct_max", 60)

    metrics = state.get("macro_metrics") or {}
    lines = [
        f"# 宏观轮动编排报告",
        f"",
        f"## 摘要结论",
        f"一句话结论：当前宏观定相为 **{phase}**。查询：{state.get('query','')}",
        f"编排意图 intent=`{intent}`（macro=仅定相；prosperity/valuation/full 见说明书）。",
        f"",
        f"## 宏观阶段判定",
        f"阶段：{phase}；loose_liquidity={state.get('loose_liquidity')}；note={state.get('phase_note','')}"
        + (f"；asof={state.get('macro_asof')}" if state.get("macro_asof") else ""),
    ]
    if metrics:
        lines.append(
            "四维快照："
            f"PMI={metrics.get('pmi')}，CPI同比={metrics.get('cpi_yoy')}，"
            f"M2同比={metrics.get('m2_yoy')}，社融同比={metrics.get('sf_yoy')}，"
            f"政策预期差={metrics.get('policy_gap')}"
        )
    lines += [
        f"",
        f"## 行业筛选",
        ", ".join(x.get("name", "") for x in (state.get("industries") or [])) or "（无）",
        f"",
        f"## 景气确认",
    ]
    if state.get("prosperity"):
        lines.append("另类高频 Nowcast（及时样本，非官方统计）：")
        for p in state["prosperity"]:
            note = p.get("note") or ""
            extra = f"；{note}" if note else ""
            lines.append(
                f"- {p['industry']}: 景气={p.get('score')}（{p.get('period')}，"
                f"{p.get('source')} / {p.get('method', '-')}{extra}）"
            )
    else:
        lines.append("（已跳过或暂不可用）")

    lines += ["", "## 估值过滤", f"调参偏好 pe_pct_max={pe_max}（仅影响筛选门槛，不改原始值）"]
    if state.get("valuation"):
        for v in state["valuation"]:
            flag = "过筛" if v.get("pass_filter") else "未过筛"
            metric = v.get("metric") or "pe_ttm"
            mom = v.get("mom_20")
            mom_s = f"，mom20={mom}%" if mom is not None else ""
            pb = v.get("pb_pct")
            pb_s = f"，PB分位={pb}" if pb is not None else ""
            lines.append(
                f"- {v['industry']}: {metric}分位={v.get('pe_pct')}{pb_s}（{flag}{mom_s}，"
                f"{v.get('period')}，{v.get('source')} / {v.get('method', '-')}）"
            )
    else:
        lines.append("（已跳过或暂不可用）")

    lines += ["", "## 推荐结论"]
    prosp_map = {p["industry"]: p.get("score") for p in (state.get("prosperity") or [])}
    # 三重：估值过筛 + 景气非负（无景气分数则不拦）
    passed = []
    for v in state.get("valuation") or []:
        if not v.get("pass_filter"):
            continue
        sc = prosp_map.get(v["industry"])
        if sc is not None and float(sc) < 0:
            continue
        passed.append(v)
    if passed:
        lines.append("优先关注：" + "、".join(v["industry"] for v in passed))
        lines.append("宏观阶段 + 景气 + 估值三重维度已在上文列出（示意/降级路径请见标注）。")
    elif intent == "macro" and state.get("macro_phase"):
        names = "、".join(x.get("name", "") for x in (state.get("industries") or []))
        lines.append(f"本轮 intent=macro：仅完成定相。阶段映射行业参考：{names or '（无）'}。")
        lines.append("未跑景气/估值；完整轮动请改问「关注什么行业」或「完整报告」。")
    elif state.get("macro_phase") and (state.get("industries") or []):
        names = "、".join(x.get("name", "") for x in state["industries"])
        lines.append(f"按宏观阶段初筛可关注：{names}。")
        if not state.get("prosperity") or not state.get("valuation"):
            lines.append("景气/估值层已跳过或暂不可用时，上述仅为阶段映射参考；请见数据校验表标注。")
        else:
            lines.append("宏观阶段 + 景气 + 估值已计算；当前无同时满足「估值过筛且景气非负」的标的。")
    elif not state.get("macro_phase") and not state.get("prosperity") and not state.get("valuation"):
        lines.append("全部数据源不可用：仅输出分析框架说明，不输出具体数值。")
    else:
        lines.append("可关注初筛行业；估值或景气层已降级，请见标注。")

    lines += ["", "## 四象限图 / L3 图表"]
    charts = state.get("charts") or {}
    if charts.get("note"):
        lines.append(str(charts["note"]))
    files = charts.get("files") or {}
    title_map = {
        "clock": "美林时钟钟面图",
        "quadrant": "增长-通胀轨迹图",
        "valuation": "估值-景气四象限图",
    }
    for key, title in title_map.items():
        path = files.get(key)
        if path:
            rel = pathlib.Path(path).name
            lines.append(f"### {title}")
            lines.append(f"![{title}](charts/{rel})")
    if charts.get("clock_ascii"):
        lines.append("### ASCII 备用")
        lines.append("```")
        lines.append(charts["clock_ascii"])
        lines.append("```")
    if charts.get("valuation_ascii"):
        lines.append("```")
        lines.append(charts["valuation_ascii"])
        lines.append("```")
    if not files and not charts.get("clock_ascii"):
        lines.append("美林时钟图（降级占位）")

    lines += ["", "## 数据校验表", "| 指标 | 数值 | 数据期 | 来源 Skill / 方法 |", "|------|------|--------|-------------------|"]
    asof = state.get("macro_asof") or datetime.today().strftime("%Y-%m")
    if state.get("macro_phase"):
        lines.append(f"| 宏观阶段 | {state['macro_phase']} | {asof} | macro-monitor / phase_rules |")
        lines.append(f"| loose_liquidity | {state.get('loose_liquidity')} | {asof} | phase_rules |")
    for key, label, src in (
        ("pmi", "PMI", "get_macro_ci"),
        ("cpi_yoy", "CPI同比", "get_macro_pi"),
        ("m2_yoy", "M2同比", "get_macro_mb"),
        ("sf_yoy", "社融存量同比", "get_macro_mb"),
        ("policy_gap", "政策预期差", "get_macro_ci"),
    ):
        if key in metrics and metrics[key] is not None:
            lines.append(f"| {label} | {metrics[key]} | {asof} | {src} |")
    lines.append(f"| intent | {intent} | - | runtime |")
    for p in state.get("prosperity") or []:
        lines.append(
            f"| {p['industry']}景气 | {p.get('score')} | {p.get('period')} | "
            f"{p.get('source')} / {p.get('method', '-')} |"
        )
    for v in state.get("valuation") or []:
        lines.append(
            f"| {v['industry']}估值分位 | {v.get('pe_pct')} | {v.get('period')} | "
            f"{v.get('source')} / {v.get('method', '-')} |"
        )
        if v.get("pb_pct") is not None:
            lines.append(
                f"| {v['industry']}PB分位 | {v.get('pb_pct')} | {v.get('period')} | "
                f"{v.get('source')} / get_index_indicator |"
            )
    for d in deg:
        lines.append(f"| 降级 | {d} | - | runtime |")
    lines.append(f"| 来源Skill | macro-monitor / macro-altdata-nowcast / index-valuation-rotation | - | AGENTS.md |")

    out_dir = pathlib.Path(state.get("output_dir") or (ROOT / "reports" / "runtime_out"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # L5 导出
    export_paths: Dict[str, str] = {}
    try:
        from export_runtime import export_state

        export_paths = export_state(state, str(out_dir / "export"))
        if export_paths:
            lines += ["", "## L5 数据导出"]
            for k, p in export_paths.items():
                lines.append(f"- {k}: `{p}`")
    except Exception as e:
        deg = list(deg) + [f"L5 导出失败（{e}）"]
        lines.append(f"| 降级 | L5 导出失败（{e}） | - | runtime |")

    # L4 统一页：动态四象限 + 本次分析快照（不再拆 dashboard / animation）
    try:
        from export_l4 import export_l4, snapshot_from_state

        l4_paths = export_l4(
            str(out_dir / "l4.html"),
            snapshot=snapshot_from_state(state),
            rebuild=bool(state.get("l4_rebuild")),
        )
        export_paths = {**export_paths, **l4_paths}
        lines += [
            "",
            "## L4 交互页（动态四象限 + 本次快照）",
            f"- l4: `{l4_paths.get('l4_html')}`",
        ]
        if state.get("l4_rebuild"):
            lines.append("- 已重建历史动画内嵌数据（`--l4-rebuild`）")
        else:
            lines.append("- 历史动画沿用模板内嵌；本次快照已更新（完整刷新加 `--l4-rebuild`）")
    except Exception as e:
        deg = list(deg) + [f"L4 失败（{e}）"]
        lines.append(f"| 降级 | L4 失败（{e}） | - | runtime |")

    lines += [
        "",
        "## 免责声明",
        "本报告基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。",
    ]

    report_md = "\n".join(lines)
    report_path = out_dir / "runtime_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    if state.get("macro_phase"):
        mem.append_conclusion(state["macro_phase"], f"query={state.get('query','')}", state.get("query", ""))

    return {
        **state,
        "report_md": report_md,
        "output_dir": str(out_dir),
        "pe_pct_max": pe_max,
        "export_paths": export_paths,
        "degradation": deg,
    }


PIPELINE_STEPS = (
    resolve_intent,
    macro_phase_node,
    industry_screen,
    nowcast_node,
    valuation_node,
    render_node,
    persist_and_report,
)


def run_pipeline(
    query: str,
    mock: bool = True,
    output_dir: Optional[str] = None,
    l4_rebuild: bool = False,
) -> AgentState:
    mem = MemoryStore()
    state: AgentState = {
        "query": query,
        "mock": mock,
        "output_dir": output_dir or str(ROOT / "reports" / "runtime_out"),
        "pe_pct_max": float(mem.tuning_prefs.get("pe_pct_max", 60)),
        "degradation": [],
        "l4_rebuild": l4_rebuild,
    }
    for fn in PIPELINE_STEPS:
        state = fn(state)
    return state


def build_langgraph():
    """若安装了 langgraph，构建 StateGraph；否则返回 None。

    节点仍按固定顺序连接；景气/估值是否产出由节点内 intent 门控（与 pipeline 一致）。
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    g = StateGraph(dict)
    g.add_node("intent", resolve_intent)
    g.add_node("macro", macro_phase_node)
    g.add_node("screen", industry_screen)
    g.add_node("nowcast", nowcast_node)
    g.add_node("valuation", valuation_node)
    g.add_node("render", render_node)
    g.add_node("persist", persist_and_report)
    g.set_entry_point("intent")
    g.add_edge("intent", "macro")
    g.add_edge("macro", "screen")
    g.add_edge("screen", "nowcast")
    g.add_edge("nowcast", "valuation")
    g.add_edge("valuation", "render")
    g.add_edge("render", "persist")
    g.add_edge("persist", END)
    return g.compile()


def run(
    query: str,
    mock: bool = True,
    output_dir: Optional[str] = None,
    l4_rebuild: bool = False,
) -> AgentState:
    mem = MemoryStore()
    init: AgentState = {
        "query": query,
        "mock": mock,
        "output_dir": output_dir or str(ROOT / "reports" / "runtime_out"),
        "pe_pct_max": float(mem.tuning_prefs.get("pe_pct_max", 60)),
        "degradation": [],
        "l4_rebuild": l4_rebuild,
    }
    graph = build_langgraph()
    if graph is not None:
        return graph.invoke(init)
    return run_pipeline(query, mock=mock, output_dir=output_dir, l4_rebuild=l4_rebuild)
