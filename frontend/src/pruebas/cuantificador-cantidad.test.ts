import { describe, expect, it } from 'vitest';

import { cantidadPorPiezas, numeroDeTexto } from '@/cuantificador/cantidad';

describe('Cantidad por piezas comerciales', () => {
  it('castillo K2: 4 varillas de 12 ml con 0.5 % de desperdicio dan 0.335 por ml', () => {
    expect(cantidadPorPiezas({ piezas: 4, largo: 12, desperdicioPct: 0.5 })).toBe(0.335);
  });

  it('sin desperdicio es la división a seis decimales', () => {
    expect(cantidadPorPiezas({ piezas: 4, largo: 12, desperdicioPct: 0 })).toBe(0.333333);
    expect(cantidadPorPiezas({ piezas: 2, largo: 12, desperdicioPct: 10 })).toBe(0.183333);
  });

  it('lo que no tiene sentido no da cantidad', () => {
    expect(cantidadPorPiezas({ piezas: 0, largo: 12, desperdicioPct: 0 })).toBeNull();
    expect(cantidadPorPiezas({ piezas: 4, largo: 0, desperdicioPct: 0 })).toBeNull();
    expect(cantidadPorPiezas({ piezas: 4, largo: 12, desperdicioPct: 101 })).toBeNull();
    expect(cantidadPorPiezas({ piezas: Number.NaN, largo: 12, desperdicioPct: 0 })).toBeNull();
  });

  it('acepta coma o punto al escribir', () => {
    expect(numeroDeTexto('0,5')).toBe(0.5);
    expect(numeroDeTexto(' 12 ')).toBe(12);
    expect(numeroDeTexto('')).toBeNaN();
  });
});
