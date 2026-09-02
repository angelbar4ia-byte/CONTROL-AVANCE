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
 * ## Tres granularidades, un solo modelo
 *
 * `prototipo_nodo_id` puede apuntar a un **nivel**, a una **etapa** (plantilla
 * gruesa: toda la etapa constructiva es una actividad) o a un **concepto**. Las
 * tres son nodos del mismo árbol, así que las tres son cajas del mismo tipo y
 * el canvas solo cambia cuáles muestra. El nivel entró con la Fase 4
 * (`programa_base.profundidad_captura` admite `nivel`, y
 * `domain/programacion/jerarquia.py` reparte su ventana hacia abajo): antes el
 * editor no lo dibujaba y por eso no se podía programar lo que el backend ya
 * aceptaba.
 *
 * Un concepto puede depender de un concepto de otra etapa, y un nivel de una
 * etapa o de un concepto: el grafo no conoce esas fronteras, solo el árbol las
 * conoce, y el árbol no manda sobre las precedencias. Por eso aquí no se
 * bloquea ninguna combinación de extremos — el backend tampoco lo hace.
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
  ClaseNodo,
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

/**
 * Qué nodos del árbol pueden ser renglón: las tres clases del WBS (§7.4).
 *
 * Es literalmente `ClaseNodo` del contrato, no una copia: cualquier clase que
 * el backend admita como nodo del árbol es programable, y tener aquí una lista
 * paralela garantizaría que un día discreparan. Fue el caso hasta la Fase 4,
 * cuando `nivel` pasó a ser programable y este tipo se quedó en dos.
 */
export type TipoCaja = ClaseNodo;

/** De arriba abajo del árbol; es el orden en que se ofrecen en la barra. */
export const CLASES_CAJA: readonly TipoCaja[] = ['nivel', 'etapa', 'concepto'];

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
  /**
   * Padre en el árbol del prototipo (`nodo.parent_id`), tal cual llegó.
   *
   * Se guarda crudo —y no sólo la etapa, como antes— porque el canvas dibuja
   * el árbol **filtrado**: si el usuario apaga las etapas, el concepto tiene
   * que colgar de su nivel, y eso exige poder subir un eslabón a la vez
   * (`arbolVisible`).
   */
  readonly parentId: string | null;
  /** Etapa constructiva del catálogo (`nodo.etapa_id`), no el nodo etapa. */
  readonly etapaId: string | null;
  /** Nodo etapa del árbol al que pertenece el concepto; `null` en el resto. */
  readonly etapaNodoId: string | null;
  /**
   * `null` = renglón propuesto, todavía sin capturar. No viaja en el POST.
   * Con tramos es la **suma** de los tramos, no el span (§7.6).
   */
  readonly duracionDias: number | null;
  /**
   * Ancla de arranque: el día en que la caja empieza **pase lo que pase con
   * sus predecesoras**. `null` = lo decide el grafo, que es el caso normal.
   * Espejo de `programa_base_item.inicio_dias` (migración 0043).
   */
  readonly inicioDias: number | null;
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
 * **Todo** nodo del árbol entra como caja —nivel, etapa y concepto—, tenga
 * renglón o no: las que no lo tienen quedan con `duracionDias: null` y son la
 * propuesta que el usuario llena. Que estén todas no quiere decir que se vean
 * todas: cuáles se dibujan lo decide la vista (`idsVisibles`), y el borrador no
 * puede depender de eso o apagar una clase en la barra borraría sus cables.
 *
 * Las posiciones quedan en `(0, 0)`; las fija después `acomodarEnCapas`, que
 * necesita el grafo ya completo.
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
    const tipo: TipoCaja = nodo.tipo;
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
      parentId: nodo.parent_id ?? null,
      etapaId: nodo.etapa_id ?? null,
      etapaNodoId: tipo === 'concepto' ? etapaNodoDe(nodo, porId) : null,
      duracionDias: item ? Number(item.duracion_dias) : null,
      inicioDias:
        item?.inicio_dias === null || item?.inicio_dias === undefined
          ? null
          : Number(item.inicio_dias),
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
 * ## Por qué un conjunto de clases y no un modo excluyente
 *
 * El canvas empezó con dos modos que se pisaban —etapas *o* conceptos—, y eso
 * dejaba fuera justo lo que se pide para programar: ver **niveles, etapas y
 * conceptos juntos**, o cualquier par de ellos. Un nivel se liga con una etapa
 * y una etapa con un concepto de otra rama; si las dos clases no se pueden ver
 * a la vez, ese cable no se puede ni tender ni revisar. Así que la vista deja
 * de ser un modo y pasa a ser un **filtro por clase**: tres interruptores
 * independientes, siete combinaciones útiles.
 *
 * ## Por qué la etapa abierta convive con el filtro y no lo sustituye
 *
 * `etapaNodoId` es el doble clic —entrar a una etapa a ver sus conceptos— y
 * mientras está puesto manda sobre `clases`. Pero `clases` **se conserva**
 * debajo: salir de la etapa tiene que devolver al usuario a la combinación que
 * traía, no a un default. Con una unión discriminada eso obligaría a guardar la
 * combinación anterior en otro estado paralelo.
 *
 * Arranca sólo en etapas —diez o quince cajas se leen; los ~155 nodos de un
 * prototipo real, no—.
 */
export interface Vista {
  /** Clases dibujadas cuando no hay etapa abierta. Nunca vacío. */
  readonly clases: ReadonlySet<TipoCaja>;
  /** Etapa a la que se entró con doble clic; `null` = filtro por clases. */
  readonly etapaNodoId: string | null;
}

export const VISTA_INICIAL: Vista = { clases: new Set(['etapa']), etapaNodoId: null };

/** ¿Está el canvas dentro de una etapa (doble clic) y no en el filtro? */
export function enEtapa(vista: Vista): boolean {
  return vista.etapaNodoId !== null;
}

/** ¿La barra debe mostrar esta clase como encendida? */
export function muestraClase(vista: Vista, clase: TipoCaja): boolean {
  return !enEtapa(vista) && vista.clases.has(clase);
}

/**
 * Enciende o apaga una clase.
 *
 * Dos reglas, las dos por el mismo motivo —que el gesto nunca deje un canvas
 * que no dice nada—: apagar la última clase encendida no hace nada (el canvas
 * quedaría en blanco sin que el usuario haya pedido vaciarlo), y tocar
 * cualquier interruptor estando dentro de una etapa **sale** de ella, que es lo
 * que el usuario está pidiendo al cambiar el filtro.
 */
export function alternarClase(vista: Vista, clase: TipoCaja): Vista {
  // Dentro de una etapa los interruptores no reflejan lo que se ve, así que el
  // clic no apaga nada: sale al filtro con esa clase encendida.
  if (enEtapa(vista)) {
    return { clases: new Set([...vista.clases, clase]), etapaNodoId: null };
  }
  if (!vista.clases.has(clase)) {
    return { ...vista, clases: new Set([...vista.clases, clase]) };
  }
  if (vista.clases.size === 1) return vista;
  const clases = new Set(vista.clases);
  clases.delete(clase);
  return { ...vista, clases };
}

/** Entra a una etapa; conserva debajo la combinación de clases del filtro. */
export function abrirEtapa(vista: Vista, etapaNodoId: string): Vista {
  return { ...vista, etapaNodoId };
}

/** Sale de la etapa abierta y devuelve el filtro tal como estaba. */
export function salirDeEtapa(vista: Vista): Vista {
  return { ...vista, etapaNodoId: null };
}

/**
 * Ids visibles en esta vista.
 *
 * Con etapa abierta se incluyen además los conceptos de **otras** etapas que
 * estén cableados con los de esta: el usuario pidió explícitamente poder ligar
 * conceptos entre etapas, y un cable cuyo otro extremo no se ve no se puede ni
 * revisar ni quitar. Se marcan aparte con `esForaneo` para que el canvas los
 * dibuje como contexto y no como parte de la etapa abierta.
 */
export function idsVisibles(borrador: Borrador, vista: Vista): ReadonlySet<string> {
  if (vista.etapaNodoId === null) {
    return new Set(
      borrador.cajas.filter((caja) => vista.clases.has(caja.tipo)).map((caja) => caja.id),
    );
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
  return enEtapa(vista) && caja.etapaNodoId !== vista.etapaNodoId;
}

/** Dónde cuelga una caja en el árbol filtrado, y en qué lugar del recorrido. */
export interface RamaVisible {
  /** Ancestro visible más cercano; `null` si ninguno lo es. */
  readonly padreVisibleId: string | null;
  /** Preorden dentro del árbol filtrado. */
  readonly orden: number;
}

/**
 * El árbol tal como queda después del filtro por clases.
 *
 * Es la pieza que hace utilizable la vista mixta. Si se ven niveles y conceptos
 * pero no etapas, el concepto no queda suelto: su padre pasa a ser el ancestro
 * visible más cercano —su nivel, o sea su abuelo—, porque un ancestro oculto se
 * **colapsa**, no corta la rama. Es el mismo criterio que `visiblesEnJerarquia`
 * aplica en el Gantt del árbol (`jerarquia.ts`), pero al revés: allá se esconde
 * lo que cuelga de un nodo colapsado, aquí se re-cuelga lo que sobrevive al
 * filtro.
 *
 * El `orden` es el preorden de ese árbol filtrado, no el del árbol completo:
 * así los hijos de un nivel quedan contiguos al acomodar y la columna se lee
 * como la rama que es, en vez de intercalar conceptos de niveles distintos.
 *
 * Sólo devuelve entradas para las cajas visibles.
 */
export function arbolVisible(
  borrador: Borrador,
  visibles: ReadonlySet<string>,
): ReadonlyMap<string, RamaVisible> {
  const conocidos = new Set(borrador.cajas.map((caja) => caja.id));
  // Un `parent_id` que no está entre las cajas (dato inconsistente, o un nodo
  // recortado) convierte a la caja en raíz en vez de perderla.
  const hijos = new Map<string | null, Caja[]>();
  for (const caja of borrador.cajas) {
    const padre =
      caja.parentId !== null && conocidos.has(caja.parentId) ? caja.parentId : null;
    const lista = hijos.get(padre);
    if (lista) lista.push(caja);
    else hijos.set(padre, [caja]);
  }

  const rama = new Map<string, RamaVisible>();
  const visitados = new Set<string>();
  let orden = 0;

  // Recorrido en profundidad sobre el árbol **completo**: se baja también por
  // los ocultos, porque son ellos los que se colapsan. `visitados` es la red
  // contra un `parent_id` en ciclo, que colgaría la pantalla.
  function bajar(id: string | null, padreVisibleId: string | null): void {
    for (const hijo of hijos.get(id) ?? []) {
      if (visitados.has(hijo.id)) continue;
      visitados.add(hijo.id);
      if (visibles.has(hijo.id)) {
        rama.set(hijo.id, { padreVisibleId, orden });
        orden += 1;
        bajar(hijo.id, hijo.id);
      } else {
        bajar(hijo.id, padreVisibleId);
      }
    }
  }
  bajar(null, null);

  return rama;
}

/** Qué mira el usuario en el canvas: una caja, un cable, o nada. */
export type Seleccion =
  | { readonly clase: 'caja'; readonly cajaId: string }
  | { readonly clase: 'cable'; readonly desde: string; readonly hasta: string }
  | null;

/**
 * Identidad del cable en el canvas.
 *
 * Un cable no tiene id propio en el contrato —es una entrada de
 * `dependencias[]` de su sucesora—, así que su identidad es el par ordenado, y
 * esta función es el único lugar donde se arma la cadena que usan React Flow y
 * los avisos de traslape. Los extremos son UUIDs, así que `->` no aparece
 * dentro de ninguno de los dos.
 */
export function idDeCable(desde: string, hasta: string): string {
  return `${desde}->${hasta}`;
}

/** El cable `desde → hasta` del borrador, o `null` si ya no existe. */
export function buscarCable(
  borrador: Borrador,
  desde: string,
  hasta: string,
): Cable | null {
  const sucesora = borrador.cajas.find((caja) => caja.id === hasta);
  return sucesora?.entradas.find((cable) => cable.desde === desde) ?? null;
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
 * Se ofrecen las tres clases, niveles incluidos: desde la Fase 4 un nivel es
 * programable, y que el alta no lo ofreciera mientras el canvas sí lo dibuja
 * dejaría las dos pantallas contando cosas distintas del mismo contrato.
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
    const sangria = SANGRIA.repeat(profundidad(nodo));
    const clave = nodo.clave ? `${nodo.clave} · ` : '';
    opciones.push({
      valor: nodo.id,
      etiqueta: `${sangria}${clave}${nodo.nombre}`,
      tipo: nodo.tipo,
    });
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
        inicio_dias: caja.inicioDias,
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
