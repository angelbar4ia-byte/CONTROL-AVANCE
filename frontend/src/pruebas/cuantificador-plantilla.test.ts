import { describe, expect, it } from 'vitest';

import {
  buscarPlantilla,
  factorDeReduccion,
  plantillaConForma,
  recortar,
  reducir,
  type ImagenGris,
} from '@/cuantificador/plantilla';

/** Una hoja blanca con símbolos (una «T» de 9×9) dibujados en negro en las esquinas dadas. */
function hoja(ancho: number, alto: number, simbolos: readonly (readonly [number, number])[]): ImagenGris {
  const datos = new Float32Array(ancho * alto).fill(255);
  for (const [sx, sy] of simbolos) {
    for (let i = 0; i < 9; i++) datos[sy * ancho + sx + i] = 0; // la barra de arriba
    for (let j = 0; j < 9; j++) datos[(sy + j) * ancho + sx + 4] = 0; // el tronco
  }
  return { ancho, alto, datos };
}

describe('Buscar una plantilla en la imagen', () => {
  it('encuentra todos los símbolos iguales y cada uno una sola vez', async () => {
    const donde = [
      [10, 10],
      [50, 12],
      [30, 40],
    ] as const;
    const imagen = hoja(80, 60, donde);
    const plantilla = recortar(imagen, 9, 9, 11, 11); // el primero, con un margen blanco
    const r = await buscarPlantilla(imagen, plantilla, { minimo: 0.9 });
    expect(r).toHaveLength(3);
    for (const [sx, sy] of donde) {
      expect(r.some((c) => Math.abs(c.x - (sx - 1)) <= 1 && Math.abs(c.y - (sy - 1)) <= 1 && c.puntaje > 0.95)).toBe(true);
    }
  });

  it('no inventa coincidencias donde no hay nada parecido', async () => {
    const imagen = hoja(80, 60, [[10, 10]]);
    const plantilla = recortar(imagen, 9, 9, 11, 11);
    const sinSimbolos = hoja(80, 60, []);
    expect(await buscarPlantilla(sinSimbolos, plantilla, { minimo: 0.8 })).toEqual([]);
    expect((await buscarPlantilla(imagen, plantilla, { minimo: 0.8 })).length).toBe(1);
  });

  it('una plantilla lisa (un trozo de hoja en blanco) no busca nada', async () => {
    const imagen = hoja(80, 60, [[10, 10]]);
    const blanco = recortar(imagen, 60, 40, 11, 11);
    expect(plantillaConForma(blanco)).toBe(false);
    expect(await buscarPlantilla(imagen, blanco)).toEqual([]);
  });

  it('ceder cede el paso de vez en cuando para no congelar la pantalla', async () => {
    const imagen = hoja(80, 120, [[10, 10]]);
    const plantilla = recortar(imagen, 9, 9, 11, 11);
    let cedidas = 0;
    await buscarPlantilla(imagen, plantilla, { cedeCada: 10, ceder: async () => void (cedidas += 1) });
    expect(cedidas).toBeGreaterThan(5);
  });
});

describe('Reducir la imagen', () => {
  it('promedia bloques', () => {
    const imagen: ImagenGris = { ancho: 4, alto: 2, datos: Float32Array.from([0, 0, 100, 100, 0, 0, 100, 100]) };
    const r = reducir(imagen, 2);
    expect([r.ancho, r.alto, Array.from(r.datos)]).toEqual([2, 1, [0, 100]]);
  });

  it('el factor deja la plantilla chica y la imagen manejable', () => {
    expect(factorDeReduccion(48, 48, 1000, 800)).toBe(2);
    expect(factorDeReduccion(10, 10, 6000, 4000)).toBe(4);
    expect(factorDeReduccion(10, 10, 800, 600)).toBe(1);
  });
});
