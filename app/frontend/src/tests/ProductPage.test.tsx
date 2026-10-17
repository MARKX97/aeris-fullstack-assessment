/** Frontend acceptance tests — APP-FE-1..4 (app/acceptance.md §4).
 *
 * Each test maps 1:1 to an acceptance row. Fetch is mocked at the module
 * boundary (vi.mock of ../api/client) so tests exercise the real state
 * machine, not a stubbed component.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProductPage } from '../ui/ProductPage'
import { PRODUCT } from './fixtures'
import type { AddToCartResponse } from '../api/types'

// Fetch mock: tests swap the resolved/rejected value per scenario.
const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/products/')) {
      return jsonResponse(200, PRODUCT)
    }
    if (url.includes('/api/cart/items')) {
      return jsonResponse(201, {
        cart: { items: [], totalItemCount: 1 },
      } satisfies AddToCartResponse)
    }
    return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'x', details: {} } })
  })
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

// Route the global fetch to our mock: the api layer calls window.fetch.
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

async function selectColourAndSize(user: ReturnType<typeof userEvent.setup>, colour: string, size: string) {
  await user.click(screen.getByRole('button', { name: colour }))
  await user.click(screen.getByRole('button', { name: size }))
}

describe('APP-FE-1: variant resolution', () => {
  it('selecting Red+S updates price and stock', async () => {
    const user = userEvent.setup()
    render(<ProductPage />)

    await screen.findByText('Classic Tee')
    await selectColourAndSize(user, 'Red', 'S')

    expect(screen.getByText('In stock: 10')).toBeInTheDocument()
    expect(screen.getByText('$29.00')).toBeInTheDocument()
  })

  it('marks impossible combinations disabled (Blue+L)', async () => {
    const user = userEvent.setup()
    render(<ProductPage />)

    await screen.findByText('Classic Tee')
    // Blue exists in the matrix with S and M — but with L missing, L is
    // disabled once Blue is picked.
    await user.click(screen.getByRole('button', { name: 'Blue' }))

    expect(screen.getByRole('button', { name: 'L' })).toBeDisabled()
    // S remains selectable for Blue.
    expect(screen.getByRole('button', { name: 'S' })).toBeEnabled()
  })
})

describe('APP-FE-2: duplicate-click guard', () => {
  it('disables the button during ADDING and fires fetch exactly once', async () => {
    const user = userEvent.setup()
    let resolveAdd: (r: Response) => void = () => undefined
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/products/')) {
        return jsonResponse(200, PRODUCT)
      }
      if (url.includes('/api/cart/items')) {
        return new Promise<Response>((resolve) => {
          resolveAdd = resolve
        })
      }
      return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'x', details: {} } })
    })

    render(<ProductPage />)
    await screen.findByText('Classic Tee')
    await selectColourAndSize(user, 'Green', 'L')

    const addBtn = screen.getByRole('button', { name: 'Add to cart' })
    await user.click(addBtn)
    await user.click(addBtn) // repeat click while ADDING
    await user.click(addBtn)

    expect(addBtn).toBeDisabled()
    const addCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/api/cart/items'))
    expect(addCalls).toHaveLength(1)

    resolveAdd(jsonResponse(201, { cart: { items: [], totalItemCount: 1 } }))
    await waitFor(() =>
      expect(screen.getByText(/Added to cart/i)).toBeInTheDocument(),
    )
  })
})

describe('APP-FE-3: quantity convergence', () => {
  it('qty=3 then switching to available=2 SKU converges to 2', async () => {
    const user = userEvent.setup()
    render(<ProductPage />)

    await screen.findByText('Classic Tee')
    await selectColourAndSize(user, 'Red', 'S') // available 10
    const qty = screen.getByLabelText('Quantity')
    await user.clear(qty)
    await user.type(qty, '3')
    expect(qty).toHaveValue(3)

    await user.click(screen.getByRole('button', { name: 'L' })) // Red+L available 3
    expect(qty).toHaveValue(3)

    // Switch to Green+L (available 2): quantity must converge down.
    await user.click(screen.getByRole('button', { name: 'Green' }))
    expect(qty).toHaveValue(2)
  })
})

describe('APP-FE-4: error recovery', () => {
  it('product load failure → retry button → recovers', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/products/')) {
        if (fetchMock.mock.calls.length <= 1) {
          return jsonResponse(500, { error: { code: 'INTERNAL_ERROR', message: 'boom', details: {} } })
        }
        return jsonResponse(200, PRODUCT)
      }
      return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'x', details: {} } })
    })

    const user = userEvent.setup()
    render(<ProductPage />)

    await screen.findByRole('alert')
    expect(screen.getByText(/could not load/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await screen.findByText('Classic Tee')
    expect(screen.getByRole('button', { name: 'Red' })).toBeInTheDocument()
  })
})

describe('APP-FE-8: stale stock refresh', () => {
  it('a successful add refreshes the SKU stock in place, no page reload', async () => {
    const user = userEvent.setup()
    render(<ProductPage />)

    await screen.findByText('Classic Tee')
    await selectColourAndSize(user, 'Red', 'S') // available 10
    expect(screen.getByText('In stock: 10')).toBeInTheDocument()

    const qty = screen.getByLabelText('Quantity')
    await user.clear(qty)
    await user.type(qty, '2')

    await user.click(screen.getByRole('button', { name: 'Add to cart' }))

    // The server decremented stock by 2; the UI adopts the new value
    // without any reload (spec §8.1 STALE 恢复).
    await waitFor(() => expect(screen.getByText('In stock: 8')).toBeInTheDocument())
    // And the quantity converged back to 1 after success (spec §8.2).
    expect(qty).toHaveValue(1)
    // No reload: the product was fetched exactly once.
    const productCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).includes('/api/products/'),
    )
    expect(productCalls).toHaveLength(1)
  })
})
