/**
 * Las dos bandas del encabezado del Gantt y los tres gestos del zoom (§7.5).
 *
 * ## Por qué dos bandas y no una
 *
 * El encabezado nació con una sola fila de bloques de siete días, que es lo
 * mínimo para no perderse. Un Gantt de Opus/Project rotula el eje en **dos
 * alturas** —el periodo grande arriba, el chico abajo— y no es adorno: con una
 * sola fila, o se ve el detalle y se pierde de vista en qué mes se está, o se
 * ve el mes y no se distingue un día de otro. Las cuatro escalas del menú son
 * las cuatro combinaciones útiles de ese par.
 *
 * ## Qué es un "mes" en un programa base
 *
 * En modo **fechas** es el mes de calendario de verdad: el eje ya tiene la
 * fecha simulada de cada día del programa (`ejePrograma.calendarioDelPrograma`),
 * así que agrupar por `YYYY-MM` no supone nada — los días del programa son días
 * hábiles consecutivos y su mes real se conoce.
 *
 * En modo **relativo** no hay mes al que pertenecer: un programa base es una
 * plantilla sin origen de tiempo (§7.5). Rotular ahí "Mes 1" sería inventar un
 * calendario, y además mentiría por partida doble, porque veintiocho días de
 * programa son días **hábiles** y no un mes natural. Así que la banda de arriba
 * agrupa cuatro semanas y se rotula por lo que de verdad es —`Sem 1–4`—. La
 * escala se sigue llamando "Meses" porque es lo que hace en el modo en que los
 * meses existen; la etiqueta no miente en el modo en que no.
 *
 * ## El zoom
 *
 * Acercar y alejar caminan por los escalones de `ZOOM_EJE` en vez de multiplicar
 * por un factor: con un factor libre el usuario acaba en 13.7 px/día y la
 * rejilla de días deja de caer en píxeles enteros, que es cuando el fondo
 * empieza a temblar al desplazarse. "Ajustar" sí produce un valor libre, porque
 * su trabajo es exactamente que el programa completo quepa en el ancho que hay.
 *
 * Módulo puro (§12.11).
 */

import { ZOOM_EJE, type EjePrograma } from './ejePrograma';
import type { EscalaEje } from './vistaGantt';

/** Un tramo del encabezado: dónde arranca, cuánto abarca y cómo se rotula. */
export interface BandaEje {
  /** Primer día del programa que cubre, 0-based. */
  readonly dia: number;
  /** Días del programa que abarca; el último tramo puede quedar corto. */
  readonly dias: number;
  readonly etiqueta: string;
  /** Texto largo para el `title`; el corto se recorta a lo que quepa. */
  readonly titulo: string;
  /** El tramo contiene hoy; sólo puede ser cierto en modo fechas. */
  readonly esHoy: boolean;
}

export interface BandasEje {
  /** El periodo grande: semanas o meses, según la escala. */
  readonly superior: readonly BandaEje[];
  /** El periodo chico: días o semanas. Es el que fija la rejilla del fondo. */
  readonly inferior: readonly BandaEje[];
  /**
   * Días que abarca una celda de la banda inferior. Es lo que el lienzo usa
   * para dibujar la cuadrícula, y lo que la rejilla de cantidades usa como
   * periodo (`reparto.ts`): las dos tienen que partir el eje igual o las
   * columnas de una dejarían de caer sobre las líneas de la otra.
   */
  readonly diasPorPeriodo: number;
}

const MESES = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
] as const;

const DIAS_POR_SEMANA = 7;
/** Cuatro semanas: lo que la banda de arriba agrupa en modo relativo. */
const SEMANAS_POR_BLOQUE = 4;

/** Qué pareja de periodos usa cada escala. */
const BANDA_INFERIOR: Record<EscalaEje, 'dia' | 'semana'> = {
  dias: 'dia',
  semanas: 'semana',
  'meses-dias': 'dia',
  'meses-semanas': 'semana',
};

const BANDA_SUPERIOR: Record<EscalaEje, 'semana' | 'mes'> = {
  dias: 'semana',
  semanas: 'mes',
  'meses-dias': 'mes',
  'meses-semanas': 'mes',
};

/**
 * Las dos bandas del encabezado para una escala.
 *
 * El eje ya sabe cuántos días mide el lienzo y qué fecha simulada le toca a
 * cada uno; aquí sólo se agrupa. Nada de esto toca el modelo: cambiar de escala
 * no mueve una sola actividad.
 */
export function construirBandas(eje: EjePrograma, escala: EscalaEje): BandasEje {
  const diasPorPeriodo = BANDA_INFERIOR[escala] === 'dia' ? 1 : DIAS_POR_SEMANA;

  const inferior =
    BANDA_INFERIOR[escala] === 'dia' ? bandaDeDias(eje) : bandaDeSemanas(eje);
  const superior =
    BANDA_SUPERIOR[escala] === 'mes' ? bandaDeMeses(eje) : bandaDeSemanas(eje);

  return { superior, inferior, diasPorPeriodo };
}

/** Un tramo por día del programa. */
function bandaDeDias(eje: EjePrograma): readonly BandaEje[] {
  const bandas: BandaEje[] = [];
  for (let dia = 0; dia < eje.dias; dia += 1) {
    bandas.push({
      dia,
      dias: 1,
      etiqueta: eje.modo === 'fechas' ? diaDeFecha(eje.fechas[dia]) : String(dia + 1),
      titulo: tituloDeDia(eje, dia),
      esHoy: eje.diaDeHoy === dia,
    });
  }
  return bandas;
}

/**
 * Un tramo por semana de programa (siete días hábiles).
 *
 * La etiqueta es el **primer día** que abarca —"Día 1", "Día 8"— y no el número
 * de semana. En un eje relativo lo que el jefe de obra cuenta son días del
 * programa: "el aplanado arranca el día 15" es una frase que se dice; "arranca
 * en la semana 3" obliga a multiplicar. El número de semana sigue estando, en
 * el `title`. En modo fechas la etiqueta es la fecha en que la semana arranca,
 * que es la misma idea con el calendario puesto.
 */
function bandaDeSemanas(eje: EjePrograma): readonly BandaEje[] {
  return agrupar(eje, DIAS_POR_SEMANA, (desde, dias) => {
    const semana = Math.floor(desde / DIAS_POR_SEMANA) + 1;
    return {
      etiqueta: eje.modo === 'fechas' ? etiquetaDeFecha(eje.fechas[desde]) : `Día ${desde + 1}`,
      titulo:
        eje.modo === 'fechas'
          ? `Semana ${semana} · arranca ${eje.fechas[desde] ?? '—'}`
          : `Semana ${semana} del programa · días ${desde + 1} a ${desde + dias}`,
    };
  });
}

/**
 * Meses de calendario en modo fechas; bloques de cuatro semanas en relativo.
 *
 * Los dos casos son de verdad distintos y por eso no comparten camino: el mes
 * real tiene una duración que depende del calendario y del conjunto de días
 * hábiles —febrero con sábados es más corto que marzo sin ellos—, así que se
 * agrupa por lo que dicen las fechas y no por una cuenta fija.
 */
function bandaDeMeses(eje: EjePrograma): readonly BandaEje[] {
  if (eje.modo !== 'fechas') {
    return agrupar(eje, DIAS_POR_SEMANA * SEMANAS_POR_BLOQUE, (desde, dias) => {
      const primera = Math.floor(desde / DIAS_POR_SEMANA) + 1;
      const ultima = Math.floor((desde + dias - 1) / DIAS_POR_SEMANA) + 1;
      return {
        etiqueta: primera === ultima ? `Sem ${primera}` : `Sem ${primera}–${ultima}`,
        titulo:
          `Semanas ${primera} a ${ultima} del programa. En días relativos no hay mes ` +
          'de calendario al que pertenecer: la plantilla no tiene fecha de arranque (§7.5).',
      };
    });
  }

  const bandas: BandaEje[] = [];
  let desde = 0;
  while (desde < eje.dias) {
    const mes = mesDe(eje.fechas[desde]);
    let hasta = desde + 1;
    while (hasta < eje.dias && mesDe(eje.fechas[hasta]) === mes) hasta += 1;
    bandas.push({
      dia: desde,
      dias: hasta - desde,
      etiqueta: nombreDeMes(mes),
      titulo: `${nombreDeMes(mes)} · ${hasta - desde} días de programa`,
      esHoy: eje.diaDeHoy !== null && eje.diaDeHoy >= desde && eje.diaDeHoy < hasta,
    });
    desde = hasta;
  }
  return bandas;
}

/** Agrupa el eje en tramos de tamaño fijo; el último puede quedar corto. */
function agrupar(
  eje: EjePrograma,
  tamano: number,
  rotular: (desde: number, dias: number) => { readonly etiqueta: string; readonly titulo: string },
): readonly BandaEje[] {
  const bandas: BandaEje[] = [];
  for (let dia = 0; dia < eje.dias; dia += tamano) {
    const dias = Math.min(tamano, eje.dias - dia);
    const { etiqueta, titulo } = rotular(dia, dias);
    bandas.push({
      dia,
      dias,
      etiqueta,
      titulo,
      esHoy: eje.diaDeHoy !== null && eje.diaDeHoy >= dia && eje.diaDeHoy < dia + dias,
    });
  }
  return bandas;
}

function tituloDeDia(eje: EjePrograma, dia: number): string {
  if (eje.modo !== 'fechas') return `Día ${dia + 1} del programa`;
  return `Día ${dia + 1} · ${eje.fechas[dia] ?? '—'}`;
}

/** `YYYY-MM` de una fecha ISO; cadena vacía si no la hay. */
function mesDe(iso: string | undefined): string {
  return iso === undefined ? '' : iso.slice(0, 7);
}

function nombreDeMes(mes: string): string {
  const indice = Number(mes.slice(5, 7)) - 1;
  const nombre = MESES[indice];
  if (nombre === undefined) return mes === '' ? '—' : mes;
  return `${nombre} ${mes.slice(2, 4)}`;
}

/** Día del mes de una fecha ISO, para la banda de días. */
function diaDeFecha(iso: string | undefined): string {
  return iso === undefined ? '' : String(Number(iso.slice(8, 10)));
}

/** `dd mmm` de una fecha ISO, para la banda de semanas en modo fechas. */
function etiquetaDeFecha(iso: string | undefined): string {
  if (iso === undefined) return '';
  const mes = MESES[Number(iso.slice(5, 7)) - 1] ?? '';
  return `${iso.slice(8, 10)} ${mes}`;
}

/** Dónde el calendario se saltó días entre dos días consecutivos del programa. */
export interface SaltoDeCalendario {
  /** Día del programa **después** del cual cae el salto, 0-based. */
  readonly dia: number;
  readonly diasSaltados: number;
}

/**
 * Los saltos de calendario del eje: fin de semana, día no laborable.
 *
 * Es lo que puede dibujar el fondo "bandas inhábiles", y hay que entender por
 * qué no es lo que parece. El eje del programa **sólo tiene días hábiles**: lo
 * construye `calendarioDelPrograma` caminando el conjunto de días de trabajo,
 * así que dentro del lienzo no hay ni un domingo que sombrear. Lo que sí existe
 * —y es la información útil— es la **costura**: entre el día 5 y el día 6 del
 * programa pasaron dos días de calendario que nadie trabajó. Se marca ahí, en
 * la juntura, con su cuenta en el `title`.
 *
 * En días relativos no hay ninguno: sin fechas no hay calendario del que
 * saltarse nada, y devolver algo sería inventarlo.
 */
export function saltosDeCalendario(eje: EjePrograma): readonly SaltoDeCalendario[] {
  if (eje.modo !== 'fechas') return [];

  const saltos: SaltoDeCalendario[] = [];
  for (let dia = 0; dia + 1 < eje.fechas.length; dia += 1) {
    const actual = julianoDe(eje.fechas[dia]);
    const siguiente = julianoDe(eje.fechas[dia + 1]);
    if (actual === null || siguiente === null) continue;
    const brecha = siguiente - actual - 1;
    if (brecha > 0) saltos.push({ dia, diasSaltados: brecha });
  }
  return saltos;
}

/** Días julianos de una fecha ISO; `null` si no la hay. */
function julianoDe(iso: string | undefined): number | null {
  if (iso === undefined) return null;
  const ms = Date.parse(`${iso}T00:00:00Z`);
  return Number.isFinite(ms) ? Math.floor(ms / 86_400_000) : null;
}

/** Zoom mínimo y máximo: los extremos del escalonado. */
const ZOOM_MINIMO = ZOOM_EJE[0] ?? 4;
const ZOOM_MAXIMO = ZOOM_EJE[ZOOM_EJE.length - 1] ?? 64;

/**
 * El escalón siguiente hacia arriba. Desde un zoom libre —el que deja
 * "Ajustar"— se toma el primero que sea mayor, no el vecino de una lista en la
 * que ese valor no está.
 */
export function acercarZoom(zoom: number): number {
  return ZOOM_EJE.find((paso) => paso > zoom + 0.01) ?? ZOOM_MAXIMO;
}

export function alejarZoom(zoom: number): number {
  const menores = ZOOM_EJE.filter((paso) => paso < zoom - 0.01);
  return menores[menores.length - 1] ?? ZOOM_MINIMO;
}

/**
 * Px por día que hacen caber `dias` de programa en `anchoPx`.
 *
 * Se recorta a los extremos del escalonado: por debajo del mínimo una barra de
 * una semana mediría veinte píxeles y dejaría de poder agarrarse para
 * arrastrarla, y por encima del máximo "ajustar" sería un acercamiento y no un
 * ajuste. Con un ancho o unos días no utilizables devuelve el mínimo, que es lo
 * que deja la pantalla usable mientras el contenedor se mide.
 */
export function zoomParaAjustar(dias: number, anchoPx: number): number {
  if (!Number.isFinite(dias) || !Number.isFinite(anchoPx) || dias <= 0 || anchoPx <= 0) {
    return ZOOM_MINIMO;
  }
  const bruto = anchoPx / dias;
  return Math.round(Math.min(ZOOM_MAXIMO, Math.max(ZOOM_MINIMO, bruto)) * 100) / 100;
}
