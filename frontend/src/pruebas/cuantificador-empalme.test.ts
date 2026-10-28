import { describe, expect, it } from 'vitest';

import { desfaseDeTexto, porTraer, versionesAnteriores } from '@/cuantificador/empalme';

const plano = (id: string, nombre: string, version: number) => ({ id, nombre, version });
const trazo = (id: string, vigentes: boolean[]) => ({ id, properties: { enlaces: vigentes.map((vigente) => ({ vigente })) } });

describe('Versiones del plano', () => {
  const planos = [
    plano('a1', 'Planta baja', 1),
    plano('a2', 'Planta baja', 2),
    plano('a3', 'Planta baja', 3),
    plano('b1', 'Azotea', 1),
  ];

  it('las anteriores son las del mismo nombre con versión menor, la más cercana primero', () => {
    expect(versionesAnteriores(planos, 'a3').map((p) => p.id)).toEqual(['a2', 'a1']);
    expect(versionesAnteriores(planos, 'a2').map((p) => p.id)).toEqual(['a1']);
  });

  it('la primera versión y un plano suelto no tienen anteriores', () => {
    expect(versionesAnteriores(planos, 'a1')).toEqual([]);
    expect(versionesAnteriores(planos, 'b1')).toEqual([]);
    expect(versionesAnteriores(planos, 'no-existe')).toEqual([]);
  });
});

describe('Trazos por traer', () => {
  it('quedan los que aún miden algo o no miden nada; se van los ya traídos', () => {
    const lista = [trazo('t1', [true]), trazo('t2', [false, false]), trazo('t3', []), trazo('t4', [false, true])];
    expect(porTraer(lista, new Set()).map((t) => t.id)).toEqual(['t1', 't3', 't4']);
    expect(porTraer(lista, new Set(['t1', 't3'])).map((t) => t.id)).toEqual(['t4']);
  });
});

describe('Desfase escrito a mano', () => {
  it('acepta coma y punto, y lo que no es número vale cero', () => {
    expect(desfaseDeTexto('2,5')).toBe(2.5);
    expect(desfaseDeTexto(' -3.25 ')).toBe(-3.25);
    expect(desfaseDeTexto('')).toBe(0);
    expect(desfaseDeTexto('abc')).toBe(0);
  });
});
