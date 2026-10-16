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

### Task A

```bash
cd A
python3 a.py < input.txt
python3 -m pytest -q
```

### Task B

```bash
cd B
python3 b.py < input.txt
python3 -m pytest -q
```

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
   matching the example. Open reservations are printed after all commands, and the final line is
   `OPEN <count>`, followed by one line per open reservation ordered by `order_id`.
3. **Task A — malformed input.** A malformed line is reported as `REJECTED` and leaves state untouched.
   The stream continues rather than aborting, since the brief requires "no partial state changes"
   rather than termination.
4. **Task B — tie-breaking.** "Lexicographically smallest allocation list when sorted by
   `warehouse_id`" is read as: compare the sequences of allocated quantities in ascending
   `warehouse_id` order, element by element, preferring the smaller quantity at the first
   difference. _Placeholder — confirm and refine after implementing._
5. **App — stock race.** _Placeholder — state the concurrency mechanism (lock / CAS / transaction)._

## Architecture notes

> TODO

## Known limitations

> TODO

## AI assistance disclosure

Per the brief, every place AI-assisted tooling was used is disclosed here.

> TODO — complete before submission.

## Submission checklist

- [ ] Repository access verified
- [ ] Setup commands tested from a clean checkout
- [ ] Automated tests pass
- [ ] Assumptions documented
- [ ] AI assistance disclosed
- [ ] No secrets committed
