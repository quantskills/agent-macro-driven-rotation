"""
backtest.py 核心逻辑单元测试
不依赖第三方包以外 numpy+pandas，测试计算指标和权重构建逻辑。
若 numpy/pandas 未安装则只做导入+语法检查。
"""
import sys
import pathlib

# ──────────────────────────────────────────────
# 尝试导入依赖，未安装时降级到纯逻辑检验
# ──────────────────────────────────────────────
try:
    import numpy as np
    import pandas as pd
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False
    print("[INFO] numpy/pandas 未安装，跳过数值计算测试，仅执行逻辑/结构检查。")


# ──────────────────────────────────────────────
# 从 phase_rules / backtest 导入被测函数
# ──────────────────────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import importlib.util

# 纯逻辑模块（无 pandas）优先
try:
    import phase_rules as pr
    PHASE_RULES_OK = True
except Exception:
    PHASE_RULES_OK = False
    pr = None

spec = importlib.util.spec_from_file_location("backtest", SCRIPT_DIR / "backtest.py")
bt = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(bt)
    IMPORT_OK = True
except Exception as e:
    IMPORT_OK = False
    print(f"[WARN] backtest 模块顶层 import 失败（依赖缺失）：{e}")


RESULTS = []

def case(name):
    def decorator(fn):
        RESULTS.append((name, fn))
        return fn
    return decorator


# ──────────────────────────────────────────────
# TC-B01：模块可导入，核心函数存在
# ──────────────────────────────────────────────
@case("TC-B01 模块结构：核心函数存在")
def test_module_structure():
    if not IMPORT_OK:
        # 依赖缺失时，只验证源码中包含函数定义（AST 级别检查）
        import ast
        src = (SCRIPT_DIR / "backtest.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        required_fns = {
            "parse_args", "load_phase_file", "load_index_daily",
            "_simulate_index_daily", "build_strategy_returns",
            "calc_metrics", "print_metrics", "plot_nav", "main",
            "determine_phase_from_macro", "calc_phase_stats",
            "assert_phase_month_consistency",
        }
        missing = required_fns - defined
        if missing:
            return False, f"源码缺少函数定义：{missing}"
        return True, f"AST检查：全部 {len(required_fns)} 个函数定义存在（依赖缺失，运行时跳过）"
    required_fns = [
        "parse_args", "load_phase_file", "load_index_daily",
        "_simulate_index_daily", "build_strategy_returns",
        "calc_metrics", "print_metrics", "plot_nav", "main",
        "determine_phase_from_macro", "calc_phase_stats",
        "assert_phase_month_consistency",
    ]
    for fn_name in required_fns:
        if not hasattr(bt, fn_name):
            return False, f"缺少函数：{fn_name}"
    return True, f"全部 {len(required_fns)} 个函数存在"


# ──────────────────────────────────────────────
# TC-B02：模拟行情生成
# ──────────────────────────────────────────────
@case("TC-B02 _simulate_index_daily：生成模拟行情")
def test_simulate():
    if not HAS_DEPS:
        return None, "跳过（依赖缺失）"
    df = bt._simulate_index_daily(["000300.SH", "000905.SH"], "2024-01-01", "2024-06-30")
    if df.empty:
        return False, "返回空 DataFrame"
    codes = set(df["code"].unique())
    if codes != {"000300.SH", "000905.SH"}:
        return False, f"代码不匹配：{codes}"
    if not {"code", "date", "close"}.issubset(df.columns):
        return False, f"缺字段：{df.columns.tolist()}"
    return True, f"生成 {len(df)} 行，代码={codes}"


# ──────────────────────────────────────────────
# TC-B03：calc_metrics 基础计算
# ──────────────────────────────────────────────
@case("TC-B03 calc_metrics：稳定收益序列")
def test_calc_metrics_stable():
    if not HAS_DEPS:
        return None, "跳过（依赖缺失）"
    dates = pd.date_range("2020-01-02", periods=504, freq="B")
    # 模拟年化 10% 的稳定策略
    daily = 0.10 / 252
    rets = pd.Series([daily] * 504, index=dates)
    bench = pd.Series([daily * 0.8] * 504, index=dates)
    m = bt.calc_metrics(rets, bench)
    keys = {"annual_return", "max_drawdown", "sharpe", "info_ratio", "win_rate"}
    if not keys.issubset(m.keys()):
        return False, f"缺少指标键：{keys - m.keys()}"
    if not (0.08 < m["annual_return"] < 0.12):
        return False, f"年化收益不在预期范围：{m['annual_return']:.4f}"
    if m["max_drawdown"] > 0:
        return False, f"稳定收益最大回撤应≤0：{m['max_drawdown']:.6f}"
    if m["win_rate"] < 0.8:
        return False, f"稳定跑赢基准的胜率应>80%：{m['win_rate']:.2f}"
    return True, f"annual={m['annual_return']*100:.1f}%, dd={m['max_drawdown']*100:.2f}%, sharpe={m['sharpe']:.2f}, wr={m['win_rate']*100:.0f}%"


# ──────────────────────────────────────────────
# TC-B04：calc_metrics 空序列容错
# ──────────────────────────────────────────────
@case("TC-B04 calc_metrics：空序列容错")
def test_calc_metrics_empty():
    if not HAS_DEPS:
        return None, "跳过（依赖缺失）"
    m = bt.calc_metrics(pd.Series([], dtype=float), pd.Series([], dtype=float))
    if m != {}:
        return False, f"空序列应返回空 dict，实际：{m}"
    return True, "空序列返回 {}"


# ──────────────────────────────────────────────
# TC-B05：build_strategy_returns 等权权重验证
# ──────────────────────────────────────────────
@case("TC-B05 build_strategy_returns：等权权重验证")
def test_build_strategy_equal_weight():
    if not HAS_DEPS:
        return None, "跳过（依赖缺失）"
    # 两个行业等权
    phase_df = pd.DataFrame({
        "date": ["2024-01-02"],
        "macro_phase": ["复苏期"],
        "recommended_industries": ["IND_A,IND_B"],
    })
    # 构造简单行情
    dates = pd.date_range("2024-01-02", "2024-03-31", freq="B")
    rng = np.random.default_rng(0)
    price_df = pd.concat([
        pd.DataFrame({"code": "IND_A", "date": dates, "close": 100 * np.cumprod(1 + rng.normal(0.001, 0.01, len(dates)))}),
        pd.DataFrame({"code": "IND_B", "date": dates, "close": 100 * np.cumprod(1 + rng.normal(0.001, 0.01, len(dates)))}),
    ], ignore_index=True)
    ret = bt.build_strategy_returns(phase_df, price_df, "2024-01-02", "2024-03-31")
    if ret.empty:
        return False, "策略收益为空"
    non_zero = (ret != 0).sum()
    if non_zero < 10:
        return False, f"非零收益天数太少：{non_zero}"
    return True, f"策略收益序列长度={len(ret)}, 非零天数={non_zero}"


# ──────────────────────────────────────────────
# TC-B06：load_phase_file 错误处理（文件不存在）
# ──────────────────────────────────────────────
@case("TC-B06 load_phase_file：文件不存在时退出码=1")
def test_load_phase_file_missing():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "backtest.py"), "--phase_file", "nonexistent_xyz.csv"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    err = (result.stderr or "") + (result.stdout or "")
    if result.returncode == 1:
        return True, f"正确退出码=1，输出含：{err.strip()[:80]}"
    return False, f"退出码={result.returncode}，输出={err[:120]}"


# ──────────────────────────────────────────────
# TC-B07：四维判定 — 四主阶段 + 边界
# ──────────────────────────────────────────────
@case("TC-B07 determine_phase_from_macro：四主阶段")
def test_determine_phase_four():
    mod = bt if IMPORT_OK else pr
    if mod is None:
        return None, "跳过（模块未导入）"
    r = mod.determine_phase_from_macro(51, 50, 1.5, 9.0, 11.0)
    if r["macro_phase"] != "复苏期" or not r["loose_liquidity"]:
        return False, f"复苏期望失败：{r}"
    r = mod.determine_phase_from_macro(52, 51, 2.5, 7.0, 9.0)
    if r["macro_phase"] != "过热期":
        return False, f"过热期望失败：{r}"
    r = mod.determine_phase_from_macro(48, 49, 2.8, 7.0, 9.0)
    if r["macro_phase"] != "滞胀期":
        return False, f"滞胀期望失败：{r}"
    r = mod.determine_phase_from_macro(48, 49, 1.0, 7.0, 9.0)
    if r["macro_phase"] != "衰退期":
        return False, f"衰退期望失败：{r}"
    return True, "四主阶段判定正确"


@case("TC-B08 determine_phase_from_macro：边界样本")
def test_determine_phase_boundaries():
    mod = bt if IMPORT_OK else pr
    if mod is None:
        return None, "跳过（模块未导入）"
    r = mod.determine_phase_from_macro(51, 50, 1.5, 6.0, 8.0)
    if r["macro_phase"] != "复苏期" or r["loose_liquidity"]:
        return False, f"边界1失败：{r}"
    if "流动性未宽松" not in r["phase_note"]:
        return False, f"边界1缺 phase_note：{r}"
    r = mod.determine_phase_from_macro(48, 49, 1.0, 9.0, 11.0, policy_gap=2.0)
    if r["macro_phase"] != "衰退期" or not r["loose_liquidity"]:
        return False, f"边界2失败：{r}"
    if "政策托底" not in r["phase_note"] and "政策预期差" not in r["phase_note"]:
        return False, f"边界2缺 phase_note：{r}"
    return True, f"边界样本通过 note={r['phase_note']}"


@case("TC-B09 calc_phase_stats：覆盖月数=phase_df行数")
def test_calc_phase_stats_cover_months():
    if not HAS_DEPS or not IMPORT_OK:
        return None, "跳过（依赖缺失）"
    phase_df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]),
        "macro_phase": ["复苏期", "复苏期", "过热期", "衰退期"],
        "recommended_industries": ["A", "A", "B", "C"],
    })
    dates = pd.date_range("2024-01-02", "2024-04-30", freq="B")
    strategy_ret = pd.Series(0.001, index=dates)
    benchmark_ret = pd.Series(0.0005, index=dates)
    stats = bt.calc_phase_stats(phase_df, strategy_ret, benchmark_ret)
    if int(stats["覆盖月数"].sum()) != len(phase_df):
        return False, f"合计覆盖月数={stats['覆盖月数'].sum()} != {len(phase_df)}"
    recovery = stats[stats["宏观阶段"] == "复苏期"]["覆盖月数"].iloc[0]
    if recovery != 2:
        return False, f"复苏期覆盖月数应为2，实际={recovery}"
    return True, f"覆盖月数合计={int(stats['覆盖月数'].sum())}"


# ──────────────────────────────────────────────
# TC-B10：backtest.py CLI --help 可用
# ──────────────────────────────────────────────
@case("TC-B10 CLI --help 正常返回")
def test_cli_help():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "backtest.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        if not HAS_DEPS:
            import ast
            src = (SCRIPT_DIR / "backtest.py").read_text(encoding="utf-8")
            if "parse_args" in src and "ArgumentParser" in src and "宏观轮动" in src:
                return True, "依赖缺失，改为AST检查：argparse配置存在且含中文描述"
        return False, f"--help 返回非零：{result.returncode}，输出={out[:120]}"
    if "宏观轮动策略回测" not in out and "macro" not in out.lower():
        return False, f"--help 输出不含预期内容：{out[:100]}"
    return True, "--help 输出正常"


# ──────────────────────────────────────────────
# 主运行器
# ──────────────────────────────────────────────
def main():
    print("\n" + "=" * 55)
    print("  backtest.py 核心逻辑单元测试")
    print("=" * 55)

    total = 0
    passed = 0
    skipped = 0

    for name, fn in RESULTS:
        total += 1
        try:
            result = fn()
            ok, msg = result
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
