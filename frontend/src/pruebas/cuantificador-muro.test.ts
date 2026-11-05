import { describe, expect, it } from 'vitest';

import { aPeticion, hayCambios, type BorradorDeConversion } from '@/cuantificador/ConversionDelEnlace';

const muro = (c: Partial<BorradorDeConversion> = {}): BorradorDeConversion => ({
  modo: 'area', mide: 'cara2', cara: 'int', lado: 'der', partes: [], alt: '2,6', ...c,
});

describe('conversión del enlace (D-633)', () => {
  it('manda los números como números, con coma o con punto', () => {
    expect(aPeticion(muro({ alt: '2,6', gro: '0.15' }))).toMatchObject({ modo: 'area', alt: 2.6, gro: 0.15, mide: 'cara2' });
  });

  it('un campo vacío no se manda', () => {
    expect('esp' in aPeticion(muro({ esp: '' }))).toBe(false);
  });

  it('hay cambios sin aplicar solo si lo editado difiere de lo vigente, sin importar cómo se escribió', () => {
    expect(hayCambios(muro({ alt: '2.6' }), muro({ alt: '2,6' }))).toBe(false);
    expect(hayCambios(muro({ mide: 'eje' }), muro())).toBe(true);
    expect(hayCambios(muro({ partes: [{ nombre: 'M', desde_m: 0, hasta_m: 2.3, suma: true }] }), muro())).toBe(true);
    expect(hayCambios(null, muro())).toBe(false);
  });
});
