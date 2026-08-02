"""
宏观轮动报告校验脚本

Usage:
    python validate_report.py <report_path>

参数：
    report_path    待校验的报告 Markdown 文件路径

退出码：
    0  全部校验通过
    1  有一项或多项校验失败

校验项目（共七项）：
    1. 必须章节检查（摘要结论/宏观阶段判定/行业筛选/景气确认/估值过滤/推荐结论/数据校验表/免责声明）
    2. 数据时效标注检查（引用数值是否附带时间戳）
    3. 三个 Skill 来源标注检查（Macro Monitor / Alt-Data Nowcast / Index Valuation Rotation）
    4. 免责声明完整性检查
    5. 四象限图检查（Base64 PNG / Markdown 图 / ASCII 降级）
    6. 推荐三重佐证检查（宏观阶段 + 景气 + 估值）
    7. 确定性投资建议用语检查（禁用词：买入/卖出/强烈推荐/必涨/必跌 等）
"""

import re
import sys
import pathlib
import argparse
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    ("摘要结论", ["摘要", "摘要结论", "一句话结论"]),
    ("宏观阶段判定", ["宏观阶段", "宏观判定", "宏观定相", "macro phase", "宏观定相位"]),
    ("行业筛选", ["行业筛选", "行业初筛", "初筛", "行业推荐"]),
    ("景气确认", ["景气确认", "景气度确认", "nowcast", "另类高频", "景气度", "高频数据"]),
    ("估值过滤", ["估值过滤", "估值筛选", "valuation", "估值温度", "pe分位", "pb分位", "估值分位"]),
    ("推荐结论", ["推荐结论", "推荐行业", "优先关注", "配置建议", "超配"]),
    ("数据校验表", ["数据校验", "校验表", "数据来源", "数据证据"]),
    # 免责声明：只检查内容关键词，不强制要求特定标题，避免与 check_disclaimer 重叠
    ("免责声明", ["不构成任何投资建议", "仅供研究参考", "disclaimer", "研究参考"]),
]

REQUIRED_SKILL_SOURCES = [
    ("Macro Monitor", ["macro monitor", "宏观监控", "macro-monitor"]),
    ("Alt-Data Nowcast", ["alt-data nowcast", "另类高频", "altdata", "nowcast", "macro-altdata-nowcast"]),
    ("Index Valuation Rotation", ["index valuation", "估值轮动", "valuation rotation", "index-valuation-rotation"]),
]

DISCLAIMER_PHRASES = [
    "不构成任何投资建议",
    "仅供研究参考",
    "投资建议",
]

FORBIDDEN_PHRASES = [
    "买入",
    "卖出",
    "强烈推荐",
    "必涨",
    "必跌",
    "一定会涨",
    "一定会跌",
    "稳赚",
    "无风险",
    "保证收益",
    "强烈建议买",
]

TIMESTAMP_PATTERN = re.compile(
    r"\d{4}[-/]\d{2}(?:[-/]\d{2})?(?:[-_]W\d{1,2})?|"  # YYYY-MM or YYYY-MM-DD or YYYY-MM-DD-W1
    r"\d{4}Q[1-4]|"  # YYYY-Q1/Q2/Q3/Q4
    r"2\d{3}年\d{1,2}月",  # 中文日期
    re.IGNORECASE,
)

DATA_VALUE_PATTERN = re.compile(
    r"(?:"
    r"\d+\.?\d*\s*%|"         # 百分比数值
    r"\d+\.?\d*\s*(?:亿|万亿|bp|个百分点)|"  # 带单位数值
    r"(?:PMI|GDP|CPI|PPI|M2|社融)\s*[=:：]\s*\d|"  # 常见宏观指标赋值
    r"(?:PE|PB)\s*分位\s*\d|"  # 估值分位
    r"景气(?:分数|指数)?\s*[+\-]?\d"  # 景气分数
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 校验函数
# ---------------------------------------------------------------------------

def check_required_sections(content: str) -> CheckResult:
    """检查必须章节是否存在。"""
    content_lower = content.lower()
    missing = []
    for section_name, keywords in REQUIRED_SECTIONS:
        found = any(kw.lower() in content_lower for kw in keywords)
        if not found:
            missing.append(section_name)

    if missing:
        return CheckResult(
            name="必须章节检查",
            passed=False,
            message=f"以下必须章节缺失：{', '.join(missing)}",
        )
    return CheckResult(name="必须章节检查", passed=True, message="全部必须章节存在")


def check_timestamps(content: str) -> CheckResult:
    """检查数据时效标注：凡引用了数据值的行，应附近出现时间戳。"""
    lines = content.split("\n")
    issues = []
    for i, line in enumerate(lines, 1):
        if DATA_VALUE_PATTERN.search(line):
            # 在当前行及前后2行范围内查找时间戳
            context = "\n".join(lines[max(0, i-3):i+2])
            if not TIMESTAMP_PATTERN.search(context):
                issues.append(f"第{i}行：`{line.strip()[:80]}` 似乎缺少时间戳")
    if issues:
        # 超过5个问题时截断
        display = issues[:5]
        extra = len(issues) - 5 if len(issues) > 5 else 0
        msg = "部分数据引用缺少时间戳：\n  " + "\n  ".join(display)
        if extra > 0:
            msg += f"\n  ... 另有 {extra} 处未列出"
        return CheckResult(name="数据时效标注检查", passed=False, message=msg)
    return CheckResult(
        name="数据时效标注检查",
        passed=True,
        message="时间戳标注检查通过（所有数据值附近均发现时间戳）",
    )


def check_skill_sources(content: str) -> CheckResult:
    """检查三个 Skill 来源标注是否存在。"""
    content_lower = content.lower()
    missing = []
    for skill_name, keywords in REQUIRED_SKILL_SOURCES:
        found = any(kw.lower() in content_lower for kw in keywords)
        if not found:
            missing.append(skill_name)
    if missing:
        return CheckResult(
            name="Skill 来源标注检查",
            passed=False,
            message=f"以下 Skill 来源未在报告中标注：{', '.join(missing)}",
        )
    return CheckResult(
        name="Skill 来源标注检查",
        passed=True,
        message="三个 Skill 来源标注均已找到",
    )


def check_disclaimer(content: str) -> CheckResult:
    """检查免责声明是否完整。"""
    content_lower = content.lower()
    found_phrases = [p for p in DISCLAIMER_PHRASES if p.lower() in content_lower]
    if len(found_phrases) < 1:
        return CheckResult(
            name="免责声明检查",
            passed=False,
            message=f"未找到免责声明（期望包含以下任一短语：{', '.join(DISCLAIMER_PHRASES)}）",
        )
    return CheckResult(
        name="免责声明检查",
        passed=True,
        message=f"免责声明已找到（含：{', '.join(found_phrases)}）",
    )


def check_forbidden_phrases(content: str) -> CheckResult:
    """检查是否存在确定性投资建议用语。"""
    found = [p for p in FORBIDDEN_PHRASES if p in content]
    if found:
        return CheckResult(
            name="确定性投资建议检查",
            passed=False,
            message=f"发现禁用词（确定性投资建议）：{', '.join(found)}",
        )
    return CheckResult(
        name="确定性投资建议检查",
        passed=True,
        message="未发现禁用的确定性投资建议用语",
    )


def check_quadrant_chart(content: str) -> CheckResult:
    """检查四象限图是否已输出（Base64 PNG 或 ASCII 降级版）。"""
    chart_indicators = [
        "Base64", "base64", "iVBORw0",
        "四象限图", "美林时钟图", "推荐区",
        "![](",  "<img",
        "render_quadrant", "render_clock",
    ]
    found = any(ind in content for ind in chart_indicators)
    if not found:
        return CheckResult(
            name="四象限图检查",
            passed=False,
            message="未找到四象限图（应包含 Base64 PNG、Markdown 图片引用或 ASCII 象限图）",
        )
    return CheckResult(name="四象限图检查", passed=True, message="四象限图已在报告中找到")


def check_triple_evidence(content: str) -> CheckResult:
    """检查推荐行业是否有宏观阶段+景气+估值三重佐证。"""
    rec_m = re.search(
        r"#+\s*(推荐|轮动推荐|配置建议)(.*?)(?=#+|\Z)",
        content, re.DOTALL | re.IGNORECASE
    )
    if not rec_m:
        return CheckResult(
            name="推荐三重佐证检查",
            passed=True,
            message="未找到推荐章节，跳过三重佐证检查",
        )
    seg = rec_m.group(0).lower()
    missing = []
    if not re.search(r"景气|nowcast|同比|环比|高频", seg):
        missing.append("景气度证据（景气/Nowcast/同比）")
    if not re.search(r"估值|pe|pb|分位|温度", seg):
        missing.append("估值证据（估值/PE/PB/分位）")
    if not re.search(r"宏观|阶段|复苏|过热|滞胀|衰退|美林", seg):
        missing.append("宏观阶段证据（宏观/阶段/复苏/过热等）")
    if missing:
        return CheckResult(
            name="推荐三重佐证检查",
            passed=False,
            message="推荐章节缺少以下佐证：" + "、".join(missing),
        )
    return CheckResult(
        name="推荐三重佐证检查",
        passed=True,
        message="推荐章节包含宏观阶段+景气+估值三重佐证",
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def validate(report_path: str) -> List[CheckResult]:
    p = pathlib.Path(report_path)
    if not p.exists():
        print(f"[ERROR] 报告文件不存在：{report_path}", file=sys.stderr)
        sys.exit(2)

    content = p.read_text(encoding="utf-8")

    checks = [
        check_required_sections(content),
        check_timestamps(content),
        check_skill_sources(content),
        check_disclaimer(content),
        check_quadrant_chart(content),
        check_triple_evidence(content),
        check_forbidden_phrases(content),
    ]
    return checks


def print_results(results: List[CheckResult], report_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  报告校验结果：{report_path}")
    print(f"{'='*60}")

    all_passed = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"\n  [{status}] {r.name}")
        if r.message:
            for line in r.message.split("\n"):
                print(f"         {line}")
        if r.warnings:
            for w in r.warnings:
                print(f"    WARN  {w}")
        if not r.passed:
            all_passed = False

    print(f"\n{'='*60}")
    overall = "PASS — 全部校验通过" if all_passed else "FAIL — 存在校验失败项"
    print(f"  总体结果：{overall}")
    print(f"{'='*60}\n")
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="宏观轮动报告校验脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("report_path", help="待校验的报告 Markdown 文件路径")
    args = parser.parse_args()

    results = validate(args.report_path)
    passed = print_results(results, args.report_path)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
