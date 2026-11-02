import { describe, expect, it } from 'vitest';

import type { GeometriaGeoJson, Punto } from '@/cuantificador/geometria';
import {
  REFERENCIAS_POR_DEFECTO,
  buscarReferencia,
  interseccion,
  type ReferenciasActivas,
} from '@/cuantificador/referencias';

const CUADRADO: GeometriaGeoJson = {
  type: 'Polygon',
  coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
};
const LINEA: GeometriaGeoJson = { type: 'LineString', coordinates: [[-5, 5], [15, 5]] };

const busca = (g: GeometriaGeoJson[], cursor: Punto, activas: ReferenciasActivas = REFERENCIAS_POR_DEFECTO, desde: Punto | null = null) =>
  buscarReferencia({ geometrias: g }, cursor, 0.5, activas, desde);

describe('referencia a objetos', () => {
  it('se pega a un extremo y dice cuál es', () => {
    expect(busca([CUADRADO], [10.2, 0.1])).toEqual({ punto: [10, 0], tipo: 'extremo' });
  });

  it('se pega al punto medio de un lado y al centro del área', () => {
    expect(busca([CUADRADO], [5.1, 0.2])).toEqual({ punto: [5, 0], tipo: 'medio' });
    expect(busca([CUADRADO], [5.1, 4.9])?.tipo).toBe('centro');
  });

  it('se pega al cruce de dos trazos', () => {
    expect(busca([CUADRADO, LINEA], [9.9, 5.1])).toEqual({ punto: [10, 5], tipo: 'interseccion' });
  });

  it('fuera de la tolerancia no se pega a nada', () => {
    expect(busca([CUADRADO], [3, 3])).toBeNull();
  });

  it('lo apagado no se ofrece', () => {
    const sinExtremos = { ...REFERENCIAS_POR_DEFECTO, extremo: false, interseccion: false };
    expect(busca([CUADRADO], [10.1, 0.1], sinExtremos)).toBeNull();
  });

  it('la perpendicular se mide desde el último punto puesto', () => {
    // Desde (3, 8), la perpendicular al lado de abajo (y = 0) cae en (3, 0).
    const solo = { extremo: false, medio: false, centro: false, interseccion: false, perpendicular: true, cercano: false };
    expect(busca([CUADRADO], [3.1, 0.2], solo, [3, 8])).toEqual({ punto: [3, 0], tipo: 'perpendicular' });
    expect(busca([CUADRADO], [3.1, 0.2], solo, null)).toBeNull(); // sin punto previo no hay perpendicular
  });

  it('«más cercano» pega al borde, pero pierde contra cualquier otra referencia', () => {
    const conCercano = { ...REFERENCIAS_POR_DEFECTO, cercano: true };
    expect(busca([CUADRADO], [2.1, 0.2], conCercano)).toEqual({ punto: [2.1, 0], tipo: 'cercano' });
    expect(busca([CUADRADO], [0.3, 0.2], conCercano)?.tipo).toBe('extremo'); // más lejos, pero preferido
  });

  it('también se pega a lo que se está dibujando', () => {
    const r = buscarReferencia({ geometrias: [], enCurso: [[[0, 0], [4, 0], [4, 3]]] }, [0.2, 0.1], 0.5, REFERENCIAS_POR_DEFECTO);
    expect(r).toEqual({ punto: [0, 0], tipo: 'extremo' });
  });

  it('la intersección de dos segmentos, y nada si no se tocan', () => {
    expect(interseccion([[0, 0], [10, 10]], [[0, 10], [10, 0]])).toEqual([5, 5]);
    expect(interseccion([[0, 0], [1, 1]], [[5, 0], [6, 1]])).toBeNull();
    expect(interseccion([[0, 0], [10, 0]], [[0, 1], [10, 1]])).toBeNull(); // paralelos
  });
});
