/**
 * Reflejo de UX del bloque "Programación · CPM" (§6, §7.5, §7.6, §11.2).
 *
 * Este módulo **no decide nada y no calcula nada del CPM**. La ruta crítica,
 * la holgura y el desfase los calcula el motor del backend
 * (`domain/programacion/cpm.py`) y llegan ya resueltos por actividad
 * (`es_critica`, `holgura`, `desfase`, fechas). Aquí solo se traduce el
 * contrato a presentación: qué color lleva una barra, qué etiqueta lleva un
 * tipo de dependencia y qué botón tiene sentido ofrecerle a cada rol para no
 * provocar un 403 evitable. El permiso real lo impone el RBAC del backend
 * (`exigir_rol` en `adapters/api/v1/programacion.py`) y el alcance real lo
 * impone RLS (§12.4).
 *
 * El contrato (§11.2, bloque "Programación · CPM") reparte así:
 *   - `GET/POST /programas-base` · `GET /programas-base/{id}/items` → **C**
 *   - `GET /obras/{id}/programa` · `POST /obras/{id}/programa` → **C, S**
 *   - `GET /obras/{id}/ruta-critica` → **todos**, cada uno con su alcance
 *     (el Residente ve la de su obra porque RLS no le deja ver otra)
 *   - `POST /obras/{id}/ruta-critica/recalcular` → **S, C**
 *   - `PATCH /actividades/{id}/programacion` → **S, C**
 */

import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

/**
 * ¿Este rol administra los programas base de duraciones? — todo el bloque
 * `/programas-base` es de Control de obra (§11.2), y su sidebar lo trae en
 * Configuración → "Programas base" (§5.1).
 */
export function puedeAdministrarProgramasBase(rol: Rol): boolean {
  return rol === 'control_obra';
}

/**
 * ¿Este rol puede leer el cronograma completo? — `GET /obras/{id}/programa`
 * es (C, S) (§11.2).
 *
 * Consecuencia para la UI: Residente y Super intendente **no** pueden pedir
 * el programa; su Gantt se dibuja con `GET /obras/{id}/ruta-critica`, que sí
 * es de todos los roles y trae las mismas actividades con sus fechas
 * calculadas (ver `filas.ts`).
 */
export function puedeVerCronograma(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'supervisor';
}

/**
 * ¿Este rol ajusta el cronograma? — instanciar/versionar el programa,
 * recalcular la ruta y `PATCH /actividades/{id}/programacion` son (S, C)
 * (§11.2). Es el mismo trío de permisos, así que una sola función los cubre.
 */
export function puedeEditarProgramacion(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'supervisor';
}

/** Tono de la barra del Gantt (`.gantt__bar--*` del sistema de diseño). */
export type TonoBarra = 'critica' | 'retrasada' | 'concluida' | 'normal';

export interface EstadoBarra {
  readonly esCritica: boolean;
  readonly bloqueada: boolean;
  /** `desfase` que devolvió el motor, en días (§6). */
  readonly desfaseDias: number | null;
  /** `avance_pct` 0–100 tal como lo guarda la BD (§7.6). */
  readonly avancePct: number;
}

/**
 * Color de la barra de una actividad en el Gantt.
 *
 * Mapeo de presentación puro: los cuatro insumos —`es_critica`, `bloqueada`,
 * `desfase` y `avance_pct`— ya vienen resueltos del servidor. Aquí solo se
 * decide el orden en que se muestran cuando coinciden varios:
 *
 *   1. **crítica** manda sobre todo: es lo que la pantalla existe para
 *      resaltar (§11.2 "Web: Gantt con ruta crítica resaltada").
 *   2. **retrasada** — el motor reportó desfase, o la actividad quedó
 *      bloqueada por una incidencia `detiene` (§11.3 F.5).
 *   3. **concluida** — 100% de avance.
 *   4. el resto, neutro.
 */
export function tonoBarra(estado: EstadoBarra): TonoBarra {
  if (estado.esCritica) return 'critica';
  if (estado.bloqueada) return 'retrasada';
  if (estado.desfaseDias !== null && estado.desfaseDias > 0) return 'retrasada';
  if (estado.avancePct >= 100) return 'concluida';
  return 'normal';
}

const CLASE_BARRA: Record<TonoBarra, string> = {
  critica: 'gantt__bar--danger',
  retrasada: 'gantt__bar--warn',
  concluida: 'gantt__bar--done',
  normal: '',
};

/** Clase del sistema de diseño que corresponde al tono (DESIGN_SYSTEM.md §4). */
export function claseBarra(tono: TonoBarra): string {
  return CLASE_BARRA[tono];
}

const ETIQUETA_TONO: Record<TonoBarra, string> = {
  critica: 'En ruta crítica',
  retrasada: 'Con desfase',
  concluida: 'Concluida',
  normal: 'En programa',
};

/** Texto del tono, para que la barra no comunique solo por color (§12.10). */
export function etiquetaTono(tono: TonoBarra): string {
  return ETIQUETA_TONO[tono];
}

const TONO_BADGE: Record<TonoBarra, TonoBadge> = {
  critica: 'danger',
  retrasada: 'warn',
  concluida: 'ok',
  normal: 'outline',
};

export function tonoBadgeDeBarra(tono: TonoBarra): TonoBadge {
  return TONO_BADGE[tono];
}

const ETIQUETA_DEPENDENCIA: Record<string, string> = {
  FS: 'Fin → inicio',
  SS: 'Inicio → inicio',
};

/**
 * Etiqueta legible del tipo de dependencia. El contrato solo documenta `FS`
 * y `SS` (`DependenciaDTO.tipo`, §7.5); cualquier otro valor se muestra tal
 * cual en vez de inventarle nombre.
 */
export function etiquetaTipoDependencia(tipo: string | undefined): string {
  const clave = (tipo ?? 'FS').toUpperCase();
  return ETIQUETA_DEPENDENCIA[clave] ?? clave;
}

/** Tipos que el contrato documenta hoy para el select de dependencias (§7.5). */
export const TIPOS_DEPENDENCIA: readonly string[] = ['FS', 'SS'];

const ETIQUETA_ESTATUS_ACTIVIDAD: Record<string, string> = {
  programada: 'Programada',
  en_proceso: 'En proceso',
  casi: 'Casi',
  pendiente_cierre: 'Pendiente de cierre',
  concluida: 'Concluida',
  retrasada: 'Retrasada',
  extra_catalogo: 'Extra-catálogo',
};

/** Etiqueta legible de `actividad.estatus` (§8.2); el estatus lo fija el backend. */
export function etiquetaEstatusActividad(estatus: string): string {
  return ETIQUETA_ESTATUS_ACTIVIDAD[estatus] ?? estatus;
}
