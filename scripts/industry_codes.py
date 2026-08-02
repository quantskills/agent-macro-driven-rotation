# -*- coding: utf-8 -*-
"""申万一级行业映射 + Pandadata 可拉行情代理码（回测 / 导出 / 动画共用）。

定码说明（2026-07-30，行情代理复核 2026-07-30）：
  - 业务映射仍对齐 SKILL.md「宏观阶段 → 行业」
  - 申万一级码见 SW_INDUSTRY_CODES（.SI）；panda_data.get_index_daily 对 .SI 常返回 0 行
  - 实际拉行情用 INDUSTRY_INDEX_CODES（SH/SZ 指数或黄金 ETF）
  - 对话路径仍须先定码；代理指数≠申万官方点位，仅作景气/动量近似
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# 定码日期（写入 CSV / 文档可追溯）
CODE_VERIFIED_DATE = "2026-07-30"

# 申万一级行业指数码（文档参考；勿直接用于 get_index_daily）
SW_INDUSTRY_CODES: Dict[str, str] = {
    "电子": "801080.SI",
    "医药生物": "801150.SI",
    "计算机": "801750.SI",
    "食品饮料": "801120.SI",
    "家用电器": "801110.SI",
    "社会服务": "801890.SI",
    "有色金属": "801050.SI",
    "煤炭": "801950.SI",
    "石油石化": "801960.SI",
    "钢铁": "801040.SI",
    "银行": "801780.SI",
    "农林牧渔": "801010.SI",
    "公用事业": "801160.SI",
    "交通运输": "801170.SI",
    "黄金": "399293.SZ",  # 旧占位，已证实非黄金主题；行情见下方代理
}

# Pandadata 可拉日行情的代理（经 get_index_daily / get_fund_daily 冒烟有数据）
# 名称 → (symbol, feed)  feed: index | fund
INDUSTRY_PRICE_FEEDS: Dict[str, Tuple[str, str]] = {
    "电子": ("399811.SZ", "index"),      # CSSW电子
    "医药生物": ("000991.SH", "index"),  # 全指医药
    "计算机": ("000993.SH", "index"),    # 全指信息
    "食品饮料": ("399396.SZ", "index"),  # 国证食品
    "家用电器": ("000990.SH", "index"),  # 全指消费（家电无独立可用码时用大消费代理）
    "社会服务": ("000990.SH", "index"),
    "有色金属": ("399395.SZ", "index"),  # 国证有色
    "煤炭": ("399998.SZ", "index"),      # 中证煤炭
    "石油石化": ("000068.SH", "index"),  # 上证资源（能化/资源代理）
    "钢铁": ("399440.SZ", "index"),      # 国证钢铁
    "银行": ("399986.SZ", "index"),      # 中证银行
    "农林牧渔": ("399814.SZ", "index"),  # 大农业
    "公用事业": ("000995.SH", "index"),  # 全指公用
    "交通运输": ("399433.SZ", "index"),  # 国证交运
    "黄金": ("518880.SH", "fund"),       # 黄金 ETF（指数库无黄金主题码）
    # 动画短标签
    "消费": ("000990.SH", "index"),      # 全指消费
    "医药": ("000991.SH", "index"),
    "资源": ("000068.SH", "index"),      # 上证资源
    "周期": ("399440.SZ", "index"),      # 国证钢铁（周期代理）
    "防御消费": ("399396.SZ", "index"),  # 国证食品
    "债券": ("000012.SH", "index"),      # 国债指数
}

# 兼容旧接口：行业中文名 → 行情代码
INDUSTRY_INDEX_CODES: Dict[str, str] = {
    name: feed[0] for name, feed in INDUSTRY_PRICE_FEEDS.items()
}

# 阶段 → 推荐行业中文名（与 SKILL / guide 对齐）
PHASE_INDUSTRY_NAMES: Dict[str, List[str]] = {
    "复苏期": ["电子", "医药生物", "计算机", "食品饮料", "家用电器"],
    "过热期": ["有色金属", "煤炭", "石油石化", "钢铁", "银行"],
    "滞胀期": ["农林牧渔", "医药生物", "公用事业", "交通运输"],
    "衰退期": ["黄金"],
}

# 图表 / 动画展示短标签
PHASE_DISPLAY_LABELS: Dict[str, List[str]] = {
    "复苏期": ["电子", "消费", "医药"],
    "过热期": ["资源", "周期", "银行"],
    "滞胀期": ["防御消费", "公用事业", "医药"],
    "衰退期": ["黄金", "债券", "现金"],
}

# 动画宇宙（短标签全集）
ANIMATION_INDUSTRIES: List[str] = [
    "电子", "消费", "医药", "资源", "周期", "银行", "防御消费", "公用事业", "黄金", "债券"
]


def phase_index_codes(phase: str) -> List[str]:
    """返回某宏观阶段推荐行业的行情代理代码列表。"""
    names = PHASE_INDUSTRY_NAMES.get(phase, [])
    codes = []
    for name in names:
        code = INDUSTRY_INDEX_CODES.get(name)
        if code:
            codes.append(code)
    return codes


def all_phase_codes() -> Dict[str, List[str]]:
    """阶段 → 指数代码（供 backtest PHASE_INDUSTRIES 使用）。"""
    return {phase: phase_index_codes(phase) for phase in PHASE_INDUSTRY_NAMES}


def name_code_pairs(phase: str) -> List[Tuple[str, str]]:
    """返回 (行业名, 代码) 列表。"""
    pairs = []
    for name in PHASE_INDUSTRY_NAMES.get(phase, []):
        code = INDUSTRY_INDEX_CODES.get(name)
        if code:
            pairs.append((name, code))
    return pairs


def price_feed(name: str) -> Tuple[str, str]:
    """返回 (symbol, feed_kind)，feed_kind 为 index 或 fund。"""
    return INDUSTRY_PRICE_FEEDS.get(name, ("", "index"))
