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

/** Anchos de columna del zoom, en px por día del programa. */
export const ZOOM_EJE: readonly number[] = [6, 10, 16, 26, 40];

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

/** Alto del encabezado pegajoso; los dos lados llevan uno y miden igual. */
export const ALTO_ENCABEZADO = 26;

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

export interface EjePrograma {
  readonly modo: ModoEje;
  /** Días que mide el lienzo; múltiplo de `DIAS_POR_BLOQUE`. */
  readonly dias: number;
  readonly pxPorDia: number;
  /** Ancho del lienzo en px. */
  readonly ancho: number;
  readonly bloques: readonly BloqueEje[];
  /**
   * Fecha de cada día del programa en modo fechas, `YYYY-MM-DD`, indexada por
   * día 0-based; vacío en modo relativo. Se precalcula porque caminar los días
   * hábiles es un bucle y la tabla lo consultaría una vez por renglón.
   */
  readonly fechas: readonly string[];
  /** Día del programa en que cae hoy, o `null` fuera de rango / modo relativo. */
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
  const util = Math.max(0, Math.ceil(finMaximo)) + DIAS_DE_COLA;
  const bruto = Math.max(DIAS_MINIMOS, util);
  const dias = Math.ceil(bruto / DIAS_POR_BLOQUE) * DIAS_POR_BLOQUE;

  const conFechas = modo === 'fechas' && aDia(inicio) !== null;
  const fechas = conFechas ? calendarioDelPrograma(inicio, diasHabiles, dias) : [];

  const diaDeHoy = conFechas ? indiceDeFecha(fechas, hoy) : null;

  const bloques: BloqueEje[] = [];
  for (let dia = 0; dia < dias; dia += DIAS_POR_BLOQUE) {
    bloques.push({
      dia,
      etiqueta: conFechas
        ? etiquetaDeFecha(fechas[dia])
        : `Día ${dia + 1}`,
      esHoy:
        diaDeHoy !== null && diaDeHoy >= dia && diaDeHoy < dia + DIAS_POR_BLOQUE,
    });
  }

  return {
    modo: conFechas ? 'fechas' : 'relativo',
    dias,
    pxPorDia,
    ancho: dias * pxPorDia,
    bloques,
    fechas,
    diaDeHoy,
  };
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
  return dia * eje.pxPorDia;
}

/** Ancho en px de una cantidad de días. */
export function anchoDeDias(eje: EjePrograma, dias: number): number {
  return Math.max(0, dias) * eje.pxPorDia;
}

/** Día (fraccionario) sobre el que cae una coordenada del lienzo. */
export function diaDeX(eje: EjePrograma, x: number): number {
  return eje.pxPorDia === 0 ? 0 : x / eje.pxPorDia;
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
