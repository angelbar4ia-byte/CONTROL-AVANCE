/**
 * Reflejo de UX del control de materiales (§6, §7.7, §10.5, §11.2).
 *
 * Como los `reglas.ts` de las fases 1–3, esto **no es autoridad**: es un
 * espejo de presentación. El cruce consumo vs teórico lo resuelve la vista
 * `v_consumo_vs_presupuesto` en BD, la valuación y el IVA los decide el
 * backend (§10.5) y el permiso real lo imponen RBAC + RLS (§12.4). Aquí solo
 * se traduce lo que ya viene calculado a tono, etiqueta y "¿le ofrezco este
 * botón?".
 */

import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

/**
 * Umbral de desviación real vs teórico: **±5%** por defecto (§3.6).
 *
 * El spec lo declara configurable a tres niveles (global / familia-concepto /
 * insumo) y guarda el umbral usado en cada evaluación para trazabilidad; el
 * contrato actual no expone esa configuración, así que la UI pinta contra el
 * default y no pretende ser la fuente del umbral.
 */
export const UMBRAL_DESVIACION_PCT = 5;

/**
 * Tono de la desviación porcentual que **ya viene calculada** en la vista.
 *
 * `null` (sin teórico contra qué comparar) → neutro; dentro de ±5% → ok;
 * fuera → alerta (§3.6). No se recalcula el porcentaje: llega como string
 * decimal desde el backend.
 */
export function tonoDesviacion(desviacionPct: string | null): TonoBadge {
  if (desviacionPct === null || desviacionPct === '') return 'outline';
  const pct = Number(desviacionPct);
  if (!Number.isFinite(pct)) return 'outline';
  return Math.abs(pct) <= UMBRAL_DESVIACION_PCT ? 'ok' : 'danger';
}

/** ¿La desviación se salió del umbral del §3.6? Para ordenar y filtrar. */
export function fueraDeUmbral(desviacionPct: string | null): boolean {
  return tonoDesviacion(desviacionPct) === 'danger';
}

/**
 * Cuál de las tres reglas de valuación del §10.5 aplicó el backend a este
 * renglón, deducida de las cantidades que la vista ya devolvió:
 *
 *   1. `cruce` — está en la explosión del CPU **y** en las salidas → costo último.
 *   2. `solo_explosion` — esperado, sin salida → precio base del catálogo.
 *   3. `solo_almacen` — consumido, no esperado → costo último.
 *
 * Es una **etiqueta**, no un cálculo: el `costo_valuacion` de la respuesta ya
 * trae el precio que el backend eligió. Sirve para que quien lee la tabla
 * sepa por qué un renglón vale lo que vale.
 */
export type OrigenValuacion = 'cruce' | 'solo_explosion' | 'solo_almacen';

export function origenValuacion(cantTeorica: string, cantReal: string): OrigenValuacion {
  const teorica = Number(cantTeorica);
  const real = Number(cantReal);
  const hayTeorica = Number.isFinite(teorica) && teorica !== 0;
  const hayReal = Number.isFinite(real) && real !== 0;
  if (hayTeorica && hayReal) return 'cruce';
  return hayTeorica ? 'solo_explosion' : 'solo_almacen';
}

const ETIQUETA_ORIGEN: Record<OrigenValuacion, string> = {
  cruce: 'Cruce (costo último)',
  solo_explosion: 'Solo presupuesto (precio base)',
  solo_almacen: 'Solo almacén (costo último)',
};

export function etiquetaOrigenValuacion(origen: OrigenValuacion): string {
  return ETIQUETA_ORIGEN[origen];
}

/**
 * ¿Este rol registra salidas de almacén?
 *
 * `POST /obras/{id}/salidas` es **(C)** en §11.2; el Residente ve el control
 * de materiales en **lectura** (§4, §5.1). Ocultar el botón evita ofrecer una
 * acción que el servidor contestaría 403 — no sustituye al RBAC.
 */
export function puedeRegistrarSalida(rol: Rol): boolean {
  return rol === 'control_obra';
}

/** `GET /salidas` es (C, SI) en §11.2. */
export function puedeVerSalidas(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}

/** `GET /obras/{id}/materiales/consumo` es (R lectura, C, SI) en §11.2. */
export function puedeVerConsumo(rol: Rol): boolean {
  return rol !== 'supervisor';
}

/**
 * ¿El signo de la cantidad capturada concuerda con el signo del motivo?
 *
 * §10.5: *"El signo viene en el archivo (`Efecto Qty` / `Efecto Costo`); el
 * motivo solo clasifica el bucket"*. El backend responde **409** cuando no
 * coincide. Esto es solo el aviso previo para no gastar el viaje —igual que
 * `dependeDeSiMisma` en programación—: la UI **avisa**, no bloquea, porque la
 * autoridad sigue siendo el endpoint.
 */
export function signoCoincide(signoMotivo: number, cantidad: string): boolean {
  const n = Number(cantidad);
  if (!Number.isFinite(n) || n === 0) return true;
  return Math.sign(n) === Math.sign(signoMotivo);
}

/** Texto del signo de un motivo, para el hint del formulario (§10.5). */
export function etiquetaSigno(signo: number): string {
  return signo < 0 ? 'negativo (salida)' : 'positivo (entrada)';
}
