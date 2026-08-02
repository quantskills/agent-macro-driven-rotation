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
    charts: Dict[str, str]
    degradation: List[str]
    report_md: str
    output_dir: str
    mock: bool
    pe_pct_max: float
    macro_asof: str


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
            result = determine_phase_from_macro(50.8, 50.2, 0.3, 8.2, 10.5, policy_gap=1.2)
            return {
                **state,
                "macro_phase": result["macro_phase"],
                "loose_liquidity": result["loose_liquidity"],
                "phase_note": result["phase_note"],
                "degradation": deg + ["macro: mock 示意输入（非实时 API）"],
            }
        except Exception as e:
            deg.append(f"宏观定相数据缺失，已跳过宏观阶段判定（{e}）")
            return {**state, "macro_phase": "", "degradation": deg}

    try:
        from datetime import timedelta

        from backtest import load_macro_and_determine_phases
        # 官方宏观常滞后：向前多取 8 个月，避免「当月无 PMI」时空表 iloc 越界
        end_dt = datetime.today()
        start_dt = (end_dt.replace(day=1) - timedelta(days=240)).replace(day=1)
        end = end_dt.strftime("%Y-%m-%d")
        start = start_dt.strftime("%Y-%m-%d")
        df = load_macro_and_determine_phases(start, end, allow_simulate=False)
        if df is None or len(df) == 0:
            raise RuntimeError(f"宏观阶段表为空（窗口 {start}~{end}）")
        row = df.iloc[-1]
        return {
            **state,
            "macro_phase": str(row["macro_phase"]),
            "loose_liquidity": bool(row.get("loose_liquidity", False)),
            "phase_note": str(row.get("phase_note", "")),
            "macro_asof": str(row.get("date", ""))[:10],
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
    inds = [
        {"name": n, "code": c}
        for n, c in name_code_pairs(phase)
    ]
    if not inds:
        names = PHASE_INDUSTRY_NAMES.get(phase, [])
        inds = [{"name": n, "code": ""} for n in names]
    return {**state, "industries": inds}


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

    # 诚实降级：runtime 未接入独立 Nowcast 客户端（非「偶发 API 失败」）
    deg.append(
        "景气层未接入：runtime 无 macro-altdata-nowcast 客户端，"
        "live 模式不产出景气分数（请在宿主对话中调用该 Skill，或后续接线）"
    )
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

    deg.append(
        "估值层未接入：runtime 无 index-valuation-rotation 客户端，"
        "live 模式不产出估值分位（请在宿主对话中调用该 Skill，或后续接线）"
    )
    return {**state, "valuation": [], "degradation": deg}


def render_node(state: AgentState) -> AgentState:
    phase = state.get("macro_phase") or "未知"
    charts: Dict[str, str] = {}
    try:
        from _writer import ascii_clock, ascii_valuation_chart
        charts["clock_ascii"] = ascii_clock(phase if phase != "未知" else "复苏期")
        industries_data = []
        prosp = {p["industry"]: p.get("score", 0) for p in (state.get("prosperity") or [])}
        for v in state.get("valuation") or []:
            industries_data.append({
                "name": v["industry"],
                "sentiment": prosp.get(v["industry"], 0),
                "valuation_pct": v.get("pe_pct", 50),
                "phase_match": True,
            })
        if industries_data:
            charts["valuation_ascii"] = ascii_valuation_chart(industries_data)
    except Exception as e:
        charts["error"] = str(e)
    return {**state, "charts": charts}


def persist_and_report(state: AgentState) -> AgentState:
    phase = state.get("macro_phase") or "（宏观定相已跳过）"
    intent = _intent(state)
    deg = state.get("degradation") or []
    mem = MemoryStore()
    prefs = mem.tuning_prefs
    pe_max = prefs.get("pe_pct_max", 60)

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
        f"",
        f"## 行业筛选",
        ", ".join(x.get("name", "") for x in (state.get("industries") or [])) or "（无）",
        f"",
        f"## 景气确认",
    ]
    if state.get("prosperity"):
        for p in state["prosperity"]:
            lines.append(f"- {p['industry']}: 景气={p.get('score')}（{p.get('period')}，{p.get('source')}）")
    else:
        lines.append("（已跳过或未接入）")

    lines += ["", "## 估值过滤", f"调参偏好 pe_pct_max={pe_max}（仅影响筛选门槛，不改原始值）"]
    if state.get("valuation"):
        for v in state["valuation"]:
            flag = "过筛" if v.get("pass_filter") else "未过筛"
            lines.append(
                f"- {v['industry']}: PE分位={v.get('pe_pct')}（{flag}，{v.get('period')}，{v.get('source')}）"
            )
    else:
        lines.append("（已跳过或未接入）")

    lines += ["", "## 推荐结论"]
    passed = [v for v in (state.get("valuation") or []) if v.get("pass_filter")]
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
            lines.append("景气/估值层已跳过或未接入时，上述仅为阶段映射参考；请见数据校验表标注。")
        else:
            lines.append("宏观阶段 + 景气 + 估值三重维度已在上文列出。")
    elif not state.get("macro_phase") and not state.get("prosperity") and not state.get("valuation"):
        lines.append("全部数据源不可用：仅输出分析框架说明，不输出具体数值。")
    else:
        lines.append("可关注初筛行业；估值或景气层已降级，请见标注。")

    lines += ["", "## 四象限图"]
    charts = state.get("charts") or {}
    if charts.get("clock_ascii"):
        lines.append("```")
        lines.append(charts["clock_ascii"])
        lines.append("```")
    else:
        lines.append("美林时钟图（降级占位）")

    lines += ["", "## 数据校验表", "| 指标 | 数值 | 数据期 | 来源 Skill / 方法 |", "|------|------|--------|-------------------|"]
    if state.get("macro_phase"):
        asof = state.get("macro_asof") or datetime.today().strftime("%Y-%m")
        lines.append(f"| 宏观阶段 | {state['macro_phase']} | {asof} | macro-monitor / phase_rules |")
        lines.append(f"| loose_liquidity | {state.get('loose_liquidity')} | {asof} | phase_rules |")
    lines.append(f"| intent | {intent} | - | runtime |")
    for d in deg:
        lines.append(f"| 降级 | {d} | - | runtime |")
    lines.append(f"| 来源Skill | macro-monitor / macro-altdata-nowcast / index-valuation-rotation | - | SKILL.md |")

    lines += [
        "",
        "## 免责声明",
        "本报告基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。",
    ]

    report_md = "\n".join(lines)
    out_dir = pathlib.Path(state.get("output_dir") or (ROOT / "reports" / "runtime_out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "runtime_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    if state.get("macro_phase"):
        mem.append_conclusion(state["macro_phase"], f"query={state.get('query','')}", state.get("query", ""))

    return {**state, "report_md": report_md, "output_dir": str(out_dir), "pe_pct_max": pe_max}


PIPELINE_STEPS = (
    resolve_intent,
    macro_phase_node,
    industry_screen,
    nowcast_node,
    valuation_node,
    render_node,
    persist_and_report,
)


def run_pipeline(query: str, mock: bool = True, output_dir: Optional[str] = None) -> AgentState:
    mem = MemoryStore()
    state: AgentState = {
        "query": query,
        "mock": mock,
        "output_dir": output_dir or str(ROOT / "reports" / "runtime_out"),
        "pe_pct_max": float(mem.tuning_prefs.get("pe_pct_max", 60)),
        "degradation": [],
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


def run(query: str, mock: bool = True, output_dir: Optional[str] = None) -> AgentState:
    mem = MemoryStore()
    init: AgentState = {
        "query": query,
        "mock": mock,
        "output_dir": output_dir or str(ROOT / "reports" / "runtime_out"),
        "pe_pct_max": float(mem.tuning_prefs.get("pe_pct_max", 60)),
        "degradation": [],
    }
    graph = build_langgraph()
    if graph is not None:
        return graph.invoke(init)
    return run_pipeline(query, mock=mock, output_dir=output_dir)
