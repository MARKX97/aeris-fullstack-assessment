/** Wire types for the Variant PDP API (contract: app/spec.md §5). */

export interface ProductView {
  product: { id: string; name: string; description: string }
  options: OptionDim[]
  skus: Sku[]
}

export interface OptionDim {
  id: string
  name: string
  values: string[]
}

export interface Sku {
  id: string
  options: Record<string, string>
  price: number // integer cents (AP7)
  available: number
  image: string
}

export interface CartLine {
  skuId: string
  quantity: number
  unitPrice: number
  lineTotal: number
}

export interface Cart {
  items: CartLine[]
  totalItemCount: number
}

export interface AddToCartResponse {
  cart: Cart
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string; details: Record<string, unknown> }
}

/** Union of every structured error code the backend can return (spec §5). */
export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'PRODUCT_NOT_FOUND'
  | 'SKU_NOT_FOUND'
  | 'INSUFFICIENT_STOCK'
  | 'IDEMPOTENCY_KEY_CONFLICT'
  | 'INTERNAL_ERROR'
