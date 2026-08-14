/**
 * Reflejo de UX de las reglas de captura de avance (§6).
 *
 * Estas funciones **no son la autoridad**: solo dan retroalimentación visual
 * mientras el usuario escribe, para que no descubra la violación hasta que
 * el backend la rechace. La regla real vive en `domain.avance.reglas`
 * (backend) y se aplica en `PATCH /actividades/{id}/avance`, que responde
 * `problem+json` con `campo` cuando algo se viola (`ErrorApi` en
 * `api/cliente.ts`).
 */

export interface AdvertenciasAvance {
  /** `cant_programada` excede `cant_base × 1.2` (§6). */
  readonly cantProgramadaExcedeBase: boolean;
  /** `cant_ejecutada` excede `cant_programada` (§6). */
  readonly cantEjecutadaExcedeProgramada: boolean;
}

export function advertenciasAvance(params: {
  readonly cantBase: number | null;
  readonly cantProgramada: number | null;
  readonly cantEjecutada: number | null;
}): AdvertenciasAvance {
  const { cantBase, cantProgramada, cantEjecutada } = params;
  return {
    cantProgramadaExcedeBase:
      cantBase !== null && cantProgramada !== null && cantProgramada > cantBase * 1.2,
    cantEjecutadaExcedeProgramada:
      cantProgramada !== null && cantEjecutada !== null && cantEjecutada > cantProgramada,
  };
}

import type { TonoBadge } from '@/lib/tonos';

const TONO_ESTATUS_ACTIVIDAD: Record<string, TonoBadge> = {
  programada: 'outline',
  en_proceso: 'info',
  casi: 'warn',
  pendiente_cierre: 'accent',
  concluida: 'ok',
  retrasada: 'danger',
  extra_catalogo: 'outline',
};

/**
 * Tono visual del estatus de una actividad (`actividad.estatus`, §8.2).
 *
 * Es un mapeo de presentación, no una regla: el backend decide el estatus
 * (auto-estatus + transiciones de flujo, §6); aquí solo se traduce a color.
 */
export function tonoEstatusActividad(estatus: string): TonoBadge {
  return TONO_ESTATUS_ACTIVIDAD[estatus] ?? 'outline';
}
