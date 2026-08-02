---
name: agent-macro-driven-rotation
description: 宏观驱动行业轮动分析。改进版美林时钟定相 + 另类景气 Nowcast + 估值过滤；适用于行业轮动研究参考、宏观定相位、行业配置研究。
---

# 宏观驱动行业轮动 Agent

本文是完整行为与使用说明。QuantSkills Agent 声明与多运行时入口见根目录 [AGENTS.md](AGENTS.md)；仓库主页见 [README.md](README.md)。

> 文件最上方仅保留 Agent 加载所需的两行元数据（`name` / `description`）。组织与许可证等完整元数据见 [AGENTS.md](AGENTS.md) 与 [agents/skill-manifest.yaml](agents/skill-manifest.yaml)。


## 定位边界（必读）

本仓库是 **分析型 Agent Skill**（对话编排 + 图表 + 报告校验），**不是** `alpha-*` 生产因子包。  
若进入交易链路：须另开目录，按 [references/Alpha因子开发与生产规则V2.md](references/Alpha因子开发与生产规则V2.md) 交付，禁止用会话内重算冒充生产结果。

**能做**：改进版美林定相 → 行业初筛 → 另类景气 → 估值过滤 → L1–L5 研究输出（合规措辞）。  
**不能做**：下单指令、「买入/必涨」等确定性建议；无凭证时不得当作今日 live 定相。

**核心能力**：

1. **宏观阶段判定**：官方 CPI/GDP/PMI/社融（`macro-monitor`）→ 衰退/复苏/过热/滞胀。  
2. **行业景气确认**：`macro-altdata-nowcast` 另类高频 Nowcast。  
3. **估值过滤**：`index-valuation-rotation` PE/PB 分位与动量。  
4. **综合输出**：轮动参考 + 四象限图 + 证据表。

## 快速上手

### 仓库结构

```text
agent-macro-driven-rotation/
  AGENTS.md / README.md / README.en.md / LICENSE / SKILL.md
  requirements.txt / .env.example
  templates/l4.html          # L4 模板（非交付物）
  scripts/                   # 取数、定码、图表、校验、回测
  runtime/                   # 统一 CLI + 编排
  references/                # 方法指南、Alpha 边界规则
  agents/                    # 宿主适配与发布清单
  reports/
    runtime_out/             # 运行产物（gitignore）
    backtest/                # 回测产物（gitignore）
    samples/                 # 结构样例（入库）
```


依赖 Skill：`macro-monitor`、`macro-altdata-nowcast`、`index-valuation-rotation`。

### 凭证与环境

```text
PANDA_DATA_USERNAME=...
PANDA_DATA_PASSWORD=...
```

推荐 `skills-env`（Python 3.12，`numpy<2`）：`pip install -r requirements.txt`。  
宏观码：`scripts/macro_catalog.py`；行业代理：`scripts/code_resolver.py`（缓存 `scripts/.cache/`）。

### 统一入口（本机）

```bash
python -m runtime --live --query "现在该关注什么行业"     # 分析+L3/L4/L5+自动校验
python -m runtime --live --all                            # +对账 +重建 L4 历史
python -m runtime --live --backtest --backtest-start 2024-01-01
python -m runtime --self-test
python -m runtime clean
```

| 子命令 | 作用 |
|--------|------|
| （默认） | 全链路 + 自动校验 |
| `validate` / `reconcile` | 结构校验 / L2 对账 |
| `l4 [--rebuild]` | 只写/重建 L4 |
| `backtest` | 输出到 `reports/backtest/` |
| `clean` / `test` | 清理产物 / 组件单测 |

产物：`reports/runtime_out/`（`runtime_report.md`、`l4.html`、`charts/`、`export/`）。  
L4 模板 `templates/l4.html`（轻量壳，无大宗历史内嵌）→ 产物 `reports/runtime_out/l4.html`；完整历史动画加 `--l4-rebuild`。

### 推荐话术（对话）

| 你想要的 | 可以这样说 |
|----------|------------|
| 完整轮动报告 | 「按改进版美林时钟做一轮完整行业轮动报告」 |
| 行业配置参考 | 「现在该关注什么行业？给出宏观定相和证据表」 |
| 只要宏观阶段 | 「当前宏观环境处于什么阶段？只要定相和四维数据」 |
| 只要景气 / 估值 | 「电子、医药的另类高频景气怎么样？」 |
| 要交互图 / 表 | 「请导出 L4 交互页和 CSV」 |

### 五分钟清单

- [ ] 四个 Skill 已放入宿主路径
- [ ] 已设 `PANDA_DATA_*`（要 live 时）
- [ ] `@agent-macro-driven-rotation` 或 `python -m runtime --live …`
- [ ] 检查：结论、证据表、三图/`l4.html`、免责声明

## 改进版美林时钟框架

| 维度 | 数据来源 | 说明 |
|------|---------|------|
| 增长 | GDP 实际同比、制造业 PMI | 扩张/收缩 |
| 通胀 | CPI 同比趋势 | 价格压力 |
| 流动性 | 社融增速、M2 同比 | 信用扩张/收缩 |
| 政策预期差 | PMI 新订单−库存等 | 前瞻信号 |

### 四阶段判定规则（回测与对话须一致）

| 条件 | 主阶段 | 辅助字段 |
|------|--------|----------|
| 扩张 + 低通胀 + 宽松 | 复苏期 | `loose_liquidity=True` |
| 扩张 + 低通胀 + 未宽松 | 复苏期 | `phase_note=扩张低通胀但流动性未宽松` |
| 扩张 + 高通胀 | 过热期 | 流动性写入辅助列 |
| 收缩 + 高通胀 | 滞胀期 | — |
| 收缩 + 低通胀 | 衰退期 | 若已宽松 → `phase_note=衰退末期/政策托底` |

政策预期差写入 `policy_gap`，不单独改主阶段名。

### 四阶段映射（行业概览）

| 宏观阶段 | 增长 | 通胀 | 流动性 | 推荐行业 |
|---------|------|------|--------|---------|
| 复苏期 | 上行 | 低位 | 宽松 | 科技、消费、医药 |
| 过热期 | 高位 | 上行 | 收紧趋势 | 周期、资源、能化、银行 |
| 滞胀期 | 下行 | 高位 | 收紧 | 防御消费、医药、公用事业 |
| 衰退期 | 低位 | 下行 | 宽松预期 | 债券、黄金、现金 |

## 完整工作流（六步）

```text
Step 1 意图识别 → 宏观 / 景气 / 估值 / 完整报告
Step 2 宏观定相（macro-monitor）→ 四维判定阶段
Step 3 行业初筛 → 阶段映射表
Step 4 景气确认（macro-altdata-nowcast）→ 剔除景气下行
Step 5 估值过滤（index-valuation-rotation）→ 分位+动量
Step 6 综合输出 → L1–L5
```

## 三个 Skill 的调用方式与边界

### macro-monitor

1. 先读其 `SKILL.md`；`get_macro_detail` 定码，禁止凭记忆猜码。
2. 引用须含方法名、参数、数据期、单位；说明官方滞后（常 1–2 月）。

### macro-altdata-nowcast

1. `get_macro_detail(category=...)` 定码；遵守 `stat_type`。
2. 标注「另类/及时样本，Nowcast（非官方）」；领先滞后只作观察。
3. 类目：EC/MD/EH/AD/HA/OF/RB/RE/ED/EP。

### index-valuation-rotation

1. 先确认行业指数代码；短窗冒烟再扩展。
2. 标注 PE/PB 分位、窗口、数据日期。

## 宏观阶段到行业映射表（A股申万一级）

| 阶段 | 核心受益行业 | 逻辑 |
|------|------------|------|
| 复苏期 | 电子、医药生物、计算机、食品饮料、社会服务 | 增长复苏 + 低利率 → 成长溢价修复 |
| 过热期 | 有色金属、煤炭、石油石化、钢铁、银行 | 需求旺盛 + 通胀上行 → 资源定价权 |
| 滞胀期 | 农林牧渔、医药生物、公用事业、交通运输 | 抗通胀 + 防御 |
| 衰退期 | 现金/货币基金、黄金（黄金股）、国债 | 避险 + 流动性预期宽松 |

## 输出标准

| 层级 | 内容 | 形式 | 触发 |
|------|------|------|------|
| L1 | 一句话结论 + 逻辑链 | 文本 | 每次必出 |
| L2 | 证据表（数值/数据期/来源） | Markdown | 每次必出 |
| L3 | 钟面 + 增长-通胀轨迹 + 估值-景气 | PNG / ASCII | 每次必出 |
| L4 | 动态四象限 + 本次快照 | `templates/l4.html` → `reports/runtime_out/l4.html` | runtime 自动 / 用户请求 |
| L5 | 宏观/景气/估值/推荐表 | `export/*` | runtime 自动 / 用户请求 |

回测净值图 `reports/backtest/nav_curve.html` 不等于 L4。  
结构样例：`reports/samples/e2e_rotation_sample.md`。

## 核心约束

1. **结论先行**。
2. **数据必须实时**：定相基于本次 API，禁止用记忆覆盖。
3. **时间戳强制**：数值须带数据期与来源。
4. **事实与解读分开**。
5. **不给确定性投资建议**（用「可关注 / 景气偏暖」）。
6. **禁止凭记忆定码**（须 `get_macro_detail`）。
7. **降级**：任一 Skill 失败则标注缺口，继续可做部分；全部失败只输出框架、不编造数值。
8. 有 mock / 降级标注时勿当今日 live 结论；密钥只放环境变量。

## 记忆模块

| 记忆层 | 内容 | 影响数据结果 |
|--------|------|------------|
| 对话缓冲 | 本轮会话 | 否 |
| 用户画像 | 风险偏好等（`runtime/memory/store.json`） | 否（仅措辞） |
| 调参偏好 | 估值阈值等 | 是（门槛，不改原始值） |
| 历史结论 | 30 天过期 | 否 |

系统 Prompt 须注入当前日期；记忆不得覆盖本次实时定相。

## 图表生成（必须执行）

每次分析须生成三图，调用 [scripts/chart_writer.py](scripts/chart_writer.py)；失败则 ASCII 并标注降级。

```python
import sys
sys.path.insert(0, "<AGENT_ROOT>/scripts")
from chart_writer import render_all, ascii_clock, ascii_valuation_chart

charts = render_all(
    current_phase=phase,
    growth_series=growth_series,
    inflation_series=cpi_series,
    industries_data=industries,
    output_dir="./charts",
    data_date="2026-06",
)
```

`industries_data` 字段：`name` / `sentiment`（-1~1）/ `valuation_pct`（0~100）/ `phase_match`（bool）。

- **图1** `render_clock_chart`：四扇区钟面 + 当前阶段高亮
- **图2** `render_quadrant_chart`：增长-通胀 24 月轨迹
- **图3** `render_valuation_sentiment_chart`：估值-景气四象限（右下为推荐区）

## 禁止行为

- 未经 API 验证的数值或指标代码
- 「买入 XX」「仓位提到 XX%」等确定性指令
- 以历史记忆替代本次实时定相
- 数据缺失时编造数值
- Pandadata 以外数据源
- 景气/估值不完整时仍输出完整推荐（应降级）

## 跨 Agent 使用说明

- **声明入口**：根目录 `AGENTS.md`（QuantSkills Agent 声明 / 元数据）。
- **Claude Code / Codex**：加载本文件夹为 `$agent-macro-driven-rotation`，并加载三依赖。
- **Cursor**：`.cursor/skills/agent-macro-driven-rotation` + `agents/cursor-rule.mdc`。
- **Hermes / OpenClaw**：`agents/portable-loader.md`。
- **OpenAI / Actions**：`agents/openai.yaml`。
- **无 Skill 发现**：粘贴 `agents/portable-loader.md` 并替换根路径。


## 常见问题

**Q：结论和「市场共识」不一样？**  
A：定相按规则引擎（PMI/CPI/流动性等），不是舆情投票。

**Q：只要文字不要图？**  
A：规范要求 L3；失败时应有 ASCII 降级说明。

**Q：能改估值过滤阈值吗？**  
A：可在对话说明偏好，或写入 `tuning_prefs`；只影响门槛，不改 API 原始分位。

## 参考资料

- Agent 声明：[AGENTS.md](AGENTS.md)
- 仓库主页：[README.md](README.md) / [README.en.md](README.en.md)
- 方法细节：[references/macro-driven-rotation-guide.md](references/macro-driven-rotation-guide.md)
- Alpha 边界：[references/Alpha因子开发与生产规则V2.md](references/Alpha因子开发与生产规则V2.md)
- 图表工具：[scripts/chart_writer.py](scripts/chart_writer.py)
- 发布元数据：[agents/skill-manifest.yaml](agents/skill-manifest.yaml)


> **免责声明**：本报告基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。
