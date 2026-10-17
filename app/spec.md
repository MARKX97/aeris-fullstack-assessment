# App Spec — Variant PDP（变体商品详情页）

> 状态：Draft v1（实现前定稿）。变更需同步更新 `acceptance.md`。
> 依据：`BRIEF.md` §5–§6。题面硬约束：FastAPI + React/TS、内存或 SQLite 存储、**不要过度建设**（认证 / 结算 / 支付 / 部署全部 out of scope）。

---

## 1. 问题陈述

一个"选颜色 + 选尺码 → 定位 SKU → 加购物车"的商品详情页，配三个 API。考察点：服务端权威校验、幂等键、并发防超卖、前端状态机与无障碍——**不是视觉打磨**。

## 2. Non-goals（题面明文 + 本 spec 裁定）

- 认证 / 结算 / 支付 / 生产部署 / Docker 化（可作可选加分项，默认不做）。
- 多商品、购物车持久化跨会话、购物车编辑（增删改行）——**只做题面三个接口**。
- 乐观更新 —— 可选加分项，默认不做（做了必须有回滚文档）。

## 3. 技术选型

| 层 | 选择 | 理由 |
| --- | --- | --- |
| 后端 | FastAPI + Pydantic v2，Python 3.11+ | 题面硬性 |
| 存储 | **内存 dict**（进程内单例 Store 类） | 零配置、启动即用；并发用锁保证正确（§7）。真实部署换 DB 行锁的对应关系写入 README |
| 前端 | Vite + React 18 + TypeScript（strict） | 轻于 Next.js，SPA 场景合适 |
| 前端测试 | Vitest + Testing Library | 题面要求 ≥3 个有意义测试；不引入 E2E 框架 |
| 价格表示 | 整数分（cents），API 序列化为 `"29.90"` 字符串或分值 | 杜绝浮点比较错误 |

## 4. 领域模型与种子数据（确定性，测试依赖它）

商品 `Classic Tee`（id `p-classic-tee`）：

- 维度1 `colour`：Red / Blue / Green
- 维度2 `size`：S / M / L

组合矩阵（3×3 = 9，其中 1 个组合不存在、1 个 SKU 缺货）：

| SKU id | colour | size | price(分) | available | 说明 |
| --- | --- | --- | --- | --- | --- |
| sku-red-s | Red | S | 2900 | 10 | |
| sku-red-m | Red | M | 2900 | 5 | |
| sku-red-l | Red | L | 2900 | 3 | |
| sku-blue-s | Blue | S | 3100 | 8 | |
| sku-blue-m | Blue | M | 3100 | 0 | **缺货 SKU** |
| — | Blue | L | — | — | **不存在的组合**（无此 SKU） |
| sku-green-s | Green | S | 2700 | 6 | |
| sku-green-m | Green | M | 2700 | 4 | |
| sku-green-l | Green | L | 2700 | 2 | 数量小，race 测试用它 |

共 8 个 SKU ≥ 6 ✓。图片：`/images/<sku-id>.png`（占位图即可）。

**不变量**
- APP-INV1：任意时刻每个 SKU 的 `available ≥ 0`（不超卖）。
- APP-INV2：加入购物车的行不减少商品总数以外的任何状态（价格以服务端为准）。
- APP-INV3：同一个 `Idempotency-Key` 至多产生一次库存扣减。

## 5. API 契约

所有响应 JSON；错误统一结构：

```json
{ "error": { "code": "INSUFFICIENT_STOCK", "message": "…", "details": { } } }
```

| code | HTTP | 场景 |
| --- | --- | --- |
| VALIDATION_ERROR | 400 | 请求体不合契约（Pydantic 校验失败时也映射为 400 + 本结构） |
| PRODUCT_NOT_FOUND / SKU_NOT_FOUND | 404 | id 不存在 |
| INSUFFICIENT_STOCK | 409 | 库存不足 |
| IDEMPOTENCY_KEY_CONFLICT | 409 | 同 key 不同 payload |
| INTERNAL_ERROR | 500 | 兜底（不含堆栈细节） |

### 5.1 `GET /api/products/{id}` → 200

```json
{
  "product": { "id": "p-classic-tee", "name": "Classic Tee", "description": "…" },
  "options": [
    { "id": "colour", "name": "Colour", "values": ["Red", "Blue", "Green"] },
    { "id": "size",   "name": "Size",   "values": ["S", "M", "L"] }
  ],
  "skus": [
    { "id": "sku-red-s", "options": { "colour": "Red", "size": "S" },
      "price": 2900, "available": 10, "image": "/images/sku-red-s.png" }
  ]
}
```

404：`{ "error": { "code": "PRODUCT_NOT_FOUND", … } }`

### 5.2 `POST /api/cart/items` → 201（幂等重放 → 200，返回同一 body）

请求头必填 `Idempotency-Key: <非空任意串>`。

```json
// 请求体
{ "skuId": "sku-red-m", "quantity": 2 }
// 201 响应
{
  "cart": {
    "items": [ { "skuId": "sku-red-m", "quantity": 2, "unitPrice": 3100, "lineTotal": 6200 } ],
    "totalItemCount": 2
  }
}
```

- `quantity ∈ [1, available]`；`skuId` 必须存在；**价格与库存一律服务端取值**（请求体不允许带价格/库存字段，出现即 400）。
- `quantity` 必须是 JSON 整数字面量（Pydantic strict 模式）：`"2"`、`1.5`、`2.0` 一律 400 `VALIDATION_ERROR`（AP12）。
- 幂等键查找先于业务校验：key 已命中 → 直接重放或 409 `IDEMPOTENCY_KEY_CONFLICT`，**优先于** `SKU_NOT_FOUND` / `INSUFFICIENT_STOCK`（AP12）。
- 幂等语义：key + payload 指纹（规范化 JSON）相同 → 不重复扣减，返回与首次相同的 body（状态码 200）；key 相同 payload 不同 → 409 `IDEMPOTENCY_KEY_CONFLICT`。
- 库存不足 → 409 `INSUFFICIENT_STOCK`，`details` 携带 `{ "available": <n> }`。
- 同一 SKU 以**不同**幂等键再次加购 → 合并为同一购物车行（数量累加，行金额重算）；每次成功加购仍独立扣库存、独立记幂等（AP14）。

### 5.3 `GET /api/cart` → 200

返回与 5.2 响应中 `cart` 相同结构的当前购物车；空车 → `items: []`, `totalItemCount: 0`。

## 6. 幂等实现规格

- 存储：内存 `dict[key] = (payload_fingerprint, response_snapshot)`；记录保留整个进程生命期（README 声明"非持久化"为已知限制）。
- payload 指纹：对解析后的模型字段做稳定序列化后哈希（规范化：键排序）。
- 写入时机：**业务成功后**才缓存响应；失败（409/400）不缓存（失败重试是合法的）。

## 7. 并发防超卖规格（High-risk，题面明文要求解释）

- 机制：`asyncio.Lock`（进程内单锁）保护「查库存 → 校验 → 扣减 → 记幂等」整段临界区。检查与扣减**必须同一临界区**，杜绝 TOCTOU。
- **可证伪性（AP13）**：asyncio 单线程事件循环中，若临界区内部无 await 点，则锁永不被争用（任务不可中途切换），APP-RACE 测试将退化成纯顺序测试。因此临界区内**必须保留一个受锁保护的 `await asyncio.sleep(0)`**——让出控制权一次，使两个并发请求真正在锁上排队，测试对「单线程实现中被跳过的竞争」保持可证伪。真实多进程部署下该 yield 点不影响正确性（换 DB 行锁后此机制整体替换）。
- 为什么可以单锁：单进程内存存储 + 单商品场景，锁粒度全局即可满足正确性；真实多商品/多实例部署改为「DB 事务 + 行锁（或原子 UPDATE ... WHERE available >= ?）」，对应关系写入 README 的 Architecture notes。
- 验收：两个并发请求抢最后 1 件 → 恰好一个 201、一个 409，终态 available=0（见 `acceptance.md` APP-RACE）。

## 8. 前端规格

### 8.1 状态机（必须全部可观测）

| 状态 | 进入 | 退出 |
| --- | --- | --- |
| LOADING | 首次挂载 | → READY / LOAD_ERROR |
| LOAD_ERROR | 商品请求失败 | 重试按钮 → LOADING |
| READY·未选全 | 有任一维度未选 | 加购禁用 |
| READY·非法组合 | 选中组合无 SKU（Blue+L） | 该组合按钮 disabled；界面提示不可选 |
| READY·缺货 | 选中 SKU available=0 | 加购禁用 + 缺货提示 |
| READY·可选 | 选中合法且有库存 | 可加购 |
| ADDING | 点击加购 | 按钮 disabled + aria-busy；**重复点击不产生第二个请求** |
| ADD_SUCCESS / ADD_*_ERROR | 响应到达 | aria-live 播报；错误可重试 |
| STALE 恢复 | 响应库存比本地旧值新 | 以响应为准刷新，无需整页刷新 |

### 8.2 交互与正确性规则

- 切换维度 → 重新解析 SKU，价格 / 图片 / 库存同步刷新；**禁止出现上一次选择的残留状态**（stale UI）。
- 数量选择器上限 = 当前 SKU 的 available；切换 SKU 时数量自动收敛到 `[1, min(q, available)]`。
- 加购进行中禁用按钮（防误双击）；成功后数量复位为 1。

### 8.3 无障碍与响应式（硬性）

- 全键盘可操作（Tab / Enter / Space），焦点可见（不清除默认 outline）。
- 语义化：`<button>` 选项组 / `aria-pressed` 或 radio 语义 / `<label>` 关联数量输入。
- 反馈用 `aria-live="polite"` 播报加购成功 / 失败。
- 375px 与 1280px 两档布局可用（手测 + 截图留档）。

### 8.4 代码结构

```
app/frontend/src/
├── api/        # fetch 封装：错误结构化、类型化
├── domain/     # SKU 解析、组合矩阵、数量收敛 —— 纯函数、可单测
└── ui/         # 组件与状态编排（不写业务规则）
```
- `strict: true`；**禁 `any`**（`grep -r ": any" src/` 为零）。

## 9. 测试计划（Feedback Sensors）

**后端（pytest + httpx AsyncClient）**
1. 契约：三个接口的成功路径（§5 的示例 JSON 即断言目标）。
2. 校验：quantity 越界 / 0 / 负 / 非整数；请求体携带 price 字段 → 400。
3. 幂等：同 key 同 body → 一次扣减；同 key 不同 body → 409。
4. 并发竞争：`asyncio.gather` 两请求抢最后 1 件 → 恰一成功（APP-RACE）。
5. 404：未知 product / sku。

**前端（Vitest + Testing Library，≥3 个）**
1. 变体解析：选 Red+S → 价格与库存正确刷新；选 Blue+L → 组合禁用。
2. 重复点击：点击加购后按钮 disabled，期间再点击不触发第二个请求（断言 fetch 调用次数）。
3. 数量收敛：先选数量 3，切到 available=2 的 SKU → 数量收敛为 2。
4. （补）错误恢复：商品请求失败 → 出现重试，点击后恢复。

## 10. 决策记录（须写入 README）

| ID | 级别 | 决策 | 文档依据 |
| --- | --- | --- | --- |
| AP1 | 强 | 恰好 2 个选项维度 | L307 "at least two" 与 L355 "Render **both**" 并存；取 3 维则 "both" 落空 |
| AP2 | 强 | unavailable combination = 无 SKU 的组合，不计入 SKU 数；实际交付 8 个 SKU | L310 与 L313 的 SKU 定义冲突，唯一自洽读法 |
| AP3 | 强 | 加购即预留并扣减 available | L335 "attempt to **reserve** the final unit" |
| AP4 | 解 | 缺货 SKU（available=0）时数量输入不适用、加购禁用 | L361 区间 [1, available] 在 L310/L375 必需缺货态下为空集 |
| AP5 | 解 | 全站单一匿名购物车，多用户隔离 out of scope | L413 认证 out of scope × L322 "current cart"，身份机制未定义 |
| AP6 | 解 | 幂等缓存随进程存亡（非持久化），已知限制 | L302 允许 in-memory；L329 仅约束"不得重复添加" |
| AP7 | 解 | 价格以整数分传输，展示层格式化 | L313/L326 未定义金额单位 |
| AP8 | 解 | 开发期 Vite proxy，不加 CORS | 文档未涉及 |
| AP12 | 解 | quantity 为 JSON 整数字面量（Pydantic strict）；幂等键查找先于业务校验（同 key 不同 body → 409，不落入 SKU_NOT_FOUND） | 题面 L329 只约束「不得重复添加」，未定义键检查时机 |
| AP13 | 强 | 防超卖临界区内保留 `await asyncio.sleep(0)`，保证 APP-RACE 测试可证伪 | 测试需真实竞争，asyncio 单线程无 yield 点则锁不可争用 |
| AP14 | 解 | 同 SKU 不同幂等键的加购合并为同一购物车行（数量累加、行金额重算），每次成功仍独立扣库存、独立记幂等 | 题面未定义购物车行合并规则 |

## 11. 交付物对照

| 题面要求 | 落点 |
| --- | --- |
| 3 个接口 + 服务端校验 + 幂等 + 防超卖 | `app/backend/` + `app/backend/tests/` |
| README 中记录请求/响应示例与状态码 | 根 `README.md`（英文，复制 §5 示例） |
| 前端状态机 + 无障碍 + 测试 | `app/frontend/src/` + `tests/` |
| Seed data 立即可用 | §4 种子表在启动时注入内存 |
