# -*- coding: utf-8 -*-
"""
reconcile_report_vs_api.py — L2 报告数值 vs Pandadata（或 fixture）交叉对账

用法：
  # 离线：用 fixture 序列对账（CI / 单测）
  python scripts/reconcile_report_vs_api.py reports/samples/e2e_rotation_sample.md \\
      --fixture scripts/fixtures/reconcile_macro_sample.json \\
      --output reports/samples/reconcile_sample.csv

  # 在线：真实 API（需 PANDA_DATA_USERNAME / PASSWORD）
  python scripts/reconcile_report_vs_api.py path/to/live_report.md --live \\
      --output reports/reconcile_live.csv

退出码：
  0  所有可对账项 PASS（SKIP/MANUAL 不计入失败）
  1  存在 FAIL，或 --strict 时存在 SKIP/MANUAL
  2  用法/文件错误

说明：
  - 宏观四维（PMI/CPI/M2/社融/政策差）可自动对账
  - 景气 Nowcast、PE/PB 分位默认 MANUAL（需子 Skill 同口径重算）
  - 可选校验：报告宏观阶段 vs phase_rules(报告内宏观值)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from phase_rules import determine_phase_from_macro  # noqa: E402
from macro_catalog import MACRO_CATALOG  # noqa: E402

MANUAL_HINTS = (
    "景气",
    "nowcast",
    "pe分位",
    "pb分位",
    "估值分位",
    "估值温度",
    "动量",
)

PHASE_PATTERN = re.compile(
    r"(?:宏观定相|宏观阶段|阶段)[：:\s]*[*]*\s*(复苏期|过热期|滞胀期|衰退期)",
    re.IGNORECASE,
)


@dataclass
class ReportRow:
    metric: str
    value_raw: str
    period: str
    source: str


@dataclass
class ReconcileResult:
    metric: str
    report_value: str
    report_period: str
    source: str
    catalog_key: str
    method: str
    symbol: str
    api_value: str
    api_period: str
    status: str  # PASS / FAIL / SKIP / MANUAL / ERROR
    detail: str = ""
    abs_diff: str = ""


@dataclass
class PhaseCheck:
    report_phase: str
    rule_phase: str
    status: str
    detail: str
    inputs: Dict[str, Any] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="L2：报告数据校验表 vs API/fixture 对账")
    p.add_argument("report", help="Markdown 报告路径")
    p.add_argument("--live", action="store_true", help="调用真实 panda_data")
    p.add_argument(
        "--fixture",
        default="",
        help="JSON fixture：{symbol: {YYYY-MM: value, ...}, ...}；复合键可用 CI0000010-CI0000017",
    )
    p.add_argument("--output", default="", help="对账结果 CSV 路径")
    p.add_argument("--tol", type=float, default=None, help="覆盖默认绝对误差容差")
    p.add_argument(
        "--strict",
        action="store_true",
        help="MANUAL/SKIP 也视为失败（用于强制补齐景气/估值对账）",
    )
    p.add_argument(
        "--skip-phase-check",
        action="store_true",
        help="跳过报告阶段 vs phase_rules 一致性检查",
    )
    p.add_argument(
        "--pmi-prev",
        type=float,
        default=None,
        help="定相复核用的上月 PMI；缺省时尝试从 API/fixture 取上一期",
    )
    return p.parse_args()


def normalize_metric(name: str) -> str:
    s = name.strip().lower()
    s = s.replace(" ", "").replace("　", "")
    s = s.replace("%", "").replace("％", "")
    return s


def match_catalog(metric: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    n = normalize_metric(metric)
    for key, meta in MACRO_CATALOG.items():
        for alias in meta["aliases"]:
            if normalize_metric(alias) == n or normalize_metric(alias) in n or n in normalize_metric(alias):
                return key, meta
    # 模糊：指标名含关键别名
    for key, meta in MACRO_CATALOG.items():
        for alias in meta["aliases"]:
            a = normalize_metric(alias)
            if a and a in n:
                return key, meta
    return None


def is_manual_metric(metric: str) -> bool:
    n = normalize_metric(metric)
    return any(h in n for h in MANUAL_HINTS)


def parse_number(raw: str) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "—", "N/A", "n/a"}:
        return None
    s = s.replace(",", "").replace("％", "%").replace("＋", "+")
    # 去掉单位后缀
    s = re.sub(r"(个百分点|百分点|bp|亿|万亿)$", "", s, flags=re.I)
    m = re.search(r"[+-]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    val = float(m.group(0))
    # "0.3%" → 0.3（与 API 同比口径一致，不除以 100）
    return val


def period_to_yyyymm(period: str) -> Optional[str]:
    s = period.strip()
    m = re.match(r"(\d{4})[-/年](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{4})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def parse_evidence_table(md: str) -> List[ReportRow]:
    """解析「数据校验表」或全文中第一个像证据表的 Markdown 表。"""
    # 优先切到数据校验表章节
    section = md
    m = re.search(r"#{1,3}\s*数据校验[表]?\s*", md)
    if m:
        section = md[m.end() :]
        nxt = re.search(r"\n#{1,3}\s+", section)
        if nxt:
            section = section[: nxt.start()]

    rows: List[ReportRow] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        # 跳过表头与分隔行
        joined = "".join(cells).replace("-", "").replace(":", "")
        if "指标" in cells[0] and ("数值" in "".join(cells) or "值" in "".join(cells)):
            continue
        if re.fullmatch(r"[\s\-:|]+", line.replace("|", "")):
            continue
        if set(joined) <= {"-", " "}:
            continue
        metric, value, period = cells[0], cells[1], cells[2]
        source = cells[3] if len(cells) > 3 else ""
        if not metric or metric in {"指标", "项", "说明"}:
            continue
        rows.append(ReportRow(metric=metric, value_raw=value, period=period, source=source))
    return rows


def extract_report_phase(md: str) -> Optional[str]:
    m = PHASE_PATTERN.search(md)
    if m:
        return m.group(1)
    for p in ("复苏期", "过热期", "滞胀期", "衰退期"):
        if p in md[:2500]:
            return p
    return None


def load_fixture(path: str) -> Dict[str, Dict[str, float]]:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, float]] = {}
    for sym, series in data.items():
        if sym.startswith("_"):
            continue
        out[sym] = {str(k): float(v) for k, v in series.items()}
    return out


def init_panda() -> Any:
    import panda_data

    u = os.environ.get("PANDA_DATA_USERNAME", "")
    p = os.environ.get("PANDA_DATA_PASSWORD", "")
    if u and p:
        panda_data.init_token(username=u, password=p)
    return panda_data


def fetch_series_live(method: str, symbol: str, start: str, end: str) -> Dict[str, float]:
    pd_mod = init_panda()
    fn = getattr(pd_mod, method)
    df = fn(symbol=symbol, start_date=start.replace("-", ""), end_date=end.replace("-", ""))
    # 兼容 period_date / date
    date_col = "period_date" if "period_date" in df.columns else "date"
    val_col = "data_value" if "data_value" in df.columns else "value"
    series: Dict[str, float] = {}
    for _, r in df.iterrows():
        raw = str(r[date_col])
        if len(raw) >= 6 and raw[:6].isdigit():
            key = f"{raw[:4]}-{raw[4:6]}"
        else:
            dt = datetime.strptime(raw[:10].replace("/", "-"), "%Y-%m-%d")
            key = f"{dt.year}-{dt.month:02d}"
        series[key] = float(r[val_col])
    return series


def lookup_period(series: Dict[str, float], period: str) -> Tuple[Optional[float], str]:
    yyyymm = period_to_yyyymm(period)
    if not yyyymm:
        return None, ""
    if yyyymm in series:
        return series[yyyymm], yyyymm
    # 容错：同月其他日
    prefix = yyyymm
    cands = sorted(k for k in series if k.startswith(prefix))
    if cands:
        return series[cands[-1]], cands[-1]
    return None, yyyymm


def prev_month_key(yyyymm: str) -> str:
    y, m = int(yyyymm[:4]), int(yyyymm[5:7])
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def get_series(
    meta: Dict[str, Any],
    fixture: Optional[Dict[str, Dict[str, float]]],
    live: bool,
    period: str,
) -> Tuple[Dict[str, float], str]:
    """返回 (series, note)。复合指标在此合成。"""
    symbol = meta["symbol"]
    method = meta["method"]
    yyyymm = period_to_yyyymm(period) or "2020-01"
    # 拉取窗口：报告期前后约 18 个月
    y, m = int(yyyymm[:4]), int(yyyymm[5:7])
    start = f"{y - 1}-{m:02d}-01"
    end = f"{y}-{m:02d}-28"
    if meta.get("composite"):
        s_new = meta.get("new_orders_symbol", "CI0000010")
        s_inv = meta.get("inventory_symbol", "CI0000017")
        if fixture is not None:
            a = fixture.get(s_new, {})
            b = fixture.get(s_inv, {})
            # 也允许直接给复合键
            if symbol in fixture:
                return fixture[symbol], "fixture-composite-key"
            keys = set(a) | set(b)
            series = {k: a[k] - b[k] for k in keys if k in a and k in b}
            return series, "fixture"
        if not live:
            return {}, "no-data-source"
        a = fetch_series_live(method, s_new, start, end)
        b = fetch_series_live(method, s_inv, start, end)
        keys = set(a) | set(b)
        series = {k: a[k] - b[k] for k in keys if k in a and k in b}
        return series, "live"
    if fixture is not None:
        return fixture.get(symbol, {}), "fixture"
    if not live:
        return {}, "no-data-source"
    return fetch_series_live(method, symbol, start, end), "live"


def reconcile_rows(
    rows: List[ReportRow],
    fixture: Optional[Dict[str, Dict[str, float]]],
    live: bool,
    tol_override: Optional[float],
) -> List[ReconcileResult]:
    results: List[ReconcileResult] = []
    for row in rows:
        matched = match_catalog(row.metric)
        if matched is None:
            if is_manual_metric(row.metric):
                results.append(
                    ReconcileResult(
                        metric=row.metric,
                        report_value=row.value_raw,
                        report_period=row.period,
                        source=row.source,
                        catalog_key="",
                        method="",
                        symbol="",
                        api_value="",
                        api_period="",
                        status="MANUAL",
                        detail="景气/估值类：请用子 Skill 同口径重算后人工填入，或后续扩展对账器",
                    )
                )
            else:
                results.append(
                    ReconcileResult(
                        metric=row.metric,
                        report_value=row.value_raw,
                        report_period=row.period,
                        source=row.source,
                        catalog_key="",
                        method="",
                        symbol="",
                        api_value="",
                        api_period="",
                        status="SKIP",
                        detail="未映射到宏观目录，跳过自动对账",
                    )
                )
            continue

        key, meta = matched
        report_num = parse_number(row.value_raw)
        if report_num is None:
            results.append(
                ReconcileResult(
                    metric=row.metric,
                    report_value=row.value_raw,
                    report_period=row.period,
                    source=row.source,
                    catalog_key=key,
                    method=meta["method"],
                    symbol=meta["symbol"],
                    api_value="",
                    api_period="",
                    status="ERROR",
                    detail="无法解析报告数值",
                )
            )
            continue

        try:
            series, src_note = get_series(meta, fixture, live, row.period)
        except Exception as e:  # noqa: BLE001
            results.append(
                ReconcileResult(
                    metric=row.metric,
                    report_value=row.value_raw,
                    report_period=row.period,
                    source=row.source,
                    catalog_key=key,
                    method=meta["method"],
                    symbol=meta["symbol"],
                    api_value="",
                    api_period="",
                    status="ERROR",
                    detail=f"拉取失败: {e}",
                )
            )
            continue

        if not series:
            results.append(
                ReconcileResult(
                    metric=row.metric,
                    report_value=row.value_raw,
                    report_period=row.period,
                    source=row.source,
                    catalog_key=key,
                    method=meta["method"],
                    symbol=meta["symbol"],
                    api_value="",
                    api_period="",
                    status="ERROR",
                    detail=f"无序列数据（{src_note}）；请加 --live 或 --fixture",
                )
            )
            continue

        api_val, api_period = lookup_period(series, row.period)
        if api_val is None:
            results.append(
                ReconcileResult(
                    metric=row.metric,
                    report_value=row.value_raw,
                    report_period=row.period,
                    source=row.source,
                    catalog_key=key,
                    method=meta["method"],
                    symbol=meta["symbol"],
                    api_value="",
                    api_period=api_period,
                    status="FAIL",
                    detail=f"API/fixture 中找不到数据期 {row.period}（已规范为 {api_period}）",
                )
            )
            continue

        tol = tol_override if tol_override is not None else float(meta["tol"])
        diff = abs(report_num - api_val)
        ok = diff <= tol
        results.append(
            ReconcileResult(
                metric=row.metric,
                report_value=str(report_num),
                report_period=row.period,
                source=row.source,
                catalog_key=key,
                method=meta["method"],
                symbol=meta["symbol"],
                api_value=str(api_val),
                api_period=api_period,
                status="PASS" if ok else "FAIL",
                detail=f"tol={tol}; source={src_note}" + ("" if ok else f"; |Δ|={diff:.4f}"),
                abs_diff=f"{diff:.4f}",
            )
        )
    return results


def build_macro_inputs(
    results: List[ReconcileResult],
    rows: List[ReportRow],
    fixture: Optional[Dict[str, Dict[str, float]]],
    live: bool,
    pmi_prev_arg: Optional[float],
) -> Dict[str, Any]:
    """优先用报告解析值；缺省再用 API。"""
    by_key: Dict[str, float] = {}
    period = ""
    for row in rows:
        matched = match_catalog(row.metric)
        if not matched:
            continue
        key, _ = matched
        num = parse_number(row.value_raw)
        if num is not None:
            by_key[key] = num
            period = row.period or period

    pmi = by_key.get("pmi")
    cpi = by_key.get("cpi")
    m2 = by_key.get("m2")
    sf = by_key.get("sf")
    gap = by_key.get("policy_gap")

    pmi_prev = pmi_prev_arg
    if pmi_prev is None and pmi is not None and period:
        meta = MACRO_CATALOG["pmi"]
        try:
            series, _ = get_series(meta, fixture, live, period)
            yyyymm = period_to_yyyymm(period)
            if yyyymm:
                pk = prev_month_key(yyyymm)
                if pk in series:
                    pmi_prev = series[pk]
        except Exception:  # noqa: BLE001
            pmi_prev = None
    if pmi_prev is None and pmi is not None:
        # 无上月时用略低值，使「环比上行」在边界可测；并在 detail 中标明假设
        pmi_prev = pmi - 0.1

    return {
        "pmi": pmi,
        "pmi_prev": pmi_prev,
        "cpi_yoy": cpi,
        "m2_yoy": m2,
        "sf_yoy": sf,
        "policy_gap": gap,
        "period": period,
        "pmi_prev_assumed": pmi_prev_arg is None and pmi_prev is not None,
    }


def check_phase(
    md: str,
    rows: List[ReportRow],
    results: List[ReconcileResult],
    fixture: Optional[Dict[str, Dict[str, float]]],
    live: bool,
    pmi_prev_arg: Optional[float],
) -> Optional[PhaseCheck]:
    report_phase = extract_report_phase(md)
    if not report_phase:
        return PhaseCheck("", "", "SKIP", "报告中未解析到宏观阶段名")

    inputs = build_macro_inputs(results, rows, fixture, live, pmi_prev_arg)
    needed = ("pmi", "pmi_prev", "cpi_yoy", "m2_yoy", "sf_yoy")
    if any(inputs.get(k) is None for k in needed):
        missing = [k for k in needed if inputs.get(k) is None]
        return PhaseCheck(
            report_phase,
            "",
            "SKIP",
            f"定相复核缺字段: {missing}",
            inputs,
        )

    rule = determine_phase_from_macro(
        float(inputs["pmi"]),
        float(inputs["pmi_prev"]),
        float(inputs["cpi_yoy"]),
        float(inputs["m2_yoy"]),
        float(inputs["sf_yoy"]),
        inputs.get("policy_gap"),
    )
    rule_phase = rule["macro_phase"]
    ok = rule_phase == report_phase
    detail = json.dumps(rule, ensure_ascii=False)
    if inputs.get("pmi_prev_assumed"):
        detail += " | WARN: pmi_prev 为假设（报告期 PMI-0.1），建议传 --pmi-prev 或保证 fixture/API 有上月"
    return PhaseCheck(
        report_phase,
        rule_phase,
        "PASS" if ok else "FAIL",
        detail,
        {k: inputs[k] for k in ("pmi", "pmi_prev", "cpi_yoy", "m2_yoy", "sf_yoy", "policy_gap")},
    )


def write_csv(path: pathlib.Path, results: List[ReconcileResult], phase: Optional[PhaseCheck]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(results[0]).keys()) if results else [
        "metric", "report_value", "report_period", "source", "catalog_key",
        "method", "symbol", "api_value", "api_period", "status", "detail", "abs_diff",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            w.writerow(asdict(r))
        if phase is not None:
            w.writerow({
                "metric": "__phase_rules_check__",
                "report_value": phase.report_phase,
                "report_period": "",
                "source": "phase_rules",
                "catalog_key": "",
                "method": "determine_phase_from_macro",
                "symbol": "",
                "api_value": phase.rule_phase,
                "api_period": "",
                "status": phase.status,
                "detail": phase.detail,
                "abs_diff": "",
            })


def print_summary(results: List[ReconcileResult], phase: Optional[PhaseCheck]) -> None:
    counts: Dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("\n" + "=" * 60)
    print("  L2 对账结果摘要")
    print("=" * 60)
    for r in results:
        print(f"  [{r.status:6}] {r.metric}: report={r.report_value} api={r.api_value} ({r.detail})")
    if phase:
        print(f"  [{phase.status:6}] 定相复核: 报告={phase.report_phase} 规则={phase.rule_phase}")
        print(f"         {phase.detail[:200]}")
    print("-" * 60)
    print("  计数:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("=" * 60 + "\n")


def main() -> int:
    args = parse_args()
    report_path = pathlib.Path(args.report)
    if not report_path.exists():
        print(f"[ERROR] 报告不存在: {report_path}", file=sys.stderr)
        return 2
    if not args.live and not args.fixture:
        print(
            "[ERROR] 请指定 --live 或 --fixture <json>（防止误用空数据源）",
            file=sys.stderr,
        )
        return 2

    md = report_path.read_text(encoding="utf-8")
    rows = parse_evidence_table(md)
    if not rows:
        print("[ERROR] 未解析到数据校验表行", file=sys.stderr)
        return 2

    fixture = load_fixture(args.fixture) if args.fixture else None
    results = reconcile_rows(rows, fixture, args.live, args.tol)

    phase: Optional[PhaseCheck] = None
    if not args.skip_phase_check:
        phase = check_phase(md, rows, results, fixture, args.live, args.pmi_prev)

    out = args.output
    if not out:
        out = str(report_path.with_name(report_path.stem + "_reconcile.csv"))
    write_csv(pathlib.Path(out), results, phase)
    print(f"[OK] 对账 CSV → {out}")
    print_summary(results, phase)

    hard_fail = any(r.status in {"FAIL", "ERROR"} for r in results)
    if phase and phase.status == "FAIL":
        hard_fail = True
    soft_fail = args.strict and any(r.status in {"SKIP", "MANUAL"} for r in results)
    if phase and args.strict and phase.status == "SKIP":
        soft_fail = True

    if hard_fail or soft_fail:
        print("[FAIL] 对账未通过", file=sys.stderr)
        return 1
    print("[PASS] 可对账项全部通过（MANUAL/SKIP 未计入失败，除非 --strict）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
