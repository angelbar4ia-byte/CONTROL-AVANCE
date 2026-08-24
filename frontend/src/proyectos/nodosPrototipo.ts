/**
 * Armado del árbol WBS de un prototipo: nivel → etapa → concepto (§7.4).
 *
 * `GET /prototipos/{id}/nodos` ya devuelve los nodos en recorrido
 * padre-antes-que-hijos (el backend ordena con un CTE recursivo sobre
 * `orden`, que solo es comparable entre hermanos); aquí solo se agrupan por
 * `parent_id` para poder anidarlos, sin volver a ordenar nada.
 *
 * Función pura de presentación (§12.11): no decide qué es un nodo, solo lo
 * anida. Vive fuera del componente para poder fijarla con pruebas.
 */

import type { NodoPrototipoRespuesta } from '@/api/generado/modelo';

export interface NodoArbolPrototipo {
  readonly nodo: NodoPrototipoRespuesta;
  readonly hijos: readonly NodoArbolPrototipo[];
}

interface NodoMutable {
  readonly nodo: NodoPrototipoRespuesta;
  readonly hijos: NodoMutable[];
}

/**
 * Si un nodo trae `parent_id` pero ese padre no vino en la lista (alcance
 * acotado, o inconsistencia de datos), se cuelga de la raíz en vez de
 * perderse — mismo criterio que `armarArbolExplosion`: mejor mostrarlo
 * suelto que desaparecerlo de la vista sin avisar.
 */
export function armarArbolPrototipo(
  nodos: readonly NodoPrototipoRespuesta[],
): readonly NodoArbolPrototipo[] {
  const porId = new Map<string, NodoMutable>();
  for (const nodo of nodos) {
    porId.set(nodo.id, { nodo, hijos: [] });
  }

  const raices: NodoMutable[] = [];
  for (const nodo of nodos) {
    const actual = porId.get(nodo.id);
    if (!actual) continue;
    const padre = nodo.parent_id ? porId.get(nodo.parent_id) : undefined;
    if (padre) padre.hijos.push(actual);
    else raices.push(actual);
  }

  return raices;
}

/** Cuántos nodos tiene el árbol, contando los anidados. */
export function contarNodosDelArbol(nodos: readonly NodoArbolPrototipo[]): number {
  return nodos.reduce((total, nodo) => total + 1 + contarNodosDelArbol(nodo.hijos), 0);
}
