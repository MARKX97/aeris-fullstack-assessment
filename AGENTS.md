# AGENTS.md — 仓库工程基线（Harness Baseline）

> 本文件是这个 repo 的「项目宪法」：定义**在这个仓库里怎么干活**。
> 方法论：Harness Engineering —— Spec 定义目标态，Harness 是控制系统，代码只是对 Spec 的实现产物。
> 配套阅读：`BRIEF.md`（题面原文，已 gitignore，不进提交）。

---

## 1. 背景

Aeris Health Full-Stack Developer 一面 take-home 测评。100 分 / 建议 4-6 小时。
技术栈硬性要求：Python / FastAPI / React + TypeScript。交付一个结构化 Git 仓库。

**最高优先级的三件事**：可运行（从 README 一键跑通）、可解释（每个决策本人能讲清楚）、可验证（每个行为有测试或可复现证据）。

## 2. 目录与任务映射

| 目录 | 内容 | 交付形态 | 分值 |
| --- | --- | --- | --- |
| `A/` | Inventory Reservation Ledger（库存预留账本） | 可执行 Python CLI + 测试 + 复杂度分析 | 20 |
| `B/` | Fulfilment Split Optimiser（多仓拆单优化） | 可执行 Python CLI + 测试 + 复杂度分析 | 20 |
| `C/` | Xero Integration Review（书面方案） | `answers.md` | 20 |
| `app/` | Variant PDP（FastAPI + React/TS） | 前后端代码 + 测试 | 40 |
| `README.md` | 提交说明：安装、命令、假设、架构、限制、AI 披露 | 英文 | （Delivery 5 分，扣分项） |

每个任务目录内：`spec.md`（目标态定义）+ `acceptance.md`（可观测验收标准）。**先写这两个，后写代码。**

## 3. 工作流（核心规则）

任何非平凡改动，按此循环执行：

1. **读上下文**：本文件 → 对应目录的 `spec.md` → `acceptance.md`。
2. **补齐 Harness**：spec 或 acceptance 缺失 → 先补，再动手。**没有 spec 不写代码。**
3. **实现前声明**：目标一句话 / 要改的文件 / 明确不得改的文件 / 对应验收标准编号 / 主要风险。
4. **最小实现**：只做满足 spec 的最小改动。禁止顺手重构、禁止范围外清理。
5. **真实验证**：跑最窄的、能证明验收标准的真实验证（执行命令、贴真实输出）。**严禁编造任何运行结果、测试结果或截图。** 无法运行时，如实报告"未验证"及原因。
6. **对照汇报**：结论 / 改动文件及原因 / 验证证据 / 逐条对照验收标准 / 遗留风险。

范围外的想法一律记入 `acceptance.md` 的 "Out of scope / Follow-ups"，不塞进当次实现。

**问题回路（实现或验证中发现 spec 缺口 / 错误 / 新歧义）**：停手 → 先更新 `spec.md`（含决策记录）与 `acceptance.md` → 确认方案 → 再继续写代码。禁止在代码里悄悄修正语义；同一类问题第二次出现时，改的是 harness（规则、验收标准、决策记录），不只是代码。

## 4. 任务分层（用最轻的流程保护任务）

| 层级 | 本仓库示例 | 要求 |
| --- | --- | --- |
| Micro | 跑命令、改错字、调整文案 | 直接做；只有提出结论主张时才验证 |
| Normal | 局部 bug 修复、小改 | 前后各一句范围声明 + 针对性验证 |
| Important | Task A/B 核心逻辑、任一 API 行为、前端状态机 | 先更新 spec + acceptance，再实现 |
| High risk | 幂等、并发防超卖、Task C 的安全与对账论述、提交前检查 | 完整 spec + acceptance + 风险与回滚说明 + 加宽验证 |

拿不准层级时，**向上归类**。

## 5. 约定（Feedforward Guides）

**通用**
- 注释解释"为什么"，不复述语法。
- 依赖只用常规库，且在 README 列出。Task A/B **纯标准库**。
- 数值与金额：Task A/B 用 `int`（上界 1e12，Python 无溢出）；app 的价格用整数分（cents）存储，避免浮点误差，API 层再格式化。

**Python（A/B 与 app 后端）**
- Python 3.11+；全量类型注解；测试用 `pytest`。
- A/B 从 stdin 读、向 stdout 写，单文件可直接 `python3 xxx.py` 运行。

**app 后端**：FastAPI + Pydantic 模型校验；错误响应统一结构；不信任客户端传来的价格与库存。

**app 前端**：React + TypeScript（Vite），`strict` 模式；禁止可避免的 `any`；API / domain / UI 三层分离；可访问性（键盘、焦点、aria-live）是硬性要求，不是加分项。

**文档语言**：提交面文档（`README.md`、代码、注释）用**英文**；内部工作文档（本文件、各 `spec.md` / `acceptance.md`）用**中文**。提交前按 §8 决定内部文档去留。

## 6. 验证命令（Feedback Sensors）

> 实现后启用；当前为计划命令。

```bash
# Task A / B（单元 + 端到端 + 性能冒烟）
python3 -m pytest A -q
python3 -m pytest B -q

# app 后端（契约 + 幂等 + 并发竞争）
python3 -m pytest app/backend -q

# app 前端（变体解析 + 重复点击 + …）
cd app/frontend && npm run test
```

规则：**验收结论必须附上述命令的真实输出**。任何"应该能过"不算验证。

## 7. AI 协作纪律

- 题面允许使用 AI 工具，条件：在 README 披露使用环节 + 本人能解释每一个提交的决策。复面会现场改代码/debug——**不理解的内容不允许出现在仓库里**。
- 每完成一个 Task，在 `README.md` 的 AI assistance disclosure 小节补一条记录（哪个环节、做了什么）。

## 8. 提交前决策点（Submission Gate）

- [ ] spec / acceptance 文档：翻译成英文随仓库提交（展示工程纪律），或移出版本库（加 .gitignore）——二选一，不留中文文档直接提交。
- [ ] `README.md` 六节齐备：Setup / Assumptions / Architecture notes / Known limitations / AI assistance disclosure / Submission checklist。
- [ ] 干净检出测试：`git clone` 到临时目录后按 README 从零跑通全部命令。
- [ ] 无密钥、无真实数据、无个人数据（`git log` 全历史检查，不只是工作区）。
- [ ] 题面红线自查：可运行 / 无密钥 / 无硬编码冒充 / 本人可解释全部代码。
