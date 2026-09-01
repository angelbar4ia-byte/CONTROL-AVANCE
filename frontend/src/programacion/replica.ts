/**
 * Replicar el programa base del prototipo a sus obras (§7.5, §11.2
 * `POST /programas-base/{id}/replicar`).
 *
 * *"Componentes que ayuden a establecer el programa base del prototipo y de
 * ahí replicarse para las obras"*: un cluster de 40 casas del mismo modelo se
 * programaba entrando a Programación 40 veces. Aquí vive la lógica de esa
 * pantalla que **no** necesita render —qué casas están elegidas, en qué lotes
 * se manda, cómo va el avance y cómo se lee el parte final—, para poder
 * probarla sin montar el componente (§12.11, mismo patrón que `tramos.ts` y
 * `calendario.ts`).
 *
 * Dos cosas que este módulo **no** hace, a propósito:
 *
 * - No decide si una obra se puede programar. Eso lo resuelve el backend obra
 *   por obra y vuelve en `motivo`; adivinarlo aquí solo lograría que la
 *   pantalla y el servidor discreparan.
 * - No calcula nada del cronograma. Duraciones, dependencias y ruta crítica
 *   los baja el motor (`domain/programacion/reglas.py`).
 *
 * Los tipos se declaran estructurales y no importados del cliente generado: lo
 * que este módulo necesita de cada obra son dos o tres campos, y atarlo a
 * `ObraCandidataRespuesta` lo volvería a regenerar con cada cambio del
 * contrato que no le incumbe.
 */

/** Lo que la lista de selección necesita saber de una obra candidata. */
export interface ObraElegible {
  readonly obra_id: string;
  readonly clave: string;
  /** Versión del cronograma vigente, o `null` si nunca se le instanció uno. */
  readonly version_cronograma: number | null;
}

/** El parte de una obra, tal como lo devuelve el lote. */
export interface ParteDeObra {
  readonly obra_id: string;
  readonly clave: string | null;
  readonly programada: boolean;
  readonly version: number | null;
  readonly n_actividades: number;
  readonly sin_item: readonly string[];
  readonly refs_no_resueltas: readonly string[];
  readonly motivo: string | null;
}

/**
 * Cuántas obras van por petición.
 *
 * El lote se parte en el cliente aunque el endpoint acepte las 40 de un golpe,
 * por dos razones que apuntan al mismo lado: cada obra corre su CPM y su
 * transacción, así que 40 juntas es una petición larga contra los tiempos de
 * un proxy; y sin trocear no hay forma de mover una barra de avance —la
 * pantalla se quedaría igual de quieta durante todo el reparto, que es
 * justamente lo que no puede pasar con 40 casas.
 *
 * Cinco es el compromiso: pocas peticiones y refresco visible. El troceo es
 * seguro porque el lote ya es de mejor esfuerzo por obra: partirlo no cambia
 * el resultado de ninguna casa.
 */
export const TAMANO_DE_LOTE = 5;

/** Parte una lista en tandas del tamaño pedido, conservando el orden. */
export function lotesDe<T>(items: readonly T[], tamano = TAMANO_DE_LOTE): T[][] {
  const paso = Math.max(1, Math.trunc(tamano));
  const lotes: T[][] = [];
  for (let i = 0; i < items.length; i += paso) {
    lotes.push(items.slice(i, i + paso));
  }
  return lotes;
}

/** Alterna una obra en la selección. Devuelve un conjunto nuevo: el estado de
 * React no se muta en su lugar. */
export function alternarObra(
  seleccion: ReadonlySet<string>,
  obraId: string,
): ReadonlySet<string> {
  const siguiente = new Set(seleccion);
  if (!siguiente.delete(obraId)) siguiente.add(obraId);
  return siguiente;
}

/** Seleccionar todas. */
export function todasLasObras(obras: readonly ObraElegible[]): ReadonlySet<string> {
  return new Set(obras.map((obra) => obra.obra_id));
}

/**
 * Los ids elegidos **en el orden de la lista**, no en el de los clics.
 *
 * Importa porque el parte del servidor vuelve en el orden en que se pidieron
 * las obras, y quien lo lee va bajando por la lista que tiene enfrente: si el
 * reporte saliera en el orden en que se marcaron las casillas, sería
 * imposible de seguir.
 */
export function obrasElegidas(
  obras: readonly ObraElegible[],
  seleccion: ReadonlySet<string>,
): string[] {
  return obras.filter((obra) => seleccion.has(obra.obra_id)).map((obra) => obra.obra_id);
}

/** Lo que hay que advertir antes de replicar (§7.5). */
export interface AvisoDeSeleccion {
  readonly total: number;
  /** Cuántas de las elegidas ya traen cronograma: a esas se les crea una
   * versión **nueva**, no se les corrige la que tienen. */
  readonly conCronograma: number;
}

export function avisoDeSeleccion(
  obras: readonly ObraElegible[],
  seleccion: ReadonlySet<string>,
): AvisoDeSeleccion {
  const elegidas = obras.filter((obra) => seleccion.has(obra.obra_id));
  return {
    total: elegidas.length,
    conCronograma: elegidas.filter((obra) => obra.version_cronograma !== null).length,
  };
}

/** Avance del reparto mientras corre. */
export interface Progreso {
  readonly hechas: number;
  readonly total: number;
  /** 0–100, entero: es lo que se pinta como ancho de la barra. */
  readonly pct: number;
}

export function progresoDe(hechas: number, total: number): Progreso {
  if (total <= 0) return { hechas: 0, total: 0, pct: 0 };
  const acotadas = Math.min(Math.max(hechas, 0), total);
  return {
    hechas: acotadas,
    total,
    pct: Math.round((acotadas / total) * 100),
  };
}

/** Cómo quedó el lote completo. */
export interface Recuento {
  readonly programadas: number;
  readonly fallidas: number;
  /** Cuántas obras reportaron actividades sin renglón en la plantilla: no es
   * un fallo, pero es el hueco que Control de obra debe completar (§7.5). */
  readonly conHuecos: number;
}

export function recuentoDe(partes: readonly ParteDeObra[]): Recuento {
  return {
    programadas: partes.filter((parte) => parte.programada).length,
    fallidas: partes.filter((parte) => !parte.programada).length,
    conHuecos: partes.filter(
      (parte) =>
        parte.programada &&
        (parte.sin_item.length > 0 || parte.refs_no_resueltas.length > 0),
    ).length,
  };
}

/**
 * El parte con las que fallaron arriba.
 *
 * Con 40 renglones, lo que se necesita ver primero es lo que hay que atender,
 * no las 39 que salieron bien. Dentro de cada grupo se conserva el orden de la
 * petición —que es el de la lista de la pantalla—, así que la reordenación no
 * desordena nada más.
 */
export function partesParaReporte(partes: readonly ParteDeObra[]): ParteDeObra[] {
  return [
    ...partes.filter((parte) => !parte.programada),
    ...partes.filter((parte) => parte.programada),
  ];
}
