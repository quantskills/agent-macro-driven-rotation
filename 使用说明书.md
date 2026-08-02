# 宏观驱动行业轮动 Agent — 使用说明书

面向终端用户：在 Cursor / Claude / Codex 等环境里，用自然语言完成「宏观定相 → 行业景气 → 估值过滤 → 轮动参考」。

| 项目 | 说明 |
|------|------|
| Agent 目录 | `agent-macro-driven-rotation` |
| 规范文件 | `SKILL.md`（Agent 行为以它为准） |
| 方法细节 | `references/macro-driven-rotation-guide.md` |
| 设计说明 | `设计文档.md` |
| 本文读者 | 个人投资者、研究员、资产配置相关使用者 |

---

## 1. 它能做什么 / 不能做什么

**能做**

- 判断当前更接近美林时钟的哪一阶段（改进版：增长 + 通胀 + 流动性 + 政策预期差）
- 按阶段给出申万一级受益行业池，再用另类高频景气、估值分位做过滤
- 输出：一句话结论、数据证据表、三张图；按需导出仪表盘 / CSV / Excel
- 用合规研究措辞（「可关注」「景气偏暖」），并带免责声明

**不能做**

- 不是下单系统，不会、也不应给出「买入 / 必涨 / 仓位提到 xx%」等确定性指令
- 不是 `alpha-*` 生产因子包，结果不能直接当生产交易信号入库
- 没有 Pandadata 凭证与三个依赖 Skill 时，只能跑示意 / mock，不能当「今日实时定相」

---

## 2. 使用前准备

### 2.1 需要准备的目录

本 Agent 依赖另外三个 Skill（名称以 Skill 内 `name` 为准）：

```text
agent-macro-driven-rotation          ← 本仓库
macro-monitor                        ← 官方宏观（CPI/GDP/PMI/社融/M2）
macro-altdata-nowcast                ← 另类高频景气 Nowcast
index-valuation-rotation             ← 行业估值分位与动量
```

若本地仓库目录名带 `skill-` 前缀，在宿主里按各平台要求映射到上述名称即可。可选再准备 `pandadata-api`（各 Skill 的 API 契约参考）。

### 2.2 Pandadata 凭证

实时取数需要账号。在系统环境变量中配置（**不要**把密钥写进仓库）：

```text
PANDA_DATA_USERNAME=你的用户名
PANDA_DATA_PASSWORD=你的密码
```

变量名参考仓库内 `.env.example`。Windows PowerShell 示例：

```powershell
$env:PANDA_DATA_USERNAME = "你的用户名"
$env:PANDA_DATA_PASSWORD = "你的密码"
```

### 2.3 Python 依赖（图表 / 导出 / 回测 / 校验）

根目录 `requirements.txt` 已列出常用包（`pandas` / `numpy==2.0.2` / `matplotlib` / `plotly` / `panda-data` / `openpyxl`）。  
研究运行时可选安装 LangGraph（见 `runtime/requirements-optional.txt`；未装则走顺序 pipeline）。

宏观指标代码统一在 `scripts/macro_catalog.py`（回测 / 动画 / L2 对账共用）；改码只改这一处。

建议使用独立虚拟环境，避免本机 base 环境 NumPy 冲突。本仓库推荐解释器（与 `.vscode/settings.json` 一致）：

```text
D:\env\anaconda3\envs\select-stock-pro_v2.5.0\python.exe   # Python 3.12
pip install -r requirements.txt
```

注意：目录名是下划线 `select-stock-pro_v2.5.0`，不是连字符 `select-stock-pro-v2-5-0`。

**runtime 能力边界（诚实降级）**：`python -m runtime.run` 的 live 模式可拉宏观定相；景气 / 估值客户端尚未接线，会明确标注「未接入」而非编造分数。完整三重过滤仍以宿主对话调用三个依赖 Skill 为准。`intent` 会跳过无关步骤（例如只问「美林定相」时不跑景气/估值）。
---

## 3. 在各宿主中启用

### 3.1 Cursor（推荐）

1. 将本目录放到例如：

```text
.cursor/skills/agent-macro-driven-rotation
```

2. 同步放入三个依赖 Skill（路径与 `agents/cursor-rule.mdc` 一致）：

```text
.cursor/skills/macro-monitor
.cursor/skills/macro-altdata-nowcast
.cursor/skills/index-valuation-rotation
```

3. 对话中 `@` 本 Skill，或启用 `agents/cursor-rule.mdc` 作为项目规则。  
4. 直接用自然语言提问（见第 4 节）。

### 3.2 Claude Code / Codex 等

- **支持原生 Skill**：加载本文件夹为 `$agent-macro-driven-rotation`，并同时加载三个依赖。
- **无 Skill 发现**：打开 `agents/portable-loader.md`，把全文粘贴进系统提示，把根路径占位符换成你的本机绝对路径。
- **OpenAI / Actions**：参考 `agents/openai.yaml`（注意注入当前日期）。

---

## 4. 怎么提问（推荐话术）

按意图选用，越明确越好：

| 你想要的 | 可以这样说 |
|----------|------------|
| 完整轮动报告 | 「按改进版美林时钟做一轮完整行业轮动报告」 |
| 行业配置参考 | 「现在该关注什么行业？给出宏观定相和证据表」 |
| 只要宏观阶段 | 「当前宏观环境处于什么阶段？只要定相和四维数据」 |
| 只要景气 | 「电子、医药的另类高频景气怎么样？」 |
| 只要估值 | 「复苏期受益行业的 PE/PB 分位和动量」 |
| 要交互图 | 「请导出行业轮动仪表盘 HTML」 |
| 要底层表 | 「请导出宏观/景气/估值/推荐的 CSV 或 Excel」 |
| 要动态四象限 | 「生成/打开估值–景气动态四象限（animation）」 |

Agent 标准流程（完整报告时）：

```text
意图识别 → macro-monitor 定相 → 行业初筛
       → macro-altdata-nowcast 景气 → index-valuation-rotation 估值
       → L1 结论 + L2 证据表 + L3 三图
```

---

## 5. 合格输出长什么样

一次完整回答通常包含：

1. **L1**：一句话结论 + 3～4 步逻辑链（结论在前）  
2. **L2**：Markdown 证据表——每行有**数值、数据期、来源 Skill/方法**  
3. **L3**：三张图——美林时钟钟面、增长–通胀轨迹、估值–景气四象限（失败时应有 ASCII 并标明「图表降级」）  
4. **免责声明**：仅供研究参考，不构成投资建议  
5. **措辞**：用「可关注 / 景气偏暖 / 估值适中」，不用「买入 / 必涨」

若某依赖失败，报告里应**明确写出降级**（例如「另类景气数据暂不可用」），而不是 silently 编造数字。

**自行质检（推荐）**：把报告存成 `.md` 后执行：

```bash
cd agent-macro-driven-rotation
python scripts/validate_report.py path/to/your_report.md
```

应看到「全部校验通过」。结构样例可参考：`reports/samples/e2e_rotation_sample.md`。

**数值交叉验证（L2，推荐对外引用前做）**：

```bash
# live 报告 vs Pandadata（需凭证）
python scripts/reconcile_report_vs_api.py path/to/your_report.md --live \
  --output reports/reconcile_live.csv

# 或先跑离线演示
python scripts/reconcile_report_vs_api.py reports/samples/e2e_rotation_sample.md \
  --fixture scripts/fixtures/reconcile_macro_sample.json --pmi-prev 50.2
```

详见 `交叉验证方案.md`。结构校验全绿 ≠ 数字正确；L2 对账通过后再引用宏观定相。
---

## 6. 按需附件（L4 / L5）

对话里主动说「要仪表盘 / 要 CSV」时，Agent 应调用脚本；你也可以本机手动跑：

| 需求 | 命令 | 产物 |
|------|------|------|
| L4 仪表盘 | `python scripts/export_dashboard.py --phase 复苏期 --output reports/dashboard.html` | 交互 HTML |
| L5 数据表 | `python scripts/export_data.py`（参数见脚本 `--help`） | CSV / xlsx |
| 动态四象限 | `python scripts/build_animation.py`（需凭证与依赖）后打开 `animation.html` | 期刊风交互页 |

注意：

- 默认导出可能是**示意数据**；生产请传入真实 JSON / 走 live 链路。  
- `backtest_output/nav_curve.html` 是**回测净值图**，不是行业轮动仪表盘。

---

## 7. 可选：本地研究运行时（不替代对话）

用于编排冒烟或离线复现，**不能代替**宿主里按 `SKILL.md` 的正式分析：

```bash
# 示意数据（无需真实 API）
python -m runtime.run --mock --query "现在该买什么行业？" --output-dir reports/runtime_out

# 尝试真实数据（需凭证；失败会降级并标注）
python -m runtime.run --live --query "按改进版美林时钟做一轮完整行业轮动报告"
```

轻量记忆文件：`runtime/memory/store.json`（用户画像 / 调参阈值 / 30 天历史摘要）。记忆**不得**覆盖本次 API 定相，只影响措辞或筛选门槛。

---

## 8. 其他常用脚本

| 目的 | 命令 |
|------|------|
| 校验报告 | `python scripts/validate_report.py <报告.md>` |
| 宏观阶段回测 | `python scripts/backtest.py --start_date 2022-01-01 --end_date 2026-07-25 --output_dir backtest_output` |
| 组件单测 | `python scripts/test_validate_logic.py`；`python scripts/test_backtest_logic.py` |
| 示意三图 | `python _writer.py`（若脚本支持） |

回测默认**禁止**用随机行情冒充实盘；仅结构验证时可加 `--allow-simulate`。  
仓库里已有的 `backtest_output` 若未按新口径重跑，**不要直接采信绩效数字**；以运行日志中「覆盖月数与 macro_phases 一致」为准。

---

## 9. 使用边界与安全习惯

1. 输出一律当**研究参考**，结合自身风控与实时行情复核。  
2. 宏观官方数据常有 1～2 个月滞后；另类数据须视为「及时样本 / Nowcast」。  
3. 看清报告是否标注 **mock / 示意 / 降级**——有标注时不要当成今日 live 结论。  
4. 密钥只放环境变量，勿提交 `.env` 或聊天记录中的密码。  
5. 需要交易级因子时，另按《Alpha 因子开发与生产规则 V2》开目录交付，勿用本会话结果冒充。

---

## 10. 常见问题

**Q：为什么结论和我印象中的「市场共识」不一样？**  
A：定相按规则引擎（PMI/CPI/流动性等），不是舆情投票。可要求 Agent 列出四维原始表自行核对。

**Q：只要文字、不要图可以吗？**  
A：规范要求完整分析带 L3；若环境无法出图，应出现 ASCII 降级说明。可说明「图表失败时用 ASCII」。

**Q：能改估值过滤阈值吗？**  
A：可在对话中说明偏好（如 PE 分位上限），或由研究运行时写入 `tuning_prefs`；只影响筛选门槛，不改 API 原始分位。

**Q：三个依赖 Skill 缺一个会怎样？**  
A：对应环节降级并标注；三个都没有则只应输出框架说明，不应出现具体数字。

**Q：说明书、设计文档、SKILL 冲突听谁的？**  
A：**行为以 `SKILL.md` 为准**；说明书教你怎么用；设计文档讲架构与交付状态。

---

## 11. 五分钟上手清单

- [ ] 四个 Skill 目录已放入宿主可加载路径  
- [ ] 已设置 `PANDA_DATA_USERNAME` / `PANDA_DATA_PASSWORD`（要 live 时）  
- [ ] 在 Cursor 中 `@agent-macro-driven-rotation`（或等价加载）  
- [ ] 发送：「按改进版美林时钟做一轮完整行业轮动报告」  
- [ ] 检查：结论、证据表（含数据期）、三图或降级说明、免责声明  
- [ ] （可选）报告落盘后跑 `validate_report.py`  
- [ ] （可选）要附件时再说：「导出仪表盘和 CSV」

---

> 本说明仅协助使用本 Agent；报告内容仅供研究参考，不构成任何投资建议。
