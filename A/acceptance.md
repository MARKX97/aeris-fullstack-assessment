# Task A Acceptance — 可观测验收标准

> 状态：Draft v1。每条标准必须是**可观测的 pass/fail**，禁止"工作正常"这类表述。
> 验收汇报格式：命令 + 真实输出 + 对应标准编号。证据缺失即视为未通过。

---

## 1. 端到端 fixtures（stdout 逐字节比对）

### E1 — 官方示例（最高优先级）

```
输入                          期望输出
10 6                          OK 10 4
RESERVE e1 o100 4             REJECTED 10 4
RESERVE e2 o200 7             OK 8 2
SHIP e3 o100 2                OK 8 0
RELEASE e4 o100 2             OK 11 0
RESTOCK e5 3                  DUPLICATE 11 0
RESERVE e2 o999 1             OPEN 0
```

**通过标准**：`python3 A/main.py < fixture` 的 stdout 与期望**完全一致**（含换行）。

### E2 — 全链路清零

| # | 输入 | 期望 |
| - | --- | --- |
| E2a | `5 3`<br>`RESERVE e1 o1 5`<br>`SHIP e2 o1 5`<br>`RESTOCK e3 3` | `OK 5 5`<br>`OK 0 0`<br>`OK 3 0`<br>`OPEN 0` |
| E2b | `5 3`<br>`RESERVE e1 o1 5`<br>`RELEASE e2 o1 3`<br>`SHIP e3 o1 2` | `OK 5 5`<br>`OK 5 2`<br>`OK 3 0`<br>`OPEN 0` |

### E3 — 超量拒绝（REJECTED 且状态不变）

| # | 输入 | 期望 |
| - | --- | --- |
| E3a | `3 3`<br>`RESERVE e1 o1 2`<br>`RELEASE e2 o1 3`<br>`SHIP e3 o1 1` | `OK 3 2`<br>`REJECTED 3 2`<br>`OK 2 1`<br>`OPEN 1`<br>`o1 1` |
| E3b | `3 2`<br>`RESERVE e1 o1 4`<br>`SHIP e2 o1 1` | `REJECTED 3 0`<br>`REJECTED 3 0`<br>`OPEN 0`（SHIP 对无预留订单 → 拒） |

### E4 — 被拒事件重放 → DUPLICATE（题面明文规则）

| # | 输入 | 期望 |
| - | --- | --- |
| E4a | `3 2`<br>`RESERVE e1 o1 99`<br>`RESERVE e1 o1 1` | `REJECTED 3 0`<br>`DUPLICATE 3 0`<br>`OPEN 0` |

### E5 — 同 key 换 payload 重放 → DUPLICATE，状态不变

| # | 输入 | 期望 |
| - | --- | --- |
| E5a | `10 2`<br>`RESERVE e1 o1 2`<br>`SHIP e1 o1 2` | `OK 10 2`<br>`DUPLICATE 10 2`<br>`OPEN 1`<br>`o1 2` |

### E6 — 非法输入（REJECTED，流程不中断；部分不记入 processed，见假设 A4）

| # | 输入 | 期望 | 验证点 |
| - | --- | --- | --- |
| E6a | `5 3`<br>`RESERVE e1 o1 0`<br>`RESERVE e2 o1 2`<br>`RESTOCK e3 -1` | `REJECTED 5 0`<br>`OK 5 2`<br>`REJECTED 5 2`<br>`OPEN 1`<br>`o1 2` | qty=0 → 拒（R2 路径，e1 已标记） |
| E6b | `5 3`<br>`RESERVE e1 o1 x`<br>`RESERVE e1 o1 2`<br>`FROBNICATE e9 o1 1` | `REJECTED 5 0`<br>`OK 5 2`<br>`REJECTED 5 2`<br>`OPEN 1`<br>`o1 2` | qty 非数字 → 结构非法不标记（A4），e1 首次真实执行成功；未知命令 → 拒 |

### E7 — 未结预留排序输出

| # | 输入 | 期望 |
| - | --- | --- |
| E7a | `10 4`<br>`RESERVE e1 oB 2`<br>`RESERVE e2 oA 3`<br>`RESERVE e3 oC 1`<br>`SHIP e4 oB 2` | `OK 10 2`<br>`OK 10 5`<br>`OK 10 6`<br>`OK 8 4`<br>`OPEN 2`<br>`oA 3`<br>`oC 1` |

（`oA < oB < oC` 字符串序；oB 已 SHIP 清零不出现。）

### E8 — 边界与性能

| # | 输入 | 期望 |
| - | --- | --- |
| E8a | `1000000000000 2`<br>`RESTOCK e1 1000000000000`<br>`RESERVE e2 o1 1000000000000` | `OK 2000000000000 0`<br>`OK 2000000000000 1000000000000`<br>`OPEN 1`<br>`o1 1000000000000` |
| E8b | N=200,000 条随机合法命令（脚本生成，seed 固定） | 运行 < 2s（`time` 实测记录）；任意时刻 INV2 成立（测试内断言） |

## 2. 不变量与随机性质测试

| # | 标准 |
| - | --- |
| A-INV | 10,000 条随机命令流（含非法行）后：INV1–INV6 全部成立（测试内建模影子状态） |
| A-REPLAY | 任意 fixture 重放第二遍：每行均为 DUPLICATE，`on_hand`/`reserved` 终态与第一遍终态一致 |

## 3. 性能验收

| # | 标准 |
| - | --- |
| A-PERF | `python3 A/main.py < A/tests/fixtures/perf_200k.txt`，`time` 实测 < 2s（记录真实耗时于下表） |

## 4. 证据记录（实现后填写）

| 标准 | 命令 | 实际输出/耗时 | 结果 |
| --- | --- | --- | --- |
| E1–E8b | `python3 -m pytest A -q` | （粘贴真实输出） | ☐ |
| A-INV / A-REPLAY | 同上 | | ☐ |
| A-PERF | `time python3 A/main.py < .../perf_200k.txt` | | ☐ |

## 5. Out of scope / Follow-ups

- 多 SKU 扩展、预留 TTL、事件溯源持久化 —— 均不做。
- 性能若用 PyPy / numpy 优化 —— 不做（纯标准库是题面要求）。

## 6. 与题面评分点的映射

| 题面评分点 | 由哪些标准证明 |
| --- | --- |
| Correct state transitions | E1–E3, E7, A-INV |
| Idempotency | E4, E5, A-REPLAY |
| Validation | E6, A-INV（非法行不破坏状态） |
| O(N) processing | A-PERF + 复杂度分析（`A/README.md`） |
| High-value tests | 本文件全部（官方示例逐字节 + 性质测试 + 性能门槛） |
