/**
 * Cómo se lee una desviación en la pantalla (§5.1, §3.6).
 *
 * El cálculo lo hace el dominio (`domain/presupuesto/rendimiento.py`) y viaja
 * en la respuesta. Aquí solo se decide cómo se ve: qué palabra, qué color y
 * cómo se escribe un porcentaje que puede no existir.
 */

const ETIQUETA_CLASIFICACION: Record<string, string> = {
  sobre_costo: 'Sobre costo',
  bajo_costo: 'Bajo costo',
  no_ejecutado: 'Sin ejecutar',
  sin_presupuesto: 'Extra',
  dentro_de_rango: 'En rango',
};

export function etiquetaClasificacion(clasificacion: string): string {
  return ETIQUETA_CLASIFICACION[clasificacion] ?? clasificacion;
}

/**
 * El tono de cada clasificación.
 *
 * `no_ejecutado` va en `warn` y no en `ok`, aunque el importe sea negativo:
 * gastar de menos porque el trabajo no se hizo **no es un ahorro**, y pintarlo
 * de verde invitaría a leerlo como uno.
 *
 * `sin_presupuesto` va en `info` y no en `danger`: un extra autorizado es
 * trabajo legítimo (§11.2), no un error — lo que hay que ver es cuánto suma.
 */
const TONO_CLASIFICACION: Record<string, string> = {
  sobre_costo: 'danger',
  bajo_costo: 'warn',
  no_ejecutado: 'warn',
  sin_presupuesto: 'info',
  dentro_de_rango: 'neutral',
};

export function tonoClasificacion(clasificacion: string): string {
  return TONO_CLASIFICACION[clasificacion] ?? 'neutral';
}

/** ¿Merece que alguien la mire? Espejo de `Desviacion.relevante`. */
export function esRelevante(clasificacion: string): boolean {
  return clasificacion !== 'dentro_de_rango';
}

/**
 * El porcentaje, o por qué no hay.
 *
 * `null` no es «0 %»: es que no había presupuesto contra el cual comparar, y
 * escribir un cero ahí diría que el extra no se desvió de nada.
 */
export function textoPorcentaje(porcentaje: string | null | undefined): string {
  if (porcentaje === null || porcentaje === undefined) return 'sin base';
  const numero = Number(porcentaje);
  if (!Number.isFinite(numero)) return '—';
  const signo = numero > 0 ? '+' : '';
  return `${signo}${numero.toFixed(1)} %`;
}

/** Resumen de la cabecera de «Presupuesto de obras». */
export interface ResumenPresupuesto {
  readonly obras: number;
  readonly presupuestado: number;
  readonly ejecutado: number;
  readonly desviacion: number;
  readonly sobreCosto: number;
  readonly sinPresupuesto: number;
}

interface FilaComparable {
  readonly monto_presupuestado: string;
  readonly monto_ejecutado: string;
  readonly clasificacion: string;
}

export function resumirPresupuesto(
  filas: readonly FilaComparable[],
): ResumenPresupuesto {
  let presupuestado = 0;
  let ejecutado = 0;
  let sobreCosto = 0;
  let sinPresupuesto = 0;

  for (const fila of filas) {
    presupuestado += Number(fila.monto_presupuestado);
    ejecutado += Number(fila.monto_ejecutado);
    if (fila.clasificacion === 'sobre_costo') sobreCosto += 1;
    if (fila.clasificacion === 'sin_presupuesto') sinPresupuesto += 1;
  }

  return {
    obras: filas.length,
    presupuestado,
    ejecutado,
    // Se calcula sobre los totales, no sumando desviaciones: sumar
    // porcentajes no significa nada y sumar importes con signos opuestos ya lo
    // hace esta resta.
    desviacion: ejecutado - presupuestado,
    sobreCosto,
    sinPresupuesto,
  };
}
