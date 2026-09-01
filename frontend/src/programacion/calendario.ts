/**
 * Semana laboral o natural del cronograma (§7.5, §5.1).
 *
 * El backend guarda el **conjunto de días hábiles** (ISO: 1 = lunes … 7 =
 * domingo) y no un `tipo`, porque "laboral" no es lunes a viernes en este
 * giro: en obra en México lo normal es lunes a sábado, y hay frentes que
 * trabajan domingo. El `tipo` de `CalendarioRespuesta` viene **derivado** del
 * conjunto, así que la pantalla lo lee pero nunca lo manda.
 *
 * Este módulo es el espejo de esa equivalencia en el cliente: la usa el
 * interruptor de la barra de herramientas para no reimplementarla inline, y
 * se prueba sin render (§12.11, mismo patrón que `tramos.ts` / `ciclos.ts`).
 */

export type TipoSemana = 'natural' | 'laboral';

export const SEMANA_NATURAL: readonly number[] = [1, 2, 3, 4, 5, 6, 7];
/** Los siete días: ningún día se salta y la aritmética degenera en días
 * corridos, que es el comportamiento histórico del motor y el default. */

export const SEMANA_LABORAL: readonly number[] = [1, 2, 3, 4, 5, 6];
/** Lunes a sábado: la semana normal de obra en México, no lunes a viernes.
 * Es solo el valor que propone el interruptor — los días son configurables. */

const NOMBRE_CORTO: Record<number, string> = {
  1: 'L',
  2: 'M',
  3: 'M',
  4: 'J',
  5: 'V',
  6: 'S',
  7: 'D',
};

const NOMBRE_LARGO: Record<number, string> = {
  1: 'lunes',
  2: 'martes',
  3: 'miércoles',
  4: 'jueves',
  5: 'viernes',
  6: 'sábado',
  7: 'domingo',
};

/** Inicial del día para el selector. Lunes y martes comparten "M", igual que
 * en un calendario impreso; el `title` largo los desambigua. */
export function inicialDeDia(dia: number): string {
  return NOMBRE_CORTO[dia] ?? String(dia);
}

export function nombreDeDia(dia: number): string {
  return NOMBRE_LARGO[dia] ?? String(dia);
}

/**
 * La misma derivación que hace el backend: natural ⇔ se trabajan los siete
 * días. Se replica aquí —y no se lee el `tipo` de la respuesta— porque el
 * interruptor tiene que saber el tipo del borrador **antes** de guardarlo,
 * cuando todavía no hay respuesta del servidor.
 */
export function tipoDeSemana(diasHabiles: readonly number[]): TipoSemana {
  return diasHabiles.length === 7 ? 'natural' : 'laboral';
}

/** Días hábiles normalizados: ordenados, sin repetidos y sin valores fuera
 * del rango ISO. Un conjunto vacío no existe —un cronograma sin días de
 * trabajo no termina nunca (el backend lo rechaza)— y cae a semana natural. */
export function normalizarDias(dias: readonly number[] | null | undefined): readonly number[] {
  if (!dias) return SEMANA_NATURAL;
  const limpios = [...new Set(dias.filter((dia) => dia >= 1 && dia <= 7))].sort((a, b) => a - b);
  return limpios.length === 0 ? SEMANA_NATURAL : limpios;
}

/**
 * Alterna un día del conjunto. Quitar el último día hábil no se permite: el
 * backend lo rechaza y dejar construir el estado inválido solo para
 * reventar al guardar es peor que no dejar quitarlo.
 */
export function alternarDia(
  diasHabiles: readonly number[],
  dia: number,
): readonly number[] {
  if (diasHabiles.includes(dia)) {
    if (diasHabiles.length === 1) return diasHabiles;
    return diasHabiles.filter((d) => d !== dia);
  }
  return [...diasHabiles, dia].sort((a, b) => a - b);
}

/** Etiqueta legible del calendario, para la barra y el resumen de guardado. */
export function descripcionDeSemana(diasHabiles: readonly number[]): string {
  if (tipoDeSemana(diasHabiles) === 'natural') return 'Semana natural · los 7 días';
  return `Semana laboral · ${diasHabiles.map(inicialDeDia).join('')}`;
}

/** ¿Cambió respecto al calendario con el que se abrió? Compara conjuntos, no
 * referencias: es lo que decide si el borrador está sucio. */
export function mismosDias(a: readonly number[], b: readonly number[]): boolean {
  return a.length === b.length && a.every((dia, indice) => dia === b[indice]);
}
