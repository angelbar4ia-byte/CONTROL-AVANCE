import { describe, expect, it } from 'vitest';

import { geojsonAWkt } from '@/cuantificador/geometria';
import { crearHistorial, type Accion } from '@/cuantificador/historial';

function accion(nombre: string, bitacora: string[], falla: 'deshacer' | 'rehacer' | null = null): Accion {
  return {
    etiqueta: nombre,
    deshacer: async () => {
      if (falla === 'deshacer') throw new Error('no se puede deshacer');
      bitacora.push(`-${nombre}`);
    },
    rehacer: async () => {
      if (falla === 'rehacer') throw new Error('no se puede rehacer');
      bitacora.push(`+${nombre}`);
    },
  };
}

describe('historial', () => {
  it('deshace en orden inverso y rehace en el orden en que se hizo', async () => {
    const log: string[] = [];
    const h = crearHistorial();
    h.registrar(accion('A', log));
    h.registrar(accion('B', log));
    await h.deshacer();
    await h.deshacer();
    expect(log).toEqual(['-B', '-A']);
    expect(h.siguienteAdeshacer()).toBeNull();
    await h.rehacer();
    await h.rehacer();
    expect(log.slice(2)).toEqual(['+A', '+B']);
    expect(h.siguienteArehacer()).toBeNull();
  });

  it('una acción nueva descarta lo que se podía rehacer', async () => {
    const log: string[] = [];
    const h = crearHistorial();
    h.registrar(accion('A', log));
    await h.deshacer();
    expect(h.siguienteArehacer()?.etiqueta).toBe('A');
    h.registrar(accion('B', log));
    expect(h.siguienteArehacer()).toBeNull();
  });

  it('sin nada que deshacer o rehacer no pasa nada', async () => {
    const h = crearHistorial();
    expect(await h.deshacer()).toBeNull();
    expect(await h.rehacer()).toBeNull();
  });

  it('si deshacer falla, la acción se queda donde estaba y el error sube', async () => {
    const log: string[] = [];
    const h = crearHistorial();
    h.registrar(accion('A', log, 'deshacer'));
    await expect(h.deshacer()).rejects.toThrow('no se puede deshacer');
    expect(h.siguienteAdeshacer()?.etiqueta).toBe('A'); // sigue siendo lo siguiente a deshacer
    expect(h.siguienteArehacer()).toBeNull();
  });

  it('si rehacer falla, sigue siendo lo siguiente a rehacer', async () => {
    const h = crearHistorial();
    h.registrar(accion('A', [], 'rehacer'));
    await h.deshacer();
    await expect(h.rehacer()).rejects.toThrow();
    expect(h.siguienteArehacer()?.etiqueta).toBe('A');
  });

  it('limpiar vacía las dos pilas', async () => {
    const h = crearHistorial();
    h.registrar(accion('A', []));
    h.registrar(accion('B', []));
    await h.deshacer();
    h.limpiar();
    expect(h.siguienteAdeshacer()).toBeNull();
    expect(h.siguienteArehacer()).toBeNull();
  });

  it('solo recuerda las últimas 100', () => {
    const h = crearHistorial();
    for (let i = 0; i < 120; i += 1) h.registrar(accion(`A${i}`, []));
    expect(h.siguienteAdeshacer()?.etiqueta).toBe('A119');
  });
});

describe('GeoJSON → WKT', () => {
  it('puntos, líneas y polígonos con huecos', () => {
    expect(geojsonAWkt({ type: 'Point', coordinates: [1, 2] })).toBe('POINT(1 2)');
    expect(geojsonAWkt({ type: 'LineString', coordinates: [[0, 0], [3, 4]] })).toBe('LINESTRING(0 0, 3 4)');
    expect(
      geojsonAWkt({
        type: 'Polygon',
        coordinates: [[[0, 0], [10, 0], [10, 10], [0, 0]], [[2, 2], [3, 2], [3, 3], [2, 2]]],
      }),
    ).toBe('POLYGON((0 0, 10 0, 10 10, 0 0), (2 2, 3 2, 3 3, 2 2))');
  });

  it('un multipolígono (un hueco que parte el área)', () => {
    expect(
      geojsonAWkt({
        type: 'MultiPolygon',
        coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 0]]], [[[5, 5], [6, 5], [6, 6], [5, 5]]]],
      }),
    ).toBe('MULTIPOLYGON(((0 0, 1 0, 1 1, 0 0)), ((5 5, 6 5, 6 6, 5 5)))');
  });

  it('lo que no reconoce da null', () => {
    expect(geojsonAWkt({ type: 'Circle', coordinates: [] })).toBeNull();
    expect(geojsonAWkt({ type: 'Point', coordinates: ['a', 'b'] })).toBeNull();
    expect(geojsonAWkt({ type: 'LineString' })).toBeNull();
  });
});
