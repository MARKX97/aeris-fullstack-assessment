# Task A — Inventory Reservation Ledger

A deterministic, single-SKU command processor. It reads an initial stock
level and a command stream from stdin, maintains `on_hand` stock and
per-order reservations, and prints one verdict (`OK` / `REJECTED` /
`DUPLICATE`) per command followed by the open-reservation summary.

Standard library only. Requires Python 3.11+.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | The CLI program (single file, stdlib only). |
| `test_main.py` | Acceptance fixtures, shadow-model property tests, replay test, performance smoke. |
| `tests/gen_perf_fixture.py` | Regenerates the 200k-command performance fixture (deterministic seed). |

## Running

```bash
# Process a command stream
python3 A/main.py < input.txt

# Test suite (acceptance fixtures + property tests + perf smoke)
python3 -m pytest A -q

# Manual performance check (regenerates A/tests/fixtures/perf_200k.txt)
python3 A/tests/gen_perf_fixture.py
time python3 A/main.py < A/tests/fixtures/perf_200k.txt
```

Measured on an Apple M3 / macOS 26 / CPython 3.13.12: **0.29 s** for
N = 200,000 commands (acceptance threshold: 2 s).

## Key design decisions

The brief leaves several points ambiguous; each was resolved explicitly and
recorded in the internal spec (`A/spec.md`, section 6, decisions A1–A10).
The load-bearing ones:

1. **`RESTOCK` arity** — the grammar lists 4 tokens but the worked example
   uses `RESTOCK e5 3`. Implemented to match the example: `RESTOCK event_id qty`.
2. **Two-layer validation** — *syntactic* failures (unknown command, wrong
   token count, non-digit qty such as `-1`/`x`/`3.0`) are `REJECTED` and are
   **not** recorded for idempotency, because no reliable `event_id` can be
   extracted. *Semantic* failures (`qty = 0`, insufficient stock, exceeding a
   reservation) are `REJECTED` **and** recorded — the brief states a rejected
   business operation still counts as processed, so replaying it yields
   `DUPLICATE`.
3. **Idempotency short-circuit** — a syntactically valid line whose
   `event_id` was already processed returns `DUPLICATE` with zero state
   change, even if the payload differs.
4. **Header is authoritative** — exactly `N` lines are processed; extra
   lines are ignored, missing lines end the stream at EOF. An invalid header
   writes one line to stderr and exits with code 2. A completely empty
   stream prints `OPEN 0` and exits 0.
5. **Summary format** — header-first: `OPEN <count>` followed by
   `<order_id> <qty>` lines sorted byte-wise by `order_id`; orders whose
   reservation reached zero are dropped.

## Complexity analysis

Let `N` = number of commands, `U_o` = number of unique order IDs
(`U_o ≤ N`), `U_e` = number of unique event IDs (`U_e ≤ N`).

- **Per command: O(1) amortised.** Each command is a constant number of
  dict/set operations (hash lookups on `reserved` and `processed`) and
  integer arithmetic. Python integers are arbitrary precision, so the
  10^12 bounds need no special casing. `total_reserved` is maintained
  incrementally on every mutation, so the availability check
  `on_hand - total_reserved` never iterates the reservation map.
- **Summary: O(U_o log U_o).** Printing open reservations requires sorting
  the keys; this is optimal for comparison-based ordering and replaces the
  brief's informal "O(N)" target, which cannot hold once sorted output is
  required. Since `U_o ≤ N`, the whole run is bounded by
  **O(N + U_o log U_o)**, dominated by the linear pass in practice.
- **Space: O(U_o + U_e)** for the reservation map and the processed-event
  set. The input is read once and output is assembled in a list and written
  in a single `write`, avoiding per-line flush overhead.
- **Measured:** the perf smoke test (200,000 syntactically valid commands,
  the worst case for the hot path) completes in ~0.3 s on an Apple M3
  (threshold: 2 s), consistent with linear scaling.

## Correctness approach

Tests in `test_main.py` are organised as:

1. **Byte-exact acceptance fixtures** (E1–E8a), including the official
   worked example from the brief, over-release/over-ship rejections,
   rejected-event replay, same-key/different-payload replay, illegal
   quantities, header handling, and 10^12 boundary values.
2. **Shadow-model property test** — an independently written model processes
   10,000 random commands (including malformed lines and heavy `event_id`
   reuse); the CLI's output must match it line-by-line, and the model
   asserts the no-oversell invariant (`sum(reserved) ≤ on_hand`) after every
   command.
3. **Replay test** — the full stream is fed twice; every replayed line must
   be `DUPLICATE` with frozen state, and the final summary must be identical.
4. **Performance smoke** — 200k commands must finish under 2 s.
