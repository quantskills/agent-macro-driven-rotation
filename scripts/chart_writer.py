# -*- coding: utf-8 -*-
"""
chart_writer.py ── 宏观驱动行业轮动 Agent 图表生成工具

公开函数：
  render_clock_chart(current_phase, data_date, output_dir)
      → 美林时钟钟面图（四扇区，高亮当前阶段）
  render_quadrant_chart(growth_series, inflation_series, output_dir)
      → 增长-通胀散点轨迹图（近24个月经济轨迹线）
  render_valuation_sentiment_chart(industries_data, output_dir)
      → 估值-景气四象限图（横轴景气分数，纵轴估值分位）
  render_all(current_phase, growth_series, inflation_series, industries_data, ...)
      → 一次生成全部三张图，返回 {clock, quadrant, valuation}
  ascii_clock(current_phase)   → 无 matplotlib 时的 ASCII 降级版
  ascii_valuation_chart(industries_data) → ASCII 降级版
"""
from __future__ import annotations
import base64, io, math, os, pathlib as _pathlib, warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np

PHASE_COLORS: Dict[str, str] = {
    "复苏期": "#2ECC71",
    "过热期": "#E74C3C",
    "滞胀期": "#E67E22",
    "衰退期": "#3498DB",
}

# 钟面展示短标签；与 scripts/industry_codes.PHASE_INDUSTRY_NAMES 同源（定码见该文件）
try:
    import sys as _sys
    _scripts = str(_pathlib.Path(__file__).resolve().parent / "scripts")
    if _scripts not in _sys.path:
        _sys.path.insert(0, _scripts)
    from industry_codes import PHASE_DISPLAY_LABELS as PHASE_INDUSTRIES  # noqa: E402
except Exception:
    PHASE_INDUSTRIES: Dict[str, list] = {
        "复苏期": ["电子", "消费", "医药"],
        "过热期": ["资源", "周期", "银行"],
        "滞胀期": ["防御消费", "公用事业", "医药"],
        "衰退期": ["黄金", "债券", "现金"],
    }

PHASE_ORDER = ["衰退期", "复苏期", "过热期", "滞胀期"]

def _setup_chinese_font():
    try:
        import matplotlib
        from matplotlib import font_manager
        fc = ["SimHei", "Microsoft YaHei", "STHeiti"]
        av = {x.name for x in font_manager.fontManager.ttflist}
        for fn in fc:
            if fn in av:
                matplotlib.rcParams["font.family"] = [fn]
                matplotlib.rcParams["axes.unicode_minus"] = False
                return fn
        import platform
        if platform.system() == "Windows":
            for fp in [r"C:\Windows\Fonts\simhei.ttf"]:
                if os.path.exists(fp):
                    font_manager.fontManager.addfont(fp)
                    p = font_manager.FontProperties(fname=fp)
                    matplotlib.rcParams["font.family"] = [p.get_name()]
                    matplotlib.rcParams["axes.unicode_minus"] = False
                    return p.get_name()
    except Exception:
        pass
    return None

def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return "data:image/png;base64," + b64

def _save_fig(fig, path: str) -> str:
    try:
        _pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
        return path
    except Exception as e:
        warnings.warn(f"save_fig failed: {e}")
        return ""

def render_clock_chart(
    current_phase: str,
    data_date: Optional[str] = None,
    output_dir: str = ".",
) -> Tuple[Optional[str], Optional[str]]:
    """美林时钟钟面图，返回 (base64_png, fig_path) 或 (None, None)。"""
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches, math
    except ImportError:
        warnings.warn("matplotlib not available"); return None, None
    try:
        _setup_chinese_font()
        today = data_date or datetime.now().strftime("%Y-%m")
        date_str = datetime.now().strftime("%Y%m%d")
        fig_path = str(_pathlib.Path(output_dir) / f"clock_{date_str}.png")
        fig, ax = plt.subplots(figsize=(10, 8), subplot_kw={"aspect": "equal"})
        fig.patch.set_facecolor("white")
        COLORS = PHASE_COLORS
        INDS = PHASE_INDUSTRIES
        ORDER = PHASE_ORDER
        start_deg = 90
        for i, phase in enumerate(ORDER):
            color = COLORS.get(phase, "#AAAAAA")
            is_cur = (phase == current_phase)
            alpha = 0.92 if is_cur else 0.28
            lw = 2.5 if is_cur else 0.5
            theta1 = start_deg - i * 90
            theta2 = theta1 - 90
            wedge = mpatches.Wedge(
                center=(0, 0), r=1.0, theta1=theta2, theta2=theta1,
                facecolor=color, alpha=alpha, edgecolor="white", linewidth=lw,
            )
            ax.add_patch(wedge)
            mid = (theta1 + theta2) / 2
            rad = math.radians(mid)
            tx = 0.62 * math.cos(rad)
            ty = 0.62 * math.sin(rad)
            ind_str = "\n".join(INDS.get(phase, [])[:3])
            lbl = phase + "\n" + ind_str
            fc_txt = "white" if is_cur else "#808080"
            fw_txt = "bold" if is_cur else "normal"
            ax.text(tx, ty, lbl, ha="center", va="center",
                    fontsize=9 if is_cur else 7.5,
                    fontweight=fw_txt, color=fc_txt,
                    multialignment="center", linespacing=1.4)
            if is_cur:
                ax.text(tx, ty + 0.17, "当前", ha="center",
                        fontsize=8.5, color="white", fontweight="bold")
        ax.text(0, 0, "美林时钟\n" + current_phase, ha="center", va="center",
                fontsize=11, fontweight="bold", color="#2C3E50",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          edgecolor="#2C3E50", linewidth=2))
        ax.text(0, 1.28, today, ha="center", va="center", fontsize=9, color="#555555")
        for ang, sym in [(135, "逆"), (45, "顺"), (-45, "逆"), (-135, "顺")]:
            r2 = math.radians(ang)
            ax.text(1.18 * math.cos(r2), 1.18 * math.sin(r2), sym,
                    ha="center", va="center", fontsize=14, color="#BBBBBB")
        ax.set_xlim(-1.45, 1.45)
        ax.set_ylim(-1.45, 1.45)
        ax.axis("off")
        ax.set_title("宏观驱动行业轮动 · 美林时钟", fontsize=12, fontweight="bold", pad=10)
        plt.tight_layout()
        b64 = _fig_to_base64(fig)
        _save_fig(fig, fig_path)
        return b64, fig_path
    except Exception as e:
        warnings.warn(f"render_clock_chart failed: {e}")
        return None, None
    finally:
        try: plt.close(fig)
        except: pass


def render_quadrant_chart(
    growth_series,
    inflation_series,
    labels: Optional[Dict] = None,
    output_dir: str = ".",
) -> Tuple[Optional[str], Optional[str]]:
    """增长-通胀散点轨迹图，返回 (base64_png, fig_path) 或 (None, None)。

    growth_series  : pd.Series，index=datetime，月度GDP同比/PMI合成指数
    inflation_series: pd.Series，index=datetime，月度CPI同比(%)
    labels         : {date_str: text} 可选标注字典
    """
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
    except ImportError:
        warnings.warn("matplotlib not available"); return None, None
    try:
        _setup_chinese_font()
        g = list(growth_series)
        inf = list(inflation_series)
        n = min(len(g), len(inf))
        if n < 2:
            return None, None
        g = g[-n:]; inf = inf[-n:]
        try:
            idx = list(growth_series.index[-n:])
            dates = [str(d)[:7] for d in idx]
        except Exception:
            dates = [str(i) for i in range(n)]
        date_str = datetime.now().strftime("%Y%m%d")
        fig_path = str(_pathlib.Path(output_dir) / f"quadrant_{date_str}.png")
        fig, ax = plt.subplots(figsize=(10, 8))
        fig.patch.set_facecolor("white"); ax.set_facecolor("white")
        g_mid = float(np.median(g))
        inf_base = 2.0
        xmin, xmax = min(g) - 0.5, max(g) + 0.5
        ymin, ymax = min(inf) - 0.3, max(inf) + 0.3
        # 四象限背景色
        ax.fill_betweenx([inf_base, ymax], [xmin, xmin], [g_mid, g_mid], alpha=0.12, color="#FFF3E0")
        ax.fill_betweenx([inf_base, ymax], [g_mid, g_mid], [xmax, xmax], alpha=0.12, color="#FFEBEE")
        ax.fill_betweenx([ymin, inf_base], [xmin, xmin], [g_mid, g_mid], alpha=0.12, color="#E3F2FD")
        ax.fill_betweenx([ymin, inf_base], [g_mid, g_mid], [xmax, xmax], alpha=0.12, color="#E8F5E9")
        ofs = (xmax - xmin) * 0.03
        ax.text(xmin + ofs, ymax - 0.1, "滞胀", fontsize=9, color="#E67E22", alpha=0.8)
        ax.text(xmin + ofs, ymin + 0.05, "衰退", fontsize=9, color="#3498DB", alpha=0.8)
        ax.text(g_mid + ofs, ymax - 0.1, "过热", fontsize=9, color="#E74C3C", alpha=0.8)
        ax.text(g_mid + ofs, ymin + 0.05, "复苏", fontsize=9, color="#2ECC71", alpha=0.8)
        ax.axvline(g_mid, color="gray", lw=0.8, ls="--", alpha=0.5)
        ax.axhline(inf_base, color="gray", lw=0.8, ls="--", alpha=0.5)
        # 时间渐变轨迹
        clrs = cm.Greys(np.linspace(0.2, 0.85, n))
        for i in range(n - 1):
            ax.plot([g[i], g[i + 1]], [inf[i], inf[i + 1]], color=clrs[i], lw=1.5)
        ax.scatter(g, inf, c=range(n), cmap="Greys", s=25, zorder=5)
        # 当前点高亮
        ax.scatter([g[-1]], [inf[-1]], s=150, color="#E67E22", zorder=10, marker="o")
        ax.annotate("当前", (g[-1], inf[-1]), xytext=(5, 5),
                    textcoords="offset points", fontsize=9, color="#E67E22")
        if n >= 7:
            ax.scatter([g[-6]], [inf[-6]], s=60, color="#888", zorder=8, marker="o")
            ax.annotate("6M前", (g[-6], inf[-6]), xytext=(5, 5),
                        textcoords="offset points", fontsize=8, color="#888")
        if n >= 13:
            ax.scatter([g[-12]], [inf[-12]], s=60, color="#AAA", zorder=8, marker="s")
            ax.annotate("1Y前", (g[-12], inf[-12]), xytext=(5, 5),
                        textcoords="offset points", fontsize=8, color="#AAA")
        if labels:
            for ds, txt in labels.items():
                for i, d in enumerate(dates):
                    if d == ds:
                        ax.annotate(txt, (g[i], inf[i]), xytext=(5, 5),
                                    textcoords="offset points", fontsize=8)
        ax.set_xlabel("GDP/PMI 增长指数", fontsize=11)
        ax.set_ylabel("CPI 同比 (%)", fontsize=11)
        ax.set_title("增长-通胀散点轨迹图（改进版美林时钟坐标）",
                     fontsize=12, fontweight="bold")
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
        plt.tight_layout()
        b64 = _fig_to_base64(fig)
        _save_fig(fig, fig_path)
        return b64, fig_path
    except Exception as e:
        warnings.warn(f"render_quadrant_chart failed: {e}")
        return None, None
    finally:
        try: plt.close(fig)
        except: pass


def render_valuation_sentiment_chart(
    industries_data: List[Dict],
    output_dir: str = ".",
) -> Tuple[Optional[str], Optional[str]]:
    """估值-景气四象限图。
    industries_data: list of dict: name, sentiment(-1~1), valuation_pct(0~100), phase_match(bool)
    """
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patheffects as pe
    except ImportError:
        warnings.warn("matplotlib not available"); return None,None
    try:
        _setup_chinese_font()
        date_str = datetime.now().strftime("%Y%m%d")
        today_label = datetime.now().strftime("%Y-%m-%d")
        fig_path = str(_pathlib.Path(output_dir)/f"valuation_{date_str}.png")
        fig,ax = plt.subplots(figsize=(10,8))
        fig.patch.set_facecolor("white"); ax.set_facecolor("white")
        ax.fill_betweenx([0,60],[-1,-1],[0,0],alpha=0.18,color="#F5F5F5")
        ax.fill_betweenx([60,100],[-1,-1],[0,0],alpha=0.18,color="#FFEBEE")
        ax.fill_betweenx([0,60],[0,0],[1,1],alpha=0.18,color="#E8F5E9")
        ax.fill_betweenx([60,100],[0,0],[1,1],alpha=0.18,color="#FFFDE7")
        ax.axvline(0,color="#888",lw=1,ls="--",alpha=0.6)
        ax.axhline(60,color="#888",lw=1,ls="--",alpha=0.6)
        kw = dict(fontsize=13,fontweight="bold",alpha=0.35,ha="center",va="center")
        ax.text(0.5,25,"★ 推荐区",color="#2ECC71",**kw)
        ax.text(-0.5,80,"规避区",color="#E74C3C",**kw)
        ax.text(0.5,80,"谨慎区",color="#E67E22",**kw)
        ax.text(-0.5,25,"观察区",color="#999",**kw)
        for ind in industries_data:
            name = ind.get("name","")
            sent = float(ind.get("sentiment",0))
            vp = float(ind.get("valuation_pct",50))
            match = bool(ind.get("phase_match",False))
            in_rec = (sent>0 and vp<60)
            if match:
                color="#E67E22"; size=180; fw="bold"; fc="#E67E22"
            else:
                color="#5D6D7E"; size=100; fw="normal"; fc="#888888"
            if match:
                ax.scatter([sent],[vp],c=color,s=size,zorder=6,alpha=0.9)
            else:
                ax.scatter([sent],[vp],c=color,s=size,zorder=5,alpha=0.7,marker="o",
                           facecolors="none",edgecolors=color,linewidths=1.5)
            lbl = ("★ " if in_rec else "") + name
            ax.annotate(lbl,(sent,vp),xytext=(6,4),textcoords="offset points",
                        fontsize=8.5,color=fc,fontweight=fw)
        ax.set_xlabel("景气偏冷  <───────>  景气偏热", fontsize=11)
        ax.set_ylabel("估值分位 (%)", fontsize=11)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_yticklabels(["0%(历史最低)", "20%", "40%", "60%(中性)", "80%", "100%(历史最高)"], fontsize=8)
        ax.set_xlim(-1.1, 1.1); ax.set_ylim(-5, 105)
        ax.set_title(f"估值-景气四象限图 · {today_label}", fontsize=12, fontweight="bold")
        plt.tight_layout(); b64=_fig_to_base64(fig); _save_fig(fig,fig_path); return b64,fig_path
    except Exception as e: warnings.warn(f"render_valuation_sentiment_chart failed: {e}"); return None,None
    finally:
        try: plt.close(fig)
        except: pass


def render_all(
    current_phase: str,
    growth_series,
    inflation_series,
    industries_data: List[Dict],
    output_dir: str = ".",
    data_date: Optional[str] = None,
) -> Dict[str, Tuple]:
    """一次性生成全部三张图，返回 dict。"""
    _pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    return {
        "clock": render_clock_chart(current_phase, data_date=data_date, output_dir=output_dir),
        "quadrant": render_quadrant_chart(growth_series, inflation_series, output_dir=output_dir),
        "valuation": render_valuation_sentiment_chart(industries_data, output_dir=output_dir),
    }


def ascii_clock(current_phase: str) -> str:
    """美林时钟 ASCII 降级版。"""
    lines = ["美林时钟（ASCII）", "=" * 40]
    for p in PHASE_ORDER:
        mk = ">>> " if p == current_phase else "    "
        inds = " / ".join(PHASE_INDUSTRIES.get(p, [])[:3])
        lines.append(f"{mk}[{p}]  推荐: {inds}")
    lines += ["=" * 40]
    return "\n".join(lines)


def ascii_valuation_chart(industries_data: List[Dict]) -> str:
    """估值-景气四象限 ASCII 降级版。"""
    lines = ["估值-景气四象限图（ASCII）", "=" * 55]
    lines.append("  行业        景气     估值%   阶段匹配")
    lines.append("-" * 55)
    for ind in sorted(industries_data, key=lambda x: -x.get("sentiment", 0)):
        n = ind.get("name", "")
        s = ind.get("sentiment", 0)
        v = ind.get("valuation_pct", 50)
        m = ind.get("phase_match", False)
        star = "★" if (s > 0 and v < 60) else " "
        flag = "✓" if m else "○"
        lines.append(f"{star} {n:<8}{s:>7.2f}{v:>8.1f}%  {flag}")
    lines += ["=" * 55]
    return "\n".join(lines)


if __name__ == "__main__":
    import pandas as pd, pathlib as pl
    OUT_DIR = str(pl.Path(__file__).resolve().parent.parent / "reports" / "test_charts")
    pl.Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2023-01", periods=20, freq="MS")
    g0 = [4.5,4.8,5.1,5.3,5.6,5.2,4.9,5.0,5.4,5.7,5.9,5.5,5.1,4.8,5.2,5.6,6.0,5.8,5.3,4.9]
    i0 = [0.7,0.9,1.2,1.5,1.8,2.1,2.4,2.7,2.5,2.2,1.9,1.6,1.3,1.1,1.4,1.7,2.0,2.3,2.6,2.9]
    growth = pd.Series(g0, index=dates)
    inflation = pd.Series(i0, index=dates)
    industries = [
        {"name":"电子","sentiment":0.72,"valuation_pct":38.0,"phase_match":True},
        {"name":"消费","sentiment":0.51,"valuation_pct":42.0,"phase_match":True},
        {"name":"医药","sentiment":0.35,"valuation_pct":55.0,"phase_match":True},
        {"name":"银行","sentiment":0.18,"valuation_pct":48.0,"phase_match":False},
        {"name":"资源","sentiment":-0.10,"valuation_pct":62.0,"phase_match":False},
        {"name":"周期","sentiment":0.05,"valuation_pct":70.0,"phase_match":False},
        {"name":"防御","sentiment":-0.25,"valuation_pct":35.0,"phase_match":False},
        {"name":"公用","sentiment":-0.18,"valuation_pct":28.0,"phase_match":False},
        {"name":"锂铁","sentiment":-0.42,"valuation_pct":85.0,"phase_match":False},
        {"name":"黄金","sentiment":0.02,"valuation_pct":58.0,"phase_match":False},
    ]
    result = render_all("复苏期", growth, inflation, industries,
                        output_dir=OUT_DIR, data_date="2024-12")
    for key, (b64, path) in result.items():
        if b64:
            print(f"{key}: {b64[:50]}...")
        else:
            print(f"{key}: None")
        print(f"  -> {path}")
    print()
    print(ascii_clock("复苏期"))
    print(ascii_valuation_chart(industries))