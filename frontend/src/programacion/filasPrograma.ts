/**
 * Aplanado del árbol WBS a renglones de la tabla del programa base, con el
 * rollup de las barras resumen (§7.4, §7.5).
 *
 * ## De qué es el espejo y en qué se diferencia
 *
 * Es el equivalente de `jerarquia.ts` para el **borrador**. Allá el rollup
 * —inicio, fin, span, avance ponderado— lo calcula el backend
 * (`domain/programacion/jerarquia.resumir_arbol`) y el cliente sólo aplana lo
 * recibido. Aquí no hay backend que preguntar: el programa base todavía no se
 * ha guardado, sus renglones viven en memoria (`borrador.ts`) y su colocación
 * es la pasada en días relativos de `planificacion.ts`. Así que el rollup se
 * arma aquí, sobre lo que el usuario acaba de mover.
 *
 * Lo que **no** se re-deriva es la colocación: `colocar` ya resolvió las cuatro
 * ligas y esta capa sólo agrega hacia arriba lo que aquélla dejó puesto.
 *
 * ## La regla que sostiene la vista: el resumen es derivado
 *
 * Un nodo con descendientes capturados dibuja una barra que **abarca a sus
 * hijos** y no es un renglón propio: `min(inicio)` … `max(fin)` de lo que
 * cuelga de él. No se captura sobre ella, no se arrastra y no viaja al POST
 * como cosa aparte. Es la misma regla del Gantt jerárquico de obra (§11.3 A.2)
 * y la que impide que la cantidad y el costo se cuenten dos veces (§6, §7.6).
 *
 * ## El caso que sí es un renglón con hijos: la plantilla gruesa
 *
 * `prototipo_nodo_id` puede apuntar a un nivel o a una etapa —"toda la etapa
 * constructiva es una actividad"— y ese nodo **sí** tiene duración propia
 * aunque tenga hijos en el árbol. Mientras sus hijos no estén capturados no hay
 * nada que resumir y su barra es una actividad normal.
 *
 * Que un nodo tenga las dos cosas a la vez ya no ocurre. Antes se marcaba
 * `conflicto` —el nodo declara N días y sus conceptos ocupan M— y se dejaba
 * al jefe de obra decidir. Ahora la captura hereda: `gestos.fijarDuracion`
 * reparte la ventana del padre hacia abajo vaciando la suya, y vacía a los
 * ancestros al capturar una hoja. El estado ambiguo no se puede construir, así
 * que no hay nada que señalar. La vista de **obra** conserva su propio aviso
 * (`ConflictoJerarquiaRespuesta`, `jerarquia.ts`), que viene del backend y se
 * gobierna aparte.
 *
 * ## Días laborables vs días calendario
 *
 * Son las dos cifras que `tramos.ts` ya distingue y aquí no se reinventan:
 * `trabajoDe` es la suma de los tramos (los días que de verdad se trabaja) y
 * `spanDe` el cierre del último (lo que la barra ocupa en el calendario). Sin
 * interrupción las dos coinciden; con interrupción, la diferencia son las
 * pausas. En el resumen las dos son la **ventana** que abarca a sus hojas: con
 * el reparto en paralelo de `gestos.fijarDuracion` las ramas de un nivel corren
 * simultáneas, así que sumar su trabajo daría un total que nadie ocupa.
 *
 * Módulo puro (§12.11).
 */

import type { PartidaRespuesta } from '@/api/generado/modelo';

import type { Borrador, Caja, TipoCaja } from './grafo';
import { aristas, esRenglon } from './grafo';
import { ordenTopologico } from './ciclos';
import type { Colocacion } from './planificacion';
import { spanDe, trabajoDe, type Tramo } from './tramos';

export interface FilaPrograma {
  /** `prototipo_nodo_id`: la identidad, la misma que en el borrador y el POST. */
  readonly nodoId: string;
  readonly parentId: string | null;
  /** Nivel de anidación en el árbol completo; la raíz es 0. */
  readonly profundidad: number;
  /** Número de renglón, 1-based, en el preorden del árbol completo. */
  readonly numero: number;
  readonly tipo: TipoCaja;
  readonly clave: string | null;
  readonly descripcion: string;
  /** Clave de unidad del presupuesto vigente; `null` si no hay partida. */
  readonly unidad: string | null;
  readonly cantidad: number | null;
  readonly tieneHijos: boolean;
  /** Conceptos capturados que cuelgan del nodo, a cualquier distancia. */
  readonly nHojas: number;
  /** La barra es derivada de sus hijos: no se captura ni se arrastra. */
  readonly esResumen: boolean;
  /** El nodo tiene duración propia capturada (entra al POST). */
  readonly capturado: boolean;
  /** Día del programa en que arranca la barra, 0-based; `null` sin colocar. */
  readonly inicioDias: number | null;
  /**
   * Arranque **fijado a mano** (`inicio_dias`, migración 0043), 0-based.
   * `null` = la barra la coloca su cadena de precedencias. Es distinto de
   * `inicioDias`, que es dónde acabó quedando: con ancla los dos coinciden,
   * sin ancla sólo el segundo tiene valor.
   */
  readonly anclaDias: number | null;
  readonly finDias: number | null;
  /**
   * Días de trabajo efectivo (suma de tramos). En un resumen es el **span**
   * de sus hijos, no la suma de su trabajo: con el reparto en paralelo de
   * `gestos.fijarDuracion` las ramas corren simultáneas, así que un nivel de
   * 60 días con cinco etapas debajo ocupa 60 y no 300.
   */
  readonly diasLaborables: number | null;
  /** Días que la barra ocupa en el calendario del programa (span). */
  readonly diasCalendario: number | null;
  /** Días que la barra puede correrse sin empujar el cierre del programa. */
  readonly holguraDias: number | null;
  /** Tramos de trabajo de una actividad partida; vacío en resumen y continua. */
  readonly tramos: readonly Tramo[];
  readonly nPredecesoras: number;
  /** El nodo participa de un ciclo de precedencias: no se puede guardar. */
  readonly enCiclo: boolean;
}

interface Resumen {
  readonly inicioDias: number;
  readonly finDias: number;
  readonly trabajoDias: number;
  readonly nHojas: number;
}

/**
 * Hijos de cada nodo en el orden en que llegaron, y las raíces.
 *
 * Un `parentId` que no está entre las cajas convierte al nodo en raíz en vez de
 * perderlo — mismo criterio que `arbolVisible` en `grafo.ts`.
 *
 * Se exporta porque la herencia de duraciones (`gestos.ts`) recorre el mismo
 * árbol para repartir hacia abajo y vaciar hacia arriba: dos índices distintos
 * del mismo `parentId` acabarían discrepando en el caso raro, que es
 * justamente el padre desconocido.
 */
export function indexarArbol(cajas: readonly Caja[]): {
  readonly hijos: ReadonlyMap<string | null, readonly Caja[]>;
  readonly raices: readonly Caja[];
} {
  const conocidos = new Set(cajas.map((caja) => caja.id));
  const hijos = new Map<string | null, Caja[]>();
  for (const caja of cajas) {
    const padre =
      caja.parentId !== null && conocidos.has(caja.parentId) ? caja.parentId : null;
    const lista = hijos.get(padre);
    if (lista) lista.push(caja);
    else hijos.set(padre, [caja]);
  }
  return { hijos, raices: hijos.get(null) ?? [] };
}

/**
 * La colocación de las cajas **capturadas**, y sólo de ésas.
 *
 * `colocar` recorre el grafo completo y le pone día de arranque a todo, tenga
 * duración o no: una caja sin capturar sale con la ventana degenerada
 * `0 → 0`. Para el canvas eso da igual —dibuja cajas, no barras—, pero aquí
 * significaría que **todos** los nodos del árbol están capturados y que todo
 * padre es resumen de una ventana de cero días en el día 1. Es el mismo
 * criterio que aplica `itemsDelBorrador` al armar el POST: renglón es el que
 * tiene duración positiva, el resto es propuesta.
 */
function puestosCapturados(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
): ReadonlyMap<string, Colocacion> {
  const puestos = new Map<string, Colocacion>();
  for (const caja of borrador.cajas) {
    if (!esRenglon(caja)) continue;
    const puesto = colocado.get(caja.id);
    if (puesto) puestos.set(caja.id, puesto);
  }
  return puestos;
}

/**
 * Rollup de cada nodo a partir de sus descendientes **capturados**.
 *
 * Sólo entran las cajas que `colocar` alcanzó a poner, que son las que tienen
 * duración: una propuesta sin capturar no tiene ventana que aportar y meterla
 * como cero arrancaría todos los resúmenes en el día 0.
 *
 * Devuelve entrada sólo para los nodos que tienen algo debajo; un nodo cuyo
 * subárbol está vacío no es resumen de nada.
 */
export function resumirDescendientes(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
): ReadonlyMap<string, Resumen> {
  const { hijos } = indexarArbol(borrador.cajas);
  const porId = new Map(borrador.cajas.map((caja) => [caja.id, caja]));
  const puestos = puestosCapturados(borrador, colocado);
  const resumenes = new Map<string, Resumen>();

  // Recorrido en profundidad de abajo hacia arriba. `visitados` no es una
  // optimización: es la red contra un `parent_id` en ciclo, que sin ella
  // colgaría la pantalla en vez de fallar (mismo criterio que `arbolVisible`).
  const visitados = new Set<string>();

  function subir(id: string): Resumen | null {
    if (visitados.has(id)) return resumenes.get(id) ?? null;
    visitados.add(id);

    const propios: Resumen[] = [];
    for (const hijo of hijos.get(id) ?? []) {
      const suyo = subir(hijo.id);
      const caja = porId.get(hijo.id);
      const puesto = puestos.get(hijo.id);

      // El hijo aporta lo suyo capturado y, aparte, lo que resuma de los suyos.
      if (caja && puesto) {
        propios.push({
          inicioDias: puesto.inicioDias,
          finDias: puesto.finDias,
          trabajoDias: trabajoDe(caja.duracionDias ?? 0, caja.tramos),
          nHojas: 1,
        });
      }
      if (suyo) propios.push(suyo);
    }

    if (propios.length === 0) return null;

    const resumen: Resumen = {
      inicioDias: propios.reduce((a, r) => Math.min(a, r.inicioDias), Infinity),
      finDias: propios.reduce((a, r) => Math.max(a, r.finDias), -Infinity),
      trabajoDias: propios.reduce((a, r) => a + r.trabajoDias, 0),
      nHojas: propios.reduce((a, r) => a + r.nHojas, 0),
    };
    resumenes.set(id, resumen);
    return resumen;
  }

  for (const caja of borrador.cajas) subir(caja.id);
  return resumenes;
}

/**
 * Holgura total de cada caja colocada, en días relativos del borrador.
 *
 * Es la pasada hacia **atrás** que le falta a `colocar`: cuánto puede correrse
 * una actividad sin empujar el cierre del programa. No es la holgura del motor
 * —ésa la calcula `domain/programacion/cpm.py` contra el calendario laboral de
 * la obra y llega resuelta en `GET /obras/{id}/ruta-critica`—; es la del
 * borrador contra su propio eje relativo, que es lo único que existe antes de
 * guardar. Las dos coinciden en semana natural y difieren en cuanto hay días
 * inhábiles de por medio, y por eso la columna se rotula como del borrador.
 *
 * Se resuelve sobre las mismas ligas que la pasada hacia adelante y con el
 * mismo criterio (`FS`, `SS`, `FF`, `SF` sobre el span). Con un ciclo no hay
 * orden que recorrer y devuelve vacío, igual que `colocar`.
 */
export function holguraDelBorrador(
  borrador: Borrador,
  colocado: ReadonlyMap<string, Colocacion>,
): ReadonlyMap<string, number> {
  const puestos = puestosCapturados(borrador, colocado);
  if (puestos.size === 0) return new Map();

  const orden = ordenTopologico(
    borrador.cajas.map((caja) => caja.id),
    aristas(borrador),
  );
  if (orden === null) return new Map();

  const porId = new Map(borrador.cajas.map((caja) => [caja.id, caja]));
  const cierre = [...puestos.values()].reduce((a, c) => Math.max(a, c.finDias), 0);

  // Inicio más tardío admisible de cada caja. Se arranca en el cierre del
  // programa y se baja recorriendo en orden inverso: cuando se mira una caja,
  // todas sus sucesoras ya fijaron su tope.
  const tardio = new Map<string, number>();
  for (const id of [...orden].reverse()) {
    const puesto = puestos.get(id);
    if (!puesto) continue;
    const span = puesto.finDias - puesto.inicioDias;
    tardio.set(id, Math.max(0, cierre - span));
  }

  for (const id of [...orden].reverse()) {
    const caja = porId.get(id);
    const puesto = puestos.get(id);
    if (!caja || !puesto) continue;

    // Las entradas de una caja son sus predecesoras: al mirar la sucesora se
    // aprieta el tope de cada una de ellas.
    for (const cable of caja.entradas) {
      const previa = puestos.get(cable.desde);
      const topeSucesora = tardio.get(id);
      if (!previa || topeSucesora === undefined) continue;

      const spanPrevia = previa.finDias - previa.inicioDias;
      const spanSucesora = puesto.finDias - puesto.inicioDias;
      const lag = cable.lagDias;

      // El espejo de `colocar`: se despeja el inicio de la predecesora del
      // mismo sistema de desigualdades, cambiando de lado la que manda.
      const tope =
        cable.tipo === 'FS'
          ? topeSucesora - lag - spanPrevia
          : cable.tipo === 'SS'
            ? topeSucesora - lag
            : cable.tipo === 'FF'
              ? topeSucesora + spanSucesora - lag - spanPrevia
              : topeSucesora + spanSucesora - lag;

      const actual = tardio.get(cable.desde);
      if (actual !== undefined) tardio.set(cable.desde, Math.min(actual, tope));
    }
  }

  const holguras = new Map<string, number>();
  for (const [id, puesto] of puestos) {
    const tope = tardio.get(id);
    if (tope === undefined) continue;
    holguras.set(id, redondear(Math.max(0, tope - puesto.inicioDias)));
  }
  return holguras;
}

export interface EntradaFilas {
  readonly borrador: Borrador;
  readonly colocado: ReadonlyMap<string, Colocacion>;
  /** Partidas del presupuesto vigente, por `prototipo_nodo_id` (unidad/cantidad). */
  readonly partidas?: ReadonlyMap<string, PartidaRespuesta>;
  /** Ids de las cajas que participan de un ciclo (`buscarCiclo`). */
  readonly enCiclo?: ReadonlySet<string>;
}

/**
 * Los renglones de la tabla, en preorden del árbol completo —padre antes que
 * hijos—, que es el orden en que se dibujan y en que se numeran.
 *
 * La numeración es del árbol **completo**, no de lo que se ve: colapsar una
 * etapa no puede renumerar los conceptos de la siguiente, o el número de
 * renglón dejaría de servir para referirse a una actividad en voz alta.
 */
export function aplanarPrograma({
  borrador,
  colocado,
  partidas,
  enCiclo,
}: EntradaFilas): readonly FilaPrograma[] {
  const { hijos, raices } = indexarArbol(borrador.cajas);
  const puestos = puestosCapturados(borrador, colocado);
  const resumenes = resumirDescendientes(borrador, colocado);
  const holguras = holguraDelBorrador(borrador, colocado);

  const filas: FilaPrograma[] = [];
  const visitados = new Set<string>();

  function bajar(caja: Caja, profundidad: number): void {
    if (visitados.has(caja.id)) return;
    visitados.add(caja.id);

    const debajo = hijos.get(caja.id) ?? [];
    const resumen = resumenes.get(caja.id) ?? null;
    const propio = puestos.get(caja.id) ?? null;
    const partida = partidas?.get(caja.id);

    // Manda el resumen cuando lo hay: la barra que abarca a los hijos es la
    // lectura correcta del nodo. Que además tenga duración propia ya no se
    // puede: `gestos.fijarDuracion` vacía al padre al repartirle a los hijos y
    // vacía a los ancestros al capturar una hoja, justamente para que nadie
    // tenga que decidir cuál de las dos cifras manda.
    const inicioDias = resumen?.inicioDias ?? propio?.inicioDias ?? null;
    const finDias = resumen?.finDias ?? propio?.finDias ?? null;

    filas.push({
      nodoId: caja.id,
      parentId: caja.parentId,
      profundidad,
      numero: filas.length + 1,
      tipo: caja.tipo,
      clave: caja.clave,
      descripcion: caja.nombre,
      unidad: partida?.unidad_clave ?? null,
      cantidad: aNumero(partida?.cantidad),
      tieneHijos: debajo.length > 0,
      nHojas: resumen?.nHojas ?? (propio ? 1 : 0),
      esResumen: resumen !== null,
      capturado: propio !== null,
      inicioDias,
      // El ancla es de la caja y no del resumen: un nodo derivado no se clava,
      // se clavan las hojas que lo componen.
      anclaDias: resumen === null ? caja.inicioDias : null,
      finDias,
      diasLaborables:
        resumen !== null
          ? resumen.finDias - resumen.inicioDias
          : propio
            ? trabajoDe(caja.duracionDias ?? 0, caja.tramos)
            : null,
      diasCalendario:
        resumen !== null
          ? resumen.finDias - resumen.inicioDias
          : propio
            ? spanDe(caja.duracionDias ?? 0, caja.tramos)
            : null,
      // La holgura de un resumen no es la suya: es la de la actividad que lo
      // cierra, y anunciarla en el nodo sugeriría que el bloque entero se puede
      // correr. Sólo se muestra donde se puede accionar.
      holguraDias: resumen === null ? (holguras.get(caja.id) ?? null) : null,
      tramos: resumen === null ? caja.tramos : [],
      nPredecesoras: caja.entradas.length,
      enCiclo: enCiclo?.has(caja.id) ?? false,
    });

    for (const hijo of debajo) bajar(hijo, profundidad + 1);
  }

  for (const raiz of raices) bajar(raiz, 0);
  return filas;
}

/**
 * Nodos colapsados de entrada, a partir de la profundidad de captura del
 * programa (migración 0041): se pliega lo que cuelga por debajo de la clase
 * sugerida, para que el equipo abra viendo lo mismo.
 *
 * Es el gemelo de `colapsadosPorDefecto` de `jerarquia.ts` sobre este renglón;
 * la diferencia es que allá el árbol llega del backend con su `tipo` resuelto y
 * aquí es el `tipo` de la caja del borrador.
 */
export function colapsadosDeEntrada(
  filas: readonly FilaPrograma[],
  profundidad: TipoCaja,
): ReadonlySet<string> {
  if (profundidad === 'concepto') return new Set();
  return new Set(
    filas.filter((fila) => fila.tipo === profundidad && fila.tieneHijos).map((f) => f.nodoId),
  );
}

/** Todos los nodos con hijos, para el botón de plegar todo. */
export function todosLosPadres(filas: readonly FilaPrograma[]): ReadonlySet<string> {
  return new Set(filas.filter((fila) => fila.tieneHijos).map((fila) => fila.nodoId));
}

/**
 * Colapsa el árbol a una **profundidad**: se ve todo hasta el escalón `nivel`
 * y se pliega lo que cuelga por debajo.
 *
 * Es "Expandir / Colapsar a nivel" del menú, y se expresa en profundidad y no
 * en clase de nodo —a diferencia de `colapsadosDeEntrada`, que sigue la
 * profundidad de captura guardada con la versión— porque el gesto de la barra
 * es de lectura: "enséñame dos escalones" vale igual en un prototipo cuyo
 * segundo escalón son etapas que en uno donde son otra cosa.
 *
 * `nivel = 0` deja sólo las raíces; un nivel mayor que la profundidad del árbol
 * no pliega nada, que es exactamente "expandir todo".
 */
export function colapsarANivel(
  filas: readonly FilaPrograma[],
  nivel: number,
): ReadonlySet<string> {
  return new Set(
    filas
      .filter((fila) => fila.tieneHijos && fila.profundidad >= nivel)
      .map((fila) => fila.nodoId),
  );
}

/** Profundidad máxima del árbol; cuántos escalones ofrece el menú. */
export function profundidadMaxima(filas: readonly FilaPrograma[]): number {
  return filas.reduce((mayor, fila) => Math.max(mayor, fila.profundidad), 0);
}

/**
 * Filtro por texto sobre clave y descripción, conservando a los ancestros de lo
 * que coincide: en un árbol el resultado de una búsqueda es la rama, no la hoja
 * (mismo criterio que `filtrarJerarquiaPorTexto`).
 */
export function filtrarPorTexto(
  filas: readonly FilaPrograma[],
  texto: string,
): readonly FilaPrograma[] {
  const aguja = texto.trim().toLowerCase();
  if (aguja === '') return filas;

  const porId = new Map(filas.map((fila) => [fila.nodoId, fila]));
  const conservados = new Set<string>();

  for (const fila of filas) {
    const heno = `${fila.clave ?? ''} ${fila.descripcion}`.toLowerCase();
    if (!heno.includes(aguja)) continue;
    let actual: FilaPrograma | undefined = fila;
    while (actual !== undefined && !conservados.has(actual.nodoId)) {
      conservados.add(actual.nodoId);
      actual = actual.parentId === null ? undefined : porId.get(actual.parentId);
    }
  }

  return filas.filter((fila) => conservados.has(fila.nodoId));
}

export interface ResumenPrograma {
  readonly nNodos: number;
  readonly nCapturados: number;
  readonly nResumenes: number;
  /** Días que ocupa el programa completo. */
  readonly diasTotales: number;
}

/** Conteos del encabezado. Cuentas de lo que ya hay, no métricas nuevas. */
export function resumirFilas(filas: readonly FilaPrograma[]): ResumenPrograma {
  return {
    nNodos: filas.length,
    nCapturados: filas.filter((fila) => fila.capturado).length,
    nResumenes: filas.filter((fila) => fila.esResumen).length,
    diasTotales: filas.reduce((mayor, fila) => Math.max(mayor, fila.finDias ?? 0), 0),
  };
}

/** Decimal del contrato (cadena) → número; `null` si no viene o no es finito. */
function aNumero(valor: string | number | null | undefined): number | null {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n : null;
}

/** Dos decimales, los que la columna `numeric(8,2)` guarda de verdad. */
function redondear(valor: number): number {
  return Math.round(valor * 100) / 100;
}
