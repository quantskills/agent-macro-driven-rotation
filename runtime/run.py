# -*- coding: utf-8 -*-
"""兼容入口：转发到统一 CLI。

推荐：
  python -m runtime --live --query "现在该关注什么行业"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.cli import main  # noqa: E402


if __name__ == "__main__":
    # 保留 `python -m runtime.run` 习惯；参数原样交给统一 CLI
    raise SystemExit(main())
