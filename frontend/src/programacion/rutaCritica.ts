/**
 * Ruta crítica del **borrador**, con tolerancia de holgura (§6, §7.5).
 *
 * ## Qué es y qué no es
 *
 * No es el CPM del motor. La ruta crítica de una obra la calcula
 * `domain/programacion/cpm.py` contra el calendario laboral, contra las fechas
 * reales y contra el avance capturado, y llega resuelta por actividad
 * (`es_critica`) en `GET /obras/{id}/ruta-critica`. Un programa base todavía no
 * es ninguna obra: no tiene fechas, no tiene avance y no ha pasado por el
 * motor. Lo que hay aquí es la cadena sin holgura **del eje relativo del
 * borrador**, sobre la pasada hacia atrás que ya calcula
 * `holguraDelBorrador` (`filasPrograma.ts`).
 *
 * Las dos coinciden en semana natural y difieren en cuanto hay días inhábiles
 * de por medio, exactamente igual que la columna Holgura, y por eso la
 * herramienta se rotula como del borrador. Sirve para lo que el jefe de obra
 * necesita mientras arma la plantilla —¿qué cadena estoy alargando cuando
 * alargo esto?— y no para prometer una fecha.
 *
 * ## La tolerancia
 *
 * Crítico es holgura cero. En la práctica, en un programa de ciento cincuenta
 * renglones capturados a medio día, media docena de actividades quedan con
 * holgura de 0.5 d y son crítica de facto: cualquier tropiezo las mete en la
 * cadena. La tolerancia deja decir "cuéntame como críticas las que tengan hasta
 * N días de margen", que es lo que convierte el resaltado en una herramienta de
 * lectura y no en un adorno binario. Con tolerancia 0 es la definición
 * estricta.
 *
 * ## Los resúmenes heredan, no calculan
 *
 * Una barra de nivel o de etapa es derivada (§7.4) y no tiene holgura propia
 * —la holgura es de la actividad que cierra la rama—. Se marca crítica cuando
 * **alguno** de sus descendientes lo es, que es lo que hace utilizable el
 * resaltado con el árbol plegado: si la cadena crítica está dentro de una etapa
 * colapsada, la etapa lo dice.
 *
 * Módulo puro (§12.11).
 */

import type { FilaPrograma } from './filasPrograma';

export interface RutaCritica {
  /** Nodos resaltados: las actividades sin holgura y los resúmenes que las contienen. */
  readonly criticas: ReadonlySet<string>;
  /** Cuántas actividades —no resúmenes— entraron en la cadena. */
  readonly nActividades: number;
  /** Días de trabajo que suman esas actividades. */
  readonly diasCriticos: number;
  /** La menor holgura del programa; `null` si no hay nada colocado. */
  readonly holguraMinima: number | null;
}

export const RUTA_CRITICA_VACIA: RutaCritica = {
  criticas: new Set(),
  nActividades: 0,
  diasCriticos: 0,
  holguraMinima: null,
};

/**
 * La cadena crítica del borrador.
 *
 * Se resuelve sobre las filas ya aplanadas —que traen la holgura calculada y el
 * `parentId`— y no sobre el borrador, por dos motivos: la pasada hacia atrás ya
 * está hecha ahí y repetirla daría dos cifras que un día discreparían, y la
 * herencia hacia arriba necesita el árbol en preorden, que es justo lo que las
 * filas son.
 */
export function trazarRutaCritica(
  filas: readonly FilaPrograma[],
  toleranciaDias: number,
): RutaCritica {
  const tolerancia = Math.max(0, toleranciaDias);
  const criticas = new Set<string>();

  let nActividades = 0;
  let diasCriticos = 0;
  let holguraMinima: number | null = null;

  for (const fila of filas) {
    if (fila.esResumen || !fila.capturado || fila.holguraDias === null) continue;
    holguraMinima =
      holguraMinima === null ? fila.holguraDias : Math.min(holguraMinima, fila.holguraDias);
    // Se compara con un epsilon porque la holgura viene de restas de
    // `numeric(8,2)`: una actividad con holgura exacta 0.5 no puede quedar
    // fuera de una tolerancia de 0.5 por el último bit del punto flotante.
    if (fila.holguraDias > tolerancia + 0.001) continue;
    criticas.add(fila.nodoId);
    nActividades += 1;
    diasCriticos += fila.diasLaborables ?? 0;
  }

  // Herencia hacia arriba. Las filas llegan en preorden —padre antes que
  // hijos—, así que recorrerlas al revés garantiza que cuando se mira un nodo
  // sus descendientes ya decidieron.
  for (let i = filas.length - 1; i >= 0; i -= 1) {
    const fila = filas[i];
    if (!fila || fila.parentId === null || !criticas.has(fila.nodoId)) continue;
    criticas.add(fila.parentId);
  }

  return {
    criticas,
    nActividades,
    diasCriticos: Math.round(diasCriticos * 100) / 100,
    holguraMinima,
  };
}
