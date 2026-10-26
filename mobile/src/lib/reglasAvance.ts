/**
 * Reglas de captura de avance — puerto a TypeScript de
 * `backend/src/obractrl/domain/avance/reglas.py` (§6, §11.1 única fuente de
 * verdad).
 *
 * Mismas fórmulas y mismos umbrales que el backend, para que la captura
 * offline del móvil y el endpoint web apliquen exactamente la misma regla
 * (§11.3, workflow B) — nada se inventa distinto aquí. Si una regla cambia,
 * cambia en `reglas.py` y aquí a la vez.
 *
 * Módulo puro: sin UI, sin PowerSync, sin red — 100% testeable (§12.11).
 * El backend usa `Decimal`; aquí se usa `number` porque no hay una
 * dependencia de aritmética decimal en el móvil (no está en
 * `mobile/package.json`) y esto solo valida para UX offline — el backend
 * sigue siendo la fuente autoritativa cuando el registro sincroniza.
 */

export const TOPE_SOBREPROGRAMA = 1.2;
/**
 * `cant_programada ≤ cant_base × 1.2` (§6). Valor fijo, no configurable vía
 * §8.7 — ver la nota extensa en `reglas.py` sobre por qué.
 */

export const UMBRAL_CASI_PCT = 90;
/** Umbral fijo del auto-estatus `casi` (§6). */

export type EstatusActividad =
  | 'programada'
  | 'en_proceso'
  | 'casi'
  | 'pendiente_cierre'
  | 'concluida'
  | 'retrasada'
  | 'extra_catalogo';

const ESTATUS_AUTOMATICOS: ReadonlySet<EstatusActividad> = new Set([
  'programada',
  'en_proceso',
  'casi',
]);

/**
 * Estatus que el motor de avance puede fijar solo (§6). Los de flujo
 * (`pendiente_cierre`, `concluida`, `retrasada`, `extra_catalogo`) los fija
 * el caso de uso correspondiente y el auto-estatus no los pisa.
 */
export function esAutomatico(estatus: EstatusActividad): boolean {
  return ESTATUS_AUTOMATICOS.has(estatus);
}

/** Violación de una regla de captura (§6). `campo` identifica qué input rechazar en la UI. */
export class ErrorDeCaptura extends Error {
  readonly campo: 'cant_programada' | 'cant_ejecutada';

  constructor(mensaje: string, campo: 'cant_programada' | 'cant_ejecutada') {
    super(mensaje);
    this.name = 'ErrorDeCaptura';
    this.campo = campo;
  }
}

/** `cant_programada ≤ cant_base × tope` (§6). */
export function validarProgramacion(
  cantProgramada: number,
  cantBase: number,
  tope: number = TOPE_SOBREPROGRAMA,
): void {
  if (cantProgramada < 0) {
    throw new ErrorDeCaptura('La cantidad programada no puede ser negativa.', 'cant_programada');
  }

  const maximo = cantBase * tope;
  if (cantProgramada > maximo) {
    throw new ErrorDeCaptura(
      `La cantidad programada (${cantProgramada}) excede el tope de ${Math.round(tope * 100)}% ` +
        `sobre la cantidad base (${cantBase}): máximo ${maximo}.`,
      'cant_programada',
    );
  }
}

/**
 * `cant_ejecutada ≥ 0`.
 *
 * **Ya no se compara con lo programado** (migración 0066): lo ejecutado de más
 * se registra —también sin señal, donde antes llegaba como un `conflicto` de
 * sincronización— y el excedente va a comprobación y validación de Control de
 * obra. Ver `excedenteDe`.
 */
export function validarEjecucion(cantEjecutada: number): void {
  if (cantEjecutada < 0) {
    throw new ErrorDeCaptura('La cantidad ejecutada no puede ser negativa.', 'cant_ejecutada');
  }
}

/**
 * Lo ejecutado por encima de lo programado que aún no se decidió:
 * `max(ejecutada − programada − perdida, 0)`. Derivado, nunca guardado.
 */
export function excedenteDe(
  cantEjecutada: number,
  cantProgramada: number,
  cantPerdida: number = 0,
): number {
  return Math.max(cantEjecutada - cantProgramada - cantPerdida, 0);
}

/** `avance_pct = cant_ejecutada / cant_base × 100` (§6). Con base cero el avance es 0. */
export function calcularAvance(cantEjecutada: number, cantBase: number): number {
  if (cantBase <= 0) return 0;
  const pct = (cantEjecutada / cantBase) * 100;
  return Math.round(Math.min(pct, 100) * 100) / 100;
}

/**
 * Auto-estatus: `≥ 90% → casi` · `> 0 → en_proceso` (§6). Nunca pisa un
 * estatus de flujo (`pendiente_cierre`, `concluida`, ...).
 */
export function resolverEstatus(
  avancePct: number,
  estatusActual: EstatusActividad,
  umbralCasi: number = UMBRAL_CASI_PCT,
): EstatusActividad {
  if (!esAutomatico(estatusActual)) return estatusActual;
  if (avancePct >= umbralCasi) return 'casi';
  if (avancePct > 0) return 'en_proceso';
  return 'programada';
}

export interface ResultadoCaptura {
  readonly cantBase: number;
  readonly cantProgramada: number;
  readonly cantEjecutada: number;
  readonly avancePct: number;
  readonly estatus: EstatusActividad;
  /** Lo ejecutado de más: va a comprobación y validación, no se rechaza. */
  readonly cantExcedente: number;
}

export interface ParametrosCaptura {
  readonly cantBase: number;
  readonly cantProgramada: number;
  readonly cantEjecutada: number;
  readonly estatusActual?: EstatusActividad;
  readonly tope?: number;
  readonly umbralCasi?: number;
}

/**
 * Valida y deriva una captura completa (§6). Entrada única del motor de
 * avance del lado móvil — la usa la pantalla de captura del Residente antes
 * de escribir a SQLite local (offline, §12.5).
 */
export function aplicarCaptura(params: ParametrosCaptura): ResultadoCaptura {
  const {
    cantBase,
    cantProgramada,
    cantEjecutada,
    estatusActual = 'programada',
    tope = TOPE_SOBREPROGRAMA,
    umbralCasi = UMBRAL_CASI_PCT,
  } = params;

  validarProgramacion(cantProgramada, cantBase, tope);
  validarEjecucion(cantEjecutada);

  const avancePct = calcularAvance(cantEjecutada, cantBase);
  const estatus = resolverEstatus(avancePct, estatusActual, umbralCasi);

  return {
    cantBase,
    cantProgramada,
    cantEjecutada,
    avancePct,
    estatus,
    cantExcedente: excedenteDe(cantEjecutada, cantProgramada),
  };
}
