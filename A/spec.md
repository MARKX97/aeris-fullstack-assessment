# Task A Spec — Inventory Reservation Ledger（库存预留账本）

> 状态：已实现并验证（2026-10-17，17 项测试全过；证据见 `acceptance.md` §4）。变更需同步更新 `acceptance.md`。
> 依据：`BRIEF.md` §2。本 spec 把题面转成可执行契约，并显式列出所有需要自行裁决的歧义。
> 本次变更：补齐实现前发现的 4 个 spec 缺口，不改既有语义。

---

## 1. 问题陈述

为**单个 SKU** 实现一个确定性（deterministic，同输入必同输出）的命令行批处理器：stdin 读入初始库存与命令流，维护在手库存与按订单的预留量，stdout 逐条输出裁决结果。核心难点：`event_id` 幂等、严格输入校验、O(N) 性能。

## 2. Non-goals（明确不做）

- 不做多 SKU、不做持久化（进程结束即丢）、不做并发（单线程）。
- 不做交互式 REPL：一次性批处理 stdin。
- 不做错误恢复重试：每行独立裁决，坏行不中断后续处理。
- 不做业务扩展（如部分预留、预留过期）。

## 3. 领域模型与状态

| 变量 | 类型 | 含义 |
| --- | --- | --- |
| `on_hand` | `int` | 在手库存（初始为 S） |
| `reserved: dict[order_id -> qty]` | `dict[str, int]` | 各订单当前未结预留量 |
| `processed: set[event_id]` | `set[str]` | 已处理过的事件 ID（含被 REJECT 的） |

派生量：`available = on_hand - sum(reserved.values())`；`total_reserved = sum(reserved.values())`。

**不变量（实现与测试都要守护）**

- INV1：`reserved[o] ≥ 0` 恒成立；值为 0 的键可清理，清理不改变语义。
- INV2：`sum(reserved) ≤ on_hand` 恒成立（不超卖）。
- INV3：`processed` 只增不减。
- INV4：DUPLICATE 裁决不改变 `on_hand` / `reserved` 的任何值。
- INV5：SHIP 成功时 `on_hand` 与该订单预留量**同减同量**。
- INV6：任何 REJECTED / DUPLICATE 命令不留下部分生效的变更（原子性）。

## 4. 命令契约

| 命令 | 语法 | 成功条件 | 成功效果 |
| --- | --- | --- | --- |
| RESERVE | `RESERVE event_id order_id qty` | `available ≥ qty` | `reserved[order_id] += qty` |
| RELEASE | `RELEASE event_id order_id qty` | `reserved[order_id] ≥ qty` | `reserved[order_id] -= qty` |
| SHIP | `SHIP event_id order_id qty` | `reserved[order_id] ≥ qty` | `on_hand -= qty`；`reserved[order_id] -= qty` |
| RESTOCK | `RESTOCK event_id qty`（见假设 A1） | `qty ≥ 1` | `on_hand += qty` |

通用校验分两层（决定是否记入幂等集合，与假设 A4 联动）：

**语法层（syntactic）**——任一失败 → REJECTED，**不记入 processed**：
- S1：命令名为四个之一。
- S2：token 数正确。
- S3：`event_id` / `order_id` 为非空 ASCII token（无内嵌空白）。
- S4：`qty` 匹配 `^\d+$`（纯数字字符串；`-1`、`x`、`3.0`、`+3` 均属语法失败）。

**语义层（semantic）**——仅在语法层通过后评估；失败 → REJECTED，**记入 processed**：
- M1：`qty ≥ 1`（`0` 属语义失败，非语法失败）。
- M2：上表中该命令的成功条件。

**幂等裁决（题面规则的形式化）**

- R1：`event_id ∈ processed` → 输出 DUPLICATE，不做任何校验，状态不变（即使本次参数不同、甚至本次参数非法）。
- R2：语法层通过 → 执行语义层；无论 OK 或 REJECTED，**将 `event_id` 记入 processed**。
- R3：语法层失败 → REJECTED，不记入 processed（无法可靠提取事件标识，见假设 A4）。
- R4：一个事件先 REJECTED 后重放 → DUPLICATE（R2 的推论，题面明文要求）。

## 5. 输出契约

1. 每条命令一行：`<STATUS> <on_hand> <total_reserved>`，STATUS ∈ {OK, REJECTED, DUPLICATE}。
2. 全部命令后：`OPEN <count>` 一行，随后每个未结预留一行 `<order_id> <reserved_qty>`，按 `order_id` **字符串升序**（见假设 A2）。
3. 行尾统一 `\n`，无尾随空格。空输入流（N=0）时仅输出 `OPEN 0`。

## 6. 决策记录（须写入 README Assumptions）

> 级别：**[强]** 文档强制｜**[部]** 部分确定｜**[解]** 解释性裁定。行号指 BRIEF.md。
> 本表不可删：题面将 assumptions documented 列为交付要求与 Delivery 评分点，复面抽"解释一个设计决策"。

| ID | 级别 | 决策 | 文档依据 |
| --- | --- | --- | --- |
| A1 | 强 | `RESTOCK event_id qty`（3 token） | 示例 `RESTOCK e5 3`→`OK 11 0`（L145）；按 L103 的 4-token 语法解析，官方示例输出不成立 |
| A2 | 部 | OPEN 段 header-first：`OPEN <n>` 后接 `<order_id> <qty>` 行 | `OPEN 0`（L145）仅证明存在 count 行；count 行与明细行的顺序无样本可裁决 |
| A3 | 解 | 坏行 REJECTED 后继续处理 | L108 仅要求"无部分状态变更"，未要求停机 |
| A4 | 解 | 语法层通过即记入幂等集合（`qty=0` 记入；`-1`/`x` 不记入） | L108 与 L123 的交集行为未定义 |
| A5 | 解 | `order_id` 按 byte-wise 字符串序 | L128 "ordered by `order_id`" 未定义排序规则 |
| A6 | 强 | "quantities" 仅指命令 qty；S=0 合法 | 约束分列 `0 <= S`（L135）与 `1 <= qty`（L136）；S 全文称 "initial stock" |
| A7 | 解 | header 行只信任 `N`：恰好读 N 条命令，多余行忽略、不足则止于 EOF；header 非法（非两 token / S 或 N 非纯数字）→ stderr 一行错误 + exit 2，stdout 无输出 | 题面未定义 N 与实际行数的错配行为；N 是权威契约 |
| A8 | 解 | 完全空输入流（0 字节）→ 仅输出 `OPEN 0`，exit 0 | 题面只定义了 N≥1；空流是最小健全行为 |
| A9 | 解 | OPEN 段排序不可避免 O(U_o·log U_o)；性能目标勘误为 **期望 O(N + U_o·log U_o)**，E8b 的 <2s 门槛不变 | 比较排序下界；U_o ≤ N，实际影响小 |
| A10 | 解 | R1 的"不做任何校验"指跳过 M 层；S 层失败（R3）优先于幂等查询（REJECTED 不查 processed） | 语法坏行无法可靠提取 event_id（A4 同理）；两层校验已在 §4 分层 |

## 7. 验收示例（→ 全量展开在 `acceptance.md`，此处列索引）

- E1：题面官方示例（逐字节对齐）。
- E2：预留→SHIP→清零全链路。
- E3：RELEASE / SHIP 超量 → REJECTED。
- E4：被 REJECT 的事件重放 → DUPLICATE（题面规则）。
- E5：同 event_id 换 payload 重放 → DUPLICATE 且状态不变。
- E6：非法 qty（0 / 负数 / 非数字）与未知命令。
- E7：多订单未结预留的排序输出。
- E8：边界数值 S=1e12、qty=1e12；性能冒烟 N=200,000。

## 8. 性能目标

- 时间：期望 O(N + U_o·log U_o)（U_o = 未结订单数 ≤ N；每条命令 O(1) 摊销，OPEN 段排序 O(U_o·log U_o)，见 A9）。
- 空间：O(U_o + U_e)，U_o/U_e 为唯一 order_id / event_id 数。
- I/O 用 `sys.stdin.buffer` / 批量 write，避免逐行 flush。
- 验收门槛：N=200,000 条随机合法命令在本机 < 2s（纯 Python）。

## 9. 测试计划（Feedback Sensors）

1. **单元**：每条命令的成功/失败/边界；不变量 INV1–INV6 在随机命令序列上抽样断言。
2. **端到端**：子进程跑 CLI，stdin 喂 fixture，stdout 与期望逐字节比对（含 E1 官方示例）。
3. **重放（replay）**：整段命令流重放两遍，第二遍全 DUPLICATE、终态不变。
4. **性能冒烟**：标记 `@pytest.mark.slow`，CI/本地默认跑，超时 2s 判失败。

## 10. 交付物对照（题面要求 → 本仓库）

| 题面要求 | 落点 |
| --- | --- |
| executable Python program | `A/main.py`（单文件，纯标准库） |
| edge-case and replay tests | `A/test_main.py`（含 §9） |
| short complexity analysis | `A/README.md` §复杂度（英文） |
