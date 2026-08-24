/**
 * Armado del árbol WBS de un prototipo: prototipo → nivel → etapa →
 * concepto/concepto auxiliar (§7.4, §10.1 — los cinco tipos de fila del
 * archivo real, sin bajar a material/mano de obra/subcontrato: esos arman
 * el APU del concepto, que es la explosión del CPU, no un nivel más de
 * este árbol).
 *
 * `GET /prototipos/{id}/nodos` ya devuelve los nodos en recorrido
 * padre-antes-que-hijos (el backend ordena con un CTE recursivo sobre
 * `orden`, que solo es comparable entre hermanos); aquí solo se agrupan por
 * `parent_id` para poder anidarlos, sin volver a ordenar nada. `prototipo`
 * no es un `prototipo_nodo` real —la tabla nunca lo guarda así (§7.4)—, así
 * que aquí se envuelve el bosque de niveles bajo una raíz sintética, para
 * que el árbol se vea como el archivo original lo describe.
 *
 * Función pura de presentación (§12.11): no decide qué es un nodo, solo lo
 * anida. Vive fuera del componente para poder fijarla con pruebas.
 */

import type { NodoPrototipoRespuesta, PartidaRespuesta } from '@/api/generado/modelo';

/**
 * `NodoPrototipoRespuesta.tipo` no distingue concepto de concepto auxiliar
 * —los dos se guardan como `'concepto'`, `concepto_tipo` es lo que sí lo
 * dice (§10.1)—; este tipo ensancha esa distinción para la pantalla, más
 * `'prototipo'` para la raíz sintética.
 */
export type TipoNodoArbol = 'prototipo' | 'nivel' | 'etapa' | 'concepto' | 'concepto_auxiliar';

export interface NodoArbolPrototipo {
  readonly id: string;
  readonly tipo: TipoNodoArbol;
  readonly clave: string | null;
  readonly nombre: string;
  readonly cantidad: string | null;
  readonly hijos: readonly NodoArbolPrototipo[];
}

interface NodoMutable {
  readonly id: string;
  readonly tipo: TipoNodoArbol;
  readonly clave: string | null;
  readonly nombre: string;
  readonly cantidad: string | null;
  readonly hijos: NodoMutable[];
}

function tipoDeArbol(nodo: NodoPrototipoRespuesta): TipoNodoArbol {
  return nodo.tipo === 'concepto' && nodo.concepto_tipo === 'auxiliar' ? 'concepto_auxiliar' : nodo.tipo;
}

/**
 * Si un nodo trae `parent_id` pero ese padre no vino en la lista (alcance
 * acotado, o inconsistencia de datos), se cuelga de la raíz del prototipo
 * en vez de perderse — mismo criterio que `armarArbolExplosion`: mejor
 * mostrarlo suelto que desaparecerlo de la vista sin avisar.
 */
export function armarArbolPrototipo(
  prototipo: { readonly id: string; readonly clave: string; readonly nombre: string },
  nodos: readonly NodoPrototipoRespuesta[],
): NodoArbolPrototipo {
  const porId = new Map<string, NodoMutable>();
  for (const nodo of nodos) {
    porId.set(nodo.id, {
      id: nodo.id,
      tipo: tipoDeArbol(nodo),
      clave: nodo.clave ?? null,
      nombre: nodo.nombre,
      cantidad: nodo.cantidad ?? null,
      hijos: [],
    });
  }

  const raices: NodoMutable[] = [];
  for (const nodo of nodos) {
    const actual = porId.get(nodo.id);
    if (!actual) continue;
    const padre = nodo.parent_id ? porId.get(nodo.parent_id) : undefined;
    if (padre) padre.hijos.push(actual);
    else raices.push(actual);
  }

  return {
    id: prototipo.id,
    tipo: 'prototipo',
    clave: prototipo.clave,
    nombre: prototipo.nombre,
    cantidad: null,
    hijos: raices,
  };
}

/**
 * Importe de cada nodo: el propio si es concepto/concepto auxiliar con
 * partida, o la suma de sus hijos si es prototipo/nivel/etapa — así una
 * etapa (o el prototipo completo) muestra cuánto cuesta en total sin tener
 * que sumar sus conceptos a mano. Unidad/cantidad/PU no se agregan igual
 * (mezclar M2 de un concepto con KG de otro no dice nada), por eso solo el
 * importe sube por el árbol.
 */
export function sumarImportesPorNodo(
  raiz: NodoArbolPrototipo,
  partidaPorNodo: ReadonlyMap<string, PartidaRespuesta>,
): ReadonlyMap<string, number> {
  const totales = new Map<string, number>();

  function sumar(nodo: NodoArbolPrototipo): number {
    const esConcepto = nodo.tipo === 'concepto' || nodo.tipo === 'concepto_auxiliar';
    const total = esConcepto
      ? Number(partidaPorNodo.get(nodo.id)?.importe ?? 0)
      : nodo.hijos.reduce((acumulado, hijo) => acumulado + sumar(hijo), 0);
    totales.set(nodo.id, total);
    return total;
  }

  sumar(raiz);
  return totales;
}
