/**
 * El cuadro de datos: un resumen de las medidas de lo que se ve en pantalla.
 *
 * Suma lo que cada trazo visible mide con su geometría y la escala del plano, y agrupa por
 * concepto lo que el servidor ya calculó en cada enlace vigente. Los primeros números son vista
 * previa; los de por concepto son las cantidades que cuentan.
 */

import { areaDeGeometria, longitudDeGeometria, partesDe, type GeometriaGeoJson } from './geometria';
import { unidadesDeEscala } from './etiquetas';

export interface TrazoParaResumen {
  readonly id: string;
  readonly geometry: GeometriaGeoJson;
  readonly properties: {
    readonly grosor_m?: number | string | null;
    readonly forma?: unknown;
    readonly n_huecos?: number;
    readonly enlaces: readonly {
      readonly tipo_nodo: string;
      readonly nodo_id: string;
      readonly matriz_concepto_id?: string | null;
      readonly medida: string;
      readonly vigente: boolean;
      readonly cantidad: number | string;
    }[];
  };
}

export interface ResumenPorNodo {
  readonly clave: string;
  readonly tipoNodo: string;
  readonly nodoId: string;
  readonly trazos: number;
  readonly medidas: Readonly<Record<string, number>>;
}

export interface Resumen {
  readonly trazos: number;
  readonly areas: { readonly n: number; readonly total: number };
  readonly formas: { readonly n: number; readonly total: number };
  readonly lineas: { readonly n: number; readonly longitud: number; readonly areaMuros: number };
  /** Piezas contadas con la herramienta Punto: puntos y formas estampadas. Los vértices no cuentan. */
  readonly puntos: number;
  readonly huecos: { readonly n: number; readonly total: number };
  readonly unidades: { readonly lineal: string; readonly superficie: string };
  readonly porNodo: readonly ResumenPorNodo[];
}

export function resumenDePantalla(trazos: readonly TrazoParaResumen[], escala: number | null): Resumen {
  const { lineal, superficie, k } = unidadesDeEscala(escala);
  let nAreas = 0;
  let totalAreas = 0;
  let nFormas = 0;
  let totalFormas = 0;
  let nLineas = 0;
  let longitud = 0;
  let areaMuros = 0;
  let puntos = 0;
  let nHuecos = 0;
  let totalHuecos = 0;
  const nodos = new Map<string, { tipoNodo: string; nodoId: string; trazos: Set<string>; medidas: Record<string, number> }>();

  for (const t of trazos) {
    const partes = partesDe(t.geometry);
    const area = areaDeGeometria(t.geometry) * k * k;
    const largo = longitudDeGeometria(t.geometry) * k;
    const huecos = partes.filter((p) => p.tipo === 'anillo' && p.hueco);
    if (area > 0) {
      if (t.properties.forma) {
        nFormas += 1;
        totalFormas += area;
      } else {
        nAreas += 1;
        totalAreas += area;
      }
      nHuecos += huecos.length;
      totalHuecos += huecos.reduce((s, h) => s + (h.puntos.length > 2 ? Math.abs(shoelace(h.puntos)) : 0), 0) * k * k;
    } else if (largo > 0) {
      nLineas += 1;
      longitud += largo;
      const grosor = Number(t.properties.grosor_m ?? 0);
      if (grosor > 0 && escala !== null) areaMuros += largo * grosor;
    } else if (partes.some((p) => p.tipo === 'punto')) {
      puntos += 1;
    }
    // Una forma estampada (un castillo, una columna) es también una pieza de la herramienta Punto.
    if (t.properties.forma && area > 0) puntos += 1;

    for (const e of t.properties.enlaces) {
      if (!e.vigente) continue;
      const clave = `${e.tipo_nodo}:${e.nodo_id}:${e.matriz_concepto_id ?? ''}`;
      const nodo = nodos.get(clave) ?? { tipoNodo: e.tipo_nodo, nodoId: e.nodo_id, trazos: new Set<string>(), medidas: {} };
      nodo.trazos.add(t.id);
      nodo.medidas[e.medida] = (nodo.medidas[e.medida] ?? 0) + Number(e.cantidad);
      nodos.set(clave, nodo);
    }
  }

  return {
    trazos: trazos.length,
    areas: { n: nAreas, total: totalAreas },
    formas: { n: nFormas, total: totalFormas },
    lineas: { n: nLineas, longitud, areaMuros },
    puntos,
    huecos: { n: nHuecos, total: totalHuecos },
    unidades: { lineal, superficie },
    porNodo: [...nodos.entries()].map(([clave, n]) => ({
      clave,
      tipoNodo: n.tipoNodo,
      nodoId: n.nodoId,
      trazos: n.trazos.size,
      medidas: n.medidas,
    })),
  };
}

function shoelace(puntos: readonly (readonly [number, number])[]): number {
  let suma = 0;
  for (let i = 0; i < puntos.length; i += 1) {
    const a = puntos[i] as readonly [number, number];
    const b = puntos[(i + 1) % puntos.length] as readonly [number, number];
    suma += a[0] * b[1] - b[0] * a[1];
  }
  return suma / 2;
}
