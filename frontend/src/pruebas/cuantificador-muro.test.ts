import { describe, expect, it } from 'vitest';

import { alturaQueSuma } from '@/cuantificador/MuroDelTrazo';

describe('altura que suma un muro (D-627)', () => {
  it('sin partes es la altura única', () => {
    expect(alturaQueSuma(null, '2.6')).toBeCloseTo(2.6);
    expect(alturaQueSuma([], '2,4')).toBeCloseTo(2.4);
  });

  it('por partes suma solo las que suman', () => {
    const partes = [
      { nombre: 'Muro', desde: '0', hasta: '2.3', suma: true },
      { nombre: 'Cerramiento', desde: '2.3', hasta: '2.5', suma: false },
      { nombre: 'Enrase', desde: '2.5', hasta: '3', suma: true },
    ];
    expect(alturaQueSuma(partes, '9')).toBeCloseTo(2.8);
  });

  it('una parte al revés no resta', () => {
    expect(alturaQueSuma([{ nombre: 'X', desde: '2', hasta: '1', suma: true }], '2.6')).toBe(0);
  });
});
