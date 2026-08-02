# -*- coding: utf-8 -*-
"""
export_dashboard.py — L4 行业轮动交互仪表盘（Plotly HTML）

用法：
  python scripts/export_dashboard.py --output reports/dashboard.html
  python scripts/export_dashboard.py --phase 复苏期 --output out/dash.html

输入可为 CLI 参数或 JSON（--input），默认使用示意数据生成可交互 HTML。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from industry_codes import PHASE_INDUSTRY_NAMES, name_code_pairs  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="导出行业轮动 Plotly HTML 仪表盘")
    p.add_argument("--phase", default="复苏期", help="当前宏观阶段")
    p.add_argument("--output", default="reports/samples/rotation_dashboard.html")
    p.add_argument("--input", default="", help="可选 JSON：phase/industries[{name,prosperity,pe_pct}]")
    p.add_argument("--title", default="宏观驱动行业轮动仪表盘")
    return p.parse_args()


def default_industries(phase: str) -> List[Dict[str, Any]]:
    rows = []
    demo_scores = {
        "复苏期": [(0.5, 35), (0.5, 42), (0.0, 55), (0.3, 40), (0.2, 48)],
        "过热期": [(0.6, 70), (0.5, 65), (0.4, 60), (0.3, 55), (0.2, 50)],
        "滞胀期": [(0.2, 45), (0.3, 40), (0.1, 35), (0.0, 50)],
        "衰退期": [(-0.2, 30)],
    }
    scores = demo_scores.get(phase, [(0.0, 50)] * 5)
    for i, (name, code) in enumerate(name_code_pairs(phase)):
        prosper, pe = scores[i % len(scores)]
        rows.append({
            "name": name,
            "code": code,
            "prosperity": prosper,
            "pe_pct": pe,
        })
    if not rows:
        for name in PHASE_INDUSTRY_NAMES.get(phase, ["黄金"]):
            rows.append({"name": name, "code": "", "prosperity": 0.0, "pe_pct": 50})
    return rows


def load_payload(args) -> Dict[str, Any]:
    if args.input:
        data = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
        return {
            "phase": data.get("phase", args.phase),
            "industries": data.get("industries", default_industries(args.phase)),
            "evidence": data.get("evidence", []),
        }
    return {
        "phase": args.phase,
        "industries": default_industries(args.phase),
        "evidence": [
            {"metric": "宏观阶段", "value": args.phase, "source": "macro-monitor"},
            {"metric": "说明", "value": "示意数据；生产请传入 --input JSON", "source": "export_dashboard"},
        ],
    }


def build_html(payload: Dict[str, Any], title: str) -> str:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        # 无 plotly 时输出简易 HTML
        inds = payload["industries"]
        rows = "".join(
            f"<tr><td>{x.get('name')}</td><td>{x.get('code','')}</td>"
            f"<td>{x.get('prosperity')}</td><td>{x.get('pe_pct')}</td></tr>"
            for x in inds
        )
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h1>{title}</h1>
<p>当前阶段：<b>{payload['phase']}</b>（plotly 未安装，降级为表格）</p>
<table border="1" cellpadding="6"><tr><th>行业</th><th>代码</th><th>景气</th><th>PE分位</th></tr>
{rows}</table>
<p>仅供研究参考，不构成任何投资建议。</p>
</body></html>"""

    inds = payload["industries"]
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("估值-景气象限", "行业列表"),
        specs=[[{"type": "scatter"}, {"type": "table"}]],
    )
    fig.add_trace(
        go.Scatter(
            x=[x.get("prosperity", 0) for x in inds],
            y=[x.get("pe_pct", 50) for x in inds],
            mode="markers+text",
            text=[x.get("name", "") for x in inds],
            textposition="top center",
            marker=dict(size=14),
            name="行业",
        ),
        row=1, col=1,
    )
    fig.add_hline(y=50, line_dash="dot", row=1, col=1)
    fig.add_vline(x=0, line_dash="dot", row=1, col=1)
    fig.update_xaxes(title_text="景气分数", row=1, col=1)
    fig.update_yaxes(title_text="PE分位(%)", row=1, col=1)

    fig.add_trace(
        go.Table(
            header=dict(values=["行业", "代码", "景气", "PE分位"]),
            cells=dict(values=[
                [x.get("name", "") for x in inds],
                [x.get("code", "") for x in inds],
                [x.get("prosperity", "") for x in inds],
                [x.get("pe_pct", "") for x in inds],
            ]),
        ),
        row=1, col=2,
    )
    fig.update_layout(
        title=f"{title} · 当前阶段：{payload['phase']}",
        height=520,
        showlegend=False,
        annotations=[
            dict(
                text="仅供研究参考，不构成任何投资建议",
                xref="paper", yref="paper", x=0.5, y=-0.12,
                showarrow=False, font=dict(size=11, color="#666"),
            )
        ],
    )
    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def main():
    args = parse_args()
    payload = load_payload(args)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(payload, args.title)
    out.write_text(html, encoding="utf-8")
    print(f"[OK] L4 仪表盘已写入：{out.resolve()}")


if __name__ == "__main__":
    main()
