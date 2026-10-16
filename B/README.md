# Task B — Fulfilment Split Optimiser

Allocate exactly `Q` units across up to 30 warehouses, optimising in strict
lexicographic order: **(1) fewest warehouses used, (2) lowest total cost**
(`fixed_cost + qty × unit_cost` per used warehouse), **(3) lexicographically
smallest allocation list** sorted by `warehouse_id`. Prints `-1` when the
order cannot be fulfilled exactly.

## Usage

```bash
python3 B/main.py < input.txt     # run the CLI (standard library only)
python3 -m pytest B -q            # acceptance + oracle + invariant + perf tests
```

## State representation

Warehouses are first sorted by `warehouse_id` ascending (needed for the
tie-break reconstruction below). A single **suffix DP** table is computed:

```
suff[i][k][q] = minimum cost to fulfil exactly q units using exactly k
                warehouses drawn from warehouses[i..W-1]
```

Transition (warehouse `i` has `stock s`, `fixed f`, `unit u`):

```
suff[i][k][q] = min( suff[i+1][k][q],                       # warehouse i unused
                     f + min_{1 <= a <= min(s, q)} ( a*u + suff[i+1][k-1][q-a] ) )
```

The inner minimum looks quadratic, but substituting `j = q - a` gives

```
min over j in [q - s, q - 1] of  q*u + ( suff[i+1][k-1][j] - j*u )
```

which is a **fixed-width sliding-window minimum** over `g(j) = suff[i+1][k-1][j] - j*u`.
A monotone deque maintains that minimum in amortised O(1) per `q`, so filling
one `(i, k)` row costs O(Q).

The optimum is read from the first layer: scanning `k` ascending, the first
reachable `suff[0][k][Q]` wins — the count dominates the cost in the
objective, and the DP has already minimised cost for that `k`. Costs never
need to be compared across different `k`.

## Tie-breaking strategy

The DP stores scalar costs, not allocation vectors, so the lexicographically
smallest allocation list is **reconstructed deterministically** after the
optimal `(k*, cost*)` is known. Walking warehouses in ascending id order with
remaining budget `(k_rem, q_rem, c_rem)`:

- At warehouse `i`, *using* it always beats skipping it — its id is smaller
  than any later candidate, so a solution using `i` is lexicographically
  smaller whenever one exists.
- Among feasible quantities, the **smallest** `a >= 1` wins, because the
  allocation list is compared as a sequence of `(id, qty)` pairs and the
  first differing element decides (assumption B1 below).
- Feasibility of a choice is checked exactly: a completion exists iff
  `suff[i+1][k_rem-1][q_rem-a] == c_rem - fixed_i - a*unit_i`.

The check guarantees an optimal completion for the suffix, so the greedy
prefix choice never dead-ends (induction on the invariant).

## Complexity

- **Time: O(W · K · Q)**, `K = min(W, Q)` — each of the W·K rows is filled by
  one O(Q) deque pass. With W ≤ 30, Q ≤ 2000: ≤ 1.9 × 10⁶ deque steps;
  measured 0.30 s on the maximum-size case (Apple M3, Python 3.13).
- **Space: O(W · K · Q)** — the full suffix table is retained for
  reconstruction; unreachable rows share one immutable `INF` row object, so
  real allocations are bounded by reachable states (tens of MB worst case).
- Reconstruction is O(W · Q) equality probes against the table.

Brute force over 2³⁰ subsets is ruled out by the brief; the naive
O(W·K·Q²) DP (enumerating `a` per state) is ~3.6 × 10⁹ steps at the upper
bound — too slow in Python — which is why the deque optimisation is used.

## Assumptions (ambiguities in the brief)

- **B1 — tie-break granularity.** "Lexicographically smallest allocation
  list" is read as element-wise comparison of `(warehouse_id, qty)` pairs:
  `[(A,1),(B,2)] < [(A,2),(B,1)]`. Covered by test E-B3/E-B5 and the oracle.
- **B2 — infeasible.** If `sum(stock) < Q` (or the DP finds no exact
  solution), print `-1`; partial fulfilment is never emitted.
- **B3 — "used".** A warehouse counts as used iff it is allocated `qty >= 1`,
  even when its `fixed_cost` is 0.
- Malformed input (bad header, wrong arity, duplicate id, out-of-range
  values) exits with code 2 and a stderr message; the valid-input contract
  of the brief is otherwise assumed.

## Tests

`B/test_main.py`:

| Group | What it proves |
| --- | --- |
| `test_acceptance_fixtures` | E-B1..E-B5 byte-exact: official example, infeasible, qty tie-break, zero-stock, id tie-break |
| `test_eb6b_*` | 30 identical warehouses forcing a 29-way split, byte-exact + invariants |
| `test_fixture_invariants` | B-INV on every fixture: `Σ qty = Q`, bounds, cost consistency, id order |
| `test_oracle_cross_validation` | 150 random small instances (fixed seed) against **exhaustive allocation enumeration** — ground truth sharing no reasoning with the DP; covers the `-1` path too |
| `test_perf_upper_bound_under_5s` | E-B6a maximum size (W=30, Q=2000, stock=2000 each), byte-exact output, < 5 s |

The performance fixture is generated (`B/tests/gen_perf_fixture.py`, output
gitignored) and reused by the perf test.
