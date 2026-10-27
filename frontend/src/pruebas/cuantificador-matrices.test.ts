import { describe, expect, it } from 'vitest';

import { arbolDeMatrices, llavesConHijos, type MatrizPlana } from '@/cuantificador/matrices';

const m = (clave: string, nivel: number, extra: Partial<MatrizPlana> = {}): MatrizPlana => ({
  concepto_id: `id-${clave}`,
  nivel,
  clave,
  descripcion: clave,
  unidad: 'm2',
  cantidad_catalogo: '10',
  cantidad_medida: null,
  ...extra,
});

describe('Árbol de matrices', () => {
  it('anida por nivel a cualquier profundidad, en el orden en que llegan', () => {
    const arbol = arbolDeMatrices([m('NERV', 1), m('BAST', 2), m('VAR', 3), m('TRABE', 1), m('EST', 2)]);
    expect(arbol.map((n) => n.clave)).toEqual(['NERV', 'TRABE']);
    expect(arbol[0]!.hijos.map((n) => n.clave)).toEqual(['BAST']);
    expect(arbol[0]!.hijos[0]!.hijos.map((n) => n.clave)).toEqual(['VAR']);
    expect(arbol[1]!.hijos.map((n) => n.clave)).toEqual(['EST']);
  });

  it('un hermano posterior no cuelga de lo más profundo de la rama anterior', () => {
    const arbol = arbolDeMatrices([m('A', 1), m('A1', 2), m('A1a', 3), m('A2', 2)]);
    expect(arbol[0]!.hijos.map((n) => n.clave)).toEqual(['A1', 'A2']);
    expect(arbol[0]!.hijos[1]!.hijos).toHaveLength(0);
  });

  it('cada rama cuenta sus matrices medidas y las que tiene', () => {
    const arbol = arbolDeMatrices([m('NERV', 1, { cantidad_medida: '8' }), m('BAST', 2), m('TRABE', 1)]);
    expect(arbol[0]).toMatchObject({ medidas: 1, total: 2 });
    expect(arbol[1]).toMatchObject({ medidas: 0, total: 1 });
  });

  it('el tipo sale de la unidad de cada matriz, y las cantidades llegan como números', () => {
    const [nerv] = arbolDeMatrices([m('NERV', 1, { cantidad_catalogo: '5.5', cantidad_medida: '8', diferencia: '2.5' }), m('BAST', 2, { unidad: 'ml' })]);
    expect(nerv).toMatchObject({ tipo: 'area', cantidadCatalogo: 5.5, cantidadMedida: 8, diferencia: 2.5 });
    expect(nerv!.hijos[0]).toMatchObject({ tipo: 'lineal', cantidadMedida: null });
  });

  it('la misma matriz bajo dos madres tiene llaves distintas', () => {
    const arbol = arbolDeMatrices([m('A', 1), m('X', 2), m('B', 1), m('X', 2)]);
    expect(arbol[0]!.hijos[0]!.llave).not.toBe(arbol[1]!.hijos[0]!.llave);
  });

  it('las llaves con hijos son las que se pueden abrir y cerrar', () => {
    const arbol = arbolDeMatrices([m('A', 1), m('A1', 2), m('B', 1)]);
    expect(llavesConHijos(arbol)).toEqual([arbol[0]!.llave]);
    expect(arbolDeMatrices([])).toEqual([]);
  });
});
