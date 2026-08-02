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

Use this Agent when a user needs a Pandadata-backed research answer for:

> Given the current macro regime, which A-share industries are worth researching further?

This is a **Community Project** under QuantSkills. It is an analysis / research Agent (dialogue orchestration + charts + report validation), **not** an `alpha-*` production factor package and **not** an automated trading system.

Detailed behavior rules live in [`SKILL.md`](SKILL.md). This file is the QuantSkills Agent declaration and multi-runtime entry.

## What It Does

1. **Macro phase detection** — official CPI / GDP / PMI / social financing via `macro-monitor` → Recovery / Overheating / Stagflation / Recession.
2. **Industry prosperity confirmation** — alternative high-frequency nowcast via `macro-altdata-nowcast`.
3. **Valuation filter** — PE/PB percentile and momentum via `index-valuation-rotation`.
4. **Integrated research output** — L1–L5 materials (conclusion, evidence table, charts, interactive L4, CSV export).

## How To Use

### Local CLI

```bash
pip install -r requirements.txt
# set PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD in the environment (never commit credentials)

python -m runtime --live --query "现在该关注什么行业"
python -m runtime --live --all
python -m runtime --live --backtest --backtest-start 2024-01-01
python -m runtime --self-test
python -m runtime clean
```

Artifacts land under `reports/runtime_out/` (`runtime_report.md`, `l4.html`, `charts/`, `export/`). Structure sample: `reports/samples/e2e_rotation_sample.md`.

### Runtime entry points

| Runtime | Entry |
| --- | --- |
| Claude Code / Codex | Load this folder; follow `SKILL.md` + dependencies |
| Cursor | `.cursor/skills/agent-macro-driven-rotation` + `agents/cursor-rule.mdc` |
| Hermes / OpenClaw / portable | Paste `agents/portable-loader.md` and replace the root path |
| OpenAI-compatible | `agents/openai.yaml` |

Publish metadata: [`agents/skill-manifest.yaml`](agents/skill-manifest.yaml).

## Maintainer

Maintained by `frocir` as a QuantSkills community project.

## Supported Scenarios

- Full industry-rotation research report (macro phase → screen → prosperity → valuation).
- Macro phase-only questions (Improved Merrill Lynch Clock dimensions).
- Sector prosperity / valuation deep-dives for a short industry list.
- Export of L4 interactive page and L5 CSV tables for research notes.
- Offline / mock self-test of the package layout and validators.

## Limitations And Boundaries

- Research and education only. Outputs are **not** investment advice and do **not** promise returns.
- Live conclusions must come from this session's API calls; memory must not override phase determination.
- Indicator codes must be resolved via `get_macro_detail`; never invent codes.
- Official macro series are often lagged (commonly 1–2 months); alternative nowcast is timely but non-official.
- If any dependency skill fails, degrade and label gaps — do not fabricate numbers.
- No broker connectivity, no order placement, no unconditional buy/sell / position-sizing commands.
- Not a substitute for an Alpha production package; trading-link delivery must follow a separate Alpha production process.

## Data Source And Assumptions

- Primary data: Pandadata (`panda_data` / `panda-data`).
- Credentials via environment variables only (`PANDA_DATA_*`); see `.env.example`.
- Phase rules: expansion/contraction × inflation × liquidity (see `SKILL.md` and `references/macro-driven-rotation-guide.md`).
- Industry mapping uses Shenwan Level-1 proxies resolved by `scripts/code_resolver.py` / `scripts/industry_codes.py`.

## Reference Documents

- [`SKILL.md`](SKILL.md) — full behavior, workflow, output levels, and hard constraints
- [`references/macro-driven-rotation-guide.md`](references/macro-driven-rotation-guide.md) — methodology detail
- [`references/Alpha因子开发与生产规则V2.md`](references/Alpha因子开发与生产规则V2.md) — Alpha production boundary
- [`agents/portable-loader.md`](agents/portable-loader.md) — portable runtime loader prompt

## Disclaimer

本报告与仓库材料基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。  
Materials in this repository are for research reference only and do not constitute investment advice.
