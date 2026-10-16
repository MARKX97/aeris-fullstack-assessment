# Task B Acceptance — 可观测验收标准

> 状态：v2 全部通过（2026-10-17，Apple M3 / Python 3.13.12 / pytest 9.1.1）。oracle 边界随 spec v2 修订。
> 验收汇报格式：命令 + 真实输出 + 标准编号。

---

## 1. 定向 fixtures（stdout 逐字节比对）

### E-B1 — 官方示例

```
输入               期望输出
3 7                1 27
AU 5 8 2           CN 7
CN 7 20 1
US 4 3 4
```

推导：单仓可行仅 CN（stock 7 ≥ 7），cost = 20 + 7×1 = 27。AU 上限 5、US 上限 4，均不可单仓。

### E-B2 — 不可行 → `-1`

```
输入               期望输出
1 5                -1
A 4 0 0
```

### E-B3 — 成本打平 + 平局规则（验证假设 B1 的关键用例）

```
输入               期望输出
2 3                2 0
A 2 0 0            A 1
B 2 0 0            B 2
```

推导：Q=3 > 任一单仓上限 2 → 必用两仓；fixed=unit=0 → cost=0 恒定；可行分配 `(A=1,B=2)` 与 `(A=2,B=1)` 打平 → 按 B1 裁定取 `[(A,1),(B,2)]`。

### E-B4 — 零库存仓

```
输入               期望输出
2 1                1 2
A 0 1 1            B 1
B 1 1 1
```

推导：A 无库存不可用；B 单仓 cost = 1 + 1×1 = 2。

### E-B5 — 单仓打平 → 字典序取小 id

```
输入               期望输出
2 2                1 7
A 2 5 1            A 2
B 2 5 1
```

推导：A、B 单仓成本同为 5+2×1=7 → `[(A,2)] < [(B,2)]`。

### E-B6 — 题面上限性能

| # | 输入 | 期望 |
| - | --- | --- |
| E-B6a | W=30（id `W01..W30`）、Q=2000、全仓 `stock=2000 fixed=0 unit=1` | `1 2000` + `W01 2000`（单仓最优，id 最小者）；`time` 实测记录，门槛 < 5s |
| E-B6b | W=30、Q=2000、全仓 `stock=70 fixed=10^6 unit=10^6` | 至少 29 仓（`Σ stock = 2100 ≥ 2000`，最少仓数 = ceil(2000/70) = 29）；运行通过且不变量成立 |

## 2. Oracle 交叉验证（平局正确性的主防线）

| # | 标准 |
| - | --- |
| B-ORACLE | 脚本生成 ≥100 组随机小用例（W ≤ 8、Q ≤ 12、stock ≤ 6、成本 ≤ 8，固定 seed）。期望值 = **全分配枚举**（递归 + 剪枝，不依赖引理1）按 `(k, cost, L)` 三元组取最小。DP 输出与 oracle **逐字节全量一致**。 |
| B-INV | 对 E-B1–E-B6 全部输出断言：`Σ a = Q`；`0 ≤ a ≤ stock`；被列出的仓 `a ≥ 1`；成本 = `Σ (fixed + a×unit)` 与首行一致；行按 id 升序。 |

## 3. 假设映射

| 假设 | 证明标准 |
| --- | --- |
| B1 平局粒度 | E-B3、E-B5 + B-ORACLE（oracle 与 DP 用同一裁定才可比） |
| B2 不可行 → -1 | E-B2 |
| B3 fixed=0 的"使用"界定 | B-ORACLE 覆盖（随机含 fixed=0） |

## 4. 证据记录（实现后填写）

| 标准 | 命令 | 实际输出/耗时 | 结果 |
| --- | --- | --- | --- |
| E-B1–E-B6b | `python3 -m pytest B -q` | `14 passed in 1.90s`（fixtures 逐字节、E-B6b 逐字节、B-INV 不变量全过） | ✅ |
| B-ORACLE | 同上（`test_oracle_cross_validation`，150 组，seed=20261017，含 `-1` 路径） | 通过；曾抓到 1 个真实 bug（最优值搜索跨 k 比成本，违反仓数优先），修复后全量一致 | ✅ |
| E-B6 性能 | `time python3 B/main.py < B/tests/fixtures/perf_max.txt` | 输出 `1 2000` + `W01 2000`；实测 **0.296s**（门槛 5s） | ✅ |

## 5. Out of scope / Follow-ups

- 按 k 剪枝、numpy 加速——仅当 E-B6 超门槛时再议（spec B4）。
- 多订单合并履约、随机化算法——不做。

## 6. 与题面评分点的映射

| 题面评分点 | 由哪些标准证明 |
| --- | --- |
| Correct optimisation order and tie-breaking | E-B1、E-B3、E-B5、B-ORACLE |
| Scalable DP | E-B6（上限尺寸 < 5s） |
| Clear complexity analysis | `B/README.md`（spec §5 推导的英文版） |
| 四类定向测试 | E-B2（不可行）/ E-B4（零库存）/ E-B3、E-B5（打平）/ E-B6（大数量） |
