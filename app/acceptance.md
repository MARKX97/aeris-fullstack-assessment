# App Acceptance — 可观测验收标准

> 状态：Draft v1。每条 pass/fail 必须有真实证据（命令输出 / 截图）。
> 验收汇报格式：命令 + 真实输出 + 标准编号。

---

## 1. 种子数据不变量（启动即查）

| # | 标准 | 验证方式 |
| - | --- | --- |
| APP-SEED | `GET /api/products/p-classic-tee` 返回 8 个 SKU；`Blue+L` 组合无对应 SKU；`sku-blue-m` 的 `available = 0` | curl + jq 实测 |

## 2. 后端契约（stdout / 响应体逐字段比对）

| # | 操作 | 通过判据 |
| - | --- | --- |
| APP-API-1 | `GET /api/products/p-classic-tee` | 200；结构与 spec §5.1 一致 |
| APP-API-2 | `GET /api/products/nope` | 404 + `PRODUCT_NOT_FOUND` |
| APP-API-3 | `POST /api/cart/items` `{skuId: "sku-red-m", quantity: 2}` 带新 key | 201；`totalItemCount: 2`；库存 5→3 |
| APP-API-4 | 同 key 同 body 重发 | **200**；与首次响应 body 一致；库存**不再**下降 |
| APP-API-5 | 同 key 换 body 重发 | 409 + `IDEMPOTENCY_KEY_CONFLICT` |
| APP-API-6 | `quantity: 0` / `-1` / `1.5` / `2.0` / `"2"` / 带额外 `price` 字段 | 400 + `VALIDATION_ERROR`（AP12：quantity 必须为 JSON 整数字面量） |
| APP-API-7 | 请求 `sku-green-l`（available=2）`quantity: 3` | 409 + `INSUFFICIENT_STOCK`，`details.available = 2` |
| APP-API-8 | 未知 `skuId` | 404 + `SKU_NOT_FOUND` |
| APP-API-9 | 不带 `Idempotency-Key` 头 | 400 + `VALIDATION_ERROR`（幂等键必填，spec §5.2） |
| APP-API-10 | `GET /api/cart` | 200；与 APP-API-3 之后的真实购物车一致 |
| APP-API-11 | 同 key 换 body 重发，且新 body 含未知 skuId | 409 `IDEMPOTENCY_KEY_CONFLICT`，而**非** 404——证明键查找先于业务校验（AP12） |

## 3. 并发防超卖（High-risk，核心验收）

| # | 标准 | 通过判据 |
| - | --- | --- |
| APP-RACE | `sku-green-l`（available=1，测试内临时置 1）下 `asyncio.gather` 并发两个合法加购 | **恰好一个 201、一个 409**；终态 available=0；购物车恰 1 行；测试 10 轮全过 |
| APP-INV | 上述流程及全部 API 测试后：每个 SKU `available ≥ 0`（APP-INV1–3 全程成立，测试内断言） |

## 4. 前端（Vitest + 手测留档）

| # | 标准 | 通过判据 |
| - | --- | --- |
| APP-FE-1 | 变体解析测试：选 Red+S → 价格/库存正确；组合矩阵使 Blue+L 不可选 | 测试绿 |
| APP-FE-2 | 重复点击测试：ADDING 期间按钮 disabled，fetch 恰调用 1 次 | 测试绿 |
| APP-FE-3 | 数量收敛测试：qty=3 时切换到 available=2 的 SKU → qty 收敛为 2 | 测试绿 |
| APP-FE-4 | 错误恢复：商品请求失败 → 出现重试按钮 → 点击后恢复 | 测试绿 |
| APP-FE-5 | 无障碍手测：纯键盘完成"选色→选码→设数量→加购"；焦点环可见；成功/失败 aria-live 播报（VoiceOver 或 DOM 断言） | 手测记录 |
| APP-FE-6 | 375px / 1280px 截图各一张，布局无错乱、无横向滚动条 | 截图留档 |
| APP-FE-7 | `grep -rn ": any" app/frontend/src/` 输出为空 | 实测粘贴 |
| APP-FE-8 | 模拟网络场景：后端返回比初始响应更新的库存 → UI 以新值刷新，无整页刷新、无 stale 显示 | 手测 / mock 测试记录 |

## 5. 端到端冒烟（干净检出）

| # | 标准 | 通过判据 |
| - | --- | --- |
| APP-SMOKE | 按根 README 的命令从零启动前后端（全新 venv / 全新 node_modules） | 两条命令均成功；打开页面完成一次加购；记录真实输出 |

## 6. 证据记录（实现后填写）

| 标准 | 命令 | 实际输出 | 结果 |
| --- | --- | --- | --- |
| 后端全部 | `python3 -m pytest app/backend -q` | | ☐ |
| APP-RACE | 同上（含于测试套件） | | ☐ |
| 前端 APP-FE-1..4 | `cd app/frontend && npm run test` | | ☐ |
| APP-FE-5..8 | 手测 | | ☐ |
| APP-SMOKE | README 命令 | | ☐ |

## 7. Out of scope / Follow-ups

- 乐观更新 + 回滚 —— 仅在核心验收全绿后作为可选加分项评估。
- Docker / 单命令双服务启动 —— 同上。
- 购物车行编辑、持久化 —— 不做。

## 8. 与题面评分点的映射

| 题面评分点（Backend 20 / Frontend 15 / Delivery 5） | 由哪些标准证明 |
| --- | --- |
| Clear contract | spec §5 + README + APP-API-1..10 |
| Server-side rules | APP-API-6（拒绝客户端传价）、APP-API-7 |
| Concurrency safety | APP-RACE、APP-INV |
| Idempotency | APP-API-4/5/9 |
| Structured errors and tests | 错误结构（spec §5）+ §9 测试计划全绿 |
| Correct SKU state / resilient async UX | APP-FE-1、APP-FE-4、APP-FE-8 |
| Accessibility | APP-FE-5、APP-FE-6 |
| TypeScript design | APP-FE-7、目录分层（spec §8.4） |
| Easy setup / clean repo / documented trade-offs | APP-SMOKE + README 六节 + spec §10 假设 |
