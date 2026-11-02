import { describe, expect, it } from 'vitest';

import { centroide, cotasDe, etiquetasDeMedidas, sinCierre } from '@/cuantificador/etiquetas';
import type { GeometriaGeoJson } from '@/cuantificador/geometria';
import { resumenDePantalla, type TrazoParaResumen } from '@/cuantificador/resumen';

const CON_HUECO: GeometriaGeoJson = {
  type: 'Polygon',
  coordinates: [
    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
    [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]],
  ],
};
const LINEA: GeometriaGeoJson = { type: 'LineString', coordinates: [[0, 0], [3, 4], [3, 10]] };

describe('Mostrar medidas', () => {
  it('no numera los vértices: da el área ya descontada y rotula el hueco', () => {
    const e = etiquetasDeMedidas(CON_HUECO, 1);
    expect(e.some((x) => x.tipo === 'punto')).toBe(false);
    expect(etiquetasDeMedidas(LINEA, 1).some((x) => x.tipo === 'punto')).toBe(false);
    expect(e.find((x) => x.tipo === 'area')?.texto).toBe('96.00 m²');
    expect(e.find((x) => x.tipo === 'hueco')?.texto).toBe('Hueco 1 −4.00 m²');
  });

  it('sin calibrar escribe en unidades de plano, no en metros', () => {
    expect(etiquetasDeMedidas(CON_HUECO, null).find((x) => x.tipo === 'area')?.texto).toBe('96.00 u²');
  });

  it('una línea con grosor dice largo × grosor = área', () => {
    const e = etiquetasDeMedidas({ type: 'LineString', coordinates: [[0, 0], [10, 0]] }, 1, 0.15);
    expect(e.find((x) => x.tipo === 'longitud')?.texto).toBe('10.00 m × 0.15 = 1.50 m²');
  });

  it('la escala convierte: 0.5 m por unidad hace que 10 × 10 sean 25 m²', () => {
    expect(etiquetasDeMedidas({ type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]] }, 0.5)
      .find((x) => x.tipo === 'area')?.texto).toBe('25.00 m²');
  });

  it('el centroide de un cuadrado es su centro', () => {
    expect(centroide([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]])).toEqual([5, 5]);
    expect(sinCierre([[0, 0], [1, 0], [0, 0]])).toEqual([[0, 0], [1, 0]]);
  });
});

describe('puntos contados', () => {
  it('un punto o una forma estampada lleva su número y nada más', () => {
    const punto = etiquetasDeMedidas({ type: 'Point', coordinates: [1, 1] }, 1, null, 3);
    expect(punto).toEqual([{ tipo: 'punto', punto: [1, 1], texto: '3' }]);
    const forma = etiquetasDeMedidas(
      { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] },
      1,
      null,
      4,
    );
    expect(forma).toHaveLength(1); // sin etiqueta de área: se cuenta, no se mide
    expect(forma[0]).toMatchObject({ tipo: 'punto', texto: '4', punto: [1, 1] });
  });

  it('un punto sin número (no se pidió contarlo) no escribe nada', () => {
    expect(etiquetasDeMedidas({ type: 'Point', coordinates: [1, 1] }, 1)).toEqual([]);
  });
});

describe('Cota', () => {
  it('una por tramo: la línea de dos tramos da dos, y el polígono cierra su último lado', () => {
    expect(cotasDe(LINEA, 1).map((c) => c.texto)).toEqual(['5.00 m', '6.00 m']);
    // exterior de 4 lados + hueco de 4 lados
    expect(cotasDe(CON_HUECO, 1)).toHaveLength(8);
  });
});

describe('Cuadro de datos', () => {
  const trazo = (id: string, geometry: GeometriaGeoJson, props: Partial<TrazoParaResumen['properties']> = {}): TrazoParaResumen => ({
    id,
    geometry,
    properties: { enlaces: [], ...props },
  });

  it('suma áreas, huecos, líneas y puntos de lo que se ve', () => {
    const r = resumenDePantalla(
      [
        trazo('a', CON_HUECO),
        trazo('b', LINEA),
        trazo('c', { type: 'LineString', coordinates: [[0, 0], [10, 0]] }, { grosor_m: '0.15' }),
        trazo('d', { type: 'Point', coordinates: [1, 1] }),
      ],
      1,
    );
    expect(r.trazos).toBe(4);
    expect(r.areas).toEqual({ n: 1, total: 96 });
    expect(r.huecos).toEqual({ n: 1, total: 4 });
    expect(r.lineas.n).toBe(2);
    expect(r.lineas.longitud).toBeCloseTo(21, 10);
    expect(r.lineas.areaMuros).toBeCloseTo(1.5, 10);
    expect(r.puntos).toBe(1);
  });

  it('agrupa por concepto lo que el servidor midió en los enlaces vigentes', () => {
    const enlace = (nodo: string, medida: string, cantidad: number, vigente = true) => ({
      tipo_nodo: 'actividad',
      nodo_id: nodo,
      medida,
      vigente,
      cantidad,
    });
    const r = resumenDePantalla(
      [
        trazo('a', CON_HUECO, { enlaces: [enlace('losa', 'area', 96)] }),
        trazo('b', CON_HUECO, { enlaces: [enlace('losa', 'area', 50), enlace('losa', 'area', 999, false)] }),
        trazo('c', LINEA, { enlaces: [enlace('muro', 'longitud', 11)] }),
      ],
      1,
    );
    const losa = r.porNodo.find((n) => n.nodoId === 'losa')!;
    expect(losa.trazos).toBe(2);
    expect(losa.medidas).toEqual({ area: 146 }); // el enlace reemplazado no suma
    expect(r.porNodo.find((n) => n.nodoId === 'muro')?.medidas).toEqual({ longitud: 11 });
  });

  it('un polígono estampado con forma cuenta como forma, no como área', () => {
    const r = resumenDePantalla(
      [trazo('f', { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] }, { forma: { tipo: 'cuadrado' } })],
      1,
    );
    expect(r.formas).toEqual({ n: 1, total: 1 });
    expect(r.areas.n).toBe(0);
    expect(r.puntos).toBe(1); // la forma estampada es una pieza de la herramienta Punto
  });
});
