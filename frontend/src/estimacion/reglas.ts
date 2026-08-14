/**
 * Reflejo de UX del flujo de estimación (§6, §11.3 workflow E).
 *
 * `borrador → enviada → validada`. Residente/Supervisor generan y envían;
 * Control de obra valida (§4). Este módulo solo traduce estatus/modo a
 * presentación — la transición real la decide el backend.
 */

import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

const TONO_ESTATUS_ESTIMACION: Record<string, TonoBadge> = {
  borrador: 'outline',
  enviada: 'info',
  validada: 'ok',
};

export function tonoEstatusEstimacion(estatus: string): TonoBadge {
  return TONO_ESTATUS_ESTIMACION[estatus] ?? 'outline';
}

const ETIQUETA_MODO: Record<string, string> = {
  destajo: 'Destajo',
  concepto: 'Concepto',
  subcontrato: 'Subcontrato',
};

export function etiquetaModo(modo: string): string {
  return ETIQUETA_MODO[modo] ?? modo;
}

export type AccionEstimacion = 'enviar' | 'validar' | null;

export function accionesDisponiblesEstimacion(
  rol: Rol,
  estatus: string,
): readonly AccionEstimacion[] {
  if ((rol === 'residente' || rol === 'supervisor') && estatus === 'borrador') {
    return ['enviar'];
  }
  if (rol === 'control_obra' && estatus === 'enviada') {
    return ['validar'];
  }
  return [];
}

/** ¿Este rol puede generar estimaciones (§11.3 E.1)? */
export function puedeGenerar(rol: Rol): boolean {
  return rol === 'residente' || rol === 'supervisor';
}
