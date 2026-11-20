/** La capa «espacio» (0143): nombres, lectura del reparto de un muro compartido y validación de lo que se teclea. */

import { describe, expect, it } from 'vitest';

import {
  NOMBRE_DE_TIPO_DE_ESPACIO,
  NOMBRE_DEL_ESTADO_DE_PARTIDA,
  TIPOS_DE_ESPACIO,
  nombreDelEspacio,
  repartoTecleado,
  textoDelReparto,
} from '@/cuantificador/espacios';

const ESPACIOS = [
  { id: 'r', nombre: 'Recámara 1' },
  { id: 'b', nombre: 'Baño' },
];

describe('espacios', () => {
  it('cada tipo de espacio tiene su nombre', () => {
    expect(TIPOS_DE_ESPACIO).toHaveLength(13);
    for (const t of TIPOS_DE_ESPACIO) expect(NOMBRE_DE_TIPO_DE_ESPACIO[t]).toBeTruthy();
    expect(NOMBRE_DE_TIPO_DE_ESPACIO.bano).toBe('Baño');
  });

  it('el nombre de un espacio: sin espacio, borrado o por su id', () => {
    expect(nombreDelEspacio(ESPACIOS, null)).toBe('sin espacio');
    expect(nombreDelEspacio(ESPACIOS, undefined)).toBe('sin espacio');
    expect(nombreDelEspacio(ESPACIOS, 'b')).toBe('Baño');
    expect(nombreDelEspacio(ESPACIOS, 'x')).toBe('espacio borrado');
  });

  it('el reparto tecleado va de más de 0 a menos de 100 y acepta la coma', () => {
    expect(repartoTecleado('')).toBeNull();
    expect(repartoTecleado('  ')).toBeNull();
    expect(repartoTecleado('40')).toBe(40);
    expect(repartoTecleado('33,5')).toBe(33.5);
    for (const mal of ['0', '100', '-5', '150', 'abc', '1e400']) expect(repartoTecleado(mal)).toBeNull();
  });

  it('el reparto de un muro se lee con sus porcentajes y suma 100', () => {
    expect(textoDelReparto(ESPACIOS, [])).toBe('sin espacio');
    expect(textoDelReparto(ESPACIOS, [{ espacio_id: 'r', fraccion: '1.000000' }])).toBe('Recámara 1 100 %');
    expect(
      textoDelReparto(ESPACIOS, [
        { espacio_id: 'r', fraccion: '0.5' },
        { espacio_id: 'b', fraccion: '0.5' },
      ]),
    ).toBe('Recámara 1 50 % · Baño 50 %');
    expect(
      textoDelReparto(ESPACIOS, [
        { espacio_id: 'r', fraccion: 0.3333 },
        { espacio_id: 'b', fraccion: 0.6667 },
      ]),
    ).toBe('Recámara 1 33.33 % · Baño 66.67 %');
  });

  it('cada estado de la partida que puede responder el servidor tiene su texto', () => {
    for (const e of ['cuenta', 'sin_espacio', 'propuesto', 'sin_concepto', 'falta_partida', 'sin_cantidad']) {
      expect(NOMBRE_DEL_ESTADO_DE_PARTIDA[e]).toBeTruthy();
    }
  });
});
