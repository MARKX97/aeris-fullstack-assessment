"""Variant PDP backend — FastAPI app (routing + validation only).

Business rules live in store.py; this file defines the HTTP contract:
  GET  /api/products/{id}
  POST /api/cart/items   (Idempotency-Key header required)
  GET  /api/cart

Contract details: app/spec.md §5. Every failure returns the structured
error shape {"error": {"code", "message", "details"}} (spec §5) — FastAPI's
default 422 is remapped to 400 VALIDATION_ERROR so clients see one shape.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from store import ApiError, Store, payload_fingerprint

app = FastAPI(title="Variant PDP", version="1.0.0")
store = Store()  # process-wide singleton; tests override via app.dependency_overrides


class AddToCartRequest(BaseModel):
    """Request body contract (spec §5.2).

    model_config forbids extra fields: a client-supplied price/stock field
    is a 400, never silently ignored (server-side authority, spec §5.2).
    StrictInt enforces AP12: only a JSON integer literal is a valid quantity.
    """

    model_config = ConfigDict(extra="forbid")

    skuId: str
    # Integer literal only (AP12); ge=1 enforces the [1, ...] bound of spec
    # §5.2 at the contract layer, before any stock is read.
    quantity: StrictInt = Field(ge=1)


def _error_response(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


@app.exception_handler(RequestValidationError)
async def _validation_to_400(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Map Pydantic/FastAPI validation failures onto the structured 400.

    This includes a missing Idempotency-Key header and any body shape
    violation, so every 400 carries the same error envelope (spec §5).
    """
    return _error_response(400, "VALIDATION_ERROR", "Request failed input validation.", _details(exc))


def _details(exc: RequestValidationError) -> dict[str, Any]:
    out: list[dict[str, str]] = []
    for err in exc.errors():
        out.append(
            {
                "loc": ".".join(str(p) for p in err.get("loc", [])),
                "msg": str(err.get("msg", "")),
            }
        )
    return {"errors": out}


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort 500 — no stack traces leak to the client (spec §5)."""
    return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")


@app.get("/api/products/{product_id}")
async def get_product(product_id: str) -> dict[str, Any]:
    view = store.get_product_view(product_id)
    if view is None:
        raise ApiError("PRODUCT_NOT_FOUND", 404, f"No product with id {product_id!r}.")
    return view


@app.post("/api/cart/items", status_code=201)
async def add_to_cart(
    body: AddToCartRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> JSONResponse:
    # A replay returns 200 with the identical body, so the response is
    # always constructed explicitly (spec §5.2).
    status, payload = await store.add_to_cart(
        body.skuId,
        body.quantity,
        idempotency_key,
        payload_fingerprint(body.skuId, body.quantity),
    )
    return JSONResponse(status_code=status, content=payload)


@app.get("/api/cart")
async def get_cart() -> dict[str, Any]:
    return {"cart": store.get_cart_view()}


if __name__ == "__main__":
    # Kept out of the module top level so the test suite does not need
    # uvicorn installed to import the app.
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
