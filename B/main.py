"""Task B - Fulfilment Split Optimiser.

Reads ``W Q`` followed by W lines ``warehouse_id stock fixed_cost unit_cost``
from stdin and prints the optimal allocation: fewest warehouses first, then
lowest total cost (``fixed + qty * unit`` per used warehouse), then the
lexicographically smallest allocation list sorted by warehouse_id
(assumption B1: pairwise ``(id, qty)`` element comparison). Prints ``-1``
when the order cannot be fulfilled exactly.

Algorithm (spec B5/B6): a single suffix DP table

    suff[i][k][q] = min cost to fulfil exactly q units using exactly k
                    warehouses drawn from warehouses[i:] (id-ascending)

computed with a monotone-deque sliding-window minimum over the allocation
amount, giving O(W * K * Q) time with K = min(W, Q). The optimum is read
directly from ``suff[0][*][Q]``; the lexicographically smallest allocation
is then reconstructed greedily in ascending id order, fixing each warehouse
to the smallest quantity that still admits an optimal completion
(equality check against the suffix table). Standard library only.
"""

from __future__ import annotations

import re
import sys
from collections import deque

_DIGITS_RE = re.compile(rb"[0-9]+")

# Any value above the true cost ceiling (30 * (1e6 + 2000 * 1e6) ~ 6e10).
INF = 1 << 62

# Input contract bounds from the brief (defensive validation, spec S7).
MAX_W = 30
MAX_Q = 2000
MAX_STOCK = 2000
MAX_COST = 10**6


def solve(
    warehouses: list[tuple[bytes, int, int, int]], q_total: int
) -> tuple[int, int, list[tuple[bytes, int]]] | None:
    """Return ``(used_count, total_cost, allocation)`` or None if infeasible.

    ``warehouses`` must already be sorted by id ascending; each entry is
    ``(id, stock, fixed_cost, unit_cost)``. ``allocation`` is the
    lexicographically smallest list of ``(id, qty)`` pairs among all
    optimal solutions.
    """
    n = len(warehouses)
    k_max = min(n, q_total)  # every used warehouse ships >= 1 unit
    width = q_total + 1
    inf_row = [INF] * width

    # Rows are never mutated after creation, so unreachable rows share one
    # list object (memory stays ~1 real int per reachable state).
    suff = [[inf_row] * (k_max + 1) for _ in range(n + 1)]
    suff[n][0] = [0] + [INF] * q_total  # empty suffix fulfils exactly 0

    for i in range(n - 1, -1, -1):
        _wid, stock, fixed, unit = warehouses[i]
        layer = suff[i]
        nxt = suff[i + 1]
        layer[0] = nxt[0]  # using 0 warehouses: only "skip" is possible
        # k > n - i can never be reachable; leave those rows as INF aliases.
        for k in range(1, min(k_max, n - i) + 1):
            skip = nxt[k]
            prev = nxt[k - 1]
            cur = [INF] * width
            # Sliding window over j = q - a in [q - stock, q - 1] of
            # g(j) = prev[j] - j * unit; f(q) = q * unit + min g(j).
            dq: deque[tuple[int, int]] = deque()
            for q in range(width):
                j = q - 1
                if j >= 0:
                    pj = prev[j]
                    if pj < INF:
                        gj = pj - j * unit
                        while dq and dq[-1][1] >= gj:
                            dq.pop()
                        dq.append((j, gj))
                lo = q - stock  # a <= stock  <=>  j >= q - stock
                while dq and dq[0][0] < lo:
                    dq.popleft()
                best = skip[q]
                if dq:
                    cand = fixed + q * unit + dq[0][1]
                    if cand < best:
                        best = cand
                cur[q] = best
            layer[k] = cur

    # Objective order: fewest warehouses FIRST, then lowest cost. Scanning k
    # ascending, the first reachable k is optimal - its cost is already
    # minimised by the DP. (Never compare costs across different k.)
    best_k = 0
    best_cost = INF
    for k in range(1, k_max + 1):
        if suff[0][k][q_total] < INF:
            best_k, best_cost = k, suff[0][k][q_total]
            break
    if best_cost == INF:
        return None

    # Lexicographic reconstruction (spec S6): walking ids ascending, using
    # warehouse i always beats skipping it (its id is smaller than any
    # later one), and the smallest feasible qty wins; a completion exists
    # iff the suffix table matches the remaining cost budget exactly.
    alloc: list[tuple[bytes, int]] = []
    k_rem, q_rem, c_rem = best_k, q_total, best_cost
    for i in range(n):
        if k_rem == 0:
            break
        wid, stock, fixed, unit = warehouses[i]
        prev_row = suff[i + 1][k_rem - 1]
        for a in range(1, min(stock, q_rem) + 1):
            rest = c_rem - fixed - a * unit
            if rest >= 0 and prev_row[q_rem - a] == rest:
                alloc.append((wid, a))
                k_rem -= 1
                q_rem -= a
                c_rem = rest
                break
        # No feasible a: warehouse i is unused in every optimal continuation.
    assert k_rem == 0 and q_rem == 0 and c_rem == 0, "reconstruction lost optimality"
    return best_k, best_cost, alloc


def run(data: bytes) -> tuple[bytes, bytes, int]:
    """Process one full input stream.

    Returns ``(stdout_bytes, stderr_bytes, exit_code)``. Pure with respect
    to its argument so tests can drive it without a subprocess.
    """
    if not data.strip():
        return b"", b"error: empty input; expected '<W> <Q>' header\n", 2

    lines = data.split(b"\n")
    header = lines[0].split()
    if (
        len(header) != 2
        or not _DIGITS_RE.fullmatch(header[0])
        or not _DIGITS_RE.fullmatch(header[1])
    ):
        return b"", b"error: invalid header; expected '<W> <Q>' as non-negative integers\n", 2

    w, q_total = int(header[0]), int(header[1])
    if not (1 <= w <= MAX_W and 1 <= q_total <= MAX_Q):
        return (
            b"",
            b"error: header out of range; expected 1 <= W <= %d and 1 <= Q <= %d\n"
            % (MAX_W, MAX_Q),
            2,
        )

    body = [ln for ln in lines[1:] if ln.strip()]
    if len(body) != w:
        return b"", b"error: expected %d warehouse lines, got %d\n" % (w, len(body)), 2

    warehouses: list[tuple[bytes, int, int, int]] = []
    seen: set[bytes] = set()
    total_stock = 0
    for ln in body:
        parts = ln.split()
        if len(parts) != 4:
            return b"", b"error: invalid warehouse line; expected '<id> <stock> <fixed> <unit>'\n", 2
        wid, s_tok, f_tok, u_tok = parts
        if (
            not wid.isascii()
            or not _DIGITS_RE.fullmatch(s_tok)
            or not _DIGITS_RE.fullmatch(f_tok)
            or not _DIGITS_RE.fullmatch(u_tok)
        ):
            return b"", b"error: invalid warehouse line; id must be ASCII, numbers digits-only\n", 2
        stock, fixed, unit = int(s_tok), int(f_tok), int(u_tok)
        if stock > MAX_STOCK or fixed > MAX_COST or unit > MAX_COST:
            return b"", b"error: warehouse value out of range\n", 2
        if wid in seen:
            return b"", b"error: duplicate warehouse id %s\n" % wid, 2
        seen.add(wid)
        total_stock += stock
        warehouses.append((wid, stock, fixed, unit))

    # Spec B2: no partial fulfilment - short-circuit before the DP.
    if total_stock < q_total:
        return b"-1\n", b"", 0

    warehouses.sort(key=lambda wh: wh[0])
    result = solve(warehouses, q_total)
    if result is None:
        return b"-1\n", b"", 0

    count, cost, alloc = result
    out = [b"%d %d" % (count, cost)]
    out += [wid + b" %d" % qty for wid, qty in alloc]
    return b"\n".join(out) + b"\n", b"", 0


def main() -> int:
    stdout, stderr, code = run(sys.stdin.buffer.read())
    if stdout:
        sys.stdout.buffer.write(stdout)
    if stderr:
        sys.stderr.buffer.write(stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
