import { describe, expect, it } from 'vitest';

import { areaLocal } from '@/cuantificador/geometria';
import {
  ELEMENTOS,
  bandaDeLinea,
  contornoUnitario,
  desplazarPolilinea,
  normalizarContorno,
  poligonoDeForma,
  type Forma,
} from '@/cuantificador/formas';

const cuadrado = (lado: number): Forma => ({ tipo: 'cuadrado', anchoM: lado, altoM: lado, rotacionGrados: 0 });

describe('formas que se estampan', () => {
  it('un cuadrado de 0.15 m centrado tiene 0.0225 m² y queda centrado', () => {
    const anillo = poligonoDeForma([10, 20], cuadrado(0.15), 1);
    expect(areaLocal(anillo)).toBeCloseTo(0.0225, 10);
    const cx = anillo.reduce((s, p) => s + p[0], 0) / anillo.length;
    const cy = anillo.reduce((s, p) => s + p[1], 0) / anillo.length;
    expect(cx).toBeCloseTo(10, 10);
    expect(cy).toBeCloseTo(20, 10);
  });

  it('el tamaño se convierte con las unidades por metro del plano', () => {
    // Plano calibrado a 0.5 m por unidad: 2 unidades por metro.
    const anillo = poligonoDeForma([0, 0], cuadrado(1), 2);
    expect(areaLocal(anillo)).toBeCloseTo(4, 10);
  });

  it('un rectángulo gira sin cambiar de área', () => {
    const f: Forma = { tipo: 'rectangulo', anchoM: 2, altoM: 1, rotacionGrados: 90 };
    const anillo = poligonoDeForma([0, 0], f, 1);
    expect(areaLocal(anillo)).toBeCloseTo(2, 10);
    const xs = anillo.map((p) => p[0]);
    expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo(1, 10); // ahora es más alto que ancho
  });

  it('cada forma tiene el área que le toca en una caja de 1 × 1', () => {
    expect(areaLocal(contornoUnitario('cuadrado'))).toBeCloseTo(1, 10);
    expect(areaLocal(contornoUnitario('triangulo'))).toBeCloseTo(0.5, 10);
    expect(areaLocal(contornoUnitario('hexagono'))).toBeCloseTo(0.75, 10);
    // 24 lados inscritos en un círculo de radio 0.5: casi π/4.
    expect(areaLocal(contornoUnitario('circulo'))).toBeCloseTo(Math.PI / 4, 1);
  });

  it('«dibujar forma» usa el contorno normalizado y cae en cuadrado si no hay uno válido', () => {
    const triangulo = normalizarContorno([
      [10, 10],
      [30, 10],
      [20, 40],
    ]);
    expect(triangulo).not.toBeNull();
    const f: Forma = { tipo: 'libre', anchoM: 2, altoM: 4, rotacionGrados: 0, vertices: triangulo! };
    expect(areaLocal(poligonoDeForma([0, 0], f, 1))).toBeCloseTo(4, 10); // 2 × 4 / 2
    expect(contornoUnitario('libre')).toHaveLength(4);
    expect(normalizarContorno([[0, 0], [1, 1]])).toBeNull();
    expect(normalizarContorno([[0, 0], [1, 0], [2, 0]])).toBeNull(); // sin alto
  });

  it('los elementos de obra traen su tamaño típico', () => {
    expect(ELEMENTOS.find((e) => e.nombre === 'Castillo')).toMatchObject({ anchoM: 0.15, altoM: 0.15 });
    expect(ELEMENTOS.find((e) => e.nombre === 'Columna circular')?.tipo).toBe('circulo');
  });
});

describe('línea con grosor', () => {
  const eje = [
    [0, 0],
    [10, 0],
  ] as const;

  it('desplazar a la izquierda mirando en el sentido del dibujo sube en pantalla (Y hacia abajo)', () => {
    expect(desplazarPolilinea(eje, 1)).toEqual([
      [0, -1],
      [10, -1],
    ]);
    expect(desplazarPolilinea(eje, -1)).toEqual([
      [0, 1],
      [10, 1],
    ]);
  });

  it('la banda mide largo × grosor, sea cual sea la alineación', () => {
    for (const alineacion of ['centro', 'izquierda', 'derecha'] as const) {
      expect(areaLocal(bandaDeLinea(eje, 0.3, alineacion))).toBeCloseTo(3, 10);
    }
  });

  it('la alineación pone el cuerpo de un lado del eje o repartido', () => {
    const ys = (a: 'centro' | 'izquierda' | 'derecha') => bandaDeLinea(eje, 0.3, a).map((p) => p[1]);
    expect(Math.min(...ys('centro'))).toBeCloseTo(-0.15, 10);
    expect(Math.max(...ys('centro'))).toBeCloseTo(0.15, 10);
    expect(Math.min(...ys('izquierda'))).toBeCloseTo(-0.3, 10);
    expect(Math.max(...ys('izquierda'))).toBeCloseTo(0, 10);
    expect(Math.min(...ys('derecha'))).toBeCloseTo(0, 10);
    expect(Math.max(...ys('derecha'))).toBeCloseTo(0.3, 10);
  });

  it('una esquina a 90° se resuelve a inglete y el cuerpo no se parte', () => {
    const l = [
      [0, 0],
      [10, 0],
      [10, 10],
    ] as const;
    // A inglete el lado exterior gana lo que el interior pierde: el área sigue siendo largo × grosor.
    expect(areaLocal(bandaDeLinea(l, 1, 'centro'))).toBeCloseTo(20, 10);
  });

  it('sin grosor o con un solo punto no hay banda', () => {
    expect(bandaDeLinea(eje, 0, 'centro')).toEqual([]);
    expect(bandaDeLinea([[0, 0]], 1, 'centro')).toEqual([]);
  });
});
