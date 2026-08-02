# Portable Loader Prompt

Use this prompt in agents that do not natively discover `SKILL.md` folders, including Claude Code, Hermes, OpenClaw, and any deployment that receives skills as copied folders.

```text
You have access to a local agent skill named agent-macro-driven-rotation at:
<AGENT_MACRO_DRIVEN_ROTATION_ROOT>

This agent provides A-share industry rotation recommendations based on the Improved Merrill Lynch Clock
framework. It depends on three sub-skills:
  - macro-monitor (official macro data: GDP/CPI/PMI/social financing/M2)
  - macro-altdata-nowcast (alternative high-frequency industry prosperity nowcasting)
  - index-valuation-rotation (index PE/PB percentile valuation and industry momentum)

When the user asks for industry rotation advice, macro phase analysis, Improved Merrill Lynch Clock
analysis, 行业轮动推荐, 宏观定相, 现在该买什么行业, or 改进版美林时钟分析:

1. Read <AGENT_MACRO_DRIVEN_ROTATION_ROOT>/SKILL.md.
2. For detailed framework, industry pool, Skill calling parameters, quadrant diagram generation,
   report template, or memory rules, also read
   <AGENT_MACRO_DRIVEN_ROTATION_ROOT>/references/macro-driven-rotation-guide.md.
3. Follow the Plan-and-Execute 6-step workflow in SKILL.md:
   Step 1 — Intent recognition
   Step 2 — Macro phase determination (use macro-monitor skill)
   Step 3 — Industry screening based on macro phase
   Step 4 — Prosperity confirmation (use macro-altdata-nowcast skill)
   Step 5 — Valuation filter (use index-valuation-rotation skill)
   Step 6 — Integrated output (L1 conclusion → L2 evidence table → L3 quadrant diagram)
4. For each sub-skill, read its own SKILL.md before calling any Pandadata API:
   - Use get_macro_detail to confirm all indicator codes; never invent codes.
   - For macro-altdata-nowcast: resolve category codes (EC/MD/EH/AD/HA/OF/RB/RE/ED/EP) first.
   - For index-valuation-rotation: smoke-test one target before expanding the universe.
5. Enforce output rules:
   - Conclusion first, then reasoning chain.
   - Tag every cited value with its data period (e.g., 2026-06 or 2026-07-W3) and source skill.
   - Separate facts (evidence table) from interpretation (reasoning).
   - Generate three charts via `chart_writer.render_all` (or ASCII fallback with degradation label).
   - On user request for L4/L5: prefer `python -m runtime --live` (or `python -m runtime l4`).
   - Never use certain investment advice language (买入/卖出/必涨/稳赚).
6. If a sub-skill fails, degrade gracefully: output what is available and clearly label the gap.
7. Validate / clean with unified CLI:
   python -m runtime validate <report_file>
   python -m runtime clean
8. End every report with the disclaimer:
   "本报告基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。"
9. Pandadata Python package name is panda_data (pip: panda-data). This skill is an analysis agent, not an alpha-* production package.
```
