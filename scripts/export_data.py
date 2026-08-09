# -*- coding: utf-8 -*-
"""
export_data.py — L5 分析数据导出（CSV / XLSX）

用法：
  python scripts/export_data.py --output-dir reports/samples/export
  python scripts/export_data.py --input payload.json --output-dir out --format both

默认写入示意宏观定相 / 景气 / 估值 / 推荐列表；生产请传 --input JSON。
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from typing import Any, Dict, List

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from industry_codes import CODE_VERIFIED_DATE, name_code_pairs  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="导出宏观轮动分析数据 CSV/XLSX")
    p.add_argument("--phase", default="复苏期")
    p.add_argument("--output-dir", default="reports/samples/export")
    p.add_argument("--input", default="", help="可选 JSON 载荷")
    p.add_argument("--format", choices=["csv", "xlsx", "both"], default="both")
    p.add_argument(
        "--live",
        action="store_true",
        help="跑 runtime 全链路后导出（需凭证）；覆盖 --phase/--input 示意数据",
    )
    p.add_argument("--query", default="按改进版美林时钟做一轮完整行业轮动报告")
    return p.parse_args()


def default_payload(phase: str) -> Dict[str, Any]:
    pairs = name_code_pairs(phase)
    macro = [
        {"metric": "宏观阶段", "value": phase, "period": "2026-06", "source": "macro-monitor"},
        {"metric": "PMI", "value": "50.8", "period": "2026-06", "source": "get_macro_ci"},
        {"metric": "CPI同比", "value": "0.3%", "period": "2026-06", "source": "get_macro_pi"},
        {"metric": "M2同比", "value": "8.2%", "period": "2026-06", "source": "get_macro_mb"},
        {"metric": "社融存量同比", "value": "10.5%", "period": "2026-06", "source": "get_macro_mb"},
        {"metric": "loose_liquidity", "value": "True", "period": "2026-06", "source": "rule"},
        {"metric": "code_verified_date", "value": CODE_VERIFIED_DATE, "period": "-", "source": "industry_codes"},
    ]
    prosperity = []
    valuation = []
    recommend = []
    for i, (name, code) in enumerate(pairs):
        prosperity.append({
            "industry": name, "code": code, "score": round(0.5 - i * 0.1, 1),
            "period": "2026-06", "source": "macro-altdata-nowcast",
            "flag": "_demo",
        })
        valuation.append({
            "industry": name, "code": code, "pe_pct": 35 + i * 5,
            "pb_pct": 40 + i * 3, "period": "2026-06",
            "source": "index-valuation-rotation",
            "flag": "_demo",
        })
        if i < 2:
            recommend.append({
                "industry": name, "code": code, "reason": "高景气+估值适中",
                "macro_phase": phase,
                "flag": "_demo",
            })
    return {
        "macro": macro,
        "prosperity": prosperity,
        "valuation": valuation,
        "recommend": recommend,
    }


def write_csv(path: pathlib.Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_xlsx(path: pathlib.Path, sheets: Dict[str, List[Dict[str, Any]]]) -> None:
    try:
        import openpyxl
    except ImportError:
        # 无 openpyxl：写一个汇总 csv 代替并提示
        print("[WARN] openpyxl 未安装，跳过 xlsx，仅保留 CSV。")
        return
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = name[:31]
            first = False
        else:
            ws = wb.create_sheet(title=name[:31])
        if not rows:
            continue
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
    wb.save(path)
    print(f"[OK] XLSX 已写入：{path}")


def main():
    print("[TIP] 推荐统一入口：python -m runtime --live （已含 L5 导出）", file=sys.stderr)
    args = parse_args()
    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.live:
        root = SCRIPT_DIR.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from export_runtime import export_state, state_to_payload
        from runtime.graph import run

        state = run(args.query, mock=False, output_dir=str(out_dir / "runtime_tmp"))
        paths = export_state(state, str(out_dir), fmt=args.format)
        for k, p in paths.items():
            print(f"[OK] live 导出 {k}: {p}")
        payload = state_to_payload(state)
    elif args.input:
        payload = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    else:
        payload = default_payload(args.phase)

    if not args.live:
        sheets = {
            "macro": payload.get("macro", []),
            "prosperity": payload.get("prosperity", []),
            "valuation": payload.get("valuation", []),
            "recommend": payload.get("recommend", []),
        }

        if args.format in ("csv", "both"):
            for name, rows in sheets.items():
                path = out_dir / f"{name}.csv"
                write_csv(path, rows)
                print(f"[OK] CSV 已写入：{path}")

        if args.format in ("xlsx", "both"):
            write_xlsx(out_dir / "rotation_export.xlsx", sheets)

    # 免责声明
    (out_dir / "README.txt").write_text(
        "仅供研究参考，不构成任何投资建议。\n",
        encoding="utf-8",
    )
    print(f"[OK] L5 导出完成：{out_dir.resolve()}")


if __name__ == "__main__":
    main()
