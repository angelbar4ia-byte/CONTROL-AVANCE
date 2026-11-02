/**
 * Volumen a partir de un trazo (herramienta «Calcular volumen» del cuantificador).
 *
 * Un polígono da un área: volumen = área × espesor. Una línea da una longitud:
 * volumen = longitud × ancho × alto (una trabe, un castillo). Se descuenta lo que
 * no se vacía (un registro, un ducto). Es una **calculadora**: no guarda nada ni
 * alimenta el presupuesto por sí sola; el resultado se copia o se teclea en la
 * cantidad que corresponda.
 */

import {
  areaDeGeometria,
  longitudDeGeometria,
  type GeometriaGeoJson,
} from './geometria';

export type BaseDeVolumen =
  | { readonly tipo: 'area'; readonly valor: number; readonly unidad: 'm²' | 'u²' }
  | { readonly tipo: 'longitud'; readonly valor: number; readonly unidad: 'm' | 'u' };

/**
 * La base del volumen que da un trazo, en metros si el plano está calibrado y en
 * unidades de plano si no. `null` si el trazo no es ni polígono ni línea (un punto).
 */
export function baseDeVolumen(
  geometria: GeometriaGeoJson,
  escalaMPorUnidad: number | null,
): BaseDeVolumen | null {
  const area = areaDeGeometria(geometria);
  if (area > 0) {
    return escalaMPorUnidad === null
      ? { tipo: 'area', valor: area, unidad: 'u²' }
      : { tipo: 'area', valor: area * escalaMPorUnidad ** 2, unidad: 'm²' };
  }
  const longitud = longitudDeGeometria(geometria);
  if (longitud > 0) {
    return escalaMPorUnidad === null
      ? { tipo: 'longitud', valor: longitud, unidad: 'u' }
      : { tipo: 'longitud', valor: longitud * escalaMPorUnidad, unidad: 'm' };
  }
  return null;
}

/** Interpreta lo que se teclea: acepta coma decimal; vacío o ilegible es 0. */
export function numeroTecleado(texto: string): number {
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/**
 * `base × factores − descuento`, nunca negativo. Si falta un factor (espesor en
 * blanco) el volumen es 0: mejor un cero visible que un número a medias.
 */
export function volumenDe(base: number, factores: readonly number[], descuento = 0): number {
  const bruto = factores.reduce((producto, f) => producto * f, base);
  return Math.max(bruto - Math.max(descuento, 0), 0);
}
