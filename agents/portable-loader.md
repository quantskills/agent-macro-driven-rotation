# Portable Loader（Hermes / OpenClaw / 无原生 Skill 机制）

将下列说明粘贴到宿主 Prompt，并把 `<REPO_ROOT>` 替换为本仓库绝对路径。

## 加载步骤

1. 将本仓库放入工作区，并确保三个依赖目录可访问：
   - `macro-monitor`
   - `macro-altdata-nowcast`
   - `index-valuation-rotation`
2. 阅读 `<REPO_ROOT>/AGENTS.md`
3. 方法细节可读 `<REPO_ROOT>/references/macro-driven-rotation-guide.md`
4. `pip install -r <REPO_ROOT>/requirements.txt`
5. 复制 `.env.example` → 环境变量（live 时填 `PANDA_DATA_*`；勿写入仓库）
6. 运行：

```bash
cd <REPO_ROOT>
python -m runtime --self-test
# 或
python -m runtime --live --query "现在该关注什么行业"
python -m runtime validate
```

7. 阅读 `reports/runtime_out/runtime_report.md` 与 `l4.html`

## 硬约束（必须注入宿主）

- 先读 `AGENTS.md`，再读依赖 Skill 的 `SKILL.md`
- 按六步工作流：意图识别 → 宏观定相 → 行业初筛 → 景气确认 → 估值过滤 → L1–L5 综合输出
- 依赖失败必须标注缺口，禁止编造数值
- 禁止买入 / 卖出 / 必涨 / 仓位指令
- 输出仅供研究参考，不构成投资建议；不承诺收益
- 未经维护者审核，不得宣称 QuantSkills 官方背书
