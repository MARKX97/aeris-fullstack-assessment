"""Generate the performance fixture referenced by B/acceptance.md (E-B6a).

Usage:
    python3 B/tests/gen_perf_fixture.py   # writes B/tests/fixtures/perf_max.txt
    time python3 B/main.py < B/tests/fixtures/perf_max.txt

Deterministic. Keep in sync with gen_perf_input() in B/test_main.py -
same W, Q and warehouse values.
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    lines = ["30 2000"] + [f"W{i:02d} 2000 0 1" for i in range(1, 31)]
    out = Path(__file__).resolve().parent / "fixtures" / "perf_max.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out} (W=30, Q=2000, stock=2000 each)")


if __name__ == "__main__":
    main()
