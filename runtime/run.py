# -*- coding: utf-8 -*-
"""CLI: python -m runtime.run --query "现在该关注什么行业" [--mock|--live]

默认 --mock：不调用真实 API，走示意输入 + 降级标注，用于编排冒烟。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证仓库根在 path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.graph import run  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="宏观轮动最小 LangGraph/顺序编排运行时")
    p.add_argument("--query", default="按改进版美林时钟做一轮完整行业轮动报告")
    p.add_argument("--output-dir", default=str(ROOT / "reports" / "runtime_out"))
    p.add_argument("--live", action="store_true", help="尝试真实 panda_data（失败则降级标注）")
    p.add_argument("--mock", action="store_true", default=True, help="使用示意输入（默认）")
    args = p.parse_args()
    mock = not args.live
    state = run(args.query, mock=mock, output_dir=args.output_dir)
    print(f"[OK] intent={state.get('intent')} phase={state.get('macro_phase')}")
    print(f"[OK] degradation={state.get('degradation')}")
    print(f"[OK] report → {Path(state.get('output_dir','')) / 'runtime_report.md'}")


if __name__ == "__main__":
    main()
