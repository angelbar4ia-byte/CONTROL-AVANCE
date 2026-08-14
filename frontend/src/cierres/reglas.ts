/**
 * Reflejo de UX del flujo de cierre (§4, §6, §11.3 workflow C).
 *
 * `validar ≠ autorizar` (§4): el Supervisor **autoriza** (cierra la
 * actividad); Control de obra **valida y comenta** (habilita para
 * estimación). Este módulo no decide nada — solo traduce el estatus a un
 * tono visual y expone qué acción le toca a cada rol, para que el
 * componente no mezcle los dos botones en un solo "aprobar".
 */

import type { Rol } from '@/shell/navegacion';
import type { EstatusSolicitudCierre } from '@/api/generado/modelo';
import type { TonoBadge } from '@/lib/tonos';

const TONO_ESTATUS_CIERRE: Record<string, TonoBadge> = {
  solicitada: 'warn',
  autorizada: 'info',
  validada: 'ok',
  rechazada: 'danger',
};

export function tonoEstatusCierre(estatus: string): TonoBadge {
  return TONO_ESTATUS_CIERRE[estatus] ?? 'outline';
}

/**
 * Acción disponible para el rol actual sobre una solicitud, según su
 * estatus. `null` si a este rol no le toca actuar sobre esta fila (§4).
 */
export type AccionCierre = 'autorizar' | 'validar' | 'rechazar' | null;

export function accionesDisponibles(
  rol: Rol,
  estatus: EstatusSolicitudCierre | string,
): readonly AccionCierre[] {
  if (rol === 'supervisor' && estatus === 'solicitada') {
    return ['autorizar', 'rechazar'];
  }
  if (rol === 'control_obra' && estatus === 'autorizada') {
    return ['validar', 'rechazar'];
  }
  return [];
}
