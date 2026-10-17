/** Variant domain logic — pure functions, no I/O, no React.

* Everything here is exhaustively unit-testable: SKU resolution, the
* combination matrix (which option pairs are selectable), and quantity
* convergence. The UI layer orchestrates these; it never re-implements
* them (spec §8.4).
*/

import type { ProductView, Sku } from '../api/types'

/** Key identifying one option combination, e.g. "colour=Red|size=M". */
export function comboKey(options: Record<string, string>): string {
  return Object.keys(options)
    .sort()
    .map((k) => `${k}=${options[k]}`)
    .join('|')
}

/** Map of every option-value pair that has a SKU (the combination matrix). */
export function buildComboMatrix(skus: Sku[]): Map<string, Sku> {
  const matrix = new Map<string, Sku>()
  for (const sku of skus) {
    matrix.set(comboKey(sku.options), sku)
  }
  return matrix
}

/** The SKU for the currently selected values, or null if none exists. */
export function resolveSku(
  matrix: Map<string, Sku>,
  selection: Partial<Record<string, string>>,
): Sku | null {
  // Only resolve when every dimension has a value: a partial selection
  // must show no SKU, not a guessed one (spec §8.1 READY·未选全).
  const hasAll = Object.values(selection).every((v) => v !== undefined && v !== '')
  if (!hasAll) return null
  return matrix.get(comboKey(selection as Record<string, string>)) ?? null
}

/** Whether a specific option value can ever be combined into an existing SKU. */
export function valueExistsInMatrix(
  matrix: Map<string, Sku>,
  dimension: string,
  value: string,
  otherSelection: Partial<Record<string, string>>,
): boolean {
  for (const sku of matrix.values()) {
    if (sku.options[dimension] === value) {
      const matchesOthers = Object.entries(otherSelection).every(
        ([dim, val]) => val === undefined || val === '' || sku.options[dim] === val,
      )
      if (matchesOthers) return true
    }
  }
  return false
}

/** Clamp the chosen quantity into [1, available] for the selected SKU.

* Called on SKU switch (spec §8.2: quantity converges automatically) and
* whenever available changes (stale stock refresh, spec §8.1 STALE).
*/
export function clampQuantity(qty: number, available: number): number {
  if (available <= 0) return 0
  return Math.min(Math.max(1, qty), available)
}

/** Human price format from integer cents (AP7: format only at display). */
export function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

/** Cart line total in cents; prices are server-authoritative (spec §5.2). */
export function lineTotalOf(sku: Sku, qty: number): number {
  return sku.price * qty
}

export function optionValueLabel(value: string): string {
  return value
}

/** Product load state shared by the UI state machine (spec §8.1). */
export type LoadState = 'LOADING' | 'READY' | 'LOAD_ERROR'

/** Add-to-cart state machine (spec §8.1 ADDING / ADD_SUCCESS / ADD_ERROR). */
export type AddState =
  | { phase: 'IDLE' }
  | { phase: 'ADDING' }
  | { phase: 'SUCCESS', totalItemCount: number }
  | { phase: 'ERROR', code: string, message: string, retryable: boolean }

export type { ProductView, Sku }
