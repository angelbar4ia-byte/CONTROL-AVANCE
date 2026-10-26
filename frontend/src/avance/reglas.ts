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
  /**
   * Lo ejecutado de más: `cant_ejecutada − cant_programada`, o 0. **No es un
   * error**: registrar nunca se bloquea y el excedente va a comprobación y
   * validación de Control de obra (migración 0066). Es solo un aviso de lo que
   * va a pasar al guardar.
   */
  readonly excedente: number;
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
    excedente:
      cantProgramada !== null && cantEjecutada !== null
        ? Math.max(cantEjecutada - cantProgramada, 0)
        : 0,
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

// --- El día del residente: agrupar y filtrar su obra (§7.4, §11.2) --------

import type { ActividadRespuesta } from '@/api/generado/modelo';

/**
 * Las vistas en que el residente parte su obra.
 *
 * No son estatus: son **preguntas**. "Qué traigo hoy" (activas), "qué puedo
 * cerrar" (listas), "qué se me atrasó". Un estatus suelto no contesta ninguna
 * —`casi` está tanto en activas como en listas— y obligar al residente a
 * traducir de estatus a pregunta es el trabajo que esta pantalla le quita.
 */
export type Vista =
  | 'todas'
  | 'activas'
  | 'listas'
  | 'concluidas'
  | 'retrasadas'
  | 'fuera_catalogo';

export const VISTAS: readonly { readonly clave: Vista; readonly etiqueta: string }[] = [
  { clave: 'todas', etiqueta: 'Todas' },
  { clave: 'activas', etiqueta: 'Activas' },
  { clave: 'listas', etiqueta: "Listas p/ cierre" },
  { clave: 'concluidas', etiqueta: 'Concluidas' },
  { clave: 'retrasadas', etiqueta: 'Retrasadas' },
  { clave: 'fuera_catalogo', etiqueta: 'Fuera de catálogo' },
];

/** ¿Esta actividad cae en esa vista? */
export function enVista(actividad: ActividadRespuesta, vista: Vista): boolean {
  switch (vista) {
    case 'todas':
      return true;
    case 'activas':
      // Lo que se está trabajando. `programada` no entra: todavía no arranca, y
      // meterla haría que "activas" fuera casi toda la obra el primer día.
      return actividad.estatus === 'en_proceso' || actividad.estatus === 'casi';
    case 'listas':
      // Al 100% pero sin cerrar, más lo que ya se solicitó. Es la lista de
      // "esto ya lo puedo cobrar".
      return (
        actividad.estatus === 'pendiente_cierre' ||
        (Number(actividad.avance_pct) >= 100 && actividad.estatus !== 'concluida')
      );
    case 'concluidas':
      return actividad.estatus === 'concluida';
    case 'retrasadas':
      // El estatus lo marca el backend; el desfase positivo lo dice el CPM. Se
      // aceptan los dos porque una actividad puede ir tarde sin que nadie haya
      // corrido la ruta crítica todavía.
      return actividad.estatus === 'retrasada' || Number(actividad.desfase ?? 0) > 0;
    case 'fuera_catalogo':
      return actividad.extra === true;
  }
}

export function contarPorVista(
  actividades: readonly ActividadRespuesta[],
): Record<Vista, number> {
  const cuenta = {} as Record<Vista, number>;
  for (const { clave } of VISTAS) {
    cuenta[clave] = actividades.filter((a) => enVista(a, clave)).length;
  }
  return cuenta;
}

/** Rótulo del frente, que es el nivel (§7.4). `null` = sin frente. */
export const SIN_FRENTE = '__sin_frente__';

export interface FrenteDelDia {
  readonly clave: string;
  readonly etiqueta: string;
  readonly actividades: number;
}

/**
 * Los frentes que la obra tiene hoy, en el orden en que llegan.
 *
 * Se derivan de las actividades y no del catálogo de niveles: un nivel que esta
 * obra no toca no es un filtro útil, es una opción que siempre sale vacía.
 */
export function frentesDe(
  actividades: readonly ActividadRespuesta[],
): readonly FrenteDelDia[] {
  const orden: string[] = [];
  const cuenta = new Map<string, { etiqueta: string; n: number }>();
  for (const actividad of actividades) {
    const clave = actividad.nivel_id ?? SIN_FRENTE;
    const etiqueta = actividad.nivel_descripcion ?? 'Sin frente';
    const previo = cuenta.get(clave);
    if (previo === undefined) {
      orden.push(clave);
      cuenta.set(clave, { etiqueta, n: 1 });
    } else {
      previo.n += 1;
    }
  }
  return orden.map((clave) => ({
    clave,
    etiqueta: cuenta.get(clave)!.etiqueta,
    actividades: cuenta.get(clave)!.n,
  }));
}

/**
 * Las actividades agrupadas por sub-frente (la etapa), en orden de llegada.
 *
 * El residente reprograma o captura **por sub-frente**: si se le atrasó la
 * albañilería de planta baja, mueve las tres actividades juntas. Sin el grupo,
 * eso son tres capturas iguales seguidas.
 */
export interface SubFrente {
  readonly clave: string;
  readonly etiqueta: string;
  readonly actividades: readonly ActividadRespuesta[];
}

export function porSubFrente(
  actividades: readonly ActividadRespuesta[],
): readonly SubFrente[] {
  const orden: string[] = [];
  const grupos = new Map<string, ActividadRespuesta[]>();
  const etiquetas = new Map<string, string>();
  for (const actividad of actividades) {
    const clave = actividad.etapa_id ?? '__sin_sub__';
    if (!grupos.has(clave)) {
      orden.push(clave);
      grupos.set(clave, []);
      etiquetas.set(clave, actividad.etapa_descripcion ?? 'Sin sub-frente');
    }
    grupos.get(clave)!.push(actividad);
  }
  return orden.map((clave) => ({
    clave,
    etiqueta: etiquetas.get(clave)!,
    actividades: grupos.get(clave)!,
  }));
}
