---
name: agent-macro-driven-rotation
description: "Macro-driven A-share industry rotation analysis. Improved Merrill Lynch Clock phase detection + alternative-data nowcast + valuation filter. Use when a research AI agent needs phase determination, industry screening, prosperity confirmation, valuation filtering, and L1–L5 research outputs without automated order placement."
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: quantskills/agent-macro-driven-rotation
  repository_url: https://github.com/quantskills/agent-macro-driven-rotation
  project_type: agent
  collection: macro-rotation
  license: GPL-3.0-only
  category: analyst
  tags: [quant, macro, rotation, merrill-lynch-clock, industry, pandadata]
  platforms: [claude-code, codex, hermes, openclaw, cursor]
  language: zh-en
  status: draft
  validation_level: runnable
  maintainer_type: community
  maintainer: frocir
  requires:
    - macro-monitor
    - macro-altdata-nowcast
    - index-valuation-rotation
  summary_zh: 宏观驱动行业轮动 Agent：改进版美林时钟定相 + 另类景气 Nowcast + 估值过滤，输出行业轮动研究参考与四象限图。
  summary_en: Macro-driven industry rotation agent: Improved Merrill Lynch Clock phase detection, alternative-data nowcast, and valuation filter for research-only rotation materials.
quantSkills:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: quantskills/agent-macro-driven-rotation
  repository_url: https://github.com/quantskills/agent-macro-driven-rotation
  project_type: agent
  collection: macro-rotation
  license: GPL-3.0-only
  category: analyst
  tags: [quant, macro, rotation, merrill-lynch-clock, industry, pandadata]
  platforms: [claude-code, codex, hermes, openclaw, cursor]
  language: zh-en
  status: draft
  validation_level: runnable
  maintainer_type: community
  maintainer: frocir
  requires:
    - macro-monitor
    - macro-altdata-nowcast
    - index-valuation-rotation
  summary_zh: 宏观驱动行业轮动 Agent：改进版美林时钟定相 + 另类景气 Nowcast + 估值过滤，输出行业轮动研究参考与四象限图。
  summary_en: Macro-driven industry rotation agent: Improved Merrill Lynch Clock phase detection, alternative-data nowcast, and valuation filter for research-only rotation materials.
---

# Macro-Driven Rotation Agent

本文是本仓库**唯一** Agent 行为入口与 QuantSkills 声明（`AGENTS.md`）。仓库主页见 [README.md](README.md)；方法细节见 [references/macro-driven-rotation-guide.md](references/macro-driven-rotation-guide.md)。

Use this Agent when a user needs a Pandadata-backed research answer for:

> Given the current macro regime, which A-share industries are worth researching further?

This is a **Community Project** under QuantSkills. It is an analysis / research Agent (dialogue orchestration + charts + report validation), **not** an `alpha-*` production factor package and **not** an automated trading system.

## 定位边界

- 品类：**分析型 Agent**（对话编排 + 图表 + 报告校验，非 `alpha-*` 生产因子包）
- **能做**：改进版美林定相 → 行业初筛 → 另类景气 → 估值过滤 → L1–L5 研究输出（合规措辞）
- **不能做**：下单指令、「买入/必涨」等确定性建议；无凭证时不得当作今日 live 定相
- 若进入交易链路：须另开目录，按 [references/Alpha因子开发与生产规则V2.md](references/Alpha因子开发与生产规则V2.md) 交付

### 依赖

| 依赖 | 消费 |
|------|------|
| `macro-monitor` | 官方 CPI/GDP/PMI/社融/M2 → 宏观定相 |
| `macro-altdata-nowcast` | 另类高频 Nowcast → 景气确认 |
| `index-valuation-rotation` | PE/PB 分位与动量 → 估值过滤 |

调用依赖前阅读其 `SKILL.md`（依赖仓库自身入口）。

## What It Does

1. **Macro phase detection** — official CPI / GDP / PMI / social financing via `macro-monitor` → Recovery / Overheating / Stagflation / Recession.
2. **Industry prosperity confirmation** — alternative high-frequency nowcast via `macro-altdata-nowcast`.
3. **Valuation filter** — PE/PB percentile and momentum via `index-valuation-rotation`.
4. **Integrated research output** — L1–L5 materials (conclusion, evidence table, charts, interactive L4, CSV export).

## 输出层级

| 层级 | 内容 | 形式 | 触发 |
|------|------|------|------|
| L1 | 一句话结论 + 逻辑链 | 文本 | 每次必出 |
| L2 | 证据表（数值 / 数据期 / 来源） | Markdown | 每次必出 |
| L3 | 钟面 + 增长-通胀轨迹 + 估值-景气 | PNG / ASCII | 每次必出 |
| L4 | 动态四象限 + 本次快照 | `reports/runtime_out/l4.html` | runtime 自动 / 用户请求 |
| L5 | 宏观 / 景气 / 估值 / 推荐表 | `export/*` | runtime 自动 / 用户请求 |

研究态目录：`reports/runtime_out/`。回测净值图 `reports/backtest/nav_curve.html` 不等于 L4。结构样例：`reports/samples/e2e_rotation_sample.md`。

## How To Use

### Local CLI

```bash
pip install -r requirements.txt
# set PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD in the environment (never commit credentials)

python -m runtime --live --query "现在该关注什么行业"
python -m runtime --live --all
python -m runtime --live --backtest --backtest-start 2024-01-01
python -m runtime --self-test
python -m runtime validate
python -m runtime clean
```

| 子命令 | 作用 |
|--------|------|
| （默认） | 全链路 + 自动校验 |
| `validate` / `reconcile` | 结构校验 / L2 对账 |
| `l4 [--rebuild]` | 只写 / 重建 L4 |
| `backtest` | 输出到 `reports/backtest/` |
| `clean` / `test` | 清理产物 / 组件单测 |

Artifacts land under `reports/runtime_out/` (`runtime_report.md`, `l4.html`, `charts/`, `export/`).

### Runtime entry points

| Runtime | Entry |
| --- | --- |
| Claude Code / Codex | Load this folder; follow `AGENTS.md` + three dependencies |
| Cursor | `.cursor/skills/agent-macro-driven-rotation` + `agents/cursor-rule.mdc` |
| Hermes / OpenClaw / portable | Paste `agents/portable-loader.md` and replace the root path |
| OpenAI-compatible | `agents/openai.yaml` |

Publish metadata: [`agents/skill-manifest.yaml`](agents/skill-manifest.yaml).

### 对话触发话术

| 意图 | 示例 |
|------|------|
| 完整轮动报告 | 「按改进版美林时钟做一轮完整行业轮动报告」 |
| 行业配置参考 | 「现在该关注什么行业？给出宏观定相和证据表」 |
| 只要宏观阶段 | 「当前宏观环境处于什么阶段？只要定相和四维数据」 |
| 只要景气 / 估值 | 「电子、医药的另类高频景气怎么样？」 |
| 要交互图 / 表 | 「请导出 L4 交互页和 CSV」 |

## 工作流（6 步）

1. 意图识别 → 宏观 / 景气 / 估值 / 完整报告
2. 宏观定相（`macro-monitor`）→ 四维判定阶段
3. 行业初筛 → 阶段映射表（`scripts/industry_codes.PHASE_INDUSTRY_NAMES`）
4. 景气确认（`macro-altdata-nowcast`）→ 剔除景气下行
5. 估值过滤（`index-valuation-rotation`）→ 分位 + 动量
6. 综合输出 → L1–L5；图表经 `chart_writer.render_all`（失败则 ASCII 并标注降级）

### 四阶段判定（摘要）

| 条件 | 主阶段 | 辅助字段 |
|------|--------|----------|
| 扩张 + 低通胀 + 宽松 | 复苏期 | `loose_liquidity=True` |
| 扩张 + 低通胀 + 未宽松 | 复苏期 | `phase_note=扩张低通胀但流动性未宽松` |
| 扩张 + 高通胀 | 过热期 | 流动性写入辅助列 |
| 收缩 + 高通胀 | 滞胀期 | — |
| 收缩 + 低通胀 | 衰退期 | 若已宽松 → `phase_note=衰退末期/政策托底` |

政策预期差写入 `policy_gap`，不单独改主阶段名。细则与行业映射见 [references/macro-driven-rotation-guide.md](references/macro-driven-rotation-guide.md)。

### 依赖调用边界

- **macro-monitor**：先读其 `SKILL.md`；`get_macro_detail` 定码；引用须含方法名、参数、数据期、单位；说明官方滞后（常 1–2 月）。
- **macro-altdata-nowcast**：`get_macro_detail(category=...)` 定码；标注「另类/及时样本，非官方」；类目 EC/MD/EH/AD/HA/OF/RB/RE/ED/EP。
- **index-valuation-rotation**：先确认行业指数代码；短窗冒烟再扩展；标注 PE/PB 分位、窗口、数据日期。

## Maintainer

Maintained by `frocir` as a QuantSkills community project.

## Supported Scenarios

- Full industry-rotation research report (macro phase → screen → prosperity → valuation).
- Macro phase-only questions (Improved Merrill Lynch Clock dimensions).
- Sector prosperity / valuation deep-dives for a short industry list.
- Export of L4 interactive page and L5 CSV tables for research notes.
- Offline / mock self-test of the package layout and validators.

## 验收与降级 / Limitations

- Research and education only. Outputs are **not** investment advice and do **not** promise returns.
- Live conclusions must come from this session's API calls; memory must not override phase determination.
- Indicator codes must be resolved via `get_macro_detail`; never invent codes.
- 结论先行；数值须带数据期与来源；事实与解读分开。
- Official macro series are often lagged (commonly 1–2 months); alternative nowcast is timely but non-official.
- If any dependency skill fails, degrade and label gaps — do not fabricate numbers.
- No broker connectivity, no order placement, no unconditional buy/sell / position-sizing commands.
- Not a substitute for an Alpha production package; trading-link delivery must follow a separate Alpha production process.
- Community Project；收录或官方认可仍需维护者审核。

## Data Source And Assumptions

- Primary data: Pandadata (`panda_data` / `panda-data`).
- Credentials via environment variables only (`PANDA_DATA_*`); see `.env.example`.
- Phase rules: expansion/contraction × inflation × liquidity (see this file and `references/macro-driven-rotation-guide.md`).
- Industry mapping uses Shenwan Level-1 proxies resolved by `scripts/code_resolver.py` / `scripts/industry_codes.py`.

## Reference Documents

- [`references/macro-driven-rotation-guide.md`](references/macro-driven-rotation-guide.md) — methodology detail
- [`references/Alpha因子开发与生产规则V2.md`](references/Alpha因子开发与生产规则V2.md) — Alpha production boundary
- [`agents/portable-loader.md`](agents/portable-loader.md) — portable runtime loader prompt
- [`agents/skill-manifest.yaml`](agents/skill-manifest.yaml) — publish metadata

## Disclaimer

本报告与仓库材料基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。  
Materials in this repository are for research reference only and do not constitute investment advice.
