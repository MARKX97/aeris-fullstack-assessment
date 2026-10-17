"""Backend contract tests — acceptance criteria APP-SEED and APP-API-1..11.

One test per acceptance row so the pass/fail report maps 1:1 to
app/acceptance.md §1-§2. Uses httpx AsyncClient against a fresh Store per
test (fixture isolation — the process-wide singleton is never reused
across tests).
"""

from __future__ import annotations

import httpx
import pytest

import main as main_mod
from main import app
from store import Store

API = "http://test"


@pytest.fixture()
async def client():
    """Fresh Store per test.

    main.py holds a module-global `store` which this fixture swaps for a
    fresh instance — the route handlers resolve it at call time, so no
    dependency-injection plumbing is needed (the brief says do not overbuild).
    """
    saved = main_mod.store
    main_mod.store = Store()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=API) as ac:
        yield ac
    main_mod.store = saved


async def post_add(ac: httpx.AsyncClient, sku: str, qty: object, key: str, extra: dict | None = None) -> httpx.Response:
    body: dict = {"skuId": sku, "quantity": qty}
    if extra:
        body.update(extra)
    return await ac.post("/api/cart/items", json=body, headers={"Idempotency-Key": key})


def err_code(resp: httpx.Response) -> str:
    return resp.json()["error"]["code"]


# ---------------------------------------------------------------------------
# APP-SEED, APP-API-1, APP-API-2: product catalogue
# ---------------------------------------------------------------------------


async def test_product_returns_full_catalogue(client):
    resp = await client.get("/api/products/p-classic-tee")
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"] == {
        "id": "p-classic-tee",
        "name": "Classic Tee",
        "description": "A soft everyday tee. Three colours, three sizes.",
    }
    assert body["options"] == [
        {"id": "colour", "name": "Colour", "values": ["Red", "Blue", "Green"]},
        {"id": "size", "name": "Size", "values": ["S", "M", "L"]},
    ]
    assert len(body["skus"]) == 8
    by_id = {s["id"]: s for s in body["skus"]}
    assert ("Blue", "L") not in {(s["options"]["colour"], s["options"]["size"]) for s in body["skus"]}
    assert by_id["sku-blue-m"]["available"] == 0
    assert by_id["sku-red-s"] == {
        "id": "sku-red-s",
        "options": {"colour": "Red", "size": "S"},
        "price": 2900,
        "available": 10,
        "image": "/images/sku-red-s.png",
    }


async def test_unknown_product_404(client):
    resp = await client.get("/api/products/nope")
    assert resp.status_code == 404
    assert err_code(resp) == "PRODUCT_NOT_FOUND"


# ---------------------------------------------------------------------------
# APP-API-3..5, 9..11: add-to-cart success, idempotency, validation
# ---------------------------------------------------------------------------


async def test_add_to_cart_success(client):
    resp = await post_add(client, "sku-red-m", 2, "k1")
    assert resp.status_code == 201
    assert resp.json() == {
        "cart": {
            "items": [
                {"skuId": "sku-red-m", "quantity": 2, "unitPrice": 2900, "lineTotal": 5800}
            ],
            "totalItemCount": 2,
        }
    }
    # Stock 5 → 3 (APP-API-3).
    product = (await client.get("/api/products/p-classic-tee")).json()
    by_id = {s["id"]: s for s in product["skus"]}
    assert by_id["sku-red-m"]["available"] == 3


async def test_idempotent_replay_same_body(client):
    first = await post_add(client, "sku-red-m", 2, "k1")
    replay = await post_add(client, "sku-red-m", 2, "k1")
    assert replay.status_code == 200
    assert replay.json() == first.json()
    # Stock unchanged after replay (APP-API-4).
    product = (await client.get("/api/products/p-classic-tee")).json()
    by_id = {s["id"]: s for s in product["skus"]}
    assert by_id["sku-red-m"]["available"] == 3


async def test_idempotency_key_conflict(client):
    await post_add(client, "sku-red-m", 2, "k1")
    resp = await post_add(client, "sku-red-m", 3, "k1")  # same key, different body
    assert resp.status_code == 409
    assert err_code(resp) == "IDEMPOTENCY_KEY_CONFLICT"


async def test_idempotency_key_conflict_precedes_business_validation(client):
    # APP-API-11: key lookup happens before business rules, so a conflicting
    # key + unknown sku must yield 409, not 404.
    await post_add(client, "sku-red-m", 2, "k1")
    resp = await post_add(client, "sku-nope", 1, "k1")
    assert resp.status_code == 409
    assert err_code(resp) == "IDEMPOTENCY_KEY_CONFLICT"


async def test_missing_idempotency_key_400(client):
    resp = await client.post("/api/cart/items", json={"skuId": "sku-red-m", "quantity": 1})
    assert resp.status_code == 400
    assert err_code(resp) == "VALIDATION_ERROR"


async def test_quantity_zero_negative_noninteger(client):
    for bad in (0, -1, 1.5, "2"):
        resp = await post_add(client, "sku-red-m", bad, f"k-{bad!r}")
        assert resp.status_code == 400, f"quantity={bad!r} should be 400"
        assert err_code(resp) == "VALIDATION_ERROR"
    # "2.0" arrives as a JSON float literal: StrictInt must reject it too.
    raw = await client.post(
        "/api/cart/items",
        content=b'{"skuId": "sku-red-m", "quantity": 2.0}',
        headers={"Idempotency-Key": "k-2.0", "Content-Type": "application/json"},
    )
    assert raw.status_code == 400
    assert err_code(raw) == "VALIDATION_ERROR"


async def test_client_supplied_price_rejected(client):
    resp = await post_add(client, "sku-red-m", 1, "k-price", extra={"price": 100})
    assert resp.status_code == 400
    assert err_code(resp) == "VALIDATION_ERROR"


async def test_unknown_sku_404(client):
    resp = await post_add(client, "sku-nope", 1, "k-unknown")
    assert resp.status_code == 404
    assert err_code(resp) == "SKU_NOT_FOUND"


async def test_insufficient_stock_409(client):
    # APP-API-7: sku-green-l has available=2, request 3 → 409 with details.
    resp = await post_add(client, "sku-green-l", 3, "k-stock")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "INSUFFICIENT_STOCK"
    assert body["error"]["details"]["available"] == 2


async def test_cart_initially_empty(client):
    resp = await client.get("/api/cart")
    cart = resp.json()["cart"]
    assert cart["items"] == []
    assert cart["totalItemCount"] == 0


async def test_get_cart_reflects_adds(client):
    await post_add(client, "sku-red-m", 2, "k1")
    resp = await client.get("/api/cart")
    assert resp.status_code == 200
    assert resp.json()["cart"]["totalItemCount"] == 2


async def test_same_sku_different_keys_merges_lines(client):
    # AP14: same SKU via different keys → one merged line, stock decremented twice.
    await post_add(client, "sku-red-m", 2, "k1")
    second = await post_add(client, "sku-red-m", 1, "k2")
    assert second.status_code == 201
    cart = (await client.get("/api/cart")).json()["cart"]
    assert cart["items"] == [
        {"skuId": "sku-red-m", "quantity": 3, "unitPrice": 2900, "lineTotal": 8700}
    ]
    product = (await client.get("/api/products/p-classic-tee")).json()
    by_id = {s["id"]: s for s in product["skus"]}
    assert by_id["sku-red-m"]["available"] == 2  # 5 - 2 - 1
