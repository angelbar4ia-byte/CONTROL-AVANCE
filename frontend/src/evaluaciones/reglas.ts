/**
 * Reflejo de UX de la evaluación en 3 niveles (§6, §7.8, §11.3 workflow H).
 *
 * **Espejo, no autoridad**: el contrato lo dice explícitamente para este
 * endpoint —*"el dominio valida el permiso del rol para ese nivel y, en
 * `nivel=auto`, que el sujeto sea el propio Residente o su propia obra"*—, y
 * responde 422 cuando no aplica. Aquí solo se traduce a etiquetas y a qué
 * nivel/sujeto se le ofrece a cada rol, para no plantar un botón que el
 * servidor va a rechazar.
 *
 * Workflow H (§11.3):
 *   1. `nivel=auto` — el **Residente** se evalúa a sí mismo y a su obra.
 *   2. `nivel=control` — **Control de obra** evalúa obra + residente + contratista.
 *   3. `nivel=final` — **Super intendente** consolida.
 */

import type { Rol } from '@/shell/navegacion';
import type { NivelEvaluacion, SujetoEvaluacion } from '@/api/generado/modelo';
import type { TonoBadge } from '@/lib/tonos';

const ETIQUETA_NIVEL: Record<string, string> = {
  auto: 'Autoevaluación',
  control: 'Control de obra',
  final: 'Final',
};

export function etiquetaNivel(nivel: string): string {
  return ETIQUETA_NIVEL[nivel] ?? nivel;
}

const DESCRIPCION_NIVEL: Record<string, string> = {
  auto: 'El Residente se evalúa a sí mismo y a su obra (§11.3 H.1).',
  control: 'Control de obra evalúa obra, residente y contratista (§11.3 H.2).',
  final: 'El Super intendente consolida (§11.3 H.3).',
};

export function descripcionNivel(nivel: string): string {
  return DESCRIPCION_NIVEL[nivel] ?? '';
}

const TONO_NIVEL: Record<string, TonoBadge> = {
  auto: 'outline',
  control: 'info',
  final: 'accent',
};

export function tonoNivel(nivel: string): TonoBadge {
  return TONO_NIVEL[nivel] ?? 'outline';
}

const ETIQUETA_SUJETO: Record<string, string> = {
  obra: 'Obra',
  residente: 'Residente',
  contratista: 'Contratista',
};

export function etiquetaSujeto(sujeto: string): string {
  return ETIQUETA_SUJETO[sujeto] ?? sujeto;
}

/**
 * Nivel que le corresponde a cada rol al **crear** una evaluación (§11.3 H).
 *
 * `null` para el Supervisor: el workflow H no le asigna nivel y su sidebar no
 * trae la entrada de Evaluaciones (§5.1). Puede seguir viendo la bandeja si
 * RLS se la devuelve, pero no se le ofrece el alta.
 */
export function nivelDelRol(rol: Rol): NivelEvaluacion | null {
  if (rol === 'residente') return 'auto';
  if (rol === 'control_obra') return 'control';
  if (rol === 'super_intendente') return 'final';
  return null;
}

export function puedeCrearEvaluacion(rol: Rol): boolean {
  return nivelDelRol(rol) !== null;
}

/**
 * Sujetos que admite cada nivel (§6 "Evaluaciones", §11.3 H).
 *
 * - `auto`: el Residente se evalúa **a sí mismo y a su obra** — no evalúa
 *   contratistas.
 * - `control`: obra, residente y contratista.
 * - `final`: consolida, así que admite los tres sujetos del §8.2.
 */
const SUJETOS_POR_NIVEL: Record<NivelEvaluacion, readonly SujetoEvaluacion[]> = {
  auto: ['obra', 'residente'],
  control: ['obra', 'residente', 'contratista'],
  final: ['obra', 'residente', 'contratista'],
};

export function sujetosDelNivel(nivel: NivelEvaluacion): readonly SujetoEvaluacion[] {
  return SUJETOS_POR_NIVEL[nivel];
}

/**
 * ¿Este rol puede responder los criterios de esta evaluación?
 *
 * §7.8, contrato de `POST /evaluaciones/{id}/respuestas`: *"solo quien creó
 * la evaluación puede responderla"*. Se compara contra el `evaluador_id` de
 * la respuesta; el 404/409 sigue siendo del backend.
 */
export function puedeResponder(usuarioId: string, evaluadorId: string): boolean {
  return usuarioId === evaluadorId;
}

/**
 * Tono del puntaje ya calculado por el backend. Llega como string decimal y
 * **no se recalcula**: la ponderación por peso de criterio es del dominio
 * (§7.8 `CriterioEvaluacion.peso`).
 */
export function tonoPuntaje(puntaje: string | null): TonoBadge {
  if (puntaje === null || puntaje === '') return 'outline';
  const n = Number(puntaje);
  if (!Number.isFinite(n)) return 'outline';
  if (n >= 90) return 'ok';
  if (n < 70) return 'danger';
  return 'warn';
}

/** ¿A la evaluación le faltan criterios por responder? */
export function criteriosPendientes(
  criterios: readonly { readonly id: string }[],
  respondidos: readonly { readonly criterio_id: string }[],
): readonly string[] {
  const yaEstan = new Set(respondidos.map((r) => r.criterio_id));
  return criterios.filter((c) => !yaEstan.has(c.id)).map((c) => c.id);
}
