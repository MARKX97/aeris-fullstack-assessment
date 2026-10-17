"""Variant PDP backend — domain model and in-memory storage.

Single process, single anonymous cart (spec §3, AP5). Concurrency safety
comes from one asyncio.Lock guarding the whole
idempotency-lookup → stock-check → reserve → record critical section
(spec §7): the check and the decrement can never be interleaved, so no
TOCTOU window exists. A production deployment would swap this for DB row
locks; the correspondence is documented in the root README.

Seed data (spec §4) is deterministic because tests and the frontend demo
depend on exact values.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from typing import Any

# ---------------------------------------------------------------------------
# Structured error (spec §5) — the single error shape every endpoint returns.
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """Raised anywhere in a handler; the router maps it to the JSON shape."""

    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.message = message
        self.details = details or {}


# ---------------------------------------------------------------------------
# Seed data (spec §4). 3x3 matrix, 8 SKUs: Blue+L does not exist and
# sku-blue-m is the out-of-stock SKU.
# ---------------------------------------------------------------------------

PRODUCT_ID = "p-classic-tee"
PRODUCT_NAME = "Classic Tee"
PRODUCT_DESCRIPTION = "A soft everyday tee. Three colours, three sizes."

PRODUCT_OPTIONS: list[dict[str, Any]] = [
    {"id": "colour", "name": "Colour", "values": ["Red", "Blue", "Green"]},
    {"id": "size", "name": "Size", "values": ["S", "M", "L"]},
]

_SEED: list[dict[str, Any]] = [
    {"id": "sku-red-s", "colour": "Red", "size": "S", "price": 2900, "available": 10},
    {"id": "sku-red-m", "colour": "Red", "size": "M", "price": 2900, "available": 5},
    {"id": "sku-red-l", "colour": "Red", "size": "L", "price": 2900, "available": 3},
    {"id": "sku-blue-s", "colour": "Blue", "size": "S", "price": 3100, "available": 8},
    {"id": "sku-blue-m", "colour": "Blue", "size": "M", "price": 3100, "available": 0},
    {"id": "sku-green-s", "colour": "Green", "size": "S", "price": 2700, "available": 6},
    {"id": "sku-green-m", "colour": "Green", "size": "M", "price": 2700, "available": 4},
    {"id": "sku-green-l", "colour": "Green", "size": "L", "price": 2700, "available": 2},
]


def payload_fingerprint(sku_id: str, quantity: int) -> str:
    """Stable fingerprint of the parsed request body (spec §6).

    Canonical JSON with sorted keys, then sha256. Computed from the Pydantic
    model's own fields, so a semantically identical body always matches
    regardless of the client's field order or formatting.
    """
    canonical = json.dumps({"skuId": sku_id, "quantity": quantity}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Store — the single source of truth. Every mutation runs under one lock.
# ---------------------------------------------------------------------------


class Store:
    """In-memory catalogue + cart + idempotency cache.

    Lifetimes (all = process lifetime, by design):
      - stock and cart: fine for the exercise; restarting resets the demo.
      - idempotency cache: a known, documented limitation (AP6).
    """

    def __init__(self) -> None:
        self._skus: dict[str, dict[str, Any]] = {
            sku["id"]: {**sku, "options": {"colour": sku["colour"], "size": sku["size"]}}
            for sku in _SEED
        }
        self._cart: dict[str, int] = {}  # sku_id → quantity; insertion order kept
        # Idempotency-Key → (payload fingerprint, response snapshot) (spec §6).
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    # -- reads (synchronous: no awaits inside → never observe a torn state) --

    def get_product_view(self, product_id: str) -> dict[str, Any] | None:
        if product_id != PRODUCT_ID:
            return None
        skus = [
            {
                "id": sku["id"],
                "options": sku["options"],
                "price": sku["price"],
                "available": sku["available"],
                "image": f"/images/{sku['id']}.png",
            }
            for sku in self._skus.values()
        ]
        return {
            "product": {
                "id": PRODUCT_ID,
                "name": PRODUCT_NAME,
                "description": PRODUCT_DESCRIPTION,
            },
            "options": PRODUCT_OPTIONS,
            "skus": skus,
        }

    def get_cart_view(self) -> dict[str, Any]:
        items = [
            {
                "skuId": sku_id,
                "quantity": qty,
                "unitPrice": self._skus[sku_id]["price"],
                "lineTotal": self._skus[sku_id]["price"] * qty,
            }
            for sku_id, qty in self._cart.items()
        ]
        return {
            "items": items,
            "totalItemCount": sum(self._cart.values()),
        }

    def available_of(self, sku_id: str) -> int:
        return self._skus[sku_id]["available"]

    # -- writes -------------------------------------------------------------

    async def add_to_cart(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        fingerprint: str,
    ) -> tuple[int, dict[str, Any]]:
        """Reserve stock and add to the cart, exactly once per idempotency key.

        Returns (status_code, body): 201 on first success, 200 + the very
        same body on replay. Failures raise ApiError and are NOT cached
        (spec §6 — a retry after a failure is legal).
        """
        async with self._lock:
            # AP13: a yield point inside the critical section. Without it the
            # single-threaded event loop would never switch tasks mid-request
            # and the APP-RACE test could not tell a real lock from a no-op.
            await asyncio.sleep(0)

            # Key lookup precedes business validation (AP12): a replayed or
            # conflicting key must never fall through to SKU_NOT_FOUND etc.
            if idempotency_key in self._idempotency:
                cached_fp, snapshot = self._idempotency[idempotency_key]
                if cached_fp != fingerprint:
                    raise ApiError(
                        "IDEMPOTENCY_KEY_CONFLICT",
                        409,
                        "This Idempotency-Key was already used with a different request body.",
                    )
                return 200, copy.deepcopy(snapshot)

            sku = self._skus.get(sku_id)
            if sku is None:
                raise ApiError(
                    "SKU_NOT_FOUND", 404, f"No SKU with id {sku_id!r}."
                )
            if quantity > sku["available"]:
                raise ApiError(
                    "INSUFFICIENT_STOCK",
                    409,
                    f"Only {sku['available']} unit(s) of {sku_id} available.",
                    details={"available": sku["available"]},
                )

            # Check and decrement share this critical section — no TOCTOU.
            sku["available"] -= quantity
            self._cart[sku_id] = self._cart.get(sku_id, 0) + quantity  # AP14 merge

            snapshot = {"cart": self.get_cart_view()}
            # Cache only on success (spec §6).
            self._idempotency[idempotency_key] = (fingerprint, copy.deepcopy(snapshot))
            return 201, snapshot
