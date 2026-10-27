import { describe, expect, it } from 'vitest';

import {
  ajustarAngulo,
  arco,
  circulo,
  elipse,
  formaDe,
  rectangulo,
} from '@/cuantificador/dibujo';
import { areaLocal, longitudLocal, type Punto } from '@/cuantificador/geometria';

describe('ortogonal', () => {
  const O: Punto = [0, 0];
  it('con 90° deja el trazo horizontal o vertical, el que quede más cerca', () => {
    expect(ajustarAngulo(O, [10, 2], { pasoGrados: 90, baseGrados: 0 })).toEqual([10, 0]);
    const v = ajustarAngulo(O, [1, -8], { pasoGrados: 90, baseGrados: 0 });
    expect(v[0]).toBeCloseTo(0, 10);
    expect(v[1]).toBeCloseTo(-8, 10);
  });

  it('conserva la coordenada apuntada y alcanza los 180° (hacia atrás)', () => {
    const p = ajustarAngulo([5, 5], [-3, 6], { pasoGrados: 90, baseGrados: 0 });
    expect(p[0]).toBeCloseTo(-3, 10);
    expect(p[1]).toBeCloseTo(5, 10);
  });

  it('con 45° también permite las diagonales', () => {
    const p = ajustarAngulo(O, [10, 9], { pasoGrados: 45, baseGrados: 0 });
    expect(p[0]).toBeCloseTo(p[1], 10);
  });

  it('un ángulo base gira la rejilla de direcciones', () => {
    // Base 30°: con paso 90 las direcciones son 30°, 120°, 210°, 300°.
    const p = ajustarAngulo(O, [10, 5.5], { pasoGrados: 90, baseGrados: 30 });
    expect(Math.atan2(p[1], p[0]) * (180 / Math.PI)).toBeCloseTo(30, 8);
  });

  it('sin distancia o sin paso no cambia nada', () => {
    expect(ajustarAngulo(O, O, { pasoGrados: 90, baseGrados: 0 })).toEqual(O);
    expect(ajustarAngulo(O, [3, 4], { pasoGrados: 0, baseGrados: 0 })).toEqual([3, 4]);
  });
});

describe('formas de pocos clics', () => {
  it('el rectángulo por dos esquinas, con la base girada o no', () => {
    expect(areaLocal(rectangulo([0, 0], [4, 3]))).toBeCloseTo(12, 10);
    // Girado 90°: sigue siendo 4 × 3 de lado, pero medido sobre los ejes girados.
    const g = rectangulo([0, 0], [4, 3], 90);
    expect(Math.abs(areaLocal(g))).toBeCloseTo(12, 10);
    expect(g[1]![0]).toBeCloseTo(0, 10); // el primer lado va ahora por el eje Y
  });

  it('el círculo mide casi π r²', () => {
    const c = circulo([0, 0], [10, 0]);
    expect(c).toHaveLength(120);
    expect(areaLocal(c) / (Math.PI * 100)).toBeGreaterThan(0.9994);
    expect(areaLocal(c)).toBeLessThan(Math.PI * 100);
  });

  it('la elipse tiene los semiejes pedidos, también girada', () => {
    const e = elipse([0, 0], [10, 0], [0, 4]);
    expect(areaLocal(e) / (Math.PI * 10 * 4)).toBeGreaterThan(0.9994);
    const girada = elipse([0, 0], [0, 6], [2, 0]); // eje largo vertical
    expect(areaLocal(girada) / (Math.PI * 6 * 2)).toBeGreaterThan(0.9994);
    expect(elipse([0, 0], [0, 0], [1, 1])).toEqual([]);
  });

  it('un arco por tres puntos es un cuarto de circunferencia y pasa por el punto medio', () => {
    const a = arco([10, 0], [Math.SQRT1_2 * 10, Math.SQRT1_2 * 10], [0, 10]);
    expect(a[0]).toEqual([10, 0]);
    expect(a[a.length - 1]).toEqual([0, 10]);
    expect(longitudLocal(a) / (Math.PI * 5)).toBeGreaterThan(0.9998);
    expect(longitudLocal(a)).toBeLessThan(Math.PI * 5);
    // Todos los puntos están a 10 del centro.
    expect(a.every((p) => Math.abs(Math.hypot(p[0], p[1]) - 10) < 1e-9)).toBe(true);
  });

  it('el arco va por el lado del punto medio: el largo, si el medio está del otro lado', () => {
    // Tres puntos sobre una circunferencia de radio 10: el medio en (-10,0) obliga a dar la vuelta larga.
    const larga = arco([10, 0], [-10, 0], [0, 10]);
    expect(longitudLocal(larga) / (Math.PI * 15)).toBeGreaterThan(0.9998); // 3/4 de 20π
  });

  it('tres puntos en línea dan un tramo recto', () => {
    expect(arco([0, 0], [5, 0], [10, 0])).toEqual([[0, 0], [10, 0]]);
  });
});

describe('forma que resulta de los clics', () => {
  it('con el cursor como siguiente clic, y sin él al guardar', () => {
    expect(formaDe('rectangulo', [[0, 0]], null)).toBeNull();
    expect(formaDe('rectangulo', [[0, 0]], [4, 3])?.tipo).toBe('poligono');
    const guardada = formaDe('rectangulo', [[0, 0], [4, 3]], [99, 99]); // ya completo: el cursor no cuenta
    expect(areaLocal(guardada!.puntos)).toBeCloseTo(12, 10);
  });

  it('la elipse y el arco muestran su eje antes de tener el tercer punto', () => {
    expect(formaDe('elipse', [[0, 0]], [10, 0])).toEqual({ tipo: 'linea', puntos: [[0, 0], [10, 0]] });
    expect(formaDe('arco', [[0, 0]], [10, 0])?.tipo).toBe('linea');
    expect(formaDe('elipse', [[0, 0], [10, 0]], [0, 4])?.tipo).toBe('poligono');
  });

  it('polilínea y polígono siguen los clics tal cual, con el cursor al final', () => {
    expect(formaDe('polilinea', [[0, 0], [1, 0]], [1, 1])?.puntos).toHaveLength(3);
    expect(formaDe('poligono', [[0, 0], [1, 0], [1, 1]], null)?.tipo).toBe('poligono');
  });
});
