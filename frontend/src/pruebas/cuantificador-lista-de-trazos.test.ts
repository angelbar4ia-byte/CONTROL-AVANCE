/**
 * La pestaña «Trazos»: agrupa por concepto, escribe la cantidad del enlace vigente, manda los
 * trazos sin enlace al final y filtra por texto.
 */

import { describe, expect, it } from 'vitest';

import type { TrazoFeature } from '@/api/generado/modelo';
import { agruparTrazos, SIN_ENLACE } from '@/cuantificador/listaDeTrazos';

function trazo(id: string, geometria: string, propiedades: Record<string, unknown>): TrazoFeature {
  return {
    type: 'Feature',
    id,
    geometry: { type: geometria, coordinates: [] },
    properties: { capa: null, enlaces: [], ...propiedades },
  } as unknown as TrazoFeature;
}

const enlace = (nodo: string, cantidad: string, vigente = true) => ({
  enlace_id: `e-${nodo}-${cantidad}`,
  tipo_nodo: 'actividad',
  nodo_id: nodo,
  medida: 'area',
  factor: '1',
  cantidad,
  vigente,
});

const OPCIONES = {
  nombreDeNodo: (_tipo: string, id: string) => (id === 'a1' ? 'EST-01 LOSA' : id === 'a2' ? 'MUR-02 MURO' : id),
  nombreDeMedicion: (id: string) => (id === 'm1' ? 'RECÁMARA 1' : undefined),
  colorDe: () => '#123456',
};

describe('lista de trazos del plano', () => {
  const trazos = [
    trazo('t1', 'Polygon', { enlaces: [enlace('a1', '12.5')], medicion_id: 'm1' }),
    trazo('t2', 'Polygon', { enlaces: [enlace('a1', '7')] }),
    trazo('t3', 'LineString', { enlaces: [enlace('a2', '4')], grosor_m: '0.15' }),
    trazo('t4', 'Point', {}),
  ];

  it('agrupa por concepto y deja «Sin enlace» al final', () => {
    const grupos = agruparTrazos(trazos, OPCIONES);
    expect(grupos.map((g) => g.nombre)).toEqual(['EST-01 LOSA', 'MUR-02 MURO', SIN_ENLACE]);
    expect(grupos[0]?.trazos.map((t) => t.id)).toEqual(['t1', 't2']);
    expect(grupos[2]?.claveDeGrupo).toBeNull();
  });

  it('nombra el tipo (una línea con grosor es un muro) y la medición', () => {
    const grupos = agruparTrazos(trazos, OPCIONES);
    expect(grupos[0]?.trazos[0]?.subtitulo).toBe('Área · RECÁMARA 1');
    expect(grupos[1]?.trazos[0]?.subtitulo).toBe('Muro');
    expect(grupos[2]?.trazos[0]?.subtitulo).toBe('Punto');
  });

  it('escribe la cantidad del enlace vigente y nada si no hay enlace', () => {
    const grupos = agruparTrazos(trazos, OPCIONES);
    expect(grupos[0]?.trazos[0]?.cantidad).toMatch(/^12[.,]50/);
    expect(grupos[2]?.trazos[0]?.cantidad).toBeNull();
  });

  it('un enlace reemplazado no cuenta para agrupar', () => {
    const solo = [trazo('t5', 'Polygon', { enlaces: [enlace('a1', '9', false)] })];
    expect(agruparTrazos(solo, OPCIONES)[0]?.nombre).toBe(SIN_ENLACE);
  });

  it('busca por trazo, concepto, medición o tipo', () => {
    expect(agruparTrazos(trazos, { ...OPCIONES, busqueda: 'recámara' }).flatMap((g) => g.trazos.map((t) => t.id))).toEqual(['t1']);
    expect(agruparTrazos(trazos, { ...OPCIONES, busqueda: 'muro' }).flatMap((g) => g.trazos.map((t) => t.id))).toEqual(['t3']);
    expect(agruparTrazos(trazos, { ...OPCIONES, busqueda: 'no existe' })).toEqual([]);
  });

  it('lleva el color que le toca a cada trazo', () => {
    expect(agruparTrazos(trazos, OPCIONES)[0]?.trazos[0]?.color).toBe('#123456');
  });
});
