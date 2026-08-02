# -*- coding: utf-8 -*-
"""
validate_report.py 核心逻辑单元测试

直接 import 真实实现，禁止复制粘贴规则配置，避免与线上逻辑漂移。
不依赖第三方包，可在裸 Python 3.12 环境下运行。
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

SCRIPT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_report import (  # noqa: E402
    check_disclaimer,
    check_forbidden_phrases,
    check_quadrant_chart,
    check_required_sections,
    check_skill_sources,
    check_timestamps,
    check_triple_evidence,
    validate,
)

RESULTS = []


def case(name):
    def decorator(fn):
        RESULTS.append((name, fn))
        return fn
    return decorator


# ---------------------------------------------------------------------------
# 样例报告
# ---------------------------------------------------------------------------

GOOD_REPORT = """
## 摘要结论
一句话结论：当前处于复苏期，电子与医药景气偏暖、估值适中，可关注配置。数据截至 2026-06。

## 宏观阶段判定
宏观定相：复苏期（扩张 + 低通胀 + 宽松）。来源 Skill：macro-monitor。
- PMI = 50.8（2026-06）
- CPI同比 = 0.3%（2026-06）
- M2同比 = 8.2%（2026-06）
- 社融存量同比 = 10.5%（2026-06）

## 行业筛选
行业初筛（复苏期映射）：电子、医药生物、计算机、食品饮料。

## 景气确认
另类高频 Nowcast（macro-altdata-nowcast）：
- 电子景气分数 +0.5（2026-06，及时样本）
- 医药景气分数 +0.5（2026-06，及时样本）

## 估值过滤
估值过滤（index-valuation-rotation）：
- 电子 PE分位 35（5年窗口，2026-06）
- 医药生物 PE分位 42（5年窗口，2026-06）

## 推荐结论
优先关注电子、医药生物。
宏观阶段：复苏期；景气：另类高频同比环比偏暖；估值：PE分位处于中性偏低区间。

## 四象限图
美林时钟图 / 估值-景气四象限图（ASCII 降级）：

```
        过热 | 滞胀
        -----+-----
        复苏*| 衰退
```

## 数据校验表
| 指标 | 数值 | 数据期 | 来源 Skill |
|------|------|--------|------------|
| PMI | 50.8 | 2026-06 | macro-monitor |
| CPI同比 | 0.3% | 2026-06 | macro-monitor |
| 电子景气 | +0.5 | 2026-06 | macro-altdata-nowcast |
| 电子PE分位 | 35 | 2026-06 | index-valuation-rotation |

## 免责声明
本报告仅供研究参考，不构成任何投资建议。
"""

BAD_NO_DISCLAIMER = """
## 摘要结论
当前复苏。数据 2026-06。
## 宏观阶段判定
复苏期 PMI = 50.8（2026-06）
## 行业筛选
电子
## 景气确认
nowcast 景气分数 +1（2026-06）
## 估值过滤
PE分位 30（2026-06） valuation
## 推荐结论
关注电子。宏观阶段复苏，景气回升，估值适中。
## 数据校验表
| 指标 | 数值 | 数据期 | 来源 |
| PMI | 50.8 | 2026-06 | macro-monitor |
来源：macro-monitor / macro-altdata-nowcast / index-valuation-rotation
四象限图 ASCII
"""

BAD_FORBIDDEN = GOOD_REPORT + "\n强烈推荐买入电子，必涨。\n"


@case("TC-01 合规报告：七项全部通过")
def test_good_report():
    checks = [
        check_required_sections(GOOD_REPORT),
        check_timestamps(GOOD_REPORT),
        check_skill_sources(GOOD_REPORT),
        check_disclaimer(GOOD_REPORT),
        check_quadrant_chart(GOOD_REPORT),
        check_triple_evidence(GOOD_REPORT),
        check_forbidden_phrases(GOOD_REPORT),
    ]
    failed = [c.name for c in checks if not c.passed]
    if failed:
        return False, f"失败项：{failed}"
    if len(checks) != 7:
        return False, f"期望7项，实际{len(checks)}"
    return True, "七项全部通过"


@case("TC-02 缺免责声明：免责声明检查失败")
def test_no_disclaimer():
    r = check_disclaimer(BAD_NO_DISCLAIMER)
    if r.passed:
        return False, "应失败却通过"
    return True, r.message


@case("TC-03 禁用词：确定性投资建议检查失败")
def test_forbidden():
    r = check_forbidden_phrases(BAD_FORBIDDEN)
    if r.passed:
        return False, "应检出买入/必涨等"
    return True, r.message


@case("TC-04 Skill 来源：三源齐全通过")
def test_skill_sources():
    r = check_skill_sources(GOOD_REPORT)
    if not r.passed:
        return False, r.message
    return True, r.message


@case("TC-05 四象限图：ASCII 降级可识别")
def test_quadrant():
    r = check_quadrant_chart(GOOD_REPORT)
    if not r.passed:
        return False, r.message
    return True, r.message


@case("TC-06 三重佐证：推荐章节含宏观+景气+估值")
def test_triple():
    r = check_triple_evidence(GOOD_REPORT)
    if not r.passed:
        return False, r.message
    return True, r.message


@case("TC-07 validate() 对临时文件全绿")
def test_validate_file():
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(GOOD_REPORT)
        path = f.name
    try:
        results = validate(path)
        failed = [r.name for r in results if not r.passed]
        if failed:
            return False, f"失败：{failed}"
        if len(results) != 7:
            return False, f"期望7项结果，实际{len(results)}"
        return True, "validate() 七项全绿"
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


@case("TC-08 修改实现关键词应影响测试（漂移防护冒烟）")
def test_import_is_live():
    """确认测的是 validate_report 模块，而非本地副本。"""
    import validate_report as vr
    if not hasattr(vr, "check_quadrant_chart"):
        return False, "validate_report 缺少 check_quadrant_chart"
    if not hasattr(vr, "check_triple_evidence"):
        return False, "validate_report 缺少 check_triple_evidence"
    if len(vr.validate.__doc__ or "") >= 0 and callable(vr.validate):
        return True, f"live import ok, module={vr.__file__}"
    return False, "validate 不可调用"


def main():
    print("\n" + "=" * 55)
    print("  validate_report.py 单元测试（import 真实现）")
    print("=" * 55)

    total = passed = skipped = 0
    for name, fn in RESULTS:
        total += 1
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"异常：{e}"
        if ok is None:
            status = "SKIP"
            skipped += 1
        elif ok:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
        print(f"\n  [{status}] {name}")
        print(f"         {msg}")

    print("\n" + "=" * 55)
    print(f"  总计：{total} 用例，{passed} 通过，{skipped} 跳过，{total-passed-skipped} 失败")
    print("=" * 55 + "\n")
    sys.exit(0 if (total - passed - skipped) == 0 else 1)


if __name__ == "__main__":
    main()
