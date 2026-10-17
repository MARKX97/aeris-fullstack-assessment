/** Typed fetch wrapper for the Variant PDP API.

* One place owns network concerns: URL construction, JSON parsing, and
* normalising every failure into a typed ApiFailure. UI code never sees a
* raw Response. Errors are structured (spec §5) so the UI can branch on
* `code` rather than string-matching messages.
*/

import type {
  AddToCartResponse,
  ApiErrorEnvelope,
  ProductView,
} from './types'

export class ApiFailure extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(code: string, status: number, message: string, details: Record<string, unknown>) {
    super(message)
    this.name = 'ApiFailure'
    this.code = code
    this.status = status
    this.details = details
  }
}

// Vite dev server proxies /api → http://127.0.0.1:8000 (vite.config.ts, AP8).
const BASE_URL = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, init)
  } catch {
    // Network-level failure (backend down, offline): surface as a typed
    // error so the UI can show its retry state (LOAD_ERROR, spec §8.1).
    throw new ApiFailure('NETWORK_ERROR', 0, 'Could not reach the server.', {})
  }
  if (!response.ok) {
    let envelope: ApiErrorEnvelope | null = null
    try {
      envelope = (await response.json()) as ApiErrorEnvelope
    } catch {
      envelope = null
    }
    if (envelope?.error) {
      throw new ApiFailure(
        envelope.error.code,
        response.status,
        envelope.error.message,
        envelope.error.details ?? {},
      )
    }
    throw new ApiFailure('INTERNAL_ERROR', response.status, 'Unexpected server response.', {})
  }
  return (await response.json()) as T
}

export function fetchProduct(productId: string): Promise<ProductView> {
  return request<ProductView>(`/products/${encodeURIComponent(productId)}`)
}

export function addToCart(
  skuId: string,
  quantity: number,
  idempotencyKey: string,
): Promise<AddToCartResponse> {
  return request<AddToCartResponse>('/cart/items', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({ skuId, quantity }),
  })
}

export function fetchCart(): Promise<AddToCartResponse> {
  return request<AddToCartResponse>('/cart')
}
