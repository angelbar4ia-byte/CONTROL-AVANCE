/**
 * Escala de tiempo del Gantt: **aritmética de lienzo, no de negocio**.
 *
 * Todo lo que hay aquí traduce fechas que el backend ya calculó (§6) a
 * posiciones en pantalla. No decide cuándo empieza una actividad, no propaga
 * dependencias, no deriva holgura: eso es del motor CPM
 * (`domain/programacion/cpm.py`), que devuelve las fechas ya resueltas en
 * `GET /obras/{id}/ruta-critica` y `GET /obras/{id}/programa`.
 *
 * Vive fuera de los componentes por la regla del §12.11 (cero lógica en
 * React) y para poder fijarlo con pruebas.
 *
 * ## Por qué días julianos
 *
 * Postgres devuelve fechas puras (`date`) como `YYYY-MM-DD`. Restarlas con
 * `Date` local corre el resultado en los cambios de horario de verano; se
 * convierten a un entero de días vía `Date.UTC`, que no tiene husos ni DST,
 * y toda la aritmética ocurre sobre enteros.
 *
 * ## Por qué semanas de lunes a domingo
 *
 * El encabezado usa columnas de ancho igual (`.gantt__timeline` es un grid de
 * `1fr`). Para que una barra posicionada por porcentaje de día caiga exacta
 * sobre su columna, el lienzo tiene que medir un múltiplo de 7 días: se
 * ancla el inicio al lunes anterior y el fin al domingo siguiente.
 *
 * Las semanas se **etiquetan por su fecha de inicio**, no con un número de
 * semana: la "semana de obra" del §3.1 se cuenta desde un ancla que fija el
 * admin en la base, y numerarlas aquí inventaría una numeración paralela.
 */

const MS_DIA = 86_400_000;
const SOLO_FECHA = /^(\d{4})-(\d{2})-(\d{2})$/;

const MESES = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
] as const;

/** Semanas mínimas del lienzo, para que un cronograma corto siga siendo legible. */
const SEMANAS_MINIMAS = 4;

/** Ancho mínimo por columna de semana, en px (DESIGN_SYSTEM.md §4: `.gantt__week`). */
export const ANCHO_SEMANA = 56;

/** Ancho de la columna de etiquetas del Gantt, en px (`.gantt__row`). */
export const ANCHO_ETIQUETAS = 280;

/**
 * `YYYY-MM-DD` → días enteros desde la época, o `null` si no es una fecha
 * pura. Se ignora cualquier cosa que no venga en el formato de Postgres:
 * un `Date` con hora metería husos en una escala que es de días.
 */
export function aDia(iso: string | null | undefined): number | null {
  if (iso === null || iso === undefined) return null;
  const m = SOLO_FECHA.exec(iso);
  if (!m) return null;
  const [, anio, mes, dia] = m;
  const ms = Date.UTC(Number(anio), Number(mes) - 1, Number(dia));
  return Number.isNaN(ms) ? null : Math.round(ms / MS_DIA);
}

/** Días enteros desde la época → `YYYY-MM-DD`. */
export function aIso(dia: number): string {
  return new Date(dia * MS_DIA).toISOString().slice(0, 10);
}

/** Lunes de la semana a la que pertenece el día (ISO: la semana abre en lunes). */
function lunesDe(dia: number): number {
  const diaSemana = new Date(dia * MS_DIA).getUTCDay(); // 0 = domingo
  return dia - ((diaSemana + 6) % 7);
}

export interface SemanaEscala {
  /** Lunes de la semana, `YYYY-MM-DD`. */
  readonly inicio: string;
  /** `dd mmm` — ver la nota sobre la semana de obra del §3.1. */
  readonly etiqueta: string;
  /** La fecha de corte cae dentro de esta semana. */
  readonly esCorte: boolean;
}

export interface Escala {
  /** Primer día del lienzo (lunes), en días enteros. */
  readonly diaInicio: number;
  /** Días que mide el lienzo; siempre múltiplo de 7. */
  readonly dias: number;
  readonly semanas: readonly SemanaEscala[];
  /** Ancho mínimo del lienzo en px, para el scroll horizontal de `.gantt`. */
  readonly anchoMinimo: number;
}

export interface RangoFecha {
  readonly inicio: string | null;
  readonly fin: string | null;
}

/**
 * Lienzo que cubre todos los rangos recibidos más la fecha de corte.
 *
 * Devuelve `null` cuando ninguna actividad tiene fechas: sin fechas no hay
 * escala que pintar, y el llamador muestra el vacío en vez de inventar un
 * rango.
 */
export function construirEscala(
  rangos: readonly RangoFecha[],
  fechaCorte?: string | null,
): Escala | null {
  const limites: number[] = [];
  for (const rango of rangos) {
    const desde = aDia(rango.inicio);
    const hasta = aDia(rango.fin);
    if (desde !== null) limites.push(desde);
    if (hasta !== null) limites.push(hasta);
  }
  const diaCorte = aDia(fechaCorte);
  if (diaCorte !== null) limites.push(diaCorte);

  if (limites.length === 0) return null;

  // `reduce` en vez de `Math.min(...)`: el spread pasa un argumento por
  // elemento y revienta la pila con listas grandes (§12.9).
  const minimo = limites.reduce((a, b) => (b < a ? b : a), limites[0] ?? 0);
  const maximo = limites.reduce((a, b) => (b > a ? b : a), limites[0] ?? 0);

  const diaInicio = lunesDe(minimo);
  // +1 porque el día de fin se pinta completo: el lienzo lo tiene que incluir.
  const diasCrudos = maximo - diaInicio + 1;
  const nSemanas = Math.max(SEMANAS_MINIMAS, Math.ceil(diasCrudos / 7));
  const dias = nSemanas * 7;

  const semanas: SemanaEscala[] = [];
  for (let i = 0; i < nSemanas; i += 1) {
    const inicioSemana = diaInicio + i * 7;
    semanas.push({
      inicio: aIso(inicioSemana),
      etiqueta: etiquetaCorta(inicioSemana),
      esCorte:
        diaCorte !== null && diaCorte >= inicioSemana && diaCorte < inicioSemana + 7,
    });
  }

  return {
    diaInicio,
    dias,
    semanas,
    anchoMinimo: ANCHO_ETIQUETAS + ANCHO_SEMANA * nSemanas,
  };
}

function etiquetaCorta(dia: number): string {
  const fecha = new Date(dia * MS_DIA);
  const numero = String(fecha.getUTCDate()).padStart(2, '0');
  return `${numero} ${MESES[fecha.getUTCMonth()] ?? ''}`;
}

export interface Tramo {
  /** Porcentaje del lienzo donde empieza el tramo. */
  readonly izquierda: number;
  /** Porcentaje del lienzo que ocupa. */
  readonly ancho: number;
}

/** Ancho mínimo de una barra, en % del lienzo: media jornada se sigue viendo. */
const ANCHO_MINIMO_PCT = 0.4;

/**
 * Tramo de una barra entre dos fechas **inclusive**: una actividad que
 * empieza y termina el mismo día ocupa ese día completo, no cero.
 *
 * Devuelve `null` si falta alguna fecha o si el tramo cae fuera del lienzo.
 */
export function tramoDeBarra(
  escala: Escala,
  inicio: string | null,
  fin: string | null,
): Tramo | null {
  const diaIni = aDia(inicio);
  const diaFin = aDia(fin);
  if (diaIni === null || diaFin === null) return null;

  const desde = Math.max(0, diaIni - escala.diaInicio);
  const hasta = Math.min(escala.dias, Math.max(diaIni, diaFin) - escala.diaInicio + 1);
  if (hasta <= desde) return null;

  return {
    izquierda: (desde / escala.dias) * 100,
    ancho: Math.max(ANCHO_MINIMO_PCT, ((hasta - desde) / escala.dias) * 100),
  };
}

/**
 * Tramo de la **holgura** que sigue a una barra: arranca al día siguiente del
 * fin y dura tantos días como reportó el motor (§6). Es la representación
 * clásica de la flotación; el número lo da el backend, aquí solo se convierte
 * a ancho.
 */
export function tramoDeHolgura(
  escala: Escala,
  fin: string | null,
  holguraDias: number | null,
): Tramo | null {
  if (holguraDias === null || holguraDias <= 0) return null;
  const diaFin = aDia(fin);
  if (diaFin === null) return null;

  const desde = diaFin - escala.diaInicio + 1;
  const hasta = Math.min(escala.dias, desde + holguraDias);
  if (hasta <= desde || desde >= escala.dias) return null;

  return {
    izquierda: (Math.max(0, desde) / escala.dias) * 100,
    ancho: ((hasta - Math.max(0, desde)) / escala.dias) * 100,
  };
}

/**
 * Posición de una fecha suelta (la de corte) en % del lienzo, o `null` si cae
 * fuera. Se ancla al **inicio** del día, no a su centro.
 */
export function posicionDeFecha(escala: Escala, fecha: string | null): number | null {
  const dia = aDia(fecha);
  if (dia === null) return null;
  const desplazamiento = dia - escala.diaInicio;
  if (desplazamiento < 0 || desplazamiento > escala.dias) return null;
  return (desplazamiento / escala.dias) * 100;
}
