import { describe, expect, it } from 'vitest';

import { conversionDeMuro, opcionesDeMuroIniciales, textoDeMuro } from '@/cuantificador/trazoPeticion';
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

  it('los tramos de un muro que cruza zonas de losa viajan tal cual y sin tramos no se manda la llave', () => {
    const tramos = [{ desde_m: 0, hasta_m: 4, alt: 3 }, { desde_m: 4, hasta_m: 8, alt: 4.2 }];
    expect(aPeticion(muro({ tramos }))).toMatchObject({ tramos });
    expect('tramos' in aPeticion(muro({ tramos: [] }))).toBe(false);
    expect('tramos' in aPeticion(muro())).toBe(false);
  });
});

describe('altura con la que nace un muro (zonas de losa 1.1)', () => {
  const o = opcionesDeMuroIniciales(3);
  it('sin teclear la altura no se manda: el servidor toma la de la zona de losa o la estándar de la obra', () => {
    expect('alt' in conversionDeMuro(o, 3, false)).toBe(false);
    expect(conversionDeMuro(o, 3, true).alt).toBe(3);
  });
  it('con partes de altura siempre se mandan', () => {
    const conPartes = { ...o, partes: [{ nombre: 'Cuerpo', desde_m: 0, hasta_m: 3, suma: true }] };
    expect(conversionDeMuro(conPartes, 3, false).alt).toBe(3);
  });
  it('el aviso no inventa una altura que el servidor aún no eligió', () => {
    expect(textoDeMuro(o, 3, false)).toContain('zona de losa');
    expect(textoDeMuro(o, 3, true)).toContain('3 m de altura');
  });
});
