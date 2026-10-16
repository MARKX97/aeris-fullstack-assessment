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

> TODO — document exact commands once each part is implemented.

### Requirements

- Python 3.11+
- Node.js 20+

```bash
pip install -r requirements-dev.txt   # pytest (tests) + httpx (app tests)
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
# backend
cd app/backend && pip install -r requirements.txt && uvicorn main:app --reload

# frontend
cd app/frontend && npm install && npm run dev
```

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
5. **App — stock race.** _Placeholder — state the concurrency mechanism (lock / CAS / transaction)._

## Architecture notes

> TODO

## Known limitations

> TODO

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

## Submission checklist

- [ ] Repository access verified
- [ ] Setup commands tested from a clean checkout
- [ ] Automated tests pass
- [ ] Assumptions documented
- [ ] AI assistance disclosed
- [ ] No secrets committed
