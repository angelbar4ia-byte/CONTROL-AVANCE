import { describe, expect, it } from 'vitest';

import { candidatosDeEscala, coberturaDeLaHoja, metrosPorUnidad } from '@/cuantificador/escalaAuto';

describe('Candidatos de escala en el texto de la hoja', () => {
  it('lee «ESC. 1:50» y «ESCALA 1/100» como rotuladas', () => {
    const c = candidatosDeEscala(['PLANTA BAJA', 'ESC. 1:50', 'otra cosa']);
    expect(c).toEqual([{ denominador: 50, texto: 'ESC. 1:50', rotulada: true, veces: 1 }]);
  });

  it('una relación suelta 1:N cuenta, pero va después de la rotulada', () => {
    const c = candidatosDeEscala(['Detalle 1:20', 'ESCALA: 1:100']);
    expect(c.map((x) => [x.denominador, x.rotulada])).toEqual([
      [100, true],
      [20, false],
    ]);
  });

  it('descarta lo que no es una escala creíble y los números pegados a otros', () => {
    expect(candidatosDeEscala(['relación 1:1', 'cota 11:50', 'hora 1:30:45', 'ESC 1:99999'])).toEqual([]);
  });

  it('los repetidos van antes que los que salen una vez', () => {
    const c = candidatosDeEscala(['Detalle 1:20', 'Detalle 1:25', 'Detalle 1:25']);
    expect(c.map((x) => x.denominador)).toEqual([25, 20]);
  });
});

describe('Metros por unidad de plano de un PDF', () => {
  it('con escala 1:50 y 2 unidades por punto, una unidad son ~0.0088 m', () => {
    expect(metrosPorUnidad(50, 2)).toBeCloseTo((0.0254 / 72) * 25, 10);
  });

  it('una hoja A1 apaisada (2384×1684 pt) a 1:50 cubre ~42 × 30 m', () => {
    const { ancho, alto } = coberturaDeLaHoja(2384, 1684, 50);
    expect(ancho).toBeCloseTo(42.05, 1);
    expect(alto).toBeCloseTo(29.7, 1);
  });
});
