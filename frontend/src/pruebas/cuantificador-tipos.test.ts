import { describe, expect, it } from 'vitest';

import { arco, contornoCerrado, contornoDe, formaDe, siguienteTramo, type TramoDeContorno } from '@/cuantificador/dibujo';
import { areaLocal, longitudLocal, type Punto } from '@/cuantificador/geometria';
import { bloqueDeTipo, tipoDeMedicion } from '@/cuantificador/tipos';

describe('Tipo de medición de un concepto', () => {
  it('deduce el tipo de la unidad, sin importar mayúsculas, puntos ni superíndices', () => {
    for (const u of ['m2', 'M²', ' m 2 ', 'MT2']) expect(tipoDeMedicion(u)).toBe('area');
    for (const u of ['m', 'ml', 'M.L.', 'mts', 'metro lineal']) expect(tipoDeMedicion(u)).toBe('lineal');
    for (const u of ['pza', 'Pieza', 'PZAS', 'lote', 'jgo', 'salida']) expect(tipoDeMedicion(u)).toBe('conteo');
    for (const u of ['m3', 'm³']) expect(tipoDeMedicion(u)).toBe('volumen');
    for (const u of ['kg', 'ton', 'Tonelada', 'lt']) expect(tipoDeMedicion(u)).toBe('derivada');
  });

  it('lo que no se reconoce no deduce nada', () => {
    expect(tipoDeMedicion('xyz')).toBeNull();
    expect(tipoDeMedicion('')).toBeNull();
    expect(tipoDeMedicion(null)).toBeNull();
    expect(tipoDeMedicion(undefined)).toBeNull();
  });

  it('el volumen se mide con áreas y lo derivado no resalta ningún bloque', () => {
    expect(bloqueDeTipo('area')).toBe('area');
    expect(bloqueDeTipo('volumen')).toBe('area');
    expect(bloqueDeTipo('lineal')).toBe('lineal');
    expect(bloqueDeTipo('conteo')).toBe('conteo');
    expect(bloqueDeTipo('derivada')).toBeNull();
    expect(bloqueDeTipo(null)).toBeNull();
  });
});

describe('Recorridos cerrados (herramientas lineales)', () => {
  const A: Punto = [0, 0];
  const B: Punto = [10, 4];

  it('el rectángulo, el círculo y la elipse son una línea cerrada que mide su longitud', () => {
    const rec = formaDe('rectangulo_l', [A, B], null)!;
    expect(rec.tipo).toBe('linea');
    expect(rec.puntos[0]).toEqual(rec.puntos[rec.puntos.length - 1]);
    expect(longitudLocal(rec.puntos)).toBeCloseTo(2 * (10 + 4), 9);

    const cir = formaDe('circulo_l', [A, [5, 0]], null)!;
    expect(cir.tipo).toBe('linea');
    expect(cir.puntos[0]).toEqual(cir.puntos[cir.puntos.length - 1]);
    expect(longitudLocal(cir.puntos) / (2 * Math.PI * 5)).toBeGreaterThan(0.9998);

    const eli = formaDe('elipse_l', [A, [6, 0], [0, 3]], null)!;
    expect(eli.tipo).toBe('linea');
    expect(eli.puntos[0]).toEqual(eli.puntos[eli.puntos.length - 1]);
  });

  it('las versiones de área siguen siendo polígonos sin repetir el primer punto', () => {
    const rec = formaDe('rectangulo', [A, B], null)!;
    expect(rec.tipo).toBe('poligono');
    expect(rec.puntos).toHaveLength(4);
    expect(areaLocal(rec.puntos)).toBeCloseTo(40, 9);
  });
});

describe('Contorno: línea y arco que se cierran en un área', () => {
  const recto = (n: number): TramoDeContorno[] => Array.from({ length: n }, () => 'r' as const);

  it('un contorno de tramos rectos es el polígono de sus vértices', () => {
    const clics: Punto[] = [[0, 0], [10, 0], [10, 10], [0, 10]];
    const anillo = contornoCerrado(clics, recto(3))!;
    expect(anillo).toHaveLength(4);
    expect(areaLocal(anillo)).toBeCloseTo(100, 9);
  });

  it('un arco son dos clics: por dónde pasa y dónde termina', () => {
    expect(siguienteTramo([], 'recto')).toBe('r');
    expect(siguienteTramo([], 'arco')).toBe('am');
    expect(siguienteTramo(['am'], 'arco')).toBe('af');
    expect(siguienteTramo(['am'], 'recto')).toBe('af'); // el arco a medias se termina antes de cambiar
    expect(siguienteTramo(['am', 'af'], 'recto')).toBe('r');
  });

  it('un contorno con un arco mide más área que sin él y cierra solo', () => {
    // Un cuadrado de 10 × 10 con el lado derecho abombado hacia afuera.
    const clics: Punto[] = [[0, 0], [10, 0], [12, 5], [10, 10], [0, 10]];
    const tramos: TramoDeContorno[] = ['r', 'am', 'af', 'r'];
    const anillo = contornoCerrado(clics, tramos)!;
    expect(anillo.length).toBeGreaterThan(10);
    const cuadrado = 100;
    expect(areaLocal(anillo)).toBeGreaterThan(cuadrado);
    // El arco va de (10,0) a (10,10) por (12,5).
    const a = arco([10, 0], [12, 5], [10, 10]);
    expect(anillo.slice(1, 1 + a.length - 1).length).toBeGreaterThan(5);
  });

  it('no hay contornos abiertos: con menos de tres vértices o un arco a medias no cierra', () => {
    expect(contornoCerrado([[0, 0], [10, 0]], recto(1))).toBeNull();
    expect(contornoCerrado([[0, 0], [10, 0], [12, 5]], ['r', 'am'])).toBeNull();
    expect(contornoCerrado([], [])).toBeNull();
  });

  it('la vista previa muestra un área desde tres vértices y una línea antes', () => {
    expect(formaDe('contorno', [[0, 0]], [5, 5], 0, [])?.tipo).toBe('linea');
    expect(formaDe('contorno', [[0, 0], [10, 0]], [10, 10], 0, ['r'])?.tipo).toBe('poligono');
    expect(formaDe('contorno', [], null, 0, [])).toBeNull();
  });

  it('un arco a medias se previsualiza pasando por el último clic y terminando en el cursor', () => {
    const camino = contornoDe([[0, 0], [5, 5]], ['am'], [10, 0]);
    expect(camino.length).toBeGreaterThan(4);
    expect(camino[camino.length - 1]).toEqual([10, 0]);
  });
});
