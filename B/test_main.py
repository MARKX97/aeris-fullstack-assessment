"""Acceptance, oracle cross-validation and performance tests for Task B.

Fixtures E-B1..E-B6b drive the real CLI in a subprocess and compare stdout
byte-for-byte against the hand-derived expectations in B/acceptance.md.
The oracle test (B-ORACLE) cross-checks the DP against exhaustive
enumeration of every feasible allocation - the oracle shares no reasoning
with the implementation (not even the unit-cost greedy lemma).
"""

from __future__ import annotations

import importlib.util
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
MAIN = HERE / "main.py"

# Import run() for the high-volume oracle loop; fixtures still go through
# the real subprocess CLI. Unique module name avoids clashing with A/main.py.
_spec = importlib.util.spec_from_file_location("taskb_main", MAIN)
assert _spec and _spec.loader
taskb_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(taskb_main)

PERF_LIMIT_S = 5.0
ORACLE_CASES = 150
ORACLE_SEED = 20261017


def run_cli(stdin: str | bytes, timeout: float = 30.0) -> tuple[str, str, int]:
    data = stdin.encode() if isinstance(stdin, str) else stdin
    proc = subprocess.run(
        [sys.executable, str(MAIN)],
        input=data,
        capture_output=True,
        timeout=timeout,
    )
    return proc.stdout.decode(), proc.stderr.decode(), proc.returncode


def assert_invariants(warehouses: dict[str, tuple[int, int, int]], q_total: int, stdout: str) -> None:
    """B-INV: sum, bounds, used-means-positive, cost consistency, id order."""
    lines = stdout.splitlines()
    if lines == ["-1"]:
        assert sum(s for s, _, _ in warehouses.values()) < q_total
        return
    count, cost = map(int, lines[0].split())
    alloc: dict[str, int] = {}
    for line in lines[1:]:
        wid, qty = line.split()
        alloc[wid] = int(qty)
    assert len(alloc) == count
    assert sum(alloc.values()) == q_total
    assert [w for w, _ in (line.split() for line in lines[1:])] == sorted(alloc)
    for wid, qty in alloc.items():
        stock, _fixed, _unit = warehouses[wid]
        assert 1 <= qty <= stock
    assert sum(
        warehouses[wid][1] + qty * warehouses[wid][2] for wid, qty in alloc.items()
    ) == cost


# ---------------------------------------------------------------------------
# Acceptance fixtures E-B1..E-B5 (byte-exact stdout comparisons)
# ---------------------------------------------------------------------------

FIXTURES: dict[str, tuple[str, str]] = {
    # E-B1: the official example from the brief - highest priority.
    "E-B1_official_example": (
        "3 7\nAU 5 8 2\nCN 7 20 1\nUS 4 3 4\n",
        "1 27\nCN 7\n",
    ),
    # E-B2: total stock below Q -> -1.
    "E-B2_infeasible": (
        "1 5\nA 4 0 0\n",
        "-1\n",
    ),
    # E-B3: cost tie broken by (id, qty) pairs - [(A,1),(B,2)] < [(A,2),(B,1)].
    "E-B3_qty_tiebreak": (
        "2 3\nA 2 0 0\nB 2 0 0\n",
        "2 0\nA 1\nB 2\n",
    ),
    # E-B4: zero-stock warehouse is unusable.
    "E-B4_zero_stock": (
        "2 1\nA 0 1 1\nB 1 1 1\n",
        "1 2\nB 1\n",
    ),
    # E-B5: equal single-warehouse cost -> smaller id wins.
    "E-B5_id_tiebreak": (
        "2 2\nA 2 5 1\nB 2 5 1\n",
        "1 7\nA 2\n",
    ),
}

# E-B6b: 30 identical warehouses, stock 70 each. Fewest warehouses =
# ceil(2000/70) = 29; lex-smallest allocation fills W01 with the minimum
# feasible 40 (= 2000 - 28*70) and W02..W29 with 70.
EB6B_INPUT = "30 2000\n" + "".join(f"W{i:02d} 70 1000000 1000000\n" for i in range(1, 31))
EB6B_EXPECTED = (
    "29 2029000000\n"
    + "W01 40\n"
    + "".join(f"W{i:02d} 70\n" for i in range(2, 30))
)


@pytest.mark.parametrize("stdin,expected", FIXTURES.values(), ids=FIXTURES.keys())
def test_acceptance_fixtures(stdin: str, expected: str) -> None:
    stdout, stderr, code = run_cli(stdin)
    assert code == 0, f"exit={code}, stderr={stderr!r}"
    assert stderr == ""
    assert stdout == expected


def test_eb6b_many_warehouses_byte_exact() -> None:
    stdout, stderr, code = run_cli(EB6B_INPUT)
    assert code == 0, f"exit={code}, stderr={stderr!r}"
    assert stdout == EB6B_EXPECTED


@pytest.mark.parametrize("stdin,_", FIXTURES.values(), ids=FIXTURES.keys())
def test_fixture_invariants(stdin: str, _: str) -> None:
    lines = stdin.splitlines()
    _w, q_total = map(int, lines[0].split())
    warehouses = {}
    for ln in lines[1:]:
        wid, s, f, u = ln.split()
        warehouses[wid] = (int(s), int(f), int(u))
    stdout, _, code = run_cli(stdin)
    assert code == 0
    assert_invariants(warehouses, q_total, stdout)


def test_eb6b_invariants() -> None:
    stdout, _, code = run_cli(EB6B_INPUT)
    assert code == 0
    warehouses = {f"W{i:02d}": (70, 10**6, 10**6) for i in range(1, 31)}
    assert_invariants(warehouses, 2000, stdout)


# ---------------------------------------------------------------------------
# B-ORACLE: exhaustive-enumeration ground truth on small random instances
# ---------------------------------------------------------------------------


def oracle_solve(
    warehouses: list[tuple[str, int, int, int]], q_total: int
) -> tuple[int, int, tuple[tuple[str, int], ...]] | None:
    """Ground truth: enumerate every feasible allocation, keep the minimum
    by (warehouse count, cost, allocation list). Deliberately independent
    of the DP and of the unit-cost greedy lemma."""
    n = len(warehouses)
    suffix_stock = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_stock[i] = suffix_stock[i + 1] + warehouses[i][1]

    best: tuple[int, int, tuple[tuple[str, int], ...]] | None = None
    alloc: list[tuple[str, int]] = []

    def rec(i: int, k: int, cost: int, q_rem: int) -> None:
        nonlocal best
        # Costs are non-negative, so an already-dominated (k, cost) prefix
        # can never catch up with the incumbent.
        if best is not None and (k > best[0] or (k == best[0] and cost > best[1])):
            return
        if q_rem == 0:
            if k > 0:
                key = (k, cost, tuple(alloc))
                if best is None or key < best:
                    best = key
            return
        if i == n or suffix_stock[i] < q_rem:
            return
        wid, stock, fixed, unit = warehouses[i]
        rec(i + 1, k, cost, q_rem)  # warehouse i unused
        for a in range(1, min(stock, q_rem) + 1):
            alloc.append((wid, a))
            rec(i + 1, k + 1, cost + fixed + a * unit, q_rem - a)
            alloc.pop()

    rec(0, 0, 0, q_total)
    return best


def gen_instance(rng: random.Random) -> tuple[str, list[tuple[str, int, int, int]], int]:
    """Small random instance; ids distinct, input order shuffled so the
    CLI's internal sort is exercised."""
    w = rng.randint(1, 8)
    q_total = rng.randint(1, 12)
    pool = [f"{c}{d}" for c in "ABCDE" for d in "1234"]
    ids = rng.sample(pool, w)
    warehouses = sorted(
        (wid, rng.randint(0, 6), rng.randint(0, 8), rng.randint(0, 8)) for wid in ids
    )
    lines = [f"{w} {q_total}"] + [
        f"{wid} {s} {f} {u}" for wid, s, f, u in warehouses
    ]
    rng.shuffle(lines[1:])
    return "\n".join(lines) + "\n", warehouses, q_total


def test_oracle_cross_validation() -> None:
    rng = random.Random(ORACLE_SEED)
    infeasible_seen = 0
    for case in range(ORACLE_CASES):
        stdin, warehouses, q_total = gen_instance(rng)
        stdout, stderr, code = taskb_main.run(stdin.encode())
        assert code == 0 and stderr == b"", f"case {case}: exit={code} stderr={stderr!r}"

        best = oracle_solve(warehouses, q_total)
        if best is None:
            expected = "-1\n"
            infeasible_seen += 1
        else:
            k, cost, alloc = best
            expected = f"{k} {cost}\n" + "".join(f"{wid} {a}\n" for wid, a in alloc)
        assert stdout.decode() == expected, f"case {case}:\n{stdin}\ngot:\n{stdout.decode()}"
        assert_invariants({w[0]: w[1:] for w in warehouses}, q_total, stdout.decode())
    assert infeasible_seen > 0, "oracle set should exercise the -1 path"


# ---------------------------------------------------------------------------
# E-B6a: upper-bound size performance smoke (W=30, Q=2000, stock=2000 each)
# ---------------------------------------------------------------------------


def gen_perf_input() -> str:
    return "30 2000\n" + "".join(f"W{i:02d} 2000 0 1\n" for i in range(1, 31))


def test_perf_upper_bound_under_5s() -> None:
    # Reuse the committed-location fixture (gitignored, regenerable via
    # B/tests/gen_perf_fixture.py); generate it in place if missing.
    fixture = HERE / "tests" / "fixtures" / "perf_max.txt"
    if not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(gen_perf_input())

    start = time.perf_counter()
    with fixture.open("rb") as fh:
        proc = subprocess.run(
            [sys.executable, str(MAIN)],
            stdin=fh,
            capture_output=True,
            timeout=30,
        )
    elapsed = time.perf_counter() - start

    assert proc.returncode == 0
    assert proc.stdout.decode() == "1 2000\nW01 2000\n"
    assert elapsed < PERF_LIMIT_S, f"took {elapsed:.3f}s (limit {PERF_LIMIT_S}s)"
