import { describe, expect, it } from 'vitest';

import { claveSiguiente, descuentoDelVano, TIPOS_DE_VANO } from '@/cuantificador/vanos';

describe('vanos de un muro', () => {
  it('una puerta de 0.9 × 2.1 en un muro de 2 caras descuenta 3.78 m²', () => {
    expect(descuentoDelVano(0.9, 2.1, 1, 2)).toBeCloseTo(3.78);
  });
  it('las piezas idénticas multiplican el descuento', () => {
    expect(descuentoDelVano(1.2, 1.2, 2, 2)).toBeCloseTo(5.76);
  });
  it('la clave sigue el consecutivo del tipo y salta las usadas', () => {
    expect(claveSiguiente('puerta', [])).toBe('P-01');
    expect(claveSiguiente('puerta', ['P-01', 'p-02', 'V-01'])).toBe('P-03');
    expect(claveSiguiente('paso', ['P-01'])).toBe('PS-01');
  });
  it('solo la ventana no llega al piso', () => {
    expect(Object.entries(TIPOS_DE_VANO).filter(([, d]) => !d.llegaAlPiso).map(([k]) => k)).toEqual(['ventana']);
  });
});
