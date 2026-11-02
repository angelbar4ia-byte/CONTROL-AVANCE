import { describe, expect, it } from 'vitest';

import {
  areaDePoligono,
  binarizar,
  contornoDe,
  dilatar,
  muros,
  regionesCerradas,
  simplificar,
  type Mascara,
} from '@/cuantificador/takeoff';
import type { ImagenGris } from '@/cuantificador/plantilla';

/** Una hoja blanca de ancho × alto con rectángulos negros (x, y, w, h) ya dibujados. */
function hoja(ancho: number, alto: number, negros: readonly (readonly [number, number, number, number])[]): ImagenGris {
  const datos = new Float32Array(ancho * alto).fill(255);
  for (const [x, y, w, h] of negros) for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) datos[j * ancho + i] = 0;
  return { ancho, alto, datos };
}

/** Un cuarto de 40×30 de interior, rodeado por paredes de 3 px, con una puerta opcional en la pared de abajo. */
function cuarto(puerta: boolean): ImagenGris {
  const negros: [number, number, number, number][] = [
    [10, 10, 46, 3], // arriba
    [10, 43, 46, 3], // abajo
    [10, 10, 3, 36], // izquierda
    [53, 10, 3, 36], // derecha
  ];
  const img = hoja(80, 60, negros);
  if (puerta) for (let j = 43; j < 46; j++) for (let i = 30; i < 36; i++) img.datos[j * 80 + i] = 255; // 6 px de hueco
  return img;
}

describe('Zonas cerradas (áreas)', () => {
  it('un cuarto cerrado es una región con el área de su interior', () => {
    const lineas = binarizar(cuarto(false), 128);
    const r = regionesCerradas(lineas, { areaMin: 50, areaMax: 10_000 });
    expect(r).toHaveLength(1);
    expect(r[0]!.pixeles).toBe(40 * 30);
  });

  it('con una puerta abierta el cuarto se escapa al exterior, salvo que se cierre el hueco', () => {
    const lineas = binarizar(cuarto(true), 128);
    expect(regionesCerradas(lineas, { areaMin: 50, areaMax: 10_000 })).toHaveLength(0);
    const cerradas = regionesCerradas(lineas, { cierre: 4, areaMin: 50, areaMax: 10_000 });
    expect(cerradas).toHaveLength(1);
    // La zona recuperada vuelve a casi todo su interior (la puerta se cuenta dentro del hueco).
    expect(cerradas[0]!.pixeles).toBeGreaterThanOrEqual(40 * 30);
  });

  it('descarta lo muy chico y lo muy grande', () => {
    const lineas = binarizar(cuarto(false), 128);
    expect(regionesCerradas(lineas, { areaMin: 5_000, areaMax: 10_000 })).toEqual([]);
    expect(regionesCerradas(lineas, { areaMin: 1, areaMax: 100 })).toEqual([]);
  });
});

describe('Contorno de una zona', () => {
  it('el contorno de un rectángulo, simplificado, son sus cuatro esquinas', () => {
    const lineas = binarizar(cuarto(false), 128);
    const [r] = regionesCerradas(lineas, { areaMin: 50, areaMax: 10_000 });
    const c = simplificar(contornoDe(r!.mascara, 80, 60), 0.5);
    expect(c).toHaveLength(4);
    expect(areaDePoligono(c)).toBeCloseTo(40 * 30, 5);
  });

  it('una zona en L conserva sus seis esquinas y su área', () => {
    const ancho = 20;
    const alto = 20;
    const mascara = new Uint8Array(ancho * alto);
    for (let y = 2; y < 18; y++) for (let x = 2; x < 8; x++) mascara[y * ancho + x] = 1; // el palo
    for (let y = 12; y < 18; y++) for (let x = 8; x < 16; x++) mascara[y * ancho + x] = 1; // el pie
    const c = simplificar(contornoDe(mascara, ancho, alto), 0.5);
    expect(c).toHaveLength(6);
    expect(areaDePoligono(c)).toBeCloseTo(16 * 6 + 6 * 8, 5);
  });
});

describe('Muros macizos', () => {
  it('encuentra un muro horizontal y uno vertical gruesos, y no las líneas finas', () => {
    const img = hoja(100, 80, [
      [10, 20, 60, 6], // muro horizontal macizo
      [80, 10, 6, 50], // muro vertical macizo
      [10, 60, 70, 1], // línea fina (una cota): no es muro
    ]);
    const lista = muros(binarizar(img, 128), { largoMin: 20, gruesoMin: 4 });
    const h = lista.find((m) => m.desde[1] === m.hasta[1]);
    const v = lista.find((m) => m.desde[0] === m.hasta[0]);
    expect(lista).toHaveLength(2);
    expect(h).toMatchObject({ desde: [10, 23], hasta: [70, 23], grueso: 6 });
    expect(v).toMatchObject({ desde: [83, 10], hasta: [83, 60], grueso: 6 });
  });
});

describe('Morfología', () => {
  it('dilatar engorda un píxel suelto', () => {
    const m: Mascara = { ancho: 5, alto: 5, datos: new Uint8Array(25) };
    m.datos[12] = 1;
    expect(dilatar(m, 1).datos.reduce((s, v) => s + v, 0)).toBe(9);
  });
});
