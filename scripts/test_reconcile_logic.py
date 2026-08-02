# -*- coding: utf-8 -*-
"""reconcile_report_vs_api.py 离线单测（不依赖 panda_data）。"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconcile_report_vs_api.py"
SAMPLE = ROOT / "reports" / "samples" / "e2e_rotation_sample.md"
FIXTURE = ROOT / "scripts" / "fixtures" / "reconcile_macro_sample.json"
OUT = ROOT / "reports" / "samples" / "reconcile_sample.csv"

sys.path.insert(0, str(ROOT / "scripts"))
import reconcile_report_vs_api as rec  # noqa: E402


def test_parse_table():
    md = SAMPLE.read_text(encoding="utf-8")
    rows = rec.parse_evidence_table(md)
    assert len(rows) >= 4, f"期望至少 4 行宏观，实际 {len(rows)}"
    metrics = [r.metric for r in rows]
    assert any("PMI" in m or "pmi" in m.lower() for m in metrics)
    return True, f"解析到 {len(rows)} 行"


def test_match_and_number():
    assert rec.match_catalog("CPI同比") is not None
    assert rec.parse_number("0.3%") == 0.3
    assert rec.parse_number("+0.5") == 0.5
    assert rec.period_to_yyyymm("2026-06") == "2026-06"
    return True, "解析/映射正常"


def test_cli_fixture_pass():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(SCRIPT),
        str(SAMPLE),
        "--fixture",
        str(FIXTURE),
        "--output",
        str(OUT),
        "--pmi-prev",
        "50.2",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    text = OUT.read_text(encoding="utf-8-sig")
    assert "PASS" in text
    assert "MANUAL" in text  # 景气/估值
    return True, f"CLI PASS，CSV → {OUT}"


def test_phase_mismatch_detected():
    # 构造：宏观数值仍是复苏特征，但正文写死过热期
    md = """# t
## 摘要结论
宏观定相为**过热期**。
## 数据校验表
| 指标 | 数值 | 数据期 | 来源 |
|------|------|--------|------|
| PMI | 50.8 | 2026-06 | macro-monitor |
| CPI同比 | 0.3% | 2026-06 | macro-monitor |
| M2同比 | 8.2% | 2026-06 | macro-monitor |
| 社融存量同比 | 10.5% | 2026-06 | macro-monitor |
"""
    rows = rec.parse_evidence_table(md)
    fixture = rec.load_fixture(str(FIXTURE))
    results = rec.reconcile_rows(rows, fixture, live=False, tol_override=None)
    phase = rec.check_phase(md, rows, results, fixture, live=False, pmi_prev_arg=50.2)
    assert phase is not None and phase.status == "FAIL", phase
    assert phase.report_phase == "过热期" and phase.rule_phase == "复苏期"
    return True, f"定相不一致可检出: 报告={phase.report_phase} 规则={phase.rule_phase}"


def main():
    cases = [
        ("TC-R01 解析数据校验表", test_parse_table),
        ("TC-R02 指标映射与数值解析", test_match_and_number),
        ("TC-R03 fixture CLI 对账通过", test_cli_fixture_pass),
        ("TC-R04 定相不一致可检出", test_phase_mismatch_detected),
    ]
    print("=" * 55)
    print("  reconcile_report_vs_api 单元测试")
    print("=" * 55)
    ok_n = fail_n = 0
    for name, fn in cases:
        try:
            ok, msg = fn()
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)
        status = "PASS" if ok else "FAIL"
        print(f"\n  [{status}] {name}")
        print(f"         {msg}")
        if ok:
            ok_n += 1
        else:
            fail_n += 1
    print("\n" + "=" * 55)
    print(f"  总计：{len(cases)} 项，{ok_n} 通过，{fail_n} 失败")
    print("=" * 55)
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
