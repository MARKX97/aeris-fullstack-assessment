/** Variant PDP — UI state machine (spec §8.1).

* All nine states are observable here:
*   LOADING → READY/LOAD_ERROR on mount; retry loops back to LOADING.
*   READY·未选全 / 非法组合 / 缺货 / 可选 drive button enablement.
*   ADDING disables the button (aria-busy) and swallows repeat clicks;
*   success/error announce via aria-live and are retryable.
*   A stale (newer) stock value in the add-to-cart response refreshes the
*   SKU in place — no page reload (STALE 恢复).
*/

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiFailure, addToCart, fetchProduct } from '../api/client'
import type { Cart, ProductView, Sku } from '../api/types'
import {
  buildComboMatrix,
  clampQuantity,
  formatPrice,
  resolveSku,
  valueExistsInMatrix,
} from '../domain/variant'
import type { AddState, LoadState } from '../domain/variant'

const PRODUCT_ID = 'p-classic-tee'

/** Cryptographically random idempotency key per add-attempt (fresh on retry
 * of a *failed* add is correct: failures are not cached server-side, so a
 * new key can never collide with a cached success. */
function newIdempotencyKey(): string {
  return `add-${globalThis.crypto.randomUUID()}`
}

export function ProductPage() {
  // --- product load state machine --------------------------------------
  const [loadState, setLoadState] = useState<LoadState>('LOADING')
  const [product, setProduct] = useState<ProductView | null>(null)
  const [cart, setCart] = useState<Cart>({ items: [], totalItemCount: 0 })

  // --- variant selection -----------------------------------------------
  const [selection, setSelection] = useState<Record<string, string>>({})
  const [quantity, setQuantity] = useState(1)
  // Display string for the quantity input. Kept separate from `quantity`
  // so clearing the field mid-edit is possible on a controlled number
  // input (React would otherwise restore the old value on every keystroke
  // and "clear + type 3" would compose into "13").
  const [qtyText, setQtyText] = useState('1')

  // --- add-to-cart state machine ----------------------------------------
  const [addState, setAddState] = useState<AddState>({ phase: 'IDLE' })
  const addInFlight = useRef(false)
  const pendingKeyRef = useRef<string | null>(null)

  const loadProduct = useCallback(async () => {
    setLoadState('LOADING')
    try {
      const view = await fetchProduct(PRODUCT_ID)
      setProduct(view)
      setLoadState('READY')
    } catch {
      setLoadState('LOAD_ERROR')
    }
  }, [])

  useEffect(() => {
    void loadProduct()
  }, [loadProduct])

  const matrix = useMemo(
    () => (product ? buildComboMatrix(product.skus) : new Map<string, Sku>()),
    [product],
  )
  const sku = useMemo(
    () => resolveSku(matrix, selection),
    [matrix, selection],
  )

  // Converge quantity on SKU change or stock refresh (spec §8.2). Switching
  // SKUs *converges* into [1, min(q, available)] — it does not reset to 1;
  // reset-to-1 happens only after a successful add (spec §8.2).
  const available = sku?.available ?? 0
  useEffect(() => {
    setQuantity((q) => clampQuantity(q, available))
  }, [available])
  // Keep the displayed text in sync with programmatic quantity changes.
  useEffect(() => {
    setQtyText(String(quantity))
  }, [quantity])

  const selectOption = (dimId: string, value: string) => {
    setSelection((prev) => ({ ...prev, [dimId]: value }))
    // No quantity reset here: convergence above is the single mechanism,
    // so no stale out-of-range value can leak into the new SKU's range.
  }

  const onAdd = useCallback(async () => {
    if (addInFlight.current || !sku) return // repeat-click guard (spec §8.2)
    addInFlight.current = true
    const key = newIdempotencyKey()
    pendingKeyRef.current = key
    setAddState({ phase: 'ADDING' })
    try {
      const { cart: updatedCart } = await addToCart(sku.id, quantity, key)
      setCart(updatedCart)
      setAddState({ phase: 'SUCCESS', totalItemCount: updatedCart.totalItemCount })
      setQuantity(1)
      setQtyText('1')
      // STALE 恢复: the server just decremented this SKU's stock; adopt the
      // new available locally so the UI never shows a stale count (spec §8.1).
      setProduct((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          skus: prev.skus.map((s) =>
            s.id === sku.id ? { ...s, available: Math.max(0, s.available - quantity) } : s,
          ),
        }
      })
    } catch (err) {
      if (pendingKeyRef.current !== key) return // a newer attempt owns the UI
      const failure =
        err instanceof ApiFailure
          ? err
          : new ApiFailure('INTERNAL_ERROR', 0, 'Unexpected error.', {})
      setAddState({
        phase: 'ERROR',
        code: failure.code,
        message: failure.message,
        retryable: failure.status !== 0 || failure.code === 'NETWORK_ERROR' || failure.status >= 500,
      })
    } finally {
      addInFlight.current = false
      if (pendingKeyRef.current === key) pendingKeyRef.current = null
    }
  }, [sku, quantity])

  const feedback =
    addState.phase === 'SUCCESS'
      ? `Added to cart. Cart now has ${addState.totalItemCount} item(s).`
      : addState.phase === 'ERROR'
        ? `Could not add to cart: ${addState.message}`
        : ''

  if (loadState === 'LOADING') {
    return (
      <main className="pdp-loading" aria-busy="true">
        <p>Loading product…</p>
      </main>
    )
  }
  if (loadState === 'LOAD_ERROR' || !product) {
    return (
      <main className="pdp-error">
        <p role="alert">Could not load the product.</p>
        <button type="button" onClick={() => void loadProduct()}>
          Retry
        </button>
      </main>
    )
  }

  const incomplete = Object.keys(selection).length < product.options.length
  const addDisabled =
    addState.phase === 'ADDING' || !sku || available <= 0

  return (
    <main className="pdp">
      <header className="pdp-header">
        <h1>{product.product.name}</h1>
        <p className="pdp-cart-count" aria-live="polite">
          Cart: {cart.totalItemCount}
        </p>
      </header>

      <div className="pdp-body">
        <figure className="pdp-image">
          <img
            src={sku?.image ?? '/images/placeholder.png'}
            alt={sku ? `${product.product.name} in ${Object.values(sku.options).join(', ')}` : `${product.product.name}`}
            width="360"
            height="360"
          />
        </figure>

        <section className="pdp-info">
          <p className="pdp-description">{product.product.description}</p>

          {product.options.map((dim) => (
            <fieldset key={dim.id} className="pdp-option-group">
              <legend>{dim.name}</legend>
              <div role="group" aria-label={dim.name}>
                {dim.values.map((value) => {
                  const disabled =
                    !valueExistsInMatrix(matrix, dim.id, value, omit(selection, dim.id))
                  const pressed = selection[dim.id] === value
                  return (
                    <button
                      key={value}
                      type="button"
                      className="pdp-option"
                      aria-pressed={pressed}
                      disabled={disabled}
                      onClick={() => selectOption(dim.id, value)}
                    >
                      {value}
                    </button>
                  )
                })}
              </div>
            </fieldset>
          ))}

          <p className="pdp-sku-status" role="status">
            {incomplete
              ? 'Select options to see price and stock.'
              : !sku
                ? 'This combination is not available.'
                : available === 0
                  ? 'Out of stock.'
                  : `In stock: ${available}`}
          </p>

          {sku && available > 0 && (
            <div className="pdp-quantity">
              <label htmlFor="qty">Quantity</label>
              <input
                id="qty"
                type="number"
                min={1}
                max={available}
                value={qtyText}
                onChange={(e) => {
                  const raw = e.target.value
                  if (raw === '') {
                    // Allow an empty field while the user is editing; the
                    // last valid quantity stays canonical until blur.
                    setQtyText('')
                    return
                  }
                  const parsed = Number.parseInt(raw, 10)
                  if (Number.isNaN(parsed)) return
                  const clamped = clampQuantity(parsed, available)
                  setQuantity(clamped)
                  setQtyText(String(clamped))
                }}
                onBlur={() => {
                  if (qtyText === '') setQtyText(String(quantity))
                }}
              />
            </div>
          )}

          <button
            type="button"
            className="pdp-add"
            disabled={addDisabled}
            aria-busy={addState.phase === 'ADDING'}
            onClick={() => void onAdd()}
          >
            {addState.phase === 'ADDING' ? 'Adding…' : 'Add to cart'}
          </button>

          {feedback && (
            <p className="pdp-feedback" role="status" aria-live="polite">
              {feedback}
            </p>
          )}
          {addState.phase === 'ERROR' && addState.retryable && (
            <button
              type="button"
              className="pdp-retry"
              onClick={() => void onAdd()}
            >
              Try again
            </button>
          )}

          <p className="pdp-price">
            {sku ? formatPrice(sku.price * quantity) : '—'}
          </p>
        </section>
      </div>
    </main>
  )
}

function omit(obj: Record<string, string>, key: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (k !== key) out[k] = v
  }
  return out
}
