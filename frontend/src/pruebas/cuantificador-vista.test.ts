import { describe, expect, it } from 'vitest';

import { cotasDe, etiquetasDeMedidas } from '@/cuantificador/etiquetas';
import { factorDePendiente, type GeometriaGeoJson, type Punto } from '@/cuantificador/geometria';
import { resumenDePantalla, type TrazoParaResumen } from '@/cuantificador/resumen';
import {
  cajaTransformada,
  girar,
  rotacionValida,
  transformacionDeVista,
  VISTA_NORMAL,
  type VistaDelPlano,
} from '@/cuantificador/vista';

const casi = (a: Punto, b: Punto) => {
  expect(a[0]).toBeCloseTo(b[0], 9);
  expect(a[1]).toBeCloseTo(b[1], 9);
};

describe('Pendiente de una línea', () => {
  it('el factor es √(1 + p²) y sin pendiente vale 1', () => {
    expect(factorDePendiente(null)).toBe(1);
    expect(factorDePendiente(0)).toBe(1);
    expect(factorDePendiente(100)).toBeCloseTo(Math.SQRT2, 12);
    expect(factorDePendiente('33')).toBeCloseTo(Math.sqrt(1 + 0.33 ** 2), 12);
  });

  const LINEA: GeometriaGeoJson = { type: 'LineString', coordinates: [[0, 0], [10, 0]] };

  it('la etiqueta y la cota escriben el largo real', () => {
    expect(etiquetasDeMedidas(LINEA, 1, null, null, 100)[0]?.texto).toBe('14.14 m ↗ 100 %');
    expect(etiquetasDeMedidas(LINEA, 1)[0]?.texto).toBe('10.00 m');
    expect(cotasDe(LINEA, 1, 100)[0]?.texto).toBe('14.14 m');
  });

  it('el cuadro de datos suma el largo real de las líneas inclinadas', () => {
    const trazo = (pendiente: number | null): TrazoParaResumen => ({
      id: String(pendiente),
      geometry: LINEA,
      properties: { pendiente_pct: pendiente, enlaces: [] },
    });
    expect(resumenDePantalla([trazo(null), trazo(100)], 1).lineas.longitud).toBeCloseTo(10 + 10 * Math.SQRT2, 9);
  });
});

describe('Vista del plano', () => {
  const TODAS: VistaDelPlano[] = [0, 90, 180, 270].flatMap((r) =>
    [false, true].flatMap((h) =>
      [false, true].map((v) => ({ rotacionGrados: r as 0 | 90 | 180 | 270, volteoH: h, volteoV: v })),
    ),
  );

  it('invertir deshace aplicar en cualquier combinación', () => {
    for (const v of TODAS) {
      const t = transformacionDeVista(v);
      for (const p of [[0, 0], [3, 7], [-5, 12.5]] as Punto[]) casi(t.invertir(t.aplicar(p)), p);
    }
  });

  it('girar a la derecha lleva el eje x hacia abajo (sentido del reloj en pantalla)', () => {
    const t = transformacionDeVista({ ...VISTA_NORMAL, rotacionGrados: 90 });
    casi(t.aplicar([10, 0]), [0, 10]);
    casi(t.aplicar([0, 10]), [-10, 0]);
  });

  it('el espejo horizontal invierte x y el vertical invierte y', () => {
    casi(transformacionDeVista({ ...VISTA_NORMAL, volteoH: true }).aplicar([4, 5]), [-4, 5]);
    casi(transformacionDeVista({ ...VISTA_NORMAL, volteoV: true }).aplicar([4, 5]), [4, -5]);
  });

  it('la vista normal no pide transformación', () => {
    const t = transformacionDeVista(VISTA_NORMAL);
    expect(t.svg).toBeUndefined();
    expect(t.contragiro(1, 2)).toBeUndefined();
    expect(t.esNormal).toBe(true);
  });

  it('girar 4 veces vuelve al inicio, y a la izquierda es lo contrario', () => {
    let v = VISTA_NORMAL;
    for (let i = 0; i < 4; i += 1) v = girar(v, true);
    expect(v.rotacionGrados).toBe(0);
    expect(girar(VISTA_NORMAL, false).rotacionGrados).toBe(270);
  });

  it('la caja de un plano apaisado, girada, queda vertical', () => {
    const t = transformacionDeVista({ ...VISTA_NORMAL, rotacionGrados: 90 });
    const c = cajaTransformada({ minX: 0, minY: 0, maxX: 200, maxY: 100 }, t);
    expect(c.maxX - c.minX).toBeCloseTo(100, 9);
    expect(c.maxY - c.minY).toBeCloseTo(200, 9);
  });

  it('el ángulo de una cota en pantalla nunca queda de cabeza', () => {
    for (const v of TODAS) {
      const t = transformacionDeVista(v);
      const ang = t.anguloEnPantalla([0, 0], [10, 3]);
      expect(ang).toBeGreaterThanOrEqual(-90);
      expect(ang).toBeLessThanOrEqual(90);
    }
  });

  it('una rotación rara del servidor se lleva a una válida', () => {
    expect(rotacionValida(null)).toBe(0);
    expect(rotacionValida(450)).toBe(90);
    expect(rotacionValida(-90)).toBe(270);
  });
});
