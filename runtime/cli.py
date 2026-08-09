# -*- coding: utf-8 -*-
"""统一入口：分析 / 校验 / 对账 / L4 / 回测 / 单测。

推荐用法（日常只需这一条）：

  python -m runtime --live --query "现在该关注什么行业"

默认会：定相→景气→估值→L3/L4/L5 → 自动校验报告。
可选：--reconcile / --l4-rebuild / --backtest / --all / --self-test
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _ensure_paths() -> None:
    for p in (str(ROOT), str(SCRIPTS)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _py() -> str:
    return sys.executable


def _run_script(script: str, argv: Sequence[str], *, check: bool = False) -> int:
    cmd = [_py(), str(SCRIPTS / script), *argv]
    print(f"\n>>> {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(ROOT))
    if check and r.returncode != 0:
        raise SystemExit(r.returncode)
    return int(r.returncode)


def cmd_run(args: argparse.Namespace) -> int:
    _ensure_paths()
    from runtime.graph import run

    mock = not args.live
    out_dir = Path(args.output_dir)
    print("=" * 60)
    print("  宏观轮动统一运行时")
    print(f"  mode={'live' if args.live else 'mock'}  query={args.query!r}")
    print(f"  output={out_dir}")
    print("=" * 60)

    state = run(
        args.query,
        mock=mock,
        output_dir=str(out_dir),
        l4_rebuild=bool(args.l4_rebuild or args.all),
    )
    report = out_dir / "runtime_report.md"
    print(f"[OK] intent={state.get('intent')} phase={state.get('macro_phase')}")
    deg = state.get("degradation") or []
    if deg:
        print(f"[OK] degradation={deg}")
    print(f"[OK] report → {report}")
    l4 = (state.get("export_paths") or {}).get("l4_html")
    if l4:
        print(f"[OK] L4 → {l4}")

    rc = 0
    do_validate = not args.no_validate
    do_reconcile = bool(args.reconcile or args.all)
    do_backtest = bool(args.backtest)

    if do_validate and report.exists():
        vrc = _run_script("validate_report.py", [str(report)])
        if vrc != 0:
            rc = vrc
            print("[WARN] 报告校验未全绿（见上）")

    if do_reconcile and report.exists():
        if args.live:
            rargv = [str(report), "--live", "--output", str(out_dir / "reconcile.csv")]
        else:
            fixture = SCRIPTS / "fixtures" / "reconcile_macro_sample.json"
            rargv = [
                str(report),
                "--fixture",
                str(fixture),
                "--output",
                str(out_dir / "reconcile.csv"),
            ]
        rrc = _run_script("reconcile_report_vs_api.py", rargv)
        if rrc != 0 and rc == 0:
            rc = rrc

    if do_backtest:
        bdir = ROOT / "reports" / "backtest"
        bargv = [
            "--start_date",
            args.backtest_start,
            "--end_date",
            args.backtest_end,
            "--output_dir",
            str(bdir),
        ]
        if args.allow_simulate or not args.live:
            bargv.append("--allow-simulate")
        brc = _run_script("backtest.py", bargv)
        if brc != 0 and rc == 0:
            rc = brc

    print("\n" + "=" * 60)
    print("  产物清单")
    print("=" * 60)
    for p in (
        out_dir / "runtime_report.md",
        out_dir / "l4.html",
        out_dir / "export" / "rotation_data.xlsx",
        out_dir / "reconcile.csv",
        ROOT / "reports" / "backtest" / "phase_stats.csv",
    ):
        if p.exists():
            print(f"  ✓ {p}")
    print("=" * 60)
    return rc


def cmd_validate(args: argparse.Namespace) -> int:
    return _run_script("validate_report.py", [args.report])


def cmd_reconcile(args: argparse.Namespace) -> int:
    argv: List[str] = [args.report]
    if args.live:
        argv.append("--live")
    if args.fixture:
        argv.extend(["--fixture", args.fixture])
    if args.output:
        argv.extend(["--output", args.output])
    if args.strict:
        argv.append("--strict")
    return _run_script("reconcile_report_vs_api.py", argv)


def cmd_backtest(args: argparse.Namespace) -> int:
    argv = [
        "--start_date",
        args.start_date,
        "--end_date",
        args.end_date,
        "--output_dir",
        args.output_dir,
    ]
    if args.allow_simulate:
        argv.append("--allow-simulate")
    if args.phase_file:
        argv.extend(["--phase_file", args.phase_file])
    if args.benchmark:
        argv.extend(["--benchmark", args.benchmark])
    return _run_script("backtest.py", argv)


def cmd_l4(args: argparse.Namespace) -> int:
    argv = ["--output", args.output]
    if args.rebuild:
        argv.append("--rebuild")
    if args.phase:
        argv.extend(["--phase", args.phase])
    if args.start_date:
        argv.extend(["--start_date", args.start_date])
    if args.end_date:
        argv.extend(["--end_date", args.end_date])
    return _run_script("export_l4.py", argv)


def cmd_self_test(args: argparse.Namespace) -> int:
    del args
    tests = [
        "test_validate_logic.py",
        "test_backtest_logic.py",
        "test_reconcile_logic.py",
    ]
    rc = 0
    for t in tests:
        code = _run_script(t, [])
        if code != 0:
            rc = code
    return rc


def cmd_clean(args: argparse.Namespace) -> int:
    """清除可再生成的运行产物与旧命名残留。"""
    import shutil

    targets = [
        ROOT / "reports" / "runtime_out",
        ROOT / "reports" / "backtest",
        ROOT / "reports" / "test_charts",
        ROOT / "reports" / "runtime_out_mock",
        ROOT / "reports" / "export_live_test",
        ROOT / "backtest_output",  # 旧路径残留
        ROOT / "test_charts",
        ROOT / "animation_data",
        ROOT / "animation.html",
        ROOT / "_writer.py",
        ROOT / "reports" / "test_results_partial.json",
        ROOT / "reports" / "test_results_full.json",
        ROOT / "reports" / "test_run_log.txt",
        ROOT / "reports" / "samples" / "rotation_dashboard.html",
        ROOT / "reports" / "samples" / "_l4_compat.html",
        ROOT / "测试报告.md",
    ]
    for p in (ROOT / "reports").rglob("dashboard.html"):
        targets.append(p)
    for p in (ROOT / "reports").rglob("charts_writer_smoke"):
        targets.append(p)

    keep_gitkeep_dirs = {
        ROOT / "reports" / "runtime_out",
        ROOT / "reports" / "backtest",
    }

    removed = 0
    for t in targets:
        if not t.exists():
            continue
        if t.is_dir():
            if args.dry_run:
                print(f"[dry-run] dir  {t}")
            else:
                shutil.rmtree(t)
                print(f"[REMOVED] dir  {t}")
            removed += 1
        else:
            if args.dry_run:
                print(f"[dry-run] file {t}")
            else:
                t.unlink()
                print(f"[REMOVED] file {t}")
            removed += 1

    if not args.dry_run:
        for d in keep_gitkeep_dirs:
            d.mkdir(parents=True, exist_ok=True)
            gk = d / ".gitkeep"
            if not gk.exists():
                gk.write_text("", encoding="utf-8")

    print(f"[OK] clean 完成（{'dry-run ' if args.dry_run else ''}{removed} 项）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m runtime",
        description="宏观轮动统一入口（分析+校验+对账+L4+回测）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python -m runtime --live --query "现在该关注什么行业"
  python -m runtime --live --all          # 含对账 + 重建 L4 历史
  python -m runtime --live --backtest     # 另跑阶段回测
  python -m runtime --self-test           # 组件单测
  python -m runtime clean                 # 清除可再生成产物 / 旧残留
  python -m runtime validate reports/runtime_out/runtime_report.md
  python -m runtime backtest --allow-simulate --start_date 2024-01-01
""",
    )
    sub = p.add_subparsers(dest="cmd")

    # --- default / run flags on top-level ---
    p.add_argument("--query", default="按改进版美林时钟做一轮完整行业轮动报告")
    p.add_argument("--output-dir", default=str(ROOT / "reports" / "runtime_out"))
    p.add_argument("--live", action="store_true", help="真实 panda_data（默认 mock）")
    p.add_argument("--mock", action="store_true", help="示意数据（默认）")
    p.add_argument("--l4-rebuild", action="store_true", help="重建 L4 历史动画内嵌")
    p.add_argument("--no-validate", action="store_true", help="跳过报告自动校验")
    p.add_argument("--reconcile", action="store_true", help="跑完后做 L2 对账")
    p.add_argument("--backtest", action="store_true", help="跑完后做阶段回测")
    p.add_argument("--all", action="store_true", help="= --reconcile --l4-rebuild（并校验）")
    p.add_argument("--self-test", action="store_true", help="只跑组件单测")
    p.add_argument("--backtest-start", default="2024-01-01")
    p.add_argument("--backtest-end", default="")
    p.add_argument("--allow-simulate", action="store_true", help="回测允许模拟行情")

    # validate
    pv = sub.add_parser("validate", help="校验 Markdown 报告")
    pv.add_argument("report")

    # reconcile
    pr = sub.add_parser("reconcile", help="报告 vs API/fixture 对账")
    pr.add_argument("report")
    pr.add_argument("--live", action="store_true")
    pr.add_argument("--fixture", default="")
    pr.add_argument("--output", default="")
    pr.add_argument("--strict", action="store_true")

    # backtest
    pb = sub.add_parser("backtest", help="宏观阶段回测")
    pb.add_argument("--start_date", default="2024-01-01")
    pb.add_argument("--end_date", default="")
    pb.add_argument("--output_dir", default=str(ROOT / "reports" / "backtest"))
    pb.add_argument("--allow-simulate", action="store_true")
    pb.add_argument("--phase_file", default="")
    pb.add_argument("--benchmark", default="000300.SH")

    # l4
    pl = sub.add_parser("l4", help="写出/重建统一 L4 页")
    pl.add_argument("--output", default=str(ROOT / "reports" / "runtime_out" / "l4.html"))
    pl.add_argument("--rebuild", action="store_true")
    pl.add_argument("--phase", default="")
    pl.add_argument("--start_date", default="2022-01-01")
    pl.add_argument("--end_date", default="")

    # test
    sub.add_parser("test", help="组件单测（同 --self-test）")

    # clean
    pc = sub.add_parser("clean", help="清除可再生成产物与旧目录残留")
    pc.add_argument("--dry-run", action="store_true", help="只列出将删除项")

    # run (explicit)
    sub.add_parser("run", help="跑完整分析（同无子命令）")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    # fill backtest end default
    if not getattr(args, "backtest_end", None):
        from datetime import datetime

        args.backtest_end = datetime.today().strftime("%Y-%m-%d")
    if hasattr(args, "end_date") and not args.end_date:
        from datetime import datetime

        args.end_date = datetime.today().strftime("%Y-%m-%d")

    if args.self_test or args.cmd == "test":
        return cmd_self_test(args)
    if args.cmd == "clean":
        return cmd_clean(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    if args.cmd == "reconcile":
        return cmd_reconcile(args)
    if args.cmd == "backtest":
        return cmd_backtest(args)
    if args.cmd == "l4":
        return cmd_l4(args)
    # default / run
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
