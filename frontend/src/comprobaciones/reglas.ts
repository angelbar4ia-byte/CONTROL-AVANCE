/**
 * Quién decide un excedente de ejecución (migración 0066).
 *
 * Espejo de UX de `domain.avance.comprobacion.puede_comprobar`: la frontera real
 * es el RBAC del backend (403). Decide quien autoriza un control de cambio:
 * Control de obra y el Super intendente (§4). No el residente, que lo originó al
 * ejecutarlo.
 */

import type { Rol } from '@/shell/navegacion';

export function puedeComprobar(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}
