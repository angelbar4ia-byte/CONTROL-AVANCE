/**
 * Modelo de grafo del editor de programas base (§7.4, §7.5).
 *
 * ## Nodos = nodos del WBS, cables = dependencias
 *
 * No hay un modelo de grafo aparte del contrato. Un renglón de programa base
 * (`ProgramaBaseItem`) **es** un nodo del árbol del prototipo con duración:
 * `item.prototipo_nodo_id` lo identifica, y `dependencias[].ref` de un
 * programa base es —textual del contrato— *"el `prototipo_nodo_id` de la
 * predecesora"*. Por eso la caja del canvas se identifica con el
 * `prototipo_nodo_id` y el cable con `(desde → hasta)` sobre esos mismos ids:
 * cualquier identificador propio del editor obligaría a mantener una tabla de
 * traducción que tarde o temprano discreparía del `POST`.
 *
 * Consecuencia práctica: un nodo del árbol que todavía no tiene duración
 * **igual existe** en el borrador, dibujado en gris, con `duracionDias: null`.
 * Es lo que resuelve el estado vacío (un prototipo sin programa base arranca
 * desde su propio árbol, no desde un canvas en blanco) sin inventar un
 * segundo tipo de entidad: el renglón propuesto y el renglón capturado son la
 * misma caja en dos estados. `duracion_dias` es obligatorio y `> 0` en
 * `ItemProgramaBasePeticion`, así que los `null` no viajan en el POST — y las
 * dependencias que apuntaban a ellos tampoco, lo que este módulo reporta en
 * vez de recortar en silencio.
 *
 * ## Dos granularidades, un solo modelo
 *
 * `prototipo_nodo_id` puede apuntar a una **etapa** (plantilla gruesa: toda la
 * etapa constructiva es una actividad) o a un **concepto**. Las dos son nodos
 * del mismo árbol, así que las dos son cajas del mismo tipo y el canvas solo
 * cambia cuáles muestra. Un concepto puede depender de un concepto de otra
 * etapa: el grafo no conoce esa frontera, solo el árbol la conoce, y el árbol
 * no manda sobre las precedencias.
 *
 * Las posiciones no viajan al backend —`ProgramaBaseItem` no tiene dónde
 * guardarlas—, así que al abrir un programa existente se recalculan con
 * `acomodarEnCapas`. Es una pérdida real y conocida: mover una caja no
 * sobrevive al cierre de la pantalla mientras el contrato no tenga campo.
 *
 * Módulo puro (§12.11): sin React, sin fetch. Todo lo que decide el editor se
 * puede fijar con pruebas sin renderizar nada.
 */

import type {
  DependenciaDTO,
  ItemProgramaBasePeticion,
  ItemProgramaBaseRespuesta,
  NodoPrototipoRespuesta,
} from '@/api/generado/modelo';

import { normalizarTramos, spanDe, type Tramo } from './tramos';

/** Los cuatro de MS Project, tal como los acepta `DependenciaDTO.tipo` (§7.5). */
export type TipoLiga = 'FS' | 'SS' | 'FF' | 'SF';

export const TIPOS_LIGA: readonly TipoLiga[] = ['FS', 'SS', 'FF', 'SF'];

export function esTipoLiga(valor: string): valor is TipoLiga {
  return (TIPOS_LIGA as readonly string[]).includes(valor.toUpperCase());
}

/** Qué nodos del árbol pueden ser renglón: etapa (gruesa) o concepto. */
export type TipoCaja = 'etapa' | 'concepto';

/**
 * Un cable del canvas visto desde su **sucesora**: es exactamente un
 * `DependenciaDTO`, con `desde` en lugar de `ref` porque en el canvas el
 * sentido de lectura es el del flujo (predecesora → sucesora) y `ref` no dice
 * de qué lado está.
 */
export interface Cable {
  readonly desde: string;
  readonly tipo: TipoLiga;
  readonly lagDias: number;
}

export interface Caja {
  /** `prototipo_nodo_id`: la identidad, la misma en el árbol y en el POST. */
  readonly id: string;
  readonly tipo: TipoCaja;
  readonly clave: string | null;
  readonly nombre: string;
  /** Etapa constructiva del catálogo (`nodo.etapa_id`), no el nodo etapa. */
  readonly etapaId: string | null;
  /** Nodo etapa del árbol al que pertenece el concepto; `null` en las etapas. */
  readonly etapaNodoId: string | null;
  /**
   * `null` = renglón propuesto, todavía sin capturar. No viaja en el POST.
   * Con tramos es la **suma** de los tramos, no el span (§7.6).
   */
  readonly duracionDias: number | null;
  readonly frenteId: string | null;
  readonly tramos: readonly Tramo[];
  readonly entradas: readonly Cable[];
  readonly orden: number;
  readonly x: number;
  readonly y: number;
}

export interface Borrador {
  readonly prototipoId: string;
  readonly nombre: string;
  readonly cajas: readonly Caja[];
}

/** Días que la caja ocupa en calendario: la duración, o el cierre del último tramo. */
export function spanDeCaja(caja: Caja): number {
  return spanDe(caja.duracionDias ?? 0, caja.tramos);
}

/** ¿Esta caja llega al POST? Solo las que tienen duración capturada y positiva. */
export function esRenglon(caja: Caja): boolean {
  return caja.duracionDias !== null && caja.duracionDias > 0;
}

function tipoDeCaja(nodo: NodoPrototipoRespuesta): TipoCaja | null {
  if (nodo.tipo === 'etapa') return 'etapa';
  if (nodo.tipo === 'concepto') return 'concepto';
  return null;
}

/**
 * El nodo etapa del que cuelga un nodo, subiendo por `parent_id`.
 *
 * Se sube en vez de leer `nodo.etapa_id` porque ese campo apunta al catálogo
 * de etapas constructivas, no al nodo del árbol: dos etapas del mismo tipo en
 * niveles distintos comparten `etapa_id` y son cajas diferentes. Lo que
 * agrupa el canvas es el nodo, no el catálogo.
 */
function etapaNodoDe(
  nodo: NodoPrototipoRespuesta,
  porId: ReadonlyMap<string, NodoPrototipoRespuesta>,
): string | null {
  let actual: NodoPrototipoRespuesta | undefined = nodo;
  // El árbol tiene tres niveles (§7.4); el tope es por si un dato inconsistente
  // encadenara padres en ciclo, que colgaría la pantalla en vez de fallar.
  for (let saltos = 0; actual && saltos < 32; saltos += 1) {
    if (actual.tipo === 'etapa') return actual.id;
    const padre: string | null = actual.parent_id ?? null;
    actual = padre ? porId.get(padre) : undefined;
  }
  return null;
}

function cableDeDependencia(dependencia: DependenciaDTO): Cable {
  const tipo = (dependencia.tipo ?? 'FS').toUpperCase();
  return {
    desde: dependencia.ref,
    tipo: esTipoLiga(tipo) ? (tipo as TipoLiga) : 'FS',
    lagDias: Number(dependencia.lag_dias ?? 0),
  };
}

export interface EntradaBorrador {
  readonly prototipoId: string;
  readonly nombre: string;
  readonly nodos: readonly NodoPrototipoRespuesta[];
  /** Renglones del programa base que se está editando; vacío = arrancar de cero. */
  readonly items?: readonly ItemProgramaBaseRespuesta[];
}

export interface BorradorArmado {
  readonly borrador: Borrador;
  /**
   * Renglones cuyo `prototipo_nodo_id` no está en el árbol (o viene vacío):
   * no tienen caja que dibujar. Se reportan para que la pantalla avise en vez
   * de perderlos, que es lo mismo que ya hace la lista de `ProgramasBase`.
   */
  readonly huerfanos: readonly ItemProgramaBaseRespuesta[];
}

/**
 * Arma el borrador a partir del árbol del prototipo y —si lo hay— los
 * renglones de un programa base existente.
 *
 * Toda etapa y todo concepto del árbol entra como caja, tenga renglón o no:
 * las que no lo tienen quedan con `duracionDias: null` y son la propuesta que
 * el usuario llena. Las posiciones quedan en `(0, 0)`; las fija después
 * `acomodarEnCapas`, que necesita el grafo ya completo.
 */
export function armarBorrador({
  prototipoId,
  nombre,
  nodos,
  items = [],
}: EntradaBorrador): BorradorArmado {
  const porId = new Map(nodos.map((nodo) => [nodo.id, nodo]));

  const itemPorNodo = new Map<string, ItemProgramaBaseRespuesta>();
  for (const item of items) {
    if (item.prototipo_nodo_id) itemPorNodo.set(item.prototipo_nodo_id, item);
  }

  const cajas: Caja[] = [];
  for (const [indice, nodo] of nodos.entries()) {
    const tipo = tipoDeCaja(nodo);
    if (tipo === null) continue;

    const item = itemPorNodo.get(nodo.id);
    const tramos = normalizarTramos(
      (item?.tramos ?? []).map((tramo) => ({
        duracionDias: Number(tramo.duracion_dias),
        offsetDias: Number(tramo.offset_dias ?? 0),
      })),
    );

    cajas.push({
      id: nodo.id,
      tipo,
      clave: nodo.clave ?? null,
      nombre: nodo.nombre,
      etapaId: nodo.etapa_id ?? null,
      etapaNodoId: tipo === 'etapa' ? null : etapaNodoDe(nodo, porId),
      duracionDias: item ? Number(item.duracion_dias) : null,
      frenteId: item?.frente_id ?? null,
      tramos,
      entradas: (item?.dependencias ?? []).map(cableDeDependencia),
      // `orden` del renglón si ya existe; si no, la posición en el árbol, que
      // el backend ya devolvió en recorrido padre-antes-que-hijos.
      orden: item?.orden ?? indice,
      x: 0,
      y: 0,
    });
  }

  const idsDelArbol = new Set(cajas.map((caja) => caja.id));
  const huerfanos = items.filter(
    (item) => !item.prototipo_nodo_id || !idsDelArbol.has(item.prototipo_nodo_id),
  );

  return { borrador: { prototipoId, nombre, cajas }, huerfanos };
}

/** Índice por id, que es lo que casi todo el editor necesita. */
export function porId(borrador: Borrador): ReadonlyMap<string, Caja> {
  return new Map(borrador.cajas.map((caja) => [caja.id, caja]));
}

export interface Arista {
  readonly desde: string;
  readonly hasta: string;
}

/** Todas las precedencias del borrador, aplanadas a `(predecesora → sucesora)`. */
export function aristas(borrador: Borrador): readonly Arista[] {
  return borrador.cajas.flatMap((caja) =>
    caja.entradas.map((cable) => ({ desde: cable.desde, hasta: caja.id })),
  );
}

/**
 * Qué muestra el canvas.
 *
 * Arranca en `etapas` —diez o quince cajas se leen; trescientos conceptos
 * no—. `conceptos-de` es el doble clic en una etapa; `conceptos` es el
 * interruptor de la barra, que las abre todas de golpe.
 */
export type Vista =
  | { readonly modo: 'etapas' }
  | { readonly modo: 'conceptos' }
  | { readonly modo: 'conceptos-de'; readonly etapaNodoId: string };

/**
 * Ids visibles en esta vista.
 *
 * En `conceptos-de` se incluyen además los conceptos de **otras** etapas que
 * estén cableados con los de esta: el usuario pidió explícitamente poder ligar
 * conceptos entre etapas, y un cable cuyo otro extremo no se ve no se puede ni
 * revisar ni quitar. Se marcan aparte con `esForaneo` para que el canvas los
 * dibuje como contexto y no como parte de la etapa abierta.
 */
export function idsVisibles(borrador: Borrador, vista: Vista): ReadonlySet<string> {
  if (vista.modo === 'etapas') {
    return new Set(borrador.cajas.filter((caja) => caja.tipo === 'etapa').map((c) => c.id));
  }
  if (vista.modo === 'conceptos') {
    return new Set(borrador.cajas.filter((caja) => caja.tipo === 'concepto').map((c) => c.id));
  }

  const propios = new Set(
    borrador.cajas
      .filter((caja) => caja.tipo === 'concepto' && caja.etapaNodoId === vista.etapaNodoId)
      .map((caja) => caja.id),
  );

  const visibles = new Set(propios);
  const conceptos = new Set(
    borrador.cajas.filter((caja) => caja.tipo === 'concepto').map((caja) => caja.id),
  );
  for (const { desde, hasta } of aristas(borrador)) {
    if (propios.has(hasta) && conceptos.has(desde)) visibles.add(desde);
    if (propios.has(desde) && conceptos.has(hasta)) visibles.add(hasta);
  }
  return visibles;
}

/** ¿Esta caja se ve solo porque está cableada con la etapa abierta? */
export function esForaneo(caja: Caja, vista: Vista): boolean {
  return vista.modo === 'conceptos-de' && caja.etapaNodoId !== vista.etapaNodoId;
}

export interface OpcionNodo {
  /** El valor que viaja en el DTO: `prototipo_nodo_id`, o la `ref`. */
  readonly valor: string;
  readonly etiqueta: string;
  readonly tipo: TipoCaja;
}

/** Dos espacios duros por nivel: en un `<option>` el espacio normal colapsa. */
const SANGRIA = '\u00a0\u00a0';

/**
 * Los nodos programables como opciones de un `select`, en orden de árbol y
 * con la sangría de su profundidad.
 *
 * Es lo que sustituye el tecleo de UUIDs en el alta: `prototipo_nodo_id` y las
 * `ref` de las dependencias son identificadores que nadie tiene memorizados, y
 * hasta ahora se capturaban a mano porque el contrato no exponía el árbol
 * (`GET /prototipos/{id}/nodos` ya existe). El orden es el que el backend ya
 * devolvió: padre antes que hijos.
 *
 * La sangría va con espacios duros y no con anidación porque un `<option>` no
 * admite marcado; con espacios normales el navegador los colapsaría y los tres
 * niveles del árbol quedarían todos al ras.
 */

export function opcionesDeNodos(
  nodos: readonly NodoPrototipoRespuesta[],
): readonly OpcionNodo[] {
  const indice = new Map(nodos.map((nodo) => [nodo.id, nodo]));

  function profundidad(nodo: NodoPrototipoRespuesta): number {
    let saltos = 0;
    let padre = nodo.parent_id ? indice.get(nodo.parent_id) : undefined;
    while (padre && saltos < 32) {
      saltos += 1;
      padre = padre.parent_id ? indice.get(padre.parent_id) : undefined;
    }
    return saltos;
  }

  const opciones: OpcionNodo[] = [];
  for (const nodo of nodos) {
    const tipo = tipoDeCaja(nodo);
    if (tipo === null) continue;
    const sangria = SANGRIA.repeat(profundidad(nodo));
    const clave = nodo.clave ? `${nodo.clave} · ` : '';
    opciones.push({ valor: nodo.id, etiqueta: `${sangria}${clave}${nodo.nombre}`, tipo });
  }
  return opciones;
}

/**
 * Etapas constructivas del catálogo presentes en el árbol, para el campo
 * `etapa_id` del renglón (la "plantilla gruesa"). Es un campo distinto de
 * `prototipo_nodo_id`: apunta al catálogo, no al nodo, así que dos etapas del
 * mismo tipo en niveles distintos comparten opción y se listan una sola vez.
 */
export function opcionesDeEtapas(
  nodos: readonly NodoPrototipoRespuesta[],
): readonly OpcionNodo[] {
  const vistas = new Map<string, string>();
  for (const nodo of nodos) {
    const etapaId = nodo.etapa_id ?? null;
    if (nodo.tipo !== 'etapa' || etapaId === null || vistas.has(etapaId)) continue;
    vistas.set(etapaId, nodo.clave ? `${nodo.clave} · ${nodo.nombre}` : nodo.nombre);
  }
  return [...vistas].map(([valor, etiqueta]) => ({ valor, etiqueta, tipo: 'etapa' as const }));
}

export interface AvisoDeGuardado {
  readonly clase: 'sin-duracion' | 'ref-fuera';
  readonly mensaje: string;
}

export interface Guardado {
  readonly items: readonly ItemProgramaBasePeticion[];
  readonly avisos: readonly AvisoDeGuardado[];
}

/**
 * El cuerpo del `POST /programas-base` a partir del borrador.
 *
 * Dos recortes, los dos avisados:
 *
 *  1. Las cajas sin duración no son renglones (`duracion_dias` es obligatorio
 *     y `> 0`); mandarlas sería un 422 por todo el programa, porque el
 *     endpoint valida y escribe todo o nada.
 *  2. Una dependencia que apunta a una caja recortada se cae con ella: su
 *     `ref` no sería resoluble. El motor las ignoraría al instanciar
 *     (`refs_no_resueltas`), pero enterarse aquí es mucho más barato.
 *
 * `duracion_dias` se manda siempre —también con tramos— porque el contrato del
 * programa base la exige; se toma la suma de los tramos, que es la invariante
 * que el backend comprueba (§7.6).
 */
export function itemsDelBorrador(borrador: Borrador): Guardado {
  const renglones = borrador.cajas.filter(esRenglon);
  const incluidos = new Set(renglones.map((caja) => caja.id));

  const avisos: AvisoDeGuardado[] = [];
  const sinDuracion = borrador.cajas.length - renglones.length;
  if (sinDuracion > 0) {
    avisos.push({
      clase: 'sin-duracion',
      mensaje:
        `${sinDuracion} ${sinDuracion === 1 ? 'caja' : 'cajas'} sin duración no ` +
        `${sinDuracion === 1 ? 'entra' : 'entran'} al programa.`,
    });
  }

  let refsFuera = 0;
  const items = renglones
    .slice()
    .sort((a, b) => a.orden - b.orden)
    .map((caja, indice): ItemProgramaBasePeticion => {
      const dependencias: DependenciaDTO[] = [];
      for (const cable of caja.entradas) {
        if (!incluidos.has(cable.desde)) {
          refsFuera += 1;
          continue;
        }
        dependencias.push({ ref: cable.desde, tipo: cable.tipo, lag_dias: cable.lagDias });
      }
      return {
        duracion_dias: caja.duracionDias ?? 0,
        prototipo_nodo_id: caja.id,
        etapa_id: caja.etapaId,
        frente_id: caja.frenteId,
        dependencias,
        tramos: caja.tramos.map((tramo) => ({
          duracion_dias: tramo.duracionDias,
          offset_dias: tramo.offsetDias,
        })),
        orden: indice,
      };
    });

  if (refsFuera > 0) {
    avisos.push({
      clase: 'ref-fuera',
      mensaje:
        `${refsFuera} ${refsFuera === 1 ? 'dependencia apunta' : 'dependencias apuntan'} a ` +
        `una caja sin duración y no se ${refsFuera === 1 ? 'guarda' : 'guardan'}.`,
    });
  }

  return { items, avisos };
}
