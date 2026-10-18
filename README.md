# Coding Interview Assessment — Full-Stack Developer

Aeris Health take-home assessment. Python / FastAPI / React + TypeScript.

## Repository structure

```
/A      Task A — Inventory Reservation Ledger (Python solution + tests)
/B      Task B — Fulfilment Split Optimiser (Python solution + tests)
/C      Task C — Xero Integration Review (written answers in answers.md)
/app    Full-Stack App — Variant PDP (FastAPI backend + React/TypeScript frontend)
README.md
```

## Setup

- Python 3.11+
- Node.js 22.12+ (Vite 8 needs `^20.19 || >=22.12`; the test runner
  Vitest 5 needs `^22.12 || ^24 || >=26`, so Node 20 cannot run the
  frontend test suite)

```bash
pip install -r requirements-dev.txt   # pytest + pytest-asyncio + httpx (test deps)
```

Test files share the `test_main.py` basename across task dirs; the root
`pyproject.toml` sets `--import-mode=importlib` so no `__init__.py` is needed.

### Task A

```bash
python3 A/main.py < input.txt     # run the CLI
python3 -m pytest A -q            # acceptance + property + replay + perf tests
```

See [`A/README.md`](A/README.md) for design decisions and complexity analysis.

### Task B

```bash
python3 B/main.py < input.txt     # run the CLI
python3 -m pytest B -q            # acceptance + oracle + invariant + perf tests
```

See [`B/README.md`](B/README.md) for the DP state representation, tie-breaking
strategy and complexity analysis.

### Task C

Written answers: [`C/answers.md`](C/answers.md)

### App

```bash
# backend (http://127.0.0.1:8000)
cd app/backend && pip install -r requirements.txt && uvicorn main:app --reload

# backend tests: contract + idempotency + stock-race (from the repo root)
python3 -m pytest app/backend -q

# frontend (http://localhost:5173, proxies /api to the backend)
cd app/frontend && npm install && npm run dev

# frontend tests (variant resolution, double-click guard, quantity
# convergence, error recovery, stale-stock refresh)
cd app/frontend && npm run test

# frontend type-check + production build (tsc -b, strict, zero `any`)
cd app/frontend && npm run build
```

#### Backend API contract

The add-to-cart endpoint requires an `Idempotency-Key` header. Replaying
the same key with the same body returns **200** with the identical body and
does not decrement stock again; the same key with a different body returns
**409**. Structured errors all share the shape
`{"error": {"code", "message", "details"}}`:

| Status | Code | When |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Malformed body, non-integer or `< 1` quantity, extra fields such as a client-supplied `price`, missing `Idempotency-Key` |
| 404 | `PRODUCT_NOT_FOUND` / `SKU_NOT_FOUND` | Unknown product / SKU id |
| 409 | `INSUFFICIENT_STOCK` | Requested quantity exceeds available; `details.available` carries the true stock |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` | Key reused with a different body |
| 500 | `INTERNAL_ERROR` | Unexpected failure (no stack traces in the response) |

Full request/response examples: FastAPI's generated OpenAPI page at
`/docs` supplements the explanations in `app/spec.md` §5 and this section.

#### Stock-race safety

Two concurrent requests for the final unit produce exactly one **201** and
one **409**. The whole idempotency-lookup → stock-check → reserve → record
path runs inside one `asyncio.Lock` critical section; the check and the
decrement can never interleave, so no TOCTOU window exists. See
"Architecture notes" below for the production-scale correspondence (DB row
locks / atomic conditional updates).

## Assumptions

Decisions taken where the brief was ambiguous or silent.

1. **Task A — `RESTOCK` arity.** The command grammar lists `RESTOCK event_id order_id qty` (4 tokens),
   but the worked example uses `RESTOCK e5 3` (3 tokens). Implemented to match the **example**:
   `RESTOCK event_id qty` — a restock is not tied to an order. Documented here because the brief
   explicitly asks for assumptions to be stated.
2. **Task A — output format.** Per-command line is `<STATUS> <on_hand> <reserved>` (space-separated),
   matching the example. After all commands, the summary starts with `OPEN <count>`, followed by one
   line per open reservation ordered by `order_id`.
3. **Task A — malformed input.** A malformed line is reported as `REJECTED` and leaves state untouched.
   The stream continues rather than aborting, since the brief requires "no partial state changes"
   rather than termination.

   The complete Task A decision list (two-layer validation and what counts as processed for
   idempotency, header handling, empty-stream behaviour, sort order) is documented in
   [`A/README.md`](A/README.md).
4. **Task B — tie-breaking.** "Lexicographically smallest allocation list when sorted by
   `warehouse_id`" is read as element-wise comparison of `(warehouse_id, qty)` pairs:
   `[(A,1),(B,2)] < [(A,2),(B,1)]`, with the first differing pair deciding. Additional
   Task B decisions (no partial fulfilment, "used" means `qty >= 1` even at zero fixed
   cost) are documented in [`B/README.md`](B/README.md#assumptions-ambiguities-in-the-brief).
5. **App — stock race.** The reserve path (idempotency lookup → stock check →
   decrement → record) runs inside a single `asyncio.Lock` critical section.
   The check and the decrement can never interleave, so there is no TOCTOU
   window; two concurrent requests for the final unit yield exactly one 201
   and one 409. A deliberate `await asyncio.sleep(0)` inside the critical
   section keeps the race test falsifiable under the single-threaded event
   loop (without a yield point the lock could never be contended and the test
   would silently degrade to a sequential one). Idempotency-key lookup happens
   *before* business validation: a replayed key with a different body returns
   409 `IDEMPOTENCY_KEY_CONFLICT` even when the new body is otherwise invalid.

## Architecture notes

**App (`app/`)** — FastAPI + Pydantic v2 backend with an in-process,
in-memory `Store` (dict-based). The mapping to a production deployment:

| In-memory implementation (this repo) | Production equivalent |
| --- | --- |
| `asyncio.Lock` around check+reserve | DB row lock / transaction, or an atomic `UPDATE skus SET available = available - ? WHERE id = ? AND available >= ?` |
| Idempotency cache: `dict[key] = (fingerprint, response)` in process memory | Persistent table keyed by `Idempotency-Key` with a TTL, cleaned by a background job |
| Anonymous single cart | Carts keyed by session/user (auth explicitly out of scope per the brief) |

The frontend is a Vite + React 19 + TypeScript SPA layered as
`api/` (typed fetch wrapper, structured errors), `domain/` (pure SKU
resolution / combination-matrix / quantity logic) and `ui/` (state
orchestration only). The Vite dev server proxies `/api` to the backend, so no
CORS configuration exists in the backend — intentional for a same-origin
deployment.

Full API contract with request/response examples: `app/spec.md` §5; the
running service also serves generated OpenAPI docs at `/docs`.

## Known limitations

- **App idempotency cache and cart are in-memory and per-process**: a backend
  restart forgets carts and idempotency records. Accepted per the brief
  (in-memory storage explicitly allowed); swap the Store for a database to
  remove this.
- **App a11y**: structural accessibility (aria-live, aria-busy, aria-pressed,
  focus outlines) is asserted in tests; a manual pure-keyboard walkthrough is
  listed as pending in `app/acceptance.md` §6 (375px/1280px screenshots are
  archived in `app/acceptance/screenshots/`).
- **App product images are placeholders** generated by
  `app/frontend/scripts/gen_placeholders.py` (pure stdlib, re-runnable) and
  committed to `app/frontend/public/images/`.
- **Task A/B** perf fixtures (4 MB) are generated, not committed; regenerate
  with the checked-in generators if needed.

## AI assistance disclosure

Per the brief, every place AI-assisted tooling was used is disclosed here.

- **Task A** — AI assistant (WorkBuddy) implemented `A/main.py`, `A/test_main.py`,
  `A/tests/gen_perf_fixture.py` and `A/README.md` from the pre-written spec/acceptance
  documents (`A/spec.md`, `A/acceptance.md`), and ran the verification commands.
  Ambiguity resolutions (A1–A10) were decided by the candidate and recorded in
  `A/spec.md` §6 before implementation.
- **Task B** — AI assistant (WorkBuddy) implemented `B/main.py`, `B/test_main.py`,
  `B/tests/gen_perf_fixture.py` and `B/README.md` from `B/spec.md` / `B/acceptance.md`,
  and ran the verification commands. The algorithm choice (suffix DP + monotone deque,
  deterministic lexicographic reconstruction) and ambiguity resolutions (B1–B3) are
  recorded in `B/spec.md`; one implementation bug found by the oracle test is logged
  in `B/acceptance.md` §4.
- **Task C** — AI assistant (WorkBuddy) authored `C/answers.md` from `C/spec.md` /
  `C/acceptance.md`, and verified each referenced Xero documentation page live
  (OAuth auth-flow, Tenants/Connections, API limits, Invoices model, and the official
  Idempotent-requests best-practices page) to avoid memory-sourced API details; any
  behaviour not confirmed in those pages is marked `Assumption` inline. All diagnosis
  and design decisions are the candidate's and are recorded in `C/spec.md` §4/§8.
- **Task app** — AI assistant (WorkBuddy) implemented the FastAPI backend
  (`app/backend/main.py`, `store.py`, 17 tests) and the React/TypeScript
  frontend (`app/frontend/`, 6 tests) from `app/spec.md` / `app/acceptance.md`,
  and ran the verification commands. One frontend bug (controlled number-input
  composing "clear + 3" into a clamped 13) and one spec deviation
  (quantity reset instead of convergence on SKU switch) were caught by the
  APP-FE-3 test and fixed; both are logged in `app/acceptance.md` §6.
  All design decisions (AP1–AP15) are the candidate's and were recorded in
  `app/spec.md` §10 before implementation.

## Submission checklist

- [ ] Repository access verified
- [x] Setup commands tested from a clean checkout (`git clone` + fresh venv
      + fresh `npm install`: 48 backend tests, 6 frontend tests, build, and a
      full add-to-cart smoke all pass; evidence in `app/acceptance.md` §6)
- [x] Automated tests pass (`pytest A B app/backend -q` → 48 passed;
      `npm run test` → 6 passed)
- [x] Assumptions documented (this file + per-task spec/README)
- [x] AI assistance disclosed (section above)
- [x] No secrets committed (`git ls-files` scan clean; `.gitignore` excludes
      `.env*`, `*.pem`, `*.key`)
