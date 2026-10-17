"""APP-RACE + APP-INV: concurrency (no overselling) and invariants.

APP-RACE (acceptance.md §3): with sku-green-l at available=1, two concurrent
add-to-cart requests must produce exactly one 201 and one 409, final stock 0,
cart with exactly one line — 10 rounds all green.

AP13 makes this test meaningful: store.add_to_cart yields once inside the
critical section, so the second request truly queues on the lock instead of
the event loop serialising both without contention.

APP-INV: after every scenario, every SKU keeps available >= 0, and
idempotency guarantees at-most-once stock decrement per key.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

import main as main_mod
from main import app
from store import Store

API = "http://test"
ROUNDS = 10


@pytest.fixture()
async def client():
    saved = main_mod.store
    main_mod.store = Store()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=API) as ac:
        yield ac
    main_mod.store = saved


async def _add(ac: httpx.AsyncClient, sku: str, qty: int, key: str) -> httpx.Response:
    return await ac.post(
        "/api/cart/items",
        json={"skuId": sku, "quantity": qty},
        headers={"Idempotency-Key": key},
    )


async def _stock_of(ac: httpx.AsyncClient, sku: str) -> int:
    product = (await ac.get("/api/products/p-classic-tee")).json()
    return {s["id"]: s for s in product["skus"]}[sku]["available"]


async def test_race_final_unit_rounds(client):
    """APP-RACE: 10 rounds, each with a fresh store and sku-green-l set to 1.

    Each round is a genuine race: both requests pass validation and enter
    add_to_cart before either decrements. The lock + single yield point
    guarantee: exactly one 201, one 409, final stock 0.
    """
    for round_no in range(ROUNDS):
        store: Store = main_mod.store
        store._skus["sku-green-l"]["available"] = 1  # test hook: set final unit
        r1, r2 = await asyncio.gather(
            _add(client, "sku-green-l", 1, f"race-a-{round_no}"),
            _add(client, "sku-green-l", 1, f"race-b-{round_no}"),
        )
        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [201, 409], f"round {round_no}: got {statuses}"
        winner = r1 if r1.status_code == 201 else r2
        loser = r2 if r1.status_code == 201 else r1
        assert loser.json()["error"]["code"] == "INSUFFICIENT_STOCK"
        assert winner.json()["cart"]["totalItemCount"] == 1
        assert await _stock_of(client, "sku-green-l") == 0
        cart = (await client.get("/api/cart")).json()["cart"]
        assert len(cart["items"]) == 1
        assert cart["items"][0]["quantity"] == 1
        # Fresh store for the next round.
        main_mod.store = Store()


async def test_race_with_replays_interleaved(client):
    """Same-key replays racing the original request: exactly one decrement.

    Three concurrent requests sharing one key. The first reserves; the
    others replay the cached response. Stock must fall exactly once, total
    items 1, all replays return the same body.
    """
    store: Store = main_mod.store
    store._skus["sku-red-m"]["available"] = 1
    r1, r2, r3 = await asyncio.gather(
        _add(client, "sku-red-m", 1, "shared-key"),
        _add(client, "sku-red-m", 1, "shared-key"),
        _add(client, "sku-red-m", 1, "shared-key"),
    )
    # One request is the original (201); the other two are concurrent replays
    # that must return the cached snapshot (200) with the identical body.
    statuses = sorted([r1.status_code, r2.status_code, r3.status_code])
    assert statuses == [200, 200, 201]
    bodies = [r.json() for r in (r1, r2, r3)]
    assert bodies[0] == bodies[1] == bodies[2]
    assert await _stock_of(client, "sku-red-m") == 0
    cart = (await client.get("/api/cart")).json()["cart"]
    assert cart["totalItemCount"] == 1


async def test_invariants_after_full_scenario(client):
    """APP-INV: full mixed scenario then assert available >= 0 for all SKUs.

    Also covers APP-INV3: a replayed key never decrements twice, even when
    interleaved with other traffic.
    """
    await _add(client, "sku-red-s", 10, "inv-1")  # exact final stock
    replay = await _add(client, "sku-red-s", 10, "inv-1")
    assert replay.status_code == 200
    over = await _add(client, "sku-red-s", 1, "inv-2")
    assert over.status_code == 409
    assert await _stock_of(client, "sku-red-s") == 0
    # All SKUs still >= 0 and cart is consistent.
    product = (await client.get("/api/products/p-classic-tee")).json()
    for sku in product["skus"]:
        assert sku["available"] >= 0, f"{sku['id']} went negative"
    cart = (await client.get("/api/cart")).json()["cart"]
    assert cart["items"][0]["skuId"] == "sku-red-s"
    assert cart["items"][0]["quantity"] == 10
