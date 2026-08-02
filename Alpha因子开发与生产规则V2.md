# Alpha 因子开发与生产规则

## 1. 定位

Alpha 因子不是只交付开发代码，也不是只交付结果文件。一个合格 Alpha 必须同时完成两件事：

1. 开发侧：把因子逻辑做出来，能计算、能验证、能回测、能复现。
2. 生产侧：把已计算好的因子结果定时落地为 `数据库.parquet`，让交易 agent 直接读取，不重复拉数和重算。

Alpha 因子必须通过 PandaAI data 数据拉取库或项目指定数据源实现。不得使用来源不明、字段不稳定、个人临时整理的数据文件作为正式输入；如不确定应该使用哪个数据源、字段口径或权限配置，必须咨询项目工作人员后再开发。

完整链路：

```text
因子需求 -> 开发 skill -> 因子计算 -> 验证回测 -> 生产定时计算 -> 数据库.parquet -> 交易 agent 读取
```

## 2. 适用范围

本规则适用于：

| 类型 | 示例 |
|---|---|
| 股票 Alpha | 龙虎榜资金、首板低吸、连板接力、板块轮动、涨停炸板回封 |
| 期货 Alpha | 会员持仓、席位分歧、主力席位一致性、持仓价格背离 |

## 3. Alpha 最终交付物

每个 Alpha 因子最终必须同时具备开发产物和生产产物。

```text
alpha-{编号}/
├── 开发产物/
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── factor.py
│   │   ├── validate.py
│   │   └── backtest.py
│   └── references/
│       └── data_guide.md
└── 生产产物/
    ├── SKILL.md
    └── 数据库.parquet
```

说明：

- 开发产物负责说明和实现“这个因子怎么算”。
- 生产产物负责说明和提供“算好的因子结果怎么给 agent 读”。
- 两者必须同源：生产产物必须来自已通过开发验收的因子逻辑。

## 4. Alpha 开发产物要求

开发目录建议使用 Claude Code 标准 skill 结构：

```text
.claude/skills/alpha-{编号}/
├── SKILL.md
├── skill.json
├── scripts/
│   ├── factor.py
│   ├── validate.py
│   └── backtest.py
└── references/
    └── data_guide.md
```

必须文件：

| 文件 | 要求 |
|---|---|
| `SKILL.md` | 描述因子逻辑、适用场景、输入、输出、依赖和运行方式 |
| `factor.py` | 因子计算主脚本，必须能独立运行 |
| `validate.py` | 验证脚本，必须包含未来函数、过拟合、样本外检查 |
| `backtest.py` | 回测脚本，输出 IC、IR、分层收益、回撤、换手等指标 |
| `data_guide.md` | 数据源、字段、频率、接口限制、数据清洗口径；必须说明使用 PandaAI data 或指定数据源的实现方式 |

## 5. Alpha 开发版 SKILL.md 模板

````markdown
---
name: alpha-{编号}
description: 当需要开发、计算、验证{因子名称}因子时，使用此 skill。支持数据获取、因子计算、沙漏检测、回测评估和信号输出。
tags: [quant, alpha, development, {stock/future}]
---

# {因子名称} Alpha

## 适用场景
- 当用户需要计算{因子名称}因子时
- 当用户需要验证该因子是否有效时
- 当用户需要生成候选交易信号时

## 因子逻辑
- 核心假设：
- 计算公式：
- 排序方向：
- 适用市场：

## 输入数据
因子计算必须使用 PandaAI data 数据拉取库或项目指定数据源获取数据；如数据源、字段含义或权限配置不明确，先咨询项目工作人员。

| 字段 | 说明 | 来源 |
|---|---|---|
| trade_date | 交易日期 | 行情/交易日历 |
| ts_code / symbol | 股票代码或期货合约 | 行情源 |

## 输出结果
| 字段 | 说明 |
|---|---|
| factor_value | 因子原始值 |
| score | 标准化评分 |
| signal | 交易信号 |

## 使用方式
```bash
python scripts/factor.py
python scripts/validate.py
python scripts/backtest.py
```

## 验收要求
- 不允许未来函数
- 必须有样本外验证
- 必须有回测指标
- 必须使用 PandaAI data 数据拉取库或项目指定数据源实现
- 不通过验证不得进入生产
````

## 6. Alpha 开发验收标准

Alpha 必须通过三层沙漏检测：

| 层级 | 检测内容 | 失败处理 |
|---|---|---|
| 第一层 | 未来函数：是否使用未来行情、未来公告、未来财务、不可得数据 | 直接退回重写 |
| 第二层 | 过拟合：训练集好、测试集明显衰减 | 简化因子，减少参数 |
| 第三层 | 样本外：跨年份、跨行情环境、跨品种验证 | 修改逻辑或降低评级 |

必须输出的回测指标：

| 指标 | 必须 |
|---|---:|
| IC / Rank IC | 是 |
| ICIR | 是 |
| 分层收益 | 是 |
| 多空收益 | 推荐 |
| 最大回撤 | 是 |
| 换手率 | 是 |
| 样本外表现 | 是 |
| 信号样例 | 是 |

数据实现要求：

- 因子输入必须来自 PandaAI data 数据拉取库或项目明确指定的数据源接口。
- `factor.py` 不得依赖个人本地临时文件、手工复制表格或来源不明的数据。
- `validate.py` 和 `backtest.py` 必须使用与 `factor.py` 一致的数据口径。
- 数据字段、复权方式、交易日历、合约换月、停牌处理等口径不明确时，必须咨询项目工作人员。

## 7. Alpha 生产产物要求

Alpha 进入生产后，交易 agent 不应临时拉取原始数据并重新计算因子。

生产产物必须包含：

```text
SKILL.md
数据库.parquet
```

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 告诉交易 agent 这个因子结果什么时候用、文件在哪里、字段怎么读、信号怎么解释 |
| `数据库.parquet` | 保存已经统一计算好的因子结果，agent 直接读取 |

## 8. Alpha 生产版 SKILL.md 模板

````markdown
---
name: alpha-{编号}-production
description: 当需要读取{因子名称}的生产计算结果时，使用此 skill。该 skill 只读取已生成的 Parquet 结果，不在调用时重新计算因子。
tags: [quant, alpha, production, {stock/future}]
---

# {因子名称}生产结果

## 适用场景
- 当用户需要查询{因子名称}最新结果时
- 当交易 agent 需要使用该因子辅助交易判断时

## 结果文件
- 文件路径：`数据库.parquet`
- 数据格式：Parquet
- 更新频率：每日收盘后 / 分钟级 / 其他
- 生成方式：生产任务定时计算

## 主键
- `trade_date`
- `factor_id`
- `ts_code` 或 `symbol`

## 字段说明
| 字段 | 类型 | 说明 |
|---|---|---|
| trade_date | date/string | 交易日期 |
| asset_type | string | stock / future |
| ts_code | string | 股票代码，股票因子使用 |
| symbol | string | 期货合约，期货因子使用 |
| factor_id | string | 因子编号 |
| factor_name | string | 因子名称 |
| factor_value | float | 因子原始值 |
| score | float | 标准化评分，建议 0-100 |
| rank | int | 横截面排名 |
| signal | string/int | buy / sell / hold 或标准数值信号 |
| confidence | float | 置信度 |
| data_version | string | 数据版本 |
| update_time | datetime/string | 结果生成时间 |

## 读取规则
交易 agent 读取 `数据库.parquet`，优先使用最新有效交易日结果。

## 禁止行为
- 不允许在 agent 调用时重新拉取原始行情。
- 不允许在 agent 调用时重新计算因子。
- 不允许手工修改 Parquet 结果。
````

## 9. Alpha 结果 Parquet 字段标准

| 字段 | 必须 | 说明 |
|---|---:|---|
| `trade_date` | 是 | 交易日期 |
| `asset_type` | 是 | `stock` / `future` |
| `ts_code` | 股票必须 | 股票代码 |
| `symbol` | 期货必须 | 期货合约 |
| `factor_id` | 是 | 因子编号，例如 `A1`、`F1` |
| `factor_name` | 是 | 因子名称 |
| `factor_value` | 是 | 因子原始值 |
| `score` | 是 | 标准化评分 |
| `rank` | 否 | 横截面排名 |
| `signal` | 是 | 交易信号 |
| `confidence` | 否 | 置信度 |
| `data_version` | 是 | 数据版本 |
| `update_time` | 是 | 结果生成时间 |

## 10. Alpha 生产数据质量要求

生成 `数据库.parquet` 前必须检查：

| 检查项 | 要求 |
|---|---|
| 主键唯一 | 同一交易日、同一标的、同一因子不得重复 |
| 字段完整 | 必须字段不能为空 |
| 日期正确 | 必须是有效交易日 |
| 分数范围 | `score` 必须在约定范围内 |
| 信号合法 | `signal` 必须使用标准枚举 |
| 缺失处理 | 停牌、无数据、接口失败必须有处理口径 |
| 版本记录 | 每次生成必须写入 `data_version` |

## 11. Alpha 生产读取规则

交易 agent 使用 Alpha 生产 skill 时：

1. 先读取生产版 `SKILL.md`。
2. 根据 `SKILL.md` 找到 `数据库.parquet`。
3. 按 `trade_date`、`ts_code` / `symbol`、`factor_id` 查询结果。
4. 默认使用最新有效交易日结果。
5. 若最新结果不存在，可回退最近有效交易日，但必须说明数据日期。
6. 不允许调用开发脚本临时重算。

## 12. Alpha 不合格情况

出现以下任一情况，Alpha 不得进入生产：

- 开发版 `SKILL.md` 缺失
- `factor.py` 不能运行
- 未通过未来函数检测
- 未提供回测结果
- 生产版 `SKILL.md` 未说明 Parquet 路径
- `数据库.parquet` 不能读取
- 生产结果字段缺失
- agent 必须重新计算才能得到结果
- 生产结果不是来自已验收开发逻辑
- 因子计算未使用 PandaAI data 数据拉取库或项目指定数据源
- 数据源、字段口径不明确且未咨询项目工作人员
