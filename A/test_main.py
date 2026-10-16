"""End-to-end, property and performance tests for Task A (A/main.py).

Every case drives the real CLI in a subprocess and compares stdout
byte-for-byte against the acceptance fixtures in A/acceptance.md.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parent / "main.py"
LINE_RE = re.compile(r"^(OK|REJECTED|DUPLICATE) (\d+) (\d+)$")

PERF_N = 200_000
PERF_SEED = 20261017
PERF_LIMIT_S = 2.0


def run_cli(stdin: str | bytes, timeout: float = 30.0) -> tuple[str, str, int]:
    data = stdin.encode() if isinstance(stdin, str) else stdin
    proc = subprocess.run(
        [sys.executable, str(MAIN)],
        input=data,
        capture_output=True,
        timeout=timeout,
    )
    return proc.stdout.decode(), proc.stderr.decode(), proc.returncode


def gen_perf_stream(n: int = PERF_N, seed: int = PERF_SEED) -> bytes:
    """Deterministic stream of n syntactically valid commands.

    Syntactically valid on purpose: every line exercises the full hot path
    (idempotency lookup + semantic check), which is the worst case.
    """
    rng = random.Random(seed)
    orders = [f"o{i}".encode() for i in range(5_000)]
    cmds = [b"RESERVE", b"RELEASE", b"SHIP", b"RESTOCK"]
    lines = [f"1000000 {n}".encode()]
    for i in range(n):
        cmd = cmds[rng.randrange(4)]
        qty = rng.randrange(1, 50)
        if cmd == b"RESTOCK":
            lines.append(b"RESTOCK e%d %d" % (i, qty))
        else:
            lines.append(b"%s e%d %s %d" % (cmd, i, orders[rng.randrange(5_000)], qty))
    return b"\n".join(lines) + b"\n"


# ---------------------------------------------------------------------------
# Acceptance fixtures E1-E8a (byte-exact stdout comparisons)
# ---------------------------------------------------------------------------

FIXTURES: dict[str, tuple[str, str]] = {
    # E1: the official example from the brief - highest priority.
    "E1_official_example": (
        "10 6\n"
        "RESERVE e1 o100 4\n"
        "RESERVE e2 o200 7\n"
        "SHIP e3 o100 2\n"
        "RELEASE e4 o100 2\n"
        "RESTOCK e5 3\n"
        "RESERVE e2 o999 1\n",
        "OK 10 4\n"
        "REJECTED 10 4\n"
        "OK 8 2\n"
        "OK 8 0\n"
        "OK 11 0\n"
        "DUPLICATE 11 0\n"
        "OPEN 0\n",
    ),
    # E2a: reserve -> ship everything -> restock.
    "E2a_full_cycle": (
        "5 3\nRESERVE e1 o1 5\nSHIP e2 o1 5\nRESTOCK e3 3\n",
        "OK 5 5\nOK 0 0\nOK 3 0\nOPEN 0\n",
    ),
    # E2b: partial release then ship the remainder.
    "E2b_partial_release": (
        "5 3\nRESERVE e1 o1 5\nRELEASE e2 o1 3\nSHIP e3 o1 2\n",
        "OK 5 5\nOK 5 2\nOK 3 0\nOPEN 0\n",
    ),
    # E3a: RELEASE beyond the reservation is rejected, state untouched.
    "E3a_over_release": (
        "3 3\nRESERVE e1 o1 2\nRELEASE e2 o1 3\nSHIP e3 o1 1\n",
        "OK 3 2\nREJECTED 3 2\nOK 2 1\nOPEN 1\no1 1\n",
    ),
    # E3b: over-reserve, then SHIP against an order with no reservation.
    "E3b_ship_without_reservation": (
        "3 2\nRESERVE e1 o1 4\nSHIP e2 o1 1\n",
        "REJECTED 3 0\nREJECTED 3 0\nOPEN 0\n",
    ),
    # E4a: a rejected event is still processed -> replay is DUPLICATE.
    "E4a_rejected_replay": (
        "3 2\nRESERVE e1 o1 99\nRESERVE e1 o1 1\n",
        "REJECTED 3 0\nDUPLICATE 3 0\nOPEN 0\n",
    ),
    # E5a: same event_id with a different payload -> DUPLICATE, no change.
    "E5a_replay_different_payload": (
        "10 2\nRESERVE e1 o1 2\nSHIP e1 o1 2\n",
        "OK 10 2\nDUPLICATE 10 2\nOPEN 1\no1 2\n",
    ),
    # E6a: qty=0 is a semantic rejection (event recorded); qty=-1 fails
    # the syntax layer (not recorded).
    "E6a_zero_and_negative_qty": (
        "5 3\nRESERVE e1 o1 0\nRESERVE e2 o1 2\nRESTOCK e3 -1\n",
        "REJECTED 5 0\nOK 5 2\nREJECTED 5 2\nOPEN 1\no1 2\n",
    ),
    # E6b: non-numeric qty is a syntax failure, so e1 is NOT recorded and
    # its first valid execution succeeds; unknown command is rejected.
    "E6b_bad_qty_not_recorded": (
        "5 3\nRESERVE e1 o1 x\nRESERVE e1 o1 2\nFROBNICATE e9 o1 1\n",
        "REJECTED 5 0\nOK 5 2\nREJECTED 5 2\nOPEN 1\no1 2\n",
    ),
    # E6e: N is authoritative - the extra line is ignored entirely.
    "E6e_extra_lines_ignored": (
        "5 1\nRESERVE e1 o1 2\nRESERVE e2 o1 2\n",
        "OK 5 2\nOPEN 1\no1 2\n",
    ),
    # E7a: open reservations sorted by order_id; fully-shipped order drops out.
    "E7a_open_sorted": (
        "10 4\nRESERVE e1 oB 2\nRESERVE e2 oA 3\nRESERVE e3 oC 1\nSHIP e4 oB 2\n",
        "OK 10 2\nOK 10 5\nOK 10 6\nOK 8 4\nOPEN 2\noA 3\noC 1\n",
    ),
    # E8a: 1e12 boundary values (Python ints, no overflow).
    "E8a_large_numbers": (
        "1000000000000 2\nRESTOCK e1 1000000000000\nRESERVE e2 o1 1000000000000\n",
        "OK 2000000000000 0\nOK 2000000000000 1000000000000\n"
        "OPEN 1\no1 1000000000000\n",
    ),
}


@pytest.mark.parametrize("stdin,expected", FIXTURES.values(), ids=FIXTURES.keys())
def test_acceptance_fixtures(stdin: str, expected: str) -> None:
    stdout, stderr, code = run_cli(stdin)
    assert code == 0, f"exit={code}, stderr={stderr!r}"
    assert stderr == ""
    assert stdout == expected


def test_empty_stream_outputs_open_zero() -> None:
    # E6c / spec A8.
    stdout, stderr, code = run_cli(b"")
    assert (stdout, stderr, code) == ("OPEN 0\n", "", 0)


def test_invalid_header_exits_2_with_stderr() -> None:
    # E6d / spec A7: no stdout, one stderr line, exit code 2.
    stdout, stderr, code = run_cli("xx\n")
    assert stdout == ""
    assert code == 2
    assert stderr.count("\n") == 1 and stderr.strip() != ""


# ---------------------------------------------------------------------------
# Property tests: shadow-model invariants (A-INV) and replay (A-REPLAY)
# ---------------------------------------------------------------------------


def shadow_run(lines: list[str], stock: int) -> tuple[list[str], dict[str, int], int]:
    """Independent shadow model used to cross-check the CLI.

    Deliberately re-derived from spec section 4 rather than imported from
    main.py, so a bug in one is caught by the other.
    """
    on_hand = stock
    reserved: dict[str, int] = {}
    processed: set[str] = set()
    verdicts: list[str] = []
    for line in lines:
        parts = line.split()
        arity = {"RESERVE": 4, "RELEASE": 4, "SHIP": 4, "RESTOCK": 3}
        if not parts or parts[0] not in arity or len(parts) != arity[parts[0]]:
            verdicts.append("REJECTED")
            continue
        cmd, eid = parts[0], parts[1]
        oid = parts[2] if cmd != "RESTOCK" else ""
        qty_tok = parts[-1]
        if not eid.isascii() or not oid.isascii() or not re.fullmatch(r"[0-9]+", qty_tok):
            verdicts.append("REJECTED")
            continue
        if eid in processed:
            verdicts.append("DUPLICATE")
            continue
        processed.add(eid)
        qty = int(qty_tok)
        if qty < 1:
            verdicts.append("REJECTED")
        elif cmd == "RESTOCK":
            on_hand += qty
            verdicts.append("OK")
        elif cmd == "RESERVE":
            if on_hand - sum(reserved.values()) >= qty:
                reserved[oid] = reserved.get(oid, 0) + qty
                verdicts.append("OK")
            else:
                verdicts.append("REJECTED")
        else:
            cur = reserved.get(oid, 0)
            if cur < qty:
                verdicts.append("REJECTED")
            else:
                reserved[oid] = cur - qty
                if reserved[oid] == 0:
                    del reserved[oid]
                if cmd == "SHIP":
                    on_hand -= qty
                verdicts.append("OK")
        # INV1/INV2 after every single command.
        assert all(v >= 0 for v in reserved.values()), "INV1 violated"
        assert sum(reserved.values()) <= on_hand, "INV2 violated (oversell)"
    return verdicts, reserved, on_hand


def random_command_stream(rng: random.Random, n: int) -> list[str]:
    """Mixed valid/invalid stream: bad arity, bad qty, unknown commands,
    duplicate event_ids included."""
    lines = []
    for i in range(n):
        roll = rng.random()
        eid = f"e{rng.randrange(n // 2)}"  # heavy event_id reuse -> duplicates
        oid = f"o{rng.randrange(50)}"
        qty = rng.randrange(0, 20)
        cmd = rng.choice(["RESERVE", "RELEASE", "SHIP", "RESTOCK"])
        if roll < 0.05:
            lines.append(f"FROB {eid} {oid} {qty}")  # unknown command
        elif roll < 0.10:
            lines.append(f"RESERVE {eid} {oid}")  # wrong arity
        elif roll < 0.15:
            lines.append(f"{cmd} {eid} {oid} {rng.choice(['-1', 'x', '3.0', '+3'])}")
        elif cmd == "RESTOCK":
            lines.append(f"RESTOCK {eid} {qty}")
        else:
            lines.append(f"{cmd} {eid} {oid} {qty}")
    return lines


def test_shadow_model_invariants_on_random_stream() -> None:
    # A-INV: 10k mixed commands; CLI output must match the shadow model
    # line-by-line, and the final OPEN section must match shadow state.
    rng = random.Random(42)
    lines = random_command_stream(rng, 10_000)
    stdin = f"100 {len(lines)}\n" + "\n".join(lines) + "\n"
    stdout, _, code = run_cli(stdin)
    assert code == 0

    verdicts, reserved, on_hand = shadow_run(lines, 100)
    out_lines = stdout.splitlines()
    assert len(out_lines) == len(lines) + 1 + len(reserved)

    for i, (line, verdict) in enumerate(zip(out_lines, verdicts)):
        m = LINE_RE.match(line)
        assert m, f"line {i} malformed: {line!r}"
        assert m.group(1) == verdict, f"line {i}: {line!r} != shadow {verdict}"
    assert out_lines[len(lines)] == f"OPEN {len(reserved)}"
    tail = out_lines[len(lines) + 1 :]
    assert tail == [f"{oid} {qty}" for oid, qty in sorted(reserved.items())]
    last = LINE_RE.match(out_lines[len(lines) - 1])
    assert int(last.group(2)) == on_hand
    assert int(last.group(3)) == sum(reserved.values())


def test_replay_second_pass_is_all_duplicate() -> None:
    # A-REPLAY: feeding the same syntactically valid stream twice yields
    # DUPLICATE for every replayed line and leaves the final state unchanged.
    stdin = FIXTURES["E1_official_example"][0]  # all lines syntactically valid
    cmds = stdin.splitlines()[1:]
    first_stdout, _, _ = run_cli(stdin)
    first_lines = first_stdout.splitlines()
    state_after_first = first_lines[len(cmds) - 1].split()[1:]  # on_hand, reserved

    doubled = f"10 {2 * len(cmds)}\n" + "\n".join(cmds + cmds) + "\n"
    stdout, _, code = run_cli(doubled)
    assert code == 0
    out_lines = stdout.splitlines()

    assert out_lines[: len(cmds)] == first_lines[: len(cmds)]
    for line in out_lines[len(cmds) : 2 * len(cmds)]:
        assert line.split()[0] == "DUPLICATE"
        assert line.split()[1:] == state_after_first  # INV4: state frozen
    assert out_lines[2 * len(cmds) :] == first_lines[len(cmds) :]  # same OPEN block


# ---------------------------------------------------------------------------
# Performance smoke (E8b / A-PERF)
# ---------------------------------------------------------------------------


def test_perf_200k_commands_under_2s() -> None:
    # Reuse the committed-location fixture (gitignored, regenerable via
    # A/tests/gen_perf_fixture.py); generate it in place if missing.
    fixture = MAIN.parent / "tests" / "fixtures" / "perf_200k.txt"
    if not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(gen_perf_stream())

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
    out_lines = proc.stdout.decode().splitlines()
    assert len(out_lines) >= PERF_N + 1  # one verdict per command + OPEN header
    assert out_lines[PERF_N].startswith("OPEN ")
    assert elapsed < PERF_LIMIT_S, f"took {elapsed:.3f}s (limit {PERF_LIMIT_S}s)"
