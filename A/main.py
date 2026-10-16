"""Task A - Inventory Reservation Ledger.

Single-SKU deterministic command processor. Reads ``S N`` followed by N
command lines from stdin, prints one verdict line per command, then the
open-reservation summary. Full contract: ``A/spec.md``; assumptions A1-A10
are documented there and summarised in ``A/README.md``.

Standard library only. Target complexity: O(N + U_o log U_o) time and
O(U_o + U_e) space, where U_o/U_e are the numbers of unique order/event IDs.
"""

from __future__ import annotations

import re
import sys

# qty and header fields must be plain ASCII digits: "-1", "+3", "3.0" and
# Unicode digits all fail the syntax layer (spec S4). Matching on bytes
# keeps the hot loop free of decoding.
_DIGITS_RE = re.compile(rb"[0-9]+")

# Command name -> token count. RESTOCK takes no order_id (spec A1: the
# official example `RESTOCK e5 3` only parses with the 3-token form).
_ARITY = {b"RESERVE": 4, b"RELEASE": 4, b"SHIP": 4, b"RESTOCK": 3}


def run(data: bytes) -> tuple[bytes, bytes, int]:
    """Process one full input stream.

    Returns ``(stdout_bytes, stderr_bytes, exit_code)``. Pure with respect
    to its argument so tests can drive it without a subprocess.
    """
    if not data.strip():
        # Spec A8: an empty stream is a degenerate but valid run.
        return b"OPEN 0\n", b"", 0

    lines = data.split(b"\n")
    header = lines[0].split()
    if (
        len(header) != 2
        or not _DIGITS_RE.fullmatch(header[0])
        or not _DIGITS_RE.fullmatch(header[1])
    ):
        # Spec A7: the header is the authoritative contract; refuse to guess.
        return b"", b"error: invalid header; expected '<S> <N>' as non-negative integers\n", 2

    on_hand = int(header[0])
    n = int(header[1])

    reserved: dict[bytes, int] = {}
    total_reserved = 0  # maintained incrementally: O(1) per command
    processed: set[bytes] = set()

    out: list[bytes] = []

    # Spec A7: trust N exactly - extra lines are ignored, missing lines
    # simply end the stream at EOF (slicing handles both).
    for line in lines[1 : n + 1]:
        parts = line.split()

        # --- Syntax layer (S1-S4). Failures are NOT recorded for
        # idempotency (spec A4/R3): a malformed line has no reliably
        # extractable event_id. ---
        if not parts or parts[0] not in _ARITY or len(parts) != _ARITY[parts[0]]:
            out.append(b"REJECTED %d %d" % (on_hand, total_reserved))
            continue

        cmd = parts[0]
        event_id = parts[1]
        order_id = parts[2] if cmd != b"RESTOCK" else b""
        qty_tok = parts[-1]
        if (
            not event_id.isascii()
            or not order_id.isascii()
            or not _DIGITS_RE.fullmatch(qty_tok)
        ):
            out.append(b"REJECTED %d %d" % (on_hand, total_reserved))
            continue

        # --- Idempotency (R1/R2). Any syntactically valid event is recorded
        # exactly once, whether it succeeds or is semantically rejected. ---
        if event_id in processed:
            out.append(b"DUPLICATE %d %d" % (on_hand, total_reserved))
            continue
        processed.add(event_id)

        # --- Semantic layer (M1/M2). ---
        qty = int(qty_tok)
        verdict: bytes
        if qty < 1:
            verdict = b"REJECTED"
        elif cmd == b"RESTOCK":
            on_hand += qty
            verdict = b"OK"
        elif cmd == b"RESERVE":
            if on_hand - total_reserved >= qty:  # available stock check
                reserved[order_id] = reserved.get(order_id, 0) + qty
                total_reserved += qty
                verdict = b"OK"
            else:
                verdict = b"REJECTED"
        else:  # RELEASE or SHIP: bounded by this order's open reservation
            current = reserved.get(order_id, 0)
            if current < qty:
                verdict = b"REJECTED"
            else:
                remaining = current - qty
                if remaining:
                    reserved[order_id] = remaining
                else:
                    del reserved[order_id]  # INV1: zero keys are cleaned up
                total_reserved -= qty
                if cmd == b"SHIP":
                    on_hand -= qty  # INV5: on_hand and reservation drop together
                verdict = b"OK"

        out.append(verdict + b" %d %d" % (on_hand, total_reserved))

    # Summary: header-first, orders sorted byte-wise (spec A2/A5).
    out.append(b"OPEN %d" % len(reserved))
    for oid in sorted(reserved):
        out.append(oid + b" %d" % reserved[oid])

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
