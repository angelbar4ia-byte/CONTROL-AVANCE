/**
 * Reflejo en el front de la revisión física (§7.8, §11.2).
 *
 * Sin lógica de negocio: la escala de calidad y quién registra. Las reglas de
 * verdad viven en `domain/revisiones/reglas.py` y la base repite la escala como
 * `CHECK` (migración 0009).
 */

import type { Rol } from '@/shell/navegacion';

/** Espejo de `CALIDAD_MINIMA` / `CALIDAD_MAXIMA` del dominio (§7.8). */
export const CALIDAD_MINIMA = 1;
export const CALIDAD_MAXIMA = 5;

/**
 * ¿Este rol registra revisiones? (§11.2)
 *
 * Control de obra. El §11.2 marca la `(C)` sobre el alta; la bandeja la ve
 * quien vea la obra, y por eso esta pregunta solo gobierna el formulario.
 */
export function puedeRegistrarRevision(rol: Rol): boolean {
  return rol === 'control_obra';
}

/**
 * Qué significa cada número de la escala.
 *
 * Un «3» sin etiqueta obliga a cada quien a inventarse la escala, y dos
 * personas calificando distinto la misma obra hacen que el promedio no
 * signifique nada.
 */
const ETIQUETA_CALIDAD: Record<number, string> = {
  1: 'Rehacer',
  2: 'Deficiente',
  3: 'Aceptable',
  4: 'Buena',
  5: 'Excelente',
};

export function etiquetaCalidad(calidad: number): string {
  return ETIQUETA_CALIDAD[calidad] ?? String(calidad);
}

export function tonoCalidad(calidad: number): string {
  if (calidad <= 2) return 'danger';
  if (calidad === 3) return 'warn';
  return 'ok';
}
