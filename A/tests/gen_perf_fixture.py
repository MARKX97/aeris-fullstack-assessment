"""Generate the performance fixture referenced by A/acceptance.md (A-PERF).

Usage:
    python3 A/tests/gen_perf_fixture.py   # writes A/tests/fixtures/perf_200k.txt
    time python3 A/main.py < A/tests/fixtures/perf_200k.txt

Deterministic (fixed seed). Keep in sync with gen_perf_stream() in
A/test_main.py - same seed, same N, same distribution.
"""

from __future__ import annotations

import random
from pathlib import Path

N = 200_000
SEED = 20261017


def main() -> None:
    rng = random.Random(SEED)
    orders = [f"o{i}" for i in range(5_000)]
    cmds = ["RESERVE", "RELEASE", "SHIP", "RESTOCK"]
    lines = [f"1000000 {N}"]
    for i in range(N):
        cmd = cmds[rng.randrange(4)]
        qty = rng.randrange(1, 50)
        if cmd == "RESTOCK":
            lines.append(f"RESTOCK e{i} {qty}")
        else:
            lines.append(f"{cmd} e{i} {orders[rng.randrange(5_000)]} {qty}")

    out = Path(__file__).resolve().parent / "fixtures" / "perf_200k.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out} ({N} commands, seed={SEED})")


if __name__ == "__main__":
    main()
