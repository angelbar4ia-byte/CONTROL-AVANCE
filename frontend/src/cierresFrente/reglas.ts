/**
 * Reflejo de UX del cierre de un frente (migración 0071; D-515/D-522/D-261).
 *
 * Un frente es un **nivel constructivo**. El residente solicita su cierre al 90 %
 * de avance, el supervisor aprueba y control de obra valida; rechaza el supervisor
 * o control. No decide nada —las reglas y los permisos los impone el backend—: solo
 * traduce el estado a una etiqueta y dice qué acción le toca a cada rol, para no
 * ofrecer un botón que el servidor va a responder con 403/409.
 */

import type { FrenteParaCierreRespuesta } from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

export type AccionDeFrente = 'solicitar' | 'aprobar' | 'validar' | 'rechazar';

/** El cierre «vivo» de un frente: el que impide solicitar otro. El rechazado no. */
function estaVivo(estatus: string | null | undefined): boolean {
  return estatus === 'solicitado' || estatus === 'aprobado' || estatus === 'validado';
}

export function accionesDeFrente(
  rol: Rol | null,
  frente: Pick<FrenteParaCierreRespuesta, 'avance_pct' | 'umbral_pct' | 'cierre_estatus'>,
): readonly AccionDeFrente[] {
  const estatus = frente.cierre_estatus ?? null;
  if (rol === 'residente') {
    return !estaVivo(estatus) && Number(frente.avance_pct) >= Number(frente.umbral_pct)
      ? ['solicitar']
      : [];
  }
  if (rol === 'supervisor' && estatus === 'solicitado') return ['aprobar', 'rechazar'];
  if (rol === 'control_obra' && estatus === 'aprobado') return ['validar', 'rechazar'];
  return [];
}

const ETIQUETA: Readonly<Record<string, string>> = {
  solicitado: 'Cierre solicitado',
  aprobado: 'Aprobado por supervisión',
  validado: 'Cerrado',
  rechazado: 'Rechazado',
};

export function etiquetaEstatusDeFrente(estatus: string | null | undefined): string {
  return estatus ? (ETIQUETA[estatus] ?? estatus) : 'Abierto';
}

const TONO: Readonly<Record<string, TonoBadge>> = {
  solicitado: 'warn',
  aprobado: 'info',
  validado: 'ok',
  rechazado: 'danger',
};

export function tonoEstatusDeFrente(estatus: string | null | undefined): TonoBadge {
  return estatus ? (TONO[estatus] ?? 'outline') : 'outline';
}
