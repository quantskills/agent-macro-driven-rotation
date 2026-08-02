# -*- coding: utf-8 -*-
"""
export_l4.py — 统一 L4 交互页（动态四象限 + 本次分析快照）

一份 HTML，不再拆成 dashboard.html / animation.html 两套出口。

用法：
  # 仅写入本次快照（沿用模板内已有历史动画数据，适合 runtime）
  python scripts/export_l4.py --output reports/runtime_out/l4.html \\
      --snapshot-json path/to/snap.json

  # 重建历史动画数据并内嵌（需凭证，较慢）
  python scripts/export_l4.py --rebuild --output reports/runtime_out/l4.html

  # runtime / 库调用
  from export_l4 import export_l4, snapshot_from_state
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

TEMPLATE_HTML = ROOT / "templates" / "l4.html"


def snapshot_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """从 runtime AgentState 生成 (f) 本次分析快照。"""
    phase = state.get("macro_phase") or "未知"
    asof = state.get("macro_asof") or datetime.today().strftime("%Y-%m-%d")
    prosp_by = {p["industry"]: p.get("score") for p in (state.get("prosperity") or [])}
    pe_by = {v["industry"]: v.get("pe_pct") for v in (state.get("valuation") or [])}
    code_by = {x.get("name"): x.get("code") for x in (state.get("industries") or [])}
    names = [x.get("name") for x in (state.get("industries") or []) if x.get("name")]
    if not names:
        names = list(dict.fromkeys(list(prosp_by) + list(pe_by)))
    industries: List[Dict[str, Any]] = [
        {
            "name": n,
            "code": code_by.get(n) or "",
            "prosperity": prosp_by.get(n),
            "pe_pct": pe_by.get(n),
        }
        for n in names
    ]
    return {
        "phase": phase,
        "asof": str(asof)[:10],
        "industries": industries,
        "metrics": state.get("macro_metrics") or {},
        "source": "runtime",
        "generated": datetime.now().isoformat(timespec="seconds"),
    }


def export_l4(
    output: str,
    *,
    snapshot: Optional[Dict[str, Any]] = None,
    rebuild: bool = False,
    start_date: str = "2022-01-01",
    end_date: str = "",
    template: Optional[str] = None,
    json_output: str = "reports/runtime_out/l4_data.json",
    write_json: bool = False,
    only_json: bool = False,
    username: str = "",
    password: str = "",
) -> Dict[str, str]:
    """写出统一 L4 HTML。返回路径字典。"""
    from build_animation import (
        _init_panda,
        build_animation_payload,
        embed_animation_data,
        embed_runtime_snapshot,
    )

    out_path = pathlib.Path(output)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, str] = {}
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    tmpl = pathlib.Path(template) if template else TEMPLATE_HTML
    if not tmpl.is_absolute():
        tmpl = ROOT / tmpl
    if not tmpl.exists():
        raise FileNotFoundError(f"L4 模板不存在：{tmpl}")

    payload = None
    if rebuild or only_json:
        pd_mod = _init_panda(username, password)
        payload = build_animation_payload(pd_mod, start_date, end)
        if write_json or only_json:
            jp = pathlib.Path(json_output)
            if not jp.is_absolute():
                jp = ROOT / jp
            jp.parent.mkdir(parents=True, exist_ok=True)
            jp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            paths["animation_json"] = str(jp)
            print(f"  [OK] JSON → {jp}（{jp.stat().st_size / 1024:.1f} KB）")
        if only_json:
            return paths

    # 以模板复制为目标页（保留样式/脚本；再覆写内嵌块）
    if out_path.resolve() != tmpl.resolve():
        shutil.copy2(tmpl, out_path)
    elif not out_path.exists():
        raise FileNotFoundError(f"模板不存在：{tmpl}")

    if payload is not None:
        embed_animation_data(out_path, payload)
        print(f"  [OK] 历史动画数据已内嵌 → {out_path}")

    if snapshot is not None:
        embed_runtime_snapshot(out_path, snapshot)
        print(f"  [OK] 本次分析快照已写入 → {out_path}")

    paths["l4_html"] = str(out_path)
    # 兼容旧键名
    paths["dashboard_html"] = str(out_path)
    paths["animation_html"] = str(out_path)
    return paths


def parse_args():
    p = argparse.ArgumentParser(description="统一 L4：动态四象限 + 本次分析快照")
    p.add_argument("--output", default="reports/runtime_out/l4.html")
    p.add_argument("--template", default=str(TEMPLATE_HTML))
    p.add_argument("--rebuild", action="store_true", help="重新拉取历史动画数据（需凭证）")
    p.add_argument("--start_date", default="2022-01-01")
    p.add_argument("--end_date", default="")
    p.add_argument("--snapshot-json", default="", help="本次快照 JSON 文件")
    p.add_argument("--phase", default="", help="无 snapshot-json 时的示意阶段")
    p.add_argument("--json-output", default="reports/runtime_out/l4_data.json")
    p.add_argument("--write-json", action="store_true")
    p.add_argument("--only-json", action="store_true")
    p.add_argument("--username", default="")
    p.add_argument("--password", default="")
    return p.parse_args()


def main():
    print("[TIP] 推荐统一入口：python -m runtime --live / python -m runtime l4 --rebuild", file=sys.stderr)
    args = parse_args()
    snap = None
    if args.snapshot_json:
        snap = json.loads(pathlib.Path(args.snapshot_json).read_text(encoding="utf-8"))
    elif args.phase:
        from industry_codes import name_code_pairs

        snap = {
            "phase": args.phase,
            "asof": datetime.today().strftime("%Y-%m-%d"),
            "industries": [
                {"name": n, "code": c, "prosperity": None, "pe_pct": None}
                for n, c in name_code_pairs(args.phase)
            ],
            "source": "export_l4_cli",
            "generated": datetime.now().isoformat(timespec="seconds"),
        }

    paths = export_l4(
        args.output,
        snapshot=snap,
        rebuild=args.rebuild,
        start_date=args.start_date,
        end_date=args.end_date,
        template=args.template,
        json_output=args.json_output,
        write_json=args.write_json,
        only_json=args.only_json,
        username=args.username,
        password=args.password,
    )
    print(f"[OK] L4 → {paths.get('l4_html') or paths}")


if __name__ == "__main__":
    main()
