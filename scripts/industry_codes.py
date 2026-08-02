# -*- coding: utf-8 -*-
"""宏观阶段→行业名（业务规则）+ 行情/申万码解析入口。

重要区分：
  - PHASE_INDUSTRY_NAMES：美林阶段受益行业（来自 SKILL，属研究框架，不能靠 API「猜」）
  - 申万码 / 行情代理 / 另类类目：优先 code_resolver 自动匹配 panda_data；
    失败时回退下方 FALLBACK_* 静态表（仅兜底）
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# 静态兜底定码日期（自动解析成功时以 cache.updated_at 为准）
CODE_VERIFIED_DATE = "2026-07-30"

# ── 业务规则：阶段 → 申万一级行业中文名（与 SKILL.md 对齐）────────────────
PHASE_INDUSTRY_NAMES: Dict[str, List[str]] = {
    "复苏期": ["电子", "医药生物", "计算机", "食品饮料", "社会服务"],
    "过热期": ["有色金属", "煤炭", "石油石化", "钢铁", "银行"],
    "滞胀期": ["农林牧渔", "医药生物", "公用事业", "交通运输"],
    "衰退期": ["黄金"],
}

PHASE_DISPLAY_LABELS: Dict[str, List[str]] = {
    "复苏期": ["电子", "消费", "医药"],
    "过热期": ["资源", "周期", "银行"],
    "滞胀期": ["防御消费", "公用事业", "医药"],
    "衰退期": ["黄金", "债券", "现金"],
}

ANIMATION_INDUSTRIES: List[str] = [
    "电子", "消费", "医药", "资源", "周期", "银行", "防御消费", "公用事业", "黄金", "债券"
]

# ── 静态兜底（API 不可用时）────────────────────────────────────────────
# 注意：申万码须与 get_industry_detail 一致；旧表曾误把社会服务写成 801890（实为机械设备）
FALLBACK_SW_CODES: Dict[str, str] = {
    "电子": "801080",
    "医药生物": "801150",
    "计算机": "801750",
    "食品饮料": "801120",
    "家用电器": "801110",
    "社会服务": "801210",
    "有色金属": "801050",
    "煤炭": "801950",
    "石油石化": "801960",
    "钢铁": "801040",
    "银行": "801780",
    "农林牧渔": "801010",
    "公用事业": "801160",
    "交通运输": "801170",
}

FALLBACK_PRICE_FEEDS: Dict[str, Tuple[str, str]] = {
    "电子": ("399811.SZ", "index"),
    "医药生物": ("000991.SH", "index"),
    "计算机": ("000993.SH", "index"),
    "食品饮料": ("399396.SZ", "index"),
    "家用电器": ("000990.SH", "index"),
    "社会服务": ("000990.SH", "index"),
    "有色金属": ("399395.SZ", "index"),
    "煤炭": ("399998.SZ", "index"),
    "石油石化": ("000068.SH", "index"),
    "钢铁": ("399440.SZ", "index"),
    "银行": ("399986.SZ", "index"),
    "农林牧渔": ("399814.SZ", "index"),
    "公用事业": ("000995.SH", "index"),
    "交通运输": ("399433.SZ", "index"),
    "黄金": ("518880.SH", "fund"),
    "消费": ("000990.SH", "index"),
    "医药": ("000991.SH", "index"),
    "资源": ("000068.SH", "index"),
    "周期": ("399440.SZ", "index"),
    "防御消费": ("399396.SZ", "index"),
    "债券": ("000012.SH", "index"),
}

# 兼容旧名
SW_INDUSTRY_CODES: Dict[str, str] = {
    k: (v if "." in v else f"{v}.SI") for k, v in FALLBACK_SW_CODES.items()
}
INDUSTRY_PRICE_FEEDS: Dict[str, Tuple[str, str]] = dict(FALLBACK_PRICE_FEEDS)
INDUSTRY_INDEX_CODES: Dict[str, str] = {
    name: feed[0] for name, feed in INDUSTRY_PRICE_FEEDS.items()
}

# 另类类目静态兜底（优先用 code_resolver 关键词匹配）
INDUSTRY_ALT_CATEGORIES: Dict[str, List[str]] = {
    "电子": ["ED"],
    "计算机": ["ED"],
    "医药生物": ["MD"],
    "医药": ["MD"],
    "家用电器": ["HA"],
    "食品饮料": ["EC", "OF"],
    "消费": ["EC", "OF"],
    "防御消费": ["EC", "OF"],
    "社会服务": ["RB", "OF"],
    "石油石化": ["EH"],
    "有色金属": ["EH"],
    "资源": ["EH"],
    "周期": ["EH"],
}

PREFERRED_ALT_SYMBOLS: Dict[str, List[str]] = {
    "电子": ["ED0000072"],
    "计算机": ["ED0000072"],
}

_USE_AUTO = True


def set_auto_resolve(enabled: bool) -> None:
    global _USE_AUTO
    _USE_AUTO = enabled


def refresh_codes_from_api(force: bool = False) -> Dict[str, str]:
    """用 get_industry_detail / get_index_detail 刷新模块级码表。"""
    from code_resolver import get_resolver

    r = get_resolver()
    sw = r.refresh_sw_industries(force=force)
    # 同步 SW 展示码
    global SW_INDUSTRY_CODES, INDUSTRY_PRICE_FEEDS, INDUSTRY_INDEX_CODES
    SW_INDUSTRY_CODES = {
        k: (v if str(v).endswith((".SI", ".SH", ".SZ")) else f"{v}.SI")
        for k, v in sw.items()
    }
    # 预解析阶段相关 + 动画短标签
    names = set()
    for lst in PHASE_INDUSTRY_NAMES.values():
        names.update(lst)
    names.update(ANIMATION_INDUSTRIES)
    feeds: Dict[str, Tuple[str, str]] = dict(FALLBACK_PRICE_FEEDS)
    notes: Dict[str, str] = {}
    for name in sorted(names):
        if name == "现金":
            continue
        try:
            sym, feed, note = r.resolve_price_feed(name, force=force)
            feeds[name] = (sym, feed)
            notes[name] = note
        except Exception as e:
            notes[name] = f"fallback:{e}"
    INDUSTRY_PRICE_FEEDS = feeds
    INDUSTRY_INDEX_CODES = {n: f[0] for n, f in feeds.items()}
    return notes


def price_feed(name: str) -> Tuple[str, str]:
    """返回 (symbol, feed_kind)。live 时自动匹配，失败回退静态表。"""
    if _USE_AUTO:
        try:
            from code_resolver import get_price_feed

            return get_price_feed(name)
        except Exception:
            pass
    return INDUSTRY_PRICE_FEEDS.get(name) or FALLBACK_PRICE_FEEDS.get(name, ("", "index"))


def alt_categories(name: str) -> List[str]:
    if _USE_AUTO:
        try:
            from code_resolver import get_alt_categories

            cats = get_alt_categories(name)
            if cats:
                return cats
        except Exception:
            pass
    return list(INDUSTRY_ALT_CATEGORIES.get(name, []))


def sw_code(name: str) -> str:
    if _USE_AUTO:
        try:
            from code_resolver import get_resolver

            c = get_resolver().sw_code(name)
            if c:
                return c if "." in c else f"{c}.SI"
        except Exception:
            pass
    return SW_INDUSTRY_CODES.get(name) or (
        f"{FALLBACK_SW_CODES[name]}.SI" if name in FALLBACK_SW_CODES else ""
    )


def phase_index_codes(phase: str) -> List[str]:
    codes = []
    for name in PHASE_INDUSTRY_NAMES.get(phase, []):
        code, _ = price_feed(name)
        if code:
            codes.append(code)
    return codes


def all_phase_codes() -> Dict[str, List[str]]:
    return {phase: phase_index_codes(phase) for phase in PHASE_INDUSTRY_NAMES}


def name_code_pairs(phase: str) -> List[Tuple[str, str]]:
    pairs = []
    for name in PHASE_INDUSTRY_NAMES.get(phase, []):
        code, _ = price_feed(name)
        if code:
            pairs.append((name, code))
        else:
            pairs.append((name, ""))
    return pairs
