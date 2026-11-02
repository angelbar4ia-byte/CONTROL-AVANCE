/**
 * «Calcular volumen» y «Solo los trazos de los conceptos elegidos»: las dos
 * herramientas del cuantificador que se deciden con aritmética y filtros puros.
 */

import { describe, expect, it } from 'vitest';

import { trazosDeConceptos } from '@/cuantificador/arbol';
import { areaDeGeometria, longitudDeGeometria, type GeometriaGeoJson } from '@/cuantificador/geometria';
import { baseDeVolumen, numeroTecleado, volumenDe } from '@/cuantificador/volumen';

const CUADRADO_10: GeometriaGeoJson = {
  type: 'Polygon',
  coordinates: [
    [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [0, 0],
    ],
  ],
};
const CON_HUECO: GeometriaGeoJson = {
  type: 'Polygon',
  coordinates: [
    [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [0, 0],
    ],
    [
      [2, 2],
      [4, 2],
      [4, 4],
      [2, 4],
      [2, 2],
    ],
  ],
};
const LINEA_5: GeometriaGeoJson = {
  type: 'LineString',
  coordinates: [
    [0, 0],
    [3, 4],
  ],
};
const PUNTO: GeometriaGeoJson = { type: 'Point', coordinates: [1, 1] };

describe('medidas de un trazo guardado', () => {
  it('el área descuenta los huecos y la longitud suma los tramos', () => {
    expect(areaDeGeometria(CUADRADO_10)).toBe(100);
    expect(areaDeGeometria(CON_HUECO)).toBe(96);
    expect(longitudDeGeometria(LINEA_5)).toBe(5);
    expect(areaDeGeometria(LINEA_5)).toBe(0);
    expect(areaDeGeometria(PUNTO)).toBe(0);
  });
});

describe('la base del volumen', () => {
  it('con la escala calibrada sale en metros: el área escala al cuadrado', () => {
    expect(baseDeVolumen(CUADRADO_10, 0.5)).toEqual({ tipo: 'area', valor: 25, unidad: 'm²' });
    expect(baseDeVolumen(LINEA_5, 0.5)).toEqual({ tipo: 'longitud', valor: 2.5, unidad: 'm' });
  });

  it('sin calibrar se queda en unidades de plano, y lo dice', () => {
    expect(baseDeVolumen(CUADRADO_10, null)).toEqual({ tipo: 'area', valor: 100, unidad: 'u²' });
    expect(baseDeVolumen(LINEA_5, null)).toEqual({ tipo: 'longitud', valor: 5, unidad: 'u' });
  });

  it('un punto no tiene base', () => {
    expect(baseDeVolumen(PUNTO, 1)).toBeNull();
  });
});

describe('el volumen', () => {
  it('área × espesor, y descuenta lo que no se vacía', () => {
    expect(volumenDe(48.2, [0.12])).toBeCloseTo(5.784, 6);
    expect(volumenDe(48.2, [0.12], 0.784)).toBeCloseTo(5, 6);
  });

  it('longitud × ancho × alto', () => {
    expect(volumenDe(10, [0.2, 0.4])).toBeCloseTo(0.8, 6);
  });

  it('nunca es negativo y un factor en blanco da cero visible', () => {
    expect(volumenDe(1, [0.1], 5)).toBe(0);
    expect(volumenDe(48.2, [numeroTecleado('')])).toBe(0);
  });

  it('lo tecleado acepta coma decimal y rechaza lo ilegible', () => {
    expect(numeroTecleado('0,12')).toBe(0.12);
    expect(numeroTecleado(' 2.5 ')).toBe(2.5);
    expect(numeroTecleado('abc')).toBe(0);
    expect(numeroTecleado('-3')).toBe(0);
  });
});

describe('solo los trazos de los conceptos elegidos', () => {
  const trazo = (id: string, enlaces: { nodo_id: string; vigente: boolean; tipo_nodo?: string }[]) => ({
    id,
    properties: { enlaces: enlaces.map((e) => ({ tipo_nodo: 'actividad', ...e })) },
  });
  const TRAZOS = [
    trazo('t1', [{ nodo_id: 'losa', vigente: true }]),
    trazo('t2', [{ nodo_id: 'muro', vigente: true }]),
    trazo('t3', [
      { nodo_id: 'losa', vigente: false },
      { nodo_id: 'muro', vigente: true },
    ]),
    trazo('t4', []),
    trazo('t5', [{ nodo_id: 'losa', vigente: true, tipo_nodo: 'prototipo_nodo' }]),
  ];

  it('deja los que alimentan algún concepto elegido', () => {
    expect(trazosDeConceptos(TRAZOS, new Set(['losa'])).map((t) => t.id)).toEqual(['t1']);
    expect(trazosDeConceptos(TRAZOS, new Set(['losa', 'muro'])).map((t) => t.id)).toEqual(['t1', 't2', 't3']);
  });

  it('un enlace reemplazado o a un nodo de prototipo no cuenta', () => {
    const ids = trazosDeConceptos(TRAZOS, new Set(['losa'])).map((t) => t.id);
    expect(ids).not.toContain('t3');
    expect(ids).not.toContain('t5');
  });

  it('sin conceptos elegidos no queda ninguno', () => {
    expect(trazosDeConceptos(TRAZOS, new Set())).toEqual([]);
  });
});
