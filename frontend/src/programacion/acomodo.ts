/**
 * Auto-acomodo del canvas: pone las cajas en capas por precedencia (§7.5).
 *
 * Un grafo de precedencias se lee de izquierda a derecha, y lo que hace que se
 * lea es que ninguna caja quede a la izquierda de una predecesora suya. Eso es
 * exactamente el **ranking por camino más largo**: la capa de una caja es una
 * más que la de su predecesora más profunda. Con eso, todo cable apunta hacia
 * adelante y el flujo constructivo se ve de un vistazo, que es lo que el
 * usuario pidió al pedir "flechas de flujo".
 *
 * No es un layout de librería (dagre y compañía) ni pretende serlo: no cruza
 * menos aristas que ellos. Pero un programa base tiene diez o quince etapas y
 * unas decenas de conceptos por etapa, y a esa escala lo que importa es que
 * las capas sean estables —que reacomodar dos veces dé lo mismo— y que dentro
 * de la capa las cajas queden en el orden del árbol, que es el orden en que el
 * jefe de obra las tiene en la cabeza. Meter una dependencia más al bundle
 * para eso no se paga.
 *
 * Si el grafo trae un ciclo no hay capas posibles; en ese caso las cajas
 * involucradas caen en la capa 0 y el editor las señala aparte (`ciclos.ts`).
 *
 * Módulo puro (§12.11).
 */

import type { Arista } from './grafo';
import { ordenTopologico } from './ciclos';

export interface Posicion {
  readonly x: number;
  readonly y: number;
}

/**
 * Geometría de una caja. Tiene que coincidir con lo que el CSS le da a
 * `.nodo-act`: React Flow no mide el DOM antes del primer render, así que el
 * acomodo trabaja con la medida nominal.
 */
export const ANCHO_CAJA = 224;
export const ALTO_CAJA = 92;
const SEPARACION_X = 92;
const SEPARACION_Y = 28;

export interface EntradaAcomodo {
  readonly id: string;
  /** Orden dentro de su capa cuando empatan; el del árbol WBS. */
  readonly orden: number;
}

/**
 * Posición de cada caja, en capas de izquierda a derecha.
 *
 * `preferidas` permite dar una capa mínima a ciertas cajas —hoy no se usa,
 * pero es el gancho natural para anclar una etapa a su columna cuando se abren
 * sus conceptos—; sin ella el resultado depende solo del grafo.
 */
export function acomodarEnCapas(
  cajas: readonly EntradaAcomodo[],
  aristas: readonly Arista[],
): ReadonlyMap<string, Posicion> {
  const ids = cajas.map((caja) => caja.id);
  const orden = ordenTopologico(ids, aristas) ?? ids;

  const conocidos = new Set(ids);
  const predecesoras = new Map<string, string[]>();
  for (const arista of aristas) {
    if (!conocidos.has(arista.desde) || !conocidos.has(arista.hasta)) continue;
    const lista = predecesoras.get(arista.hasta);
    if (lista) lista.push(arista.desde);
    else predecesoras.set(arista.hasta, [arista.desde]);
  }

  // Camino más largo: recorriendo en orden topológico, la capa de cada caja ya
  // tiene resueltas todas sus predecesoras. Con ciclo el orden es el de
  // entrada y el resultado deja de ser un ranking, pero sigue siendo estable.
  const capa = new Map<string, number>();
  for (const id of orden) {
    const previas = predecesoras.get(id) ?? [];
    const propia = previas.reduce(
      (maxima, previa) => Math.max(maxima, (capa.get(previa) ?? 0) + 1),
      0,
    );
    capa.set(id, propia);
  }

  const porCapa = new Map<number, EntradaAcomodo[]>();
  for (const caja of cajas) {
    const nivel = capa.get(caja.id) ?? 0;
    const fila = porCapa.get(nivel);
    if (fila) fila.push(caja);
    else porCapa.set(nivel, [caja]);
  }

  const posiciones = new Map<string, Posicion>();
  for (const [nivel, fila] of porCapa) {
    const ordenada = [...fila].sort((a, b) => a.orden - b.orden);
    for (const [indice, caja] of ordenada.entries()) {
      posiciones.set(caja.id, {
        x: nivel * (ANCHO_CAJA + SEPARACION_X),
        y: indice * (ALTO_CAJA + SEPARACION_Y),
      });
    }
  }

  return posiciones;
}
