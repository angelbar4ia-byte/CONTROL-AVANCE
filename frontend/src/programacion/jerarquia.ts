/**
 * Gantt jerárquico: el cronograma visto como el árbol WBS (§7.4, §6, §11.2).
 *
 * `GET /obras/{id}/programa/arbol` devuelve un renglón por nodo del árbol con
 * actividades debajo, ya resumido por el backend: inicio, fin, span y avance
 * **ponderado por importe** los calcula
 * `domain/programacion/jerarquia.resumir_arbol`. Aquí no se recalcula ninguno
 * —igual que `filas.ts` no recalcula el CPM (§12.11)—: lo que se hace es
 * presentación, y es de tres clases.
 *
 * 1. **Aplanar el árbol en renglones**, con su sangría y su estado de
 *    expansión. El Gantt dibuja una lista, no un árbol; el nivel de anidación
 *    llega como `profundidad` y aquí se vuelve indentación.
 * 2. **Casar cada nodo `concepto` con su fila de actividad**. La barra resumen
 *    de nivel y etapa se dibuja con lo que trae el árbol; la del concepto, con
 *    la `FilaGantt` que ya fusiona programa y ruta crítica (`filas.ts`), que es
 *    la única que sabe de criticidad, holgura y desfase. Un nodo `concepto`
 *    cuya actividad no llegó se dibuja igual con lo del árbol: esconderlo
 *    dejaría un hueco en la jerarquía.
 * 3. **Decidir qué se ve colapsado al abrir**, a partir de la profundidad de
 *    captura que guarda el programa base (migración 0041).
 *
 * ## Por qué el resumen no es editable
 *
 * Sólo las hojas `concepto` son `Actividad` (§11.3 A.2). La barra de un nivel
 * o una etapa es **derivada**; ofrecer el panel de ajuste sobre ella sugeriría
 * que existe una fila que editar, y capturar avance ahí duplicaría cantidad y
 * costo sobre los de sus hijos (§6, §7.6). Lo que sí se ofrece sobre un
 * resumen es programarlo —repartir su ventana hacia abajo—, que es otra cosa y
 * tiene su propio endpoint.
 */

import type {
  ArbolDeProgramaRespuesta,
  ClaseNodo,
  ConflictoJerarquiaRespuesta,
  NodoDelArbolRespuesta,
} from '@/api/generado/modelo';
import type { FilaGantt } from './filas';

export interface FilaJerarquia {
  readonly nodoId: string;
  readonly tipo: ClaseNodo;
  readonly nombre: string;
  readonly parentId: string | null;
  readonly profundidad: number;
  /** `true` en `nivel` y `etapa`: barra derivada, de lectura (§7.4). */
  readonly esResumen: boolean;
  /** Cuántos conceptos cuelgan del nodo, a cualquier distancia. */
  readonly nActividades: number;
  readonly inicio: string | null;
  readonly fin: string | null;
  /** Span de la barra en días del calendario del cronograma. */
  readonly duracionDias: number;
  /** Suma de los días de trabajo de sus conceptos. */
  readonly duracionHojasDias: number;
  /** 0–100, ponderado por importe (§6). */
  readonly avancePct: number;
  readonly importe: number;
  readonly conflicto: ConflictoJerarquiaRespuesta | null;
  /** La actividad del nodo, si es `concepto` y su fila llegó. */
  readonly fila: FilaGantt | null;
  /** El nodo tiene descendientes en el árbol: se puede colapsar. */
  readonly tieneHijos: boolean;
}

/** Decimal del contrato (cadena) → número; `0` si no viene o no es finito. */
function aNumero(valor: string | number | null | undefined): number {
  if (valor === null || valor === undefined || valor === '') return 0;
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n : 0;
}

function esResumen(tipo: ClaseNodo): boolean {
  return tipo !== 'concepto';
}

/**
 * Renglones del Gantt jerárquico, en el orden en que llegó el árbol —recorrido
 * en profundidad, padre antes que hijos—, que es el orden en que se dibujan.
 *
 * El nodo `concepto` se casa con su actividad por el **id de actividad** que el
 * propio árbol reporta (`actividades`), no por nombre: dos conceptos pueden
 * describirse igual en dos niveles distintos y casarlos por texto los
 * confundiría.
 */
export function construirFilasJerarquia(
  arbol: ArbolDeProgramaRespuesta | null | undefined,
  filas: readonly FilaGantt[],
): readonly FilaJerarquia[] {
  if (!arbol) return [];

  const porActividad = new Map(filas.map((fila) => [fila.actividadId, fila]));
  const conHijos = new Set(
    arbol.nodos.map((nodo) => nodo.parent_id).filter((id): id is string => id !== null),
  );

  return arbol.nodos.map((nodo) => renglonDe(nodo, porActividad, conHijos));
}

function renglonDe(
  nodo: NodoDelArbolRespuesta,
  porActividad: ReadonlyMap<string, FilaGantt>,
  conHijos: ReadonlySet<string>,
): FilaJerarquia {
  const resumen = esResumen(nodo.tipo);
  // Un `concepto` es su propia hoja y el árbol lo reporta con una sola
  // actividad; se toma esa. En un resumen no hay "la" actividad y queda null.
  const fila = resumen ? null : (porActividad.get(nodo.actividades[0] ?? '') ?? null);

  return {
    nodoId: nodo.nodo_id,
    tipo: nodo.tipo,
    nombre: nodo.nombre,
    parentId: nodo.parent_id ?? null,
    profundidad: nodo.profundidad,
    esResumen: resumen,
    nActividades: nodo.actividades.length,
    // En el concepto mandan las fechas de su fila: son las que el Gantt plano
    // ya dibuja, y que las dos vistas de la misma actividad discreparan por
    // medio día sería el bug más difícil de ver.
    inicio: fila?.inicio ?? nodo.fecha_inicio ?? null,
    fin: fila?.fin ?? nodo.fecha_termino ?? null,
    duracionDias: fila?.duracionDias ?? aNumero(nodo.duracion_dias),
    duracionHojasDias: aNumero(nodo.duracion_hojas_dias),
    avancePct: fila?.avancePct ?? aNumero(nodo.avance_pct),
    importe: aNumero(nodo.importe),
    conflicto: nodo.conflicto ?? null,
    fila,
    tieneHijos: conHijos.has(nodo.nodo_id),
  };
}

/**
 * Los nodos que arrancan **colapsados**, según la profundidad de captura que
 * guardó el programa base (0041).
 *
 * Es un default, no una jaula: colapsa lo que cuelga por debajo de la
 * profundidad sugerida para que el equipo abra viendo lo mismo, y el usuario
 * expande lo que necesite. Con `concepto` no se colapsa nada —capturar renglón
 * por renglón es ver el árbol completo, que es como se veía antes de la 0041—.
 *
 * Devuelve los ids de los nodos **cuyos hijos se esconden**, no los escondidos:
 * es lo que el componente alterna al hacer clic en el triángulo de un renglón.
 */
export function colapsadosPorDefecto(
  filas: readonly FilaJerarquia[],
  profundidad: ClaseNodo,
): ReadonlySet<string> {
  if (profundidad === 'concepto') return new Set();
  return new Set(
    filas.filter((fila) => fila.tipo === profundidad && fila.tieneHijos).map((f) => f.nodoId),
  );
}

/**
 * Los renglones visibles dado el conjunto de nodos colapsados.
 *
 * Un renglón se esconde si **alguno** de sus ancestros está colapsado, no sólo
 * su padre directo: colapsar una etapa tiene que esconder también los conceptos
 * que cuelgan de sus niveles, no dejarlos sueltos sin su encabezado.
 */
export function visiblesEnJerarquia(
  filas: readonly FilaJerarquia[],
  colapsados: ReadonlySet<string>,
): readonly FilaJerarquia[] {
  if (colapsados.size === 0) return filas;

  const escondidos = new Set<string>();
  const visibles: FilaJerarquia[] = [];

  // Una sola pasada: el árbol llega padre-antes-que-hijos, así que cuando se
  // mira un nodo su padre ya se clasificó.
  for (const fila of filas) {
    const padreEscondido = fila.parentId !== null && escondidos.has(fila.parentId);
    const padreColapsado = fila.parentId !== null && colapsados.has(fila.parentId);
    if (padreEscondido || padreColapsado) {
      escondidos.add(fila.nodoId);
      continue;
    }
    visibles.push(fila);
  }

  return visibles;
}

/** Alterna el estado de colapso de un nodo, sin mutar el conjunto recibido. */
export function alternarColapso(
  colapsados: ReadonlySet<string>,
  nodoId: string,
): ReadonlySet<string> {
  const siguiente = new Set(colapsados);
  if (!siguiente.delete(nodoId)) siguiente.add(nodoId);
  return siguiente;
}

/** Filtro por texto sobre el nombre del nodo, conservando a sus ancestros.
 *
 * Se conservan los ancestros de lo que coincide porque un concepto suelto sin
 * su etapa arriba deja de decir dónde está: en un árbol, el resultado de una
 * búsqueda es la rama, no la hoja.
 */
export function filtrarJerarquiaPorTexto(
  filas: readonly FilaJerarquia[],
  texto: string,
): readonly FilaJerarquia[] {
  const aguja = texto.trim().toLowerCase();
  if (aguja === '') return filas;

  const coinciden = new Set(
    filas.filter((fila) => fila.nombre.toLowerCase().includes(aguja)).map((f) => f.nodoId),
  );
  if (coinciden.size === 0) return [];

  const porId = new Map(filas.map((fila) => [fila.nodoId, fila]));
  const conservados = new Set<string>();
  for (const nodoId of coinciden) {
    let actual: FilaJerarquia | undefined = porId.get(nodoId);
    while (actual !== undefined && !conservados.has(actual.nodoId)) {
      conservados.add(actual.nodoId);
      actual = actual.parentId === null ? undefined : porId.get(actual.parentId);
    }
  }

  return filas.filter((fila) => conservados.has(fila.nodoId));
}

export interface ResumenJerarquia {
  readonly nNodos: number;
  readonly nResumenes: number;
  readonly nConflictos: number;
  /** Avance ponderado del nodo raíz más avanzado; `null` si no hay raíces. */
  readonly avanceRaiz: number | null;
}

/**
 * Conteos para el encabezado. Son cuentas de lo ya recibido, no métricas
 * derivadas: el avance ponderado lo calculó el backend (§6) y aquí sólo se
 * escoge cuál mostrar.
 */
export function resumirJerarquia(filas: readonly FilaJerarquia[]): ResumenJerarquia {
  const raices = filas.filter((fila) => fila.parentId === null);
  return {
    nNodos: filas.length,
    nResumenes: filas.filter((fila) => fila.esResumen).length,
    nConflictos: filas.filter((fila) => fila.conflicto !== null).length,
    avanceRaiz:
      raices.length === 0
        ? null
        : raices.reduce((mayor, fila) => Math.max(mayor, fila.avancePct), 0),
  };
}
