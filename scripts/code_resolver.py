# -*- coding: utf-8 -*-
"""行业码 / 行情代理 / 另类类目自动解析（替代写死码表）。

原则：
  - 阶段→行业中文名（PHASE_INDUSTRY_NAMES）是业务规则，仍来自 SKILL，API 无法「猜」美林映射
  - 申万一级码、行情代理、另类 category 尽量用 panda_data 现场匹配 + 冒烟校验
  - 结果缓存到 scripts/.cache/resolved_codes.json，避免每次全量扫表
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

CACHE_PATH = pathlib.Path(__file__).resolve().parent / ".cache" / "resolved_codes.json"

# 短标签 / 特殊名 → 检索关键词（按优先级）
_SEARCH_ALIASES: Dict[str, List[str]] = {
    "电子": ["电子", "CSSW电子", "全指电子"],
    "医药生物": ["医药生物", "全指医药", "医药"],
    "医药": ["全指医药", "医药生物", "医药"],
    "计算机": ["计算机", "全指信息", "信息"],
    "食品饮料": ["食品饮料", "国证食品", "食品"],
    "家用电器": ["家用电器", "家电", "全指消费"],
    "社会服务": ["社会服务", "消费者服务", "全指消费", "消费"],
    "有色金属": ["有色金属", "国证有色", "有色"],
    "煤炭": ["中证煤炭", "煤炭指数", "煤炭"],
    "石油石化": ["石油石化", "上证资源", "资源"],
    "钢铁": ["国证钢铁", "钢铁"],
    "银行": ["中证银行", "全指银行", "银行"],
    "农林牧渔": ["农林牧渔", "大农业", "农业"],
    "公用事业": ["全指公用", "公用事业"],
    "交通运输": ["国证交运", "交通运输", "交运"],
    "黄金": ["黄金ETF", "华安易富黄金", "黄金"],
    "消费": ["全指消费", "消费"],
    "资源": ["上证资源", "资源"],
    "周期": ["国证钢铁", "钢铁", "周期"],
    "防御消费": ["国证食品", "食品饮料", "食品"],
    "债券": ["国债指数", "国债", "债券"],
    "现金": [],
}

# 行业名关键词 → 另类特色 category（自动匹配用；比写死整表更稳）
_ALT_KEYWORD_CATS: List[Tuple[str, List[str]]] = [
    ("电子", ["ED"]),
    ("计算机", ["ED"]),
    ("通信", ["ED"]),
    ("医药", ["MD"]),
    ("家电", ["HA"]),
    ("家用电器", ["HA"]),
    ("食品", ["EC", "OF"]),
    ("商贸", ["OF"]),
    ("零售", ["OF"]),
    ("社会服务", ["RB", "OF"]),
    ("汽车", ["AD"]),
    ("石油", ["EH"]),
    ("石化", ["EH"]),
    ("有色", ["EH"]),
    ("化工", ["EH"]),
    ("房地产", ["RE"]),
    ("电力设备", ["EP"]),
    ("电新", ["EP"]),
]


class CodeResolver:
    def __init__(self, pd_mod: Any = None):
        self.pd = pd_mod
        self._cache: Dict[str, Any] = {}
        self._index_df = None
        self._fund_df = None
        self._industry_df = None
        self._load_cache()

    def _load_cache(self) -> None:
        if CACHE_PATH.exists():
            try:
                self._cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def save_cache(self) -> None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
        CACHE_PATH.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_pd(self) -> Any:
        if self.pd is not None:
            return self.pd
        from panda_client import get_panda_data

        self.pd = get_panda_data(require_token=True)
        return self.pd

    def refresh_sw_industries(self, force: bool = False) -> Dict[str, str]:
        """get_industry_detail(L1) → {行业名: 申万码}（无 .SI 后缀的原始码）。"""
        if not force and self._cache.get("sw_codes"):
            return dict(self._cache["sw_codes"])
        pd_mod = self._ensure_pd()
        df = pd_mod.get_industry_detail(level="L1")
        if df is None or len(df) == 0:
            raise RuntimeError("get_industry_detail 空表")
        mapping: Dict[str, str] = {}
        for _, row in df.iterrows():
            name = str(row.get("industry_name", "")).strip()
            code = str(row.get("industry_code", "")).strip()
            if name and code:
                mapping[name] = code
        self._cache["sw_codes"] = mapping
        self._industry_df = df
        self.save_cache()
        return mapping

    def sw_code(self, industry: str) -> str:
        m = self.refresh_sw_industries(force=False)
        return m.get(industry, "")

    def _get_index_universe(self):
        if self._index_df is not None:
            return self._index_df
        pd_mod = self._ensure_pd()
        df = pd_mod.get_index_detail(status=1)
        if df is None or len(df) == 0:
            df = pd_mod.get_index_detail()
        self._index_df = df
        return df

    def _get_fund_universe(self):
        if self._fund_df is not None:
            return self._fund_df
        pd_mod = self._ensure_pd()
        df = pd_mod.get_fund_detail()
        self._fund_df = df
        return df

    @staticmethod
    def _is_sh_sz(symbol: str) -> bool:
        s = str(symbol)
        return s.endswith(".SH") or s.endswith(".SZ")

    def _score_index_name(self, name: str, keywords: List[str]) -> int:
        n = str(name)
        score = 0
        for i, kw in enumerate(keywords):
            if not kw:
                continue
            if n == kw:
                score += 100 - i
            elif kw in n:
                score += 40 - i
        # 偏好行业主题指数，惩罚债券/策略/ESG 杂讯
        if re.search(r"全指|中证|国证|上证|CSSW|申万", n):
            score += 15
        if re.search(r"债券|信用债|可转债|ESG|红利|等权|主题|QDII|港", n):
            score -= 25
        if re.search(r"行业", n):
            score += 8
        return score

    def _smoke_index(self, symbol: str) -> bool:
        pd_mod = self._ensure_pd()
        end = datetime.today()
        start = end - timedelta(days=60)
        try:
            df = pd_mod.get_index_daily(
                symbol=symbol,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
            )
            if df is not None and len(df) >= 5:
                return True
        except Exception:
            pass
        try:
            df = pd_mod.get_index_indicator(
                symbol=symbol,
                start_date=(end - timedelta(days=120)).strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
            )
            return df is not None and len(df) >= 5
        except Exception:
            return False

    def _smoke_fund(self, symbol: str) -> bool:
        pd_mod = self._ensure_pd()
        end = datetime.today()
        start = end - timedelta(days=60)
        try:
            df = pd_mod.get_fund_daily(
                symbol=symbol,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            return df is not None and len(df) >= 5
        except Exception:
            return False

    def resolve_price_feed(
        self, industry: str, *, force: bool = False
    ) -> Tuple[str, str, str]:
        """返回 (symbol, feed, note)。feed: index|fund。"""
        feeds = self._cache.setdefault("price_feeds", {})
        if not force and industry in feeds:
            item = feeds[industry]
            return item["symbol"], item["feed"], item.get("note", "cache")

        keywords = _SEARCH_ALIASES.get(industry) or [industry]
        # 黄金优先基金 ETF
        if industry == "黄金" or (keywords and "黄金ETF" in keywords):
            fund_hit = self._resolve_fund(keywords)
            if fund_hit:
                sym, note = fund_hit
                feeds[industry] = {"symbol": sym, "feed": "fund", "note": note}
                self.save_cache()
                return sym, "fund", note

        idx = self._get_index_universe()
        if idx is None or len(idx) == 0:
            raise RuntimeError("get_index_detail 空表")

        work = idx[idx["symbol"].astype(str).map(self._is_sh_sz)].copy()
        work["_score"] = work["name"].astype(str).map(
            lambda n: self._score_index_name(n, keywords)
        )
        work = work[work["_score"] > 0].sort_values("_score", ascending=False)
        tried = []
        for _, row in work.head(12).iterrows():
            sym = str(row["symbol"])
            name = str(row["name"])
            tried.append(f"{sym}:{name}")
            if self._smoke_index(sym):
                note = f"auto:{name}; keywords={keywords}"
                feeds[industry] = {"symbol": sym, "feed": "index", "note": note}
                self.save_cache()
                return sym, "index", note

        # 行业无直接命中时：用申万名再试一次模糊（取前两字）
        if len(industry) >= 2:
            loose_kw = [industry[:2]]
            work2 = idx[idx["symbol"].astype(str).map(self._is_sh_sz)].copy()
            work2["_score"] = work2["name"].astype(str).map(
                lambda n: self._score_index_name(n, loose_kw)
            )
            work2 = work2[work2["_score"] > 0].sort_values("_score", ascending=False)
            for _, row in work2.head(8).iterrows():
                sym = str(row["symbol"])
                if sym in {t.split(":")[0] for t in tried}:
                    continue
                if self._smoke_index(sym):
                    note = f"auto-loose:{row['name']}; tried={tried[:3]}"
                    feeds[industry] = {"symbol": sym, "feed": "index", "note": note}
                    self.save_cache()
                    return sym, "index", note

        raise RuntimeError(f"无法自动匹配行情代理: {industry}; tried={tried[:5]}")

    def _resolve_fund(self, keywords: List[str]) -> Optional[Tuple[str, str]]:
        df = self._get_fund_universe()
        if df is None or len(df) == 0:
            return None
        work = df[df["symbol"].astype(str).map(self._is_sh_sz)].copy()
        # 只要 ETF
        if "etf_lof_type" in work.columns:
            work = work[work["etf_lof_type"].astype(str).str.upper() == "ETF"]
        work["_score"] = 0
        for i, kw in enumerate(keywords):
            work.loc[work["name"].astype(str).str.contains(kw, na=False), "_score"] += (
                50 - i
            )
        # 偏好商品黄金 ETF（华安易富等），惩罚「产业股票」
        work.loc[work["name"].astype(str).str.contains("产业股票", na=False), "_score"] -= 20
        work.loc[work["name"].astype(str).str.contains("商品|易富|黄金ETF", na=False), "_score"] += 10
        work = work[work["_score"] > 0].sort_values("_score", ascending=False)
        for _, row in work.head(10).iterrows():
            sym = str(row["symbol"])
            if self._smoke_fund(sym):
                return sym, f"auto-fund:{row['name']}"
        return None

    def resolve_alt_categories(self, industry: str) -> List[str]:
        """按行业名关键词匹配另类 category；无则空列表（调用方走动量代理）。"""
        cats: List[str] = []
        for kw, cat_list in _ALT_KEYWORD_CATS:
            if kw in industry:
                for c in cat_list:
                    if c not in cats:
                        cats.append(c)
        return cats

    def resolve_phase_pairs(
        self, phase_names: List[str], *, force: bool = False
    ) -> List[Tuple[str, str, str]]:
        """[(行业名, symbol, feed), ...]"""
        out = []
        for name in phase_names:
            if name in ("现金",):
                continue
            try:
                sym, feed, _note = self.resolve_price_feed(name, force=force)
                out.append((name, sym, feed))
            except Exception:
                out.append((name, "", "index"))
        return out


_RESOLVER: Optional[CodeResolver] = None


def get_resolver(pd_mod: Any = None) -> CodeResolver:
    global _RESOLVER
    if _RESOLVER is None or (pd_mod is not None and _RESOLVER.pd is None):
        _RESOLVER = CodeResolver(pd_mod=pd_mod)
    return _RESOLVER


def get_price_feed(name: str, *, force: bool = False) -> Tuple[str, str]:
    r = get_resolver()
    sym, feed, _ = r.resolve_price_feed(name, force=force)
    return sym, feed


def get_alt_categories(name: str) -> List[str]:
    return get_resolver().resolve_alt_categories(name)
