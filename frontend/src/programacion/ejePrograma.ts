/**
 * Eje de tiempo del programa base: **días relativos**, con fechas reales como
 * simulación opcional (§7.5).
 *
 * ## Por qué no se reusa `escala.ts`
 *
 * `escala.ts` es el eje del cronograma de una **obra**: parte de fechas que el
 * motor CPM ya resolvió (`YYYY-MM-DD`) y las traduce a porcentajes del lienzo.
 * Un programa base no tiene ninguna fecha —es una plantilla de duraciones sin
 * origen de tiempo, y por eso `ItemProgramaBasePeticion` no lleva ni una—, así
 * que ahí no hay nada que traducir: el eje arranca en el **día 1** y se mide en
 * días del programa. Forzar `escala.ts` a este caso obligaría a inventarle una
 * fecha de arranque al programa, que es justamente lo que un programa base no
 * tiene y lo que lo hace reusable en cuarenta obras.
 *
 * Lo que sí se reusa de `escala.ts` es su aritmética de fechas (`aDia`, `aIso`),
 * que ya está resuelta contra el problema de los husos y el horario de verano.
 *
 * ## El modo "fechas reales" es una simulación, y se dice
 *
 * El interruptor de fechas contesta *"si esto arrancara el lunes 3, ¿qué días
 * caerían?"*. No es el cronograma de ninguna obra: eso lo produce el motor al
 * instanciar el programa (`POST /obras/{id}/programa`) y llega por la API con
 * la ruta crítica ya calculada. Aquí sólo se **etiqueta** el mismo eje relativo
 * caminando los días hábiles del calendario del borrador (`calendario.ts`), que
 * es aritmética de calendario, no CPM: no propaga dependencias, no deriva
 * holgura y no decide nada. El día 5 del programa sigue siendo el día 5; lo
 * único que cambia es cómo se rotula la columna.
 *
 * Módulo puro (§12.11).
 */

import { normalizarDias } from './calendario';
import { aDia, aIso } from './escala';

export type ModoEje = 'relativo' | 'fechas';

/**
 * Escalones del zoom, en px por día del programa.
 *
 * Los dos extremos los pidió el menú de herramientas (`bandasPrograma.ts`): el
 * de 4 px es el que hace caber un programa de un año en pantalla al pulsar
 * "Ajustar", y el de 64 px es el que deja legible la etiqueta de un día suelto
 * cuando la escala baja a días. En medio están los cinco de siempre.
 */
export const ZOOM_EJE: readonly number[] = [4, 6, 10, 16, 26, 40, 64];

/** Zoom de entrada: 16 px/día deja legible un programa de ~120 días. */
export const ZOOM_POR_DEFECTO = 16;

/**
 * Geometría del renglón, compartida por las dos mitades del panel.
 *
 * Vive aquí —con el resto de la geometría del lienzo— y no en cada componente
 * porque la sincronía de scroll **depende** de que los dos lados midan
 * exactamente lo mismo: si la tabla usara 28 px por renglón y el Gantt 30, la
 * barra de la fila 100 quedaría dos renglones arriba de su descripción y nadie
 * lo notaría hasta bajar bastante. Un solo número lo hace imposible.
 */
export const ALTO_FILA = 28;

/**
 * Alto del encabezado pegajoso; los dos lados llevan uno y miden igual.
 *
 * Son dos bandas —periodo grande arriba, chico abajo (`bandasPrograma.ts`)—, y
 * por eso mide más que un renglón. Lo que no puede es medir distinto en las dos
 * mitades: el virtualizador de cada lado lo descuenta como `scrollMargin`, y un
 * píxel de diferencia corre una lista respecto de la otra.
 */
export const ALTO_ENCABEZADO = 34;

/** Días que agrupa una columna del encabezado. Siete, como `escala.ts`. */
const DIAS_POR_BLOQUE = 7;

/** Lienzo mínimo, para que un programa de dos actividades siga siendo legible. */
const DIAS_MINIMOS = 28;

/** Aire a la derecha del cierre, para poder estirar la última barra. */
const DIAS_DE_COLA = 7;

const MESES = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
] as const;

export interface BloqueEje {
  /** Primer día del bloque, 0-based (el día 0 es el arranque del programa). */
  readonly dia: number;
  readonly etiqueta: string;
  /** El bloque contiene el día de hoy; sólo puede ser cierto en modo fechas. */
  readonly esHoy: boolean;
}

/**
 * Una columna del lienzo: **un día de calendario**, se trabaje o no.
 *
 * Antes una columna era un día hábil, así que con semana de lunes a viernes el
 * sábado y el domingo no existían: una semana ocupaba cinco columnas y no había
 * forma de ver dónde caía el hueco. Ahora el fin de semana ocupa su sitio, sin
 * número debajo, y el salto se entiende con solo mirarlo.
 */
export interface ColumnaEje {
  /** Índice en el lienzo, 0-based. Es lo que multiplica `pxPorDia`. */
  readonly columna: number;
  /**
   * Día **hábil** del programa que cae aquí, 0-based, o `null` si no se
   * trabaja. Es la unidad en la que hablan las duraciones, las dependencias y
   * los tramos (§7.5, §7.6); la columna es solo dónde se dibuja.
   */
  readonly diaHabil: number | null;
  /** Día de la semana ISO, 1 = lunes … 7 = domingo. De aquí sale la letra. */
  readonly diaSemana: number;
  /** Fecha simulada `YYYY-MM-DD`, o `null` en modo relativo. */
  readonly fecha: string | null;
}

export interface EjePrograma {
  readonly modo: ModoEje;
  /** Columnas que mide el lienzo; múltiplo de `DIAS_POR_BLOQUE`. */
  readonly dias: number;
  readonly pxPorDia: number;
  /** Ancho del lienzo en px. */
  readonly ancho: number;
  readonly bloques: readonly BloqueEje[];
  /**
   * Una entrada por columna del lienzo. Se precalcula porque caminar el
   * calendario es un bucle y el Gantt lo consultaría una vez por barra.
   */
  readonly columnas: readonly ColumnaEje[];
  /**
   * Columna en que arranca cada día hábil, indexada por día hábil. Es el
   * inverso de `columnas` y existe para que colocar una barra sea un índice y
   * no una búsqueda: el Gantt lo hace dos veces por renglón.
   */
  readonly columnaPorDia: readonly number[];
  /**
   * Fecha de cada **día hábil** del programa, `YYYY-MM-DD`; vacío en modo
   * relativo. Se conserva con esa indexación porque es la que usan la tabla y
   * los tooltips, que hablan de días del programa y no de columnas.
   */
  readonly fechas: readonly string[];
  /** Día hábil en que cae hoy, o `null` fuera de rango / modo relativo. */
  readonly diaDeHoy: number | null;
}

export interface EntradaEje {
  /** Día en que cierra la última actividad colocada (`duracionDelPrograma`). */
  readonly finMaximo: number;
  readonly pxPorDia?: number;
  readonly modo?: ModoEje;
  /** Arranque de la simulación, `YYYY-MM-DD`; obligatorio en modo fechas. */
  readonly inicio?: string | null;
  /** Días hábiles ISO del borrador (`calendario.ts`). */
  readonly diasHabiles?: readonly number[];
  /** Hoy, `YYYY-MM-DD`. Se inyecta para que las pruebas no dependan del reloj. */
  readonly hoy?: string | null;
}

/**
 * Construye el eje.
 *
 * En modo fechas sin `inicio` se cae a relativo en vez de inventar una fecha de
 * arranque: un programa base no tiene ninguna y suponerle "hoy" haría que la
 * misma plantilla se leyera distinta cada mañana.
 */
export function construirEje({
  finMaximo,
  pxPorDia = ZOOM_POR_DEFECTO,
  modo = 'relativo',
  inicio = null,
  diasHabiles,
  hoy = null,
}: EntradaEje): EjePrograma {
  const conFechas = modo === 'fechas' && aDia(inicio) !== null;

  // Se piden columnas suficientes para cubrir los días hábiles del programa
  // más la cola. Con semana de lunes a viernes hacen falta siete columnas por
  // cada cinco días de trabajo, así que el lienzo se estira por el peor caso y
  // después se recorta al bloque; sobrar columnas a la derecha es aire para
  // estirar la última barra, que es lo que `DIAS_DE_COLA` ya buscaba.
  const habilesPedidos = Math.max(DIAS_MINIMOS, Math.max(0, Math.ceil(finMaximo)) + DIAS_DE_COLA);
  const columnas = construirColumnas({
    habilesPedidos,
    inicio: conFechas ? inicio : null,
    diasHabiles,
  });
  const dias = columnas.length;

  const columnaPorDia: number[] = [];
  const fechas: string[] = [];
  for (const columna of columnas) {
    if (columna.diaHabil === null) continue;
    columnaPorDia[columna.diaHabil] = columna.columna;
    if (columna.fecha !== null) fechas.push(columna.fecha);
  }

  const diaDeHoy = conFechas ? indiceDeFecha(fechas, hoy) : null;
  const columnaDeHoy = diaDeHoy === null ? null : (columnaPorDia[diaDeHoy] ?? null);

  const bloques: BloqueEje[] = [];
  for (let columna = 0; columna < dias; columna += DIAS_POR_BLOQUE) {
    const primera = columnas[columna];
    bloques.push({
      dia: columna,
      etiqueta: conFechas
        ? etiquetaDeFecha(primera?.fecha ?? undefined)
        : `Día ${(primera?.diaHabil ?? columna) + 1}`,
      esHoy:
        columnaDeHoy !== null &&
        columnaDeHoy >= columna &&
        columnaDeHoy < columna + DIAS_POR_BLOQUE,
    });
  }

  return {
    modo: conFechas ? 'fechas' : 'relativo',
    dias,
    pxPorDia,
    ancho: dias * pxPorDia,
    bloques,
    columnas,
    columnaPorDia,
    fechas,
    diaDeHoy,
  };
}

/**
 * Las columnas del lienzo, una por día de calendario.
 *
 * En modo fechas se camina desde `inicio`; en modo relativo **el día 1 es un
 * lunes**. Un programa base no tiene fecha propia (§7.5) y hay que elegir algo:
 * el lunes es lo que hace que la semana se lea como se lee en obra, y cualquier
 * otro arranque pondría el primer fin de semana en un sitio distinto cada vez.
 *
 * Se emiten columnas hasta cubrir `habilesPedidos` días de trabajo, y luego se
 * redondea al bloque para que el encabezado no quede partido.
 */
function construirColumnas({
  habilesPedidos,
  inicio,
  diasHabiles,
}: {
  readonly habilesPedidos: number;
  readonly inicio: string | null | undefined;
  readonly diasHabiles: readonly number[] | undefined;
}): readonly ColumnaEje[] {
  const habiles = new Set(normalizarDias(diasHabiles));
  const primero = aDia(inicio);

  const salida: ColumnaEje[] = [];
  let habilesVistos = 0;
  // El tope evita colgar la pantalla si el conjunto de hábiles llegara vacío
  // pese a `normalizarDias`, que ya cae a los siete.
  const tope = habilesPedidos * 7 + DIAS_POR_BLOQUE * 2 + 14;

  for (let paso = 0; paso < tope; paso += 1) {
    const juliano = primero === null ? null : primero + paso;
    // Sin fecha, el paso 0 es lunes: ISO 1..7 ciclando.
    const diaSemana = juliano === null ? (paso % 7) + 1 : diaIsoDeSemana(juliano);
    const laborable = habiles.has(diaSemana);

    salida.push({
      columna: paso,
      diaHabil: laborable ? habilesVistos : null,
      diaSemana,
      fecha: juliano === null ? null : aIso(juliano),
    });
    if (laborable) habilesVistos += 1;

    // Se corta al cerrar un bloque, y solo cuando ya se cubrió lo pedido: así
    // el encabezado siempre trae semanas completas.
    const cerrado = (paso + 1) % DIAS_POR_BLOQUE === 0;
    if (cerrado && habilesVistos >= habilesPedidos) break;
  }
  return salida;
}

/**
 * Fecha de cada día del programa, caminando **sólo los días hábiles**.
 *
 * El día 0 es el primer día hábil en o después de `inicio`: arrancar un
 * programa en domingo con semana laboral de lunes a sábado no adelanta el
 * trabajo al domingo, lo empuja al lunes — que es lo que hace el motor y lo
 * único que esta simulación tiene que respetar para no mentir.
 */
export function calendarioDelPrograma(
  inicio: string | null | undefined,
  diasHabiles: readonly number[] | null | undefined,
  dias: number,
): readonly string[] {
  const primero = aDia(inicio);
  if (primero === null || dias <= 0) return [];

  const habiles = new Set(normalizarDias(diasHabiles));
  const salida: string[] = [];

  // El tope de vueltas evita colgar la pantalla si algún día el conjunto de
  // hábiles llegara vacío pese a `normalizarDias` (que ya cae a los siete).
  const tope = dias * 7 + 14;
  let juliano = primero;
  for (let vuelta = 0; salida.length < dias && vuelta < tope; vuelta += 1, juliano += 1) {
    if (habiles.has(diaIsoDeSemana(juliano))) salida.push(aIso(juliano));
  }
  return salida;
}

/** Día ISO de la semana (1 = lunes … 7 = domingo) de un día juliano. */
function diaIsoDeSemana(juliano: number): number {
  const domingoCero = new Date(juliano * 86_400_000).getUTCDay();
  return domingoCero === 0 ? 7 : domingoCero;
}

/**
 * Día del programa en que cae una fecha, o `null` si no es hábil o queda fuera
 * del lienzo. Se busca por bisección: el arreglo va ordenado por construcción.
 */
export function indiceDeFecha(
  fechas: readonly string[],
  fecha: string | null | undefined,
): number | null {
  const objetivo = aDia(fecha);
  if (objetivo === null || fechas.length === 0) return null;

  let bajo = 0;
  let alto = fechas.length - 1;
  while (bajo <= alto) {
    const medio = (bajo + alto) >> 1;
    const actual = aDia(fechas[medio]);
    if (actual === null) return null;
    if (actual === objetivo) return medio;
    if (actual < objetivo) bajo = medio + 1;
    else alto = medio - 1;
  }
  return null;
}

function etiquetaDeFecha(iso: string | undefined): string {
  const juliano = aDia(iso);
  if (juliano === null) return '';
  const fecha = new Date(juliano * 86_400_000);
  const numero = String(fecha.getUTCDate()).padStart(2, '0');
  return `${numero} ${MESES[fecha.getUTCMonth()] ?? ''}`;
}

/** Píxeles desde el borde izquierdo del lienzo hasta el arranque de un día. */
export function xDeDia(eje: EjePrograma, dia: number): number {
  return columnaDeDiaHabil(eje, dia) * eje.pxPorDia;
}

/**
 * Columna del lienzo en que arranca un día hábil del programa.
 *
 * Fuera de rango se extrapola en vez de recortar: una barra que se sale del
 * lienzo tiene que dibujarse fuera —y quedar cortada por el scroll— y no
 * amontonarse en el borde, que se leería como que ahí termina. Se extrapola con
 * la razón real de columnas por día hábil (7/5 con semana de lunes a viernes),
 * que es la que mantiene la pendiente del dibujo.
 */
export function columnaDeDiaHabil(eje: EjePrograma, dia: number): number {
  const total = eje.columnaPorDia.length;
  if (total === 0) return dia;

  const entero = Math.floor(dia);
  const fraccion = dia - entero;

  if (entero < 0) return entero * _razon(eje);
  if (entero >= total) {
    const ultima = eje.columnaPorDia[total - 1] ?? 0;
    return ultima + (entero - (total - 1)) * _razon(eje);
  }

  const columna = eje.columnaPorDia[entero] ?? entero;
  if (fraccion === 0) return columna;
  // Dentro de un día hábil la fracción no salta el fin de semana: es la parte
  // de ESA columna, no del hueco que venga después.
  return columna + fraccion;
}

/** Columnas que ocupa un día hábil en promedio; 1 con semana natural. */
function _razon(eje: EjePrograma): number {
  const habiles = eje.columnaPorDia.length;
  return habiles === 0 ? 1 : eje.dias / habiles;
}

/**
 * Ancho en px de la ventana que va del día hábil `desde` al `hasta`.
 *
 * Sustituye al viejo `anchoDeDias(eje, hasta - desde)`, que multiplicaba la
 * duración por el zoom. Con el lienzo en días de calendario eso dejó de ser
 * cierto: **cinco días de trabajo ocupan siete columnas** si les cae un fin de
 * semana en medio, y la barra tiene que llegar hasta donde de verdad llega.
 * Por eso hacen falta los dos extremos y no basta la diferencia.
 */
export function anchoEntre(eje: EjePrograma, desde: number, hasta: number): number {
  const izquierda = columnaDeDiaHabil(eje, desde);
  const derecha = columnaDeDiaHabil(eje, Math.max(desde, hasta));
  return Math.max(0, derecha - izquierda) * eje.pxPorDia;
}

/**
 * Ancho en px de N **columnas**.
 *
 * Es la multiplicación de siempre y sigue sirviendo para lo que se mide en
 * columnas —las bandas del encabezado, el paso de la rejilla—. Lo que ya no
 * puede usarla es una barra, que se mide en días de trabajo: para eso está
 * `anchoEntre`.
 */
export function anchoDeColumnas(eje: EjePrograma, columnas: number): number {
  return Math.max(0, columnas) * eje.pxPorDia;
}

/** Día hábil (fraccionario) sobre el que cae una coordenada del lienzo. */
export function diaDeX(eje: EjePrograma, x: number): number {
  if (eje.pxPorDia === 0) return 0;
  return diaHabilDeColumna(eje, x / eje.pxPorDia);
}

/**
 * Día hábil que corresponde a una columna (fraccionaria) del lienzo.
 *
 * Una columna no laborable no tiene día hábil propio; se devuelve el del
 * **siguiente** día que se trabaja. Soltar una barra sobre un domingo no la
 * deja en el domingo —ahí no se trabaja—, la deja el lunes, que es lo que hace
 * el motor al colocar y lo único que no miente.
 */
export function diaHabilDeColumna(eje: EjePrograma, columna: number): number {
  const total = eje.columnas.length;
  if (total === 0) return columna;

  const entero = Math.floor(columna);
  const fraccion = columna - entero;

  if (entero < 0) return entero / _razon(eje);
  if (entero >= total) {
    const ultimo = eje.columnaPorDia.length - 1;
    return ultimo + (entero - (eje.columnaPorDia[ultimo] ?? 0)) / _razon(eje);
  }

  for (let i = entero; i < total; i += 1) {
    const habil = eje.columnas[i]?.diaHabil;
    if (habil !== null && habil !== undefined) {
      return i === entero ? habil + fraccion : habil;
    }
  }
  return eje.columnaPorDia.length;
}

/**
 * Etiqueta de un día suelto para los textos de la tabla y los tooltips: el
 * número de día del programa, o su fecha simulada.
 *
 * Los días se rotulan 1-based —"Día 1" es el arranque— porque así los cuenta el
 * jefe de obra; internamente el arranque es el 0, que es lo que devuelve
 * `colocar` y con lo que se hace toda la aritmética.
 */
export function etiquetaDeDia(eje: EjePrograma, dia: number | null): string {
  if (dia === null || !Number.isFinite(dia)) return '—';
  const entero = Math.round(dia);
  if (eje.modo === 'relativo') return `Día ${entero + 1}`;
  const iso = eje.fechas[Math.max(0, Math.min(eje.fechas.length - 1, entero))];
  return iso ?? '—';
}

/** Fecha simulada de un día del programa, o `null` en modo relativo. */
export function fechaDeDia(eje: EjePrograma, dia: number | null): string | null {
  if (dia === null || eje.modo !== 'fechas') return null;
  return eje.fechas[Math.max(0, Math.round(dia))] ?? null;
}
