---
name: agent-macro-driven-rotation
description: >
  宏观驱动行业轮动 Agent，基于改进版美林时钟判定宏观阶段，结合另类高频数据景气 Nowcast
  与指数估值分位，输出行业轮动推荐与估值-景气四象限图。适用于：现在该买什么行业、行业轮动推荐、
  宏观定相位、改进版美林时钟分析、行业配置参考。
tags: [quant, macro, rotation, merrill-lynch-clock, industry, pandadata, agent]
requires: [macro-monitor, macro-altdata-nowcast, index-valuation-rotation]
license: GPL-3.0-only
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: agent-macro-driven-rotation
  project_type: agent
  collection: macro-rotation
quantSkills:
  project_type: agent
  category: analyst
  tags:
  - quant
  - macro
  - rotation
  - merrill-lynch-clock
  - industry
  - pandadata
  - agent
  platforms:
  - claude-code
  - codex
  - hermes
  - openclaw
  - cursor
  status: draft
  validation_level: runnable
  maintainer_type: community
  summary_zh: >
    宏观驱动行业轮动 Agent：基于改进版美林时钟（增长+通胀+流动性+政策预期差四维）判定宏观阶段，
    调用 macro-monitor 读取官方 CPI/GDP/PMI/社融数据，调用 macro-altdata-nowcast
    获取另类高频景气 Nowcast，调用 index-valuation-rotation 获取行业估值分位与动量，
    输出行业轮动推荐与估值-景气四象限图。
  requires:
  - macro-monitor
  - macro-altdata-nowcast
  - index-valuation-rotation
---

# 宏观驱动行业轮动 Agent

## 定位边界（必读）

本仓库是 **分析型 Agent Skill**（对话编排 + 图表 + 报告校验），**不是** `alpha-*` 生产因子包。  
若进入交易链路：须另开目录，按《Alpha 因子开发与生产规则 V2》交付 `factor.py` / 未来函数沙漏检测 / `数据库.parquet`，禁止用会话内重算冒充生产结果。

可选研究运行时：`python -m runtime.run`（最小 LangGraph + 本地 JSON 记忆）；宿主对话仍以本 `SKILL.md` 为主路径。

## 定位与核心功能

本 Agent 是一个基于改进版美林时钟框架的**宏观驱动行业轮动分析系统**，面向投资研究场景，以对话形式提供：

1. **宏观阶段判定**：综合官方 CPI/GDP/PMI/社融数据（来自 `macro-monitor`）判断当前处于衰退/复苏/过热/滞胀哪个阶段。
2. **行业景气确认**：调用 `macro-altdata-nowcast` 获取另类高频景气 Nowcast，验证宏观阶段推断的行业景气是否得到高频数据支撑。
3. **估值过滤**：调用 `index-valuation-rotation` 获取行业指数 PE/PB 历史分位和动量信号，过滤出"高景气+低估值"标的。
4. **综合输出**：生成行业轮动推荐 + 估值-景气四象限图 + 数据证据表。

**适用场景**：
- 用户问"现在该买什么行业？"
- 用户问"宏观环境处于什么阶段？"
- 用户请求"改进版美林时钟分析"
- 用户需要"行业配置参考报告"

## 改进版美林时钟框架

传统美林时钟以"增长（GDP缺口）+ 通胀（CPI趋势）"两个维度划分四个宏观阶段。本 Agent 采用的**改进版框架**在此基础上引入两个本土化维度：

| 维度 | 数据来源 | 说明 |
|------|---------|------|
| 增长 | GDP 实际同比、制造业 PMI | 判断经济扩张/收缩方向 |
| 通胀 | CPI 同比趋势 | 判断价格压力方向 |
| 流动性 | 社融增速、M2 同比 | 中国特色：信用扩张/收缩 |
| 政策预期差 | 央行操作、财政节奏、PMI预期分项 | 前瞻性信号，捕捉阶段转换 |

### 四阶段判定规则（回测与对话须一致）

| 条件 | 主阶段 | 辅助字段 |
|------|--------|----------|
| 扩张 + 低通胀 + 宽松 | 复苏期 | `loose_liquidity=True` |
| 扩张 + 低通胀 + 未宽松 | 复苏期 | `phase_note=扩张低通胀但流动性未宽松` |
| 扩张 + 高通胀 | 过热期 | 流动性写入辅助列，不改主阶段名 |
| 收缩 + 高通胀 | 滞胀期 | — |
| 收缩 + 低通胀 | 衰退期 | 若已宽松 → `phase_note=衰退末期/政策托底` |

政策预期差代理：优先 **PMI 新订单 − 库存**（`get_macro_ci`）；写入 `policy_gap`，不单独改主阶段名。

### 四阶段映射（行业）

| 宏观阶段 | 增长 | 通胀 | 流动性 | 推荐行业 |
|---------|------|------|--------|---------|
| 复苏期 | ↑上行 | ↓低位 | ↑宽松（确认） | 科技、消费、医药 |
| 过热期 | ↑高位 | ↑上行 | →收紧趋势 | 周期、资源、能化、银行 |
| 滞胀期 | ↓下行 | ↑高位 | ↓收紧 | 防御消费、医药、公用事业 |
| 衰退期 | ↓低位 | ↓下行 | →宽松预期 | 债券、黄金、现金等价物 |

## 完整工作流（Plan-and-Execute 六步）

```
Step 1 意图识别
  └─ 判定请求类型：宏观查询 / 行业景气 / 估值分析 / 完整轮动报告

Step 2 宏观定相（调用 macro-monitor）
  ├─ 获取 GDP 实际同比、制造业 PMI（增长维度）
  ├─ 获取 CPI 同比（通胀维度）
  ├─ 获取 社融增速、M2 同比（流动性维度）
  └─ 综合四维判断当前宏观阶段

Step 3 行业初筛
  └─ 根据宏观阶段，从行业池中筛选受益行业（见下方映射表）

Step 4 景气确认（调用 macro-altdata-nowcast）
  ├─ 对初筛行业获取另类高频景气 Nowcast
  ├─ 计算景气分数（同比趋势 + 环比动能）
  └─ 剔除高频数据显示景气下行的行业

Step 5 估值过滤（调用 index-valuation-rotation）
  ├─ 获取景气确认行业的 PE/PB 历史分位
  ├─ 获取行业动量排名（20/60/120日）
  └─ 优选"低估值（分位<60%）+ 正动量"的行业

Step 6 综合输出
  ├─ L1 一句话结论（结论先行）
  ├─ L2 数据证据表（Markdown 表格，每行标注数据期和来源）
  ├─ L3 估值-景气四象限图（横轴：景气 Nowcast 分数；纵轴：估值温度）
  ├─ L4 交互式 HTML 仪表盘（用户主动请求时输出）
  └─ L5 底层数据 Excel/CSV（用户主动请求时输出）
```

## 三个 Skill 的调用方式与边界

### macro-monitor（宏观官方数据）

**调用时机**：Step 2（宏观定相），或用户直接询问宏观数据。

**调用规则**：
1. 先读取 `macro-monitor/SKILL.md` 了解可用方法
2. 使用 `get_macro_detail` 确认指标代码，不得凭记忆猜测代码
3. 每个引用数值必须标注：方法名、参数、数据期、数据单位
4. 官方数据存在发布滞后（通常 1-2 个月），必须说明最新可用期

**禁止事项**：
- 不得凭记忆引用具体数值（如"当前 CPI 约 2%"）
- 不得使用未通过 `get_macro_detail` 确认的指标代码

### macro-altdata-nowcast（另类高频景气）

**调用时机**：Step 4（景气确认），或用户询问行业高频景气。

**调用规则**：
1. 先通过 `get_macro_detail(category=<X>)` 解析指标代码
2. 遵守 `stat_type` 规则，不对已经是同比序列的数据再做差分
3. 标注数据为"另类/及时样本，Nowcast（非官方统计）"
4. 与官方数据的领先滞后关系只作观察，不作绝对断言

**覆盖的另类数据大类**：EC（电商）、MD（医药）、EH（能化）、AD（汽车）、HA（家电）、OF（商超/零售）、RB（招聘）、RE（地产）、ED（电子）、EP（电新）

### index-valuation-rotation（估值与轮动）

**调用时机**：Step 5（估值过滤），或用户询问行业估值/动量。

**调用规则**：
1. 先读取 `index-valuation-rotation/SKILL.md` 确认方法
2. 使用 Pandadata `panda_data` 接口前，先确认行业指数代码
3. 先用单一目标 + 短日期范围做冒烟测试，再扩展行业宇宙
4. 标注：PE/PB 分位、计算窗口、最新数据日期、是否为计算值

## 宏观阶段 → 行业映射表（A股申万一级）

| 阶段 | 核心受益行业 | 逻辑 |
|------|------------|------|
| 复苏期 | 电子、医药生物、计算机、食品饮料、社会服务 | 增长复苏 + 低利率 → 成长溢价修复 |
| 过热期 | 有色金属、煤炭、石油石化、钢铁、银行 | 需求旺盛 + 通胀上行 → 资源定价权 |
| 滞胀期 | 农林牧渔、医药生物、公用事业、交通运输 | 抗通胀 + 防御属性 |
| 衰退期 | 现金/货币基金、黄金（黄金股）、国债 | 避险资产 + 流动性预期宽松 |

## 输出标准

每次分析输出必须包含以下层次（L1–L3 必出，L4–L5 按用户请求调用脚本生成）：

| 层级 | 内容 | 形式 | 触发条件 |
|------|------|------|---------|
| L1 结论 | 一句话结论 + 逻辑链（3-4步） | 文本 | 每次必出 |
| L2 证据表 | 关键数据校验表（指标/数值/数据期/来源） | Markdown 表格 | 每次必出 |
| L3 四象限图 | 钟面 + 增长-通胀轨迹 + 估值-景气图 | Base64 PNG / ASCII备用 | 每次必出 |
| L4 交互HTML | 行业轮动仪表盘 / 动态四象限 | `export_dashboard.py`；或打开 `animation.html`（数据由 `build_animation.py` **内嵌**进页面，打开即用） | 用户请求时 |
| L5 数据文件 | 宏观/景气/估值/推荐底层表 | `python scripts/export_data.py` → `.csv` / `.xlsx` | 用户请求时生成 |

说明：回测净值 HTML（`backtest_output/nav_curve.html`）是回测产物，不等于 L4。`animation.html` 为估值–景气动态四象限的期刊风格交互图。

## 核心约束

1. **结论先行**：每次输出先给结论，后给逻辑链和数据。
2. **数据必须实时**：宏观阶段判定必须基于本次调用的最新 API 数据，禁止依赖记忆中的历史结论。
3. **时间戳强制**：每个引用的数值必须标注数据期（如 `2026-06` 或 `2026-07-W3`）和来源 Skill。
4. **事实与解读分开**：数据校验表只写事实；逻辑链注明哪部分是推断。
5. **不给确定性投资建议**：输出用"景气偏强""估值适中""可关注"等措辞，不使用"买入""必涨"等确定性表述。
6. **Pandadata 禁止凭记忆**：所有指标代码必须通过 `get_macro_detail` 确认。
7. **降级策略**：
   - `macro-monitor` 失败 → 输出景气和估值分析，标注"宏观定相数据缺失，已跳过宏观阶段判定"
   - `macro-altdata-nowcast` 失败 → 输出宏观阶段 + 估值分析，标注"另类景气数据暂不可用"
   - `index-valuation-rotation` 失败 → 输出宏观阶段 + 景气分析，标注"估值数据暂不可用"
   - 全部失败 → 仅输出分析框架说明，不输出任何具体数值

## 记忆模块

本 Agent 使用分层记忆，严格隔离"交互偏好"与"量化数据"：

| 记忆层 | 内容 | 存储 | 影响数据结果 |
|--------|------|------|------------|
| 对话缓冲 | 本轮会话历史 | 宿主上下文 | 否 |
| 用户画像 | 风险偏好、关注行业 | `runtime/memory/store.json` + 宿主 | 否（仅影响措辞） |
| 调参偏好 | 估值阈值、回撤容忍度 | 同上 | 是（影响筛选门槛，不改变原始值） |
| 历史结论 | 过往分析结论（30天自动过期） | 同上 | 否（仅供参考） |

**时间戳强制规则**：系统 Prompt 每次注入当前日期，禁止以历史偏好覆盖本次实时数据调用的结论。  
Redis / 向量库为远期可选，当前未作为交付依赖。

## 图表生成（必须执行）

**每次分析输出必须生成三张图表**，通过调用 [`_writer.py`](_writer.py) 中的工具函数实现。图表以 Base64 PNG 内嵌在回复中展示；`_writer.py` 不可用时降级为 ASCII 图表。

### 调用方式

```python
import sys
sys.path.insert(0, "<AGENT_ROOT>")   # agent-macro-driven-rotation 目录
from _writer import render_all, ascii_clock, ascii_valuation_chart

# 一次生成全部三张图
charts = render_all(
    current_phase=phase,           # str: "复苏期" / "过热期" / "滞胀期" / "衰退期"
    growth_series=growth_series,   # pd.Series, index=datetime, GDP同比或PMI
    inflation_series=cpi_series,   # pd.Series, index=datetime, CPI同比(%)
    industries_data=industries,    # list of dict, 见下方结构
    output_dir="./charts",
    data_date="2026-06",           # 当前数据期
)
# charts["clock"]    → (base64_png, file_path)  图1：美林时钟钟面图
# charts["quadrant"] → (base64_png, file_path)  图2：增长-通胀轨迹图
# charts["valuation"]→ (base64_png, file_path)  图3：估值-景气四象限图
```

**`industries_data` 每条记录结构**：

```python
{
    "name":          "电子",   # 行业名称
    "sentiment":     0.72,     # 景气分数 -1.0（冷）~ +1.0（热），来自 macro-altdata-nowcast
    "valuation_pct": 38.0,     # PE/PB 历史分位 0~100%，来自 index-valuation-rotation
    "phase_match":   True,     # 是否为当前宏观阶段推荐行业（橙色高亮）
}
```

**降级规则**：`render_all` 内部已实现异常捕获，任何图表渲染失败返回 `(None, None)`，此时调用 `ascii_clock(phase)` 和 `ascii_valuation_chart(industries_data)` 输出 ASCII 降级版，并在回复中标注 `[图表降级：matplotlib 不可用]`。

### 图 1：美林时钟钟面图（`render_clock_chart`）

- 圆形四扇区，顺时针：衰退（蓝）→ 复苏（绿）→ 过热（红）→ 滞胀（橙）
- 当前阶段扇区亮色填充，其余淡色；圆心标注当前阶段名
- 每个扇区内列出推荐行业（最多 3 个）

### 图 2：增长-通胀散点轨迹图（`render_quadrant_chart`）

- 横轴：GDP 实际同比 / PMI；纵轴：CPI 同比（%）
- 拉取过去 24 个月数据，绘制经济轨迹线（颜色从浅到深表示时间推进）
- 橙色大圆点标注"当前"，灰色标注"6M前"和"1Y前"

### 图 3（L3 核心）：估值-景气四象限图（`render_valuation_sentiment_chart`）

- 横轴：景气分数（-1 冷 ~ +1 热）；纵轴：估值分位（0% 低估 ~ 100% 高估）
- 右下象限（高景气+低估值）= **推荐区**（浅绿背景）；左上 = 规避区（浅红背景）
- 当前宏观阶段受益行业用橙色实心散点高亮；其余行业灰色空心散点
- 推荐区行业标注 ★ 号

## 禁止行为

- ❌ 不得引用未经 Pandadata API 验证的数据值或指标代码
- ❌ 不得给出"买入 XX 行业""仓位提升至 XX%"等确定性操作指令
- ❌ 不得以历史记忆中的宏观判断替代本次实时 API 调用结果
- ❌ 不得在数据缺失时编造数据或推断具体数值
- ❌ 不得引用 Pandadata 以外的数据源
- ❌ 不得在景气/估值数据不完整时输出推荐行业（降级输出框架说明）

## 跨 Agent 使用说明

- **Claude Code / Codex**：可直接加载本文件夹作为名为 `$agent-macro-driven-rotation` 的 skill，同时加载 `macro-monitor`、`macro-altdata-nowcast`、`index-valuation-rotation` 三个依赖 skill。
- **Cursor**：使用 `agents/cursor-rule.mdc` 作为 project rule adapter，将本文件夹置于 `.cursor/skills/agent-macro-driven-rotation`。
- **OpenAI / GPT Actions**：使用 `agents/openai.yaml` 中的 instructions 和 function definitions。
- **无原生 Skill 发现能力的 Agent**：使用 `agents/portable-loader.md` 中的完整粘贴版提示词。

## 参考资料

详细分析框架与数据校验规范见：[`references/macro-driven-rotation-guide.md`](references/macro-driven-rotation-guide.md)

图表生成工具见：[`_writer.py`](_writer.py)

---

> **免责声明**：本报告基于公开数据与规则化分析生成，仅供研究参考，不构成任何投资建议。