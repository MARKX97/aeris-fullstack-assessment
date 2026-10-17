/** Deterministic fixtures mirroring the backend seed data (spec §4).
 * Kept in one place so tests and mocks never drift from the contract. */

import type { ProductView } from '../api/types'

export const PRODUCT: ProductView = {
  product: {
    id: 'p-classic-tee',
    name: 'Classic Tee',
    description: 'A soft everyday tee. Three colours, three sizes.',
  },
  options: [
    { id: 'colour', name: 'Colour', values: ['Red', 'Blue', 'Green'] },
    { id: 'size', name: 'Size', values: ['S', 'M', 'L'] },
  ],
  skus: [
    { id: 'sku-red-s', options: { colour: 'Red', size: 'S' }, price: 2900, available: 10, image: '/images/sku-red-s.png' },
    { id: 'sku-red-m', options: { colour: 'Red', size: 'M' }, price: 2900, available: 5, image: '/images/sku-red-m.png' },
    { id: 'sku-red-l', options: { colour: 'Red', size: 'L' }, price: 2900, available: 3, image: '/images/sku-red-l.png' },
    { id: 'sku-blue-s', options: { colour: 'Blue', size: 'S' }, price: 3100, available: 8, image: '/images/sku-blue-s.png' },
    { id: 'sku-blue-m', options: { colour: 'Blue', size: 'M' }, price: 3100, available: 0, image: '/images/sku-blue-m.png' },
    { id: 'sku-green-s', options: { colour: 'Green', size: 'S' }, price: 2700, available: 6, image: '/images/sku-green-s.png' },
    { id: 'sku-green-m', options: { colour: 'Green', size: 'M' }, price: 2700, available: 4, image: '/images/sku-green-m.png' },
    { id: 'sku-green-l', options: { colour: 'Green', size: 'L' }, price: 2700, available: 2, image: '/images/sku-green-l.png' },
  ],
}
