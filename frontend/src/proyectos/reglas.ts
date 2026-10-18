/**
 * Reflejo de UX del bloque "Proyecto · Obra" (§4, §5.1, §11.2, §11.3 A).
 *
 * Este módulo **no decide nada**: el alcance real lo impone RLS (§12.4) y el
 * permiso real lo impone el RBAC del backend (`exigir_rol` en
 * `adapters/api/v1/proyectos.py` y `obras.py`). Aquí solo se traduce el
 * contrato a presentación, para no ofrecer un botón que el servidor va a
 * responder con 403.
 *
 * El contrato (§11.2, bloque "Proyecto · Obra") reparte así:
 *   - `GET/POST /proyectos` · `/clusters` · `/prototipos` → **C, SI**
 *   - `POST /obras` · `PATCH /obras/{id}` · `/obras/bulk` ·
 *     `/obras/{id}/generar` → **solo C** (creador de obra, §5.1)
 *   - `GET /obras` · `GET /frentes` → todos, cada uno con su alcance (§4)
 */

import type { ObraRespuesta } from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

const TONO_ESTATUS_OBRA: Record<string, TonoBadge> = {
  pendiente: 'outline',
  iniciada: 'info',
  en_proceso: 'accent',
  por_entregar: 'warn',
  entregada: 'ok',
};

/**
 * Tono visual del estatus de una obra (`obra.estatus`, §8.2).
 *
 * Mapeo de presentación: el estatus lo deriva el avance y lo cierra el
 * cierre de obra final (§6, §11.3 D); aquí solo se traduce a color.
 */
export function tonoEstatusObra(estatus: string): TonoBadge {
  return TONO_ESTATUS_OBRA[estatus] ?? 'outline';
}

const ETIQUETA_ESTATUS_OBRA: Record<string, string> = {
  pendiente: 'Pendiente',
  iniciada: 'Iniciada',
  en_proceso: 'En proceso',
  por_entregar: 'Por entregar',
  entregada: 'Entregada',
};

/** Etiqueta legible del estatus canónico (§8.2). */
export function etiquetaEstatusObra(estatus: string): string {
  return ETIQUETA_ESTATUS_OBRA[estatus] ?? estatus;
}

/**
 * ¿Este rol configura la estructura de proyecto (proyecto · cluster ·
 * prototipo)? — `GET/POST /proyectos|/clusters|/prototipos` es (C, SI).
 *
 * Consecuencia para la UI: Residente y Supervisor **no pueden listar**
 * proyectos ni clusters, así que para ellos no hay árbol que pintar; ven la
 * lista plana de sus obras (`GET /obras`, que sí es de todos los roles).
 */
export function puedeConfigurarEstructura(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}

/**
 * ¿Este rol es el **creador de obra** (§5.1)? — alta, edición, alta masiva y
 * generación desde prototipo son exclusivas de Control de obra (§11.2).
 */
export function puedeAdministrarObras(rol: Rol): boolean {
  return rol === 'control_obra';
}

/**
 * Una obra `entregada` queda **congelada** (§11.3 D.3): el cierre de obra
 * final es el hito que la sella, así que ya no se edita ni se regenera.
 */
export function obraCongelada(obra: Pick<ObraRespuesta, 'estatus'>): boolean {
  return obra.estatus === 'entregada';
}

export function puedeEditarObra(rol: Rol, obra: Pick<ObraRespuesta, 'estatus'>): boolean {
  return puedeAdministrarObras(rol) && !obraCongelada(obra);
}

/**
 * Por qué **no** se puede correr el Workflow A sobre esta obra, o `null` si
 * sí se puede ofrecer el botón.
 *
 * - `rol` — generar es de Control de obra (§11.2).
 * - `sin_prototipo` — el workflow recorre el árbol del `PrototipoNodo`
 *   (§11.3 A.2); sin prototipo no hay árbol que recorrer. `prototipo_id` es
 *   obligatorio salvo en urbanización (§7.2).
 * - `congelada` — obra ya entregada (§11.3 D.3).
 *
 * Sigue siendo el backend quien acepta o rechaza; esto solo evita ofrecer
 * una acción que ya se sabe imposible.
 */
export type ImpedimentoGenerar = 'rol' | 'sin_prototipo' | 'congelada' | null;

export function impedimentoParaGenerar(
  rol: Rol,
  obra: Pick<ObraRespuesta, 'estatus' | 'prototipo_id'>,
): ImpedimentoGenerar {
  if (!puedeAdministrarObras(rol)) return 'rol';
  if (obraCongelada(obra)) return 'congelada';
  if (obra.prototipo_id === null) return 'sin_prototipo';
  return null;
}

const MOTIVO_IMPEDIMENTO: Record<Exclude<ImpedimentoGenerar, null>, string> = {
  rol: 'Solo Control de obra genera actividades desde el prototipo (§11.2).',
  sin_prototipo:
    'La obra no tiene prototipo: sin árbol de prototipo no hay actividades que generar (§11.3 A.2).',
  congelada: 'La obra ya fue entregada y quedó congelada por el cierre de obra final (§11.3 D).',
};

export function motivoImpedimento(impedimento: Exclude<ImpedimentoGenerar, null>): string {
  return MOTIVO_IMPEDIMENTO[impedimento];
}
