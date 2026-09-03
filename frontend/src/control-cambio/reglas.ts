/**
 * Reflejo de UX de la bandeja de control de cambio (§4, §11.3, §6).
 *
 * Sin lógica de negocio: la decisión real la aplica el servidor y la garantiza
 * el CHECK `ck_control_cambio_autorizado_con_oc` (migración 0049). Esto solo
 * traduce estatus a color y expone qué puede hacer el rol actual, para que el
 * componente no adivine.
 */

import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

const TONO_ESTATUS_CAMBIO: Record<string, TonoBadge> = {
  solicitado: 'warn',
  autorizado: 'ok',
  rechazado: 'danger',
};

export function tonoEstatusCambio(estatus: string): TonoBadge {
  return TONO_ESTATUS_CAMBIO[estatus] ?? 'outline';
}

const ETIQUETA_TIPO_CAMBIO: Record<string, string> = {
  extra_catalogo: 'Más cantidad',
  fuera_catalogo: 'Fuera de catálogo',
  sustitucion: 'Sustitución',
  alta_catalogo: 'Alta de catálogo',
};

export function etiquetaTipoCambio(tipo: string): string {
  return ETIQUETA_TIPO_CAMBIO[tipo] ?? tipo;
}

/**
 * ¿Este rol resuelve controles de cambio? (§4)
 *
 * Ni el residente ni el supervisor: autorizar lo que uno mismo pidió
 * convierte el control en un trámite, y es la misma separación que el cierre
 * de actividad —`validar ≠ autorizar`—.
 */
export function puedeResolver(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}
