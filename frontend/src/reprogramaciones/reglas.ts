/**
 * Reflejo de UX de reprogramar lo contratado (migración 0072; D-533, P-4).
 *
 * «Las fechas contratadas no se mueven solas»: se **propone** la fecha nueva y una
 * cadena la acepta.
 *
 *     propone              revisa        valida           realiza
 *     Residente            Supervisor    Control de obra  Control de obra
 *     Supervisor           (se salta)    Control de obra  Control de obra
 *
 * No decide nada —las reglas y los permisos los impone el backend—: traduce el estado a
 * una etiqueta y dice qué acción le toca a cada rol, para no ofrecer un botón que el
 * servidor va a responder con 403/409.
 */

import type { ReprogramacionDeObraRespuesta } from '@/api/generado/modelo';
import type { TonoBadge } from '@/lib/tonos';
import type { Rol } from '@/shell/navegacion';

export type AccionDeReprogramacion = 'revisar' | 'validar' | 'aplicar' | 'rechazar';

/** Los roles que pueden proponer: quien vive la fecha en obra y quien la supervisa. */
export function puedeProponerReprogramacion(rol: Rol | null): boolean {
  return rol === 'residente' || rol === 'supervisor';
}

/** Qué le toca hacer a `rol` con una reprogramación en ese estatus. */
export function accionesDeReprogramacion(
  rol: Rol | null,
  estatus: string,
): readonly AccionDeReprogramacion[] {
  if (rol === 'supervisor' && estatus === 'propuesta') return ['revisar', 'rechazar'];
  if (rol === 'control_obra') {
    if (estatus === 'revisada') return ['validar', 'rechazar'];
    if (estatus === 'validada') return ['aplicar', 'rechazar'];
  }
  return [];
}

/** Sigue en la cadena: ocupa a la actividad y no admite otra propuesta. */
export function estaViva(estatus: string): boolean {
  return estatus === 'propuesta' || estatus === 'revisada' || estatus === 'validada';
}

const ETIQUETA: Readonly<Record<string, string>> = {
  propuesta: 'Propuesta',
  revisada: 'Revisada',
  validada: 'Validada',
  aplicada: 'Aplicada',
  rechazada: 'Rechazada',
};

export function etiquetaEstatusDeReprogramacion(estatus: string): string {
  return ETIQUETA[estatus] ?? estatus;
}

const TONO: Readonly<Record<string, TonoBadge>> = {
  propuesta: 'warn',
  revisada: 'info',
  validada: 'accent',
  aplicada: 'ok',
  rechazada: 'danger',
};

export function tonoEstatusDeReprogramacion(estatus: string): TonoBadge {
  return TONO[estatus] ?? 'outline';
}

/** Quién tiene que moverla ahora, en una frase. */
export function quienSigue(
  fila: Pick<ReprogramacionDeObraRespuesta, 'estatus'>,
): string | null {
  switch (fila.estatus) {
    case 'propuesta':
      return 'Espera la revisión del supervisor';
    case 'revisada':
      return 'Espera la validación de control de obra';
    case 'validada':
      return 'Espera que control de obra la realice';
    default:
      return null;
  }
}

/** El rechazo del `PATCH` de fechas de algo contratado (P-4): el camino es proponer. */
export function esFechaDeLoContratado(error: { readonly tipo?: string } | null): boolean {
  return error?.tipo?.endsWith('fechas-de-lo-contratado') === true;
}
