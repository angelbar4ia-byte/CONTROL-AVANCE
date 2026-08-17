/**
 * Reflejo de UX del flujo de incidencia (§6, §7.8, §11.3 workflow F).
 *
 * Como los `reglas.ts` de las fases 1–3: **espejo, no autoridad**. La máquina
 * de estados vive en el dominio y el endpoint responde 409 a una transición
 * no permitida; el permiso real lo imponen RBAC + RLS (§12.4). Aquí solo se
 * traduce a tono, etiqueta y "¿le ofrezco este botón a este rol?".
 *
 * Ciclo (§6): `abierta → programada → en_atencion → cierre_solicitado →
 * cerrada | rechazada`.
 */

import type { Rol } from '@/shell/navegacion';
import type { EstatusIncidencia, ImpactoIncidencia } from '@/api/generado/modelo';
import type { TonoBadge } from '@/lib/tonos';

const TONO_ESTATUS: Record<string, TonoBadge> = {
  abierta: 'warn',
  programada: 'info',
  en_atencion: 'accent',
  cierre_solicitado: 'warn',
  cerrada: 'ok',
  rechazada: 'danger',
};

export function tonoEstatusIncidencia(estatus: string): TonoBadge {
  return TONO_ESTATUS[estatus] ?? 'outline';
}

const ETIQUETA_ESTATUS: Record<string, string> = {
  abierta: 'Abierta',
  programada: 'Programada',
  en_atencion: 'En atención',
  cierre_solicitado: 'Cierre solicitado',
  cerrada: 'Cerrada',
  rechazada: 'Rechazada',
};

export function etiquetaEstatus(estatus: string): string {
  return ETIQUETA_ESTATUS[estatus] ?? estatus;
}

/** Tipos canónicos del §8.2 (`incidencia.tipo`). */
const ETIQUETA_TIPO: Record<string, string> = {
  falta_material: 'Falta de material',
  error_ejecucion: 'Error de ejecución',
  cambio_cliente: 'Cambio del cliente',
  proyecto_indef: 'Proyecto indefinido',
  retrabajo: 'Retrabajo',
  detalle: 'Detalle',
};

export function etiquetaTipo(tipo: string): string {
  return ETIQUETA_TIPO[tipo] ?? tipo;
}

/** Impactos canónicos del §8.2 y su efecto sobre el programa (§6). */
const ETIQUETA_IMPACTO: Record<string, string> = {
  detalle: 'Detalle',
  retraso: 'Retraso',
  detiene: 'Detiene',
};

export function etiquetaImpacto(impacto: string): string {
  return ETIQUETA_IMPACTO[impacto] ?? impacto;
}

const DESCRIPCION_IMPACTO: Record<string, string> = {
  detalle: 'No afecta el programa (§6).',
  retraso: 'Suma días al programa (§6).',
  detiene: 'Frena la obra: bloquea actividades y dispara el recálculo de la ruta crítica (§6, §11.3 F.5).',
};

export function descripcionImpacto(impacto: string): string {
  return DESCRIPCION_IMPACTO[impacto] ?? '';
}

const TONO_IMPACTO: Record<string, TonoBadge> = {
  detalle: 'outline',
  retraso: 'warn',
  detiene: 'danger',
};

export function tonoImpacto(impacto: string): TonoBadge {
  return TONO_IMPACTO[impacto] ?? 'outline';
}

/**
 * ¿Este impacto bloquea actividades?
 *
 * §6: *"Impacto: detalle (no afecta programa) · retraso (suma días) ·
 * detiene (frena la obra). Puede bloquear actividades"*, y §11.3 F.5: *"Si
 * `impacto=detiene` → evento bloquea actividades + recalcular CPM"*. El
 * contrato lo confirma en `AbrirIncidenciaPeticion.bloquea_actividades`:
 * *"Solo válido con impacto 'detiene' (§6)"*.
 */
export function detieneObra(impacto: ImpactoIncidencia | string): boolean {
  return impacto === 'detiene';
}

/**
 * Etapas del workflow F en orden, con la posición actual marcada.
 *
 * `cerrada` y `rechazada` son las dos salidas del flujo: `rechazada` no es un
 * paso más adelante en la escalera, así que se marca aparte.
 */
export interface EtapaFlujo {
  readonly estatus: EstatusIncidencia | string;
  readonly etiqueta: string;
  /** Ya se pasó por aquí (o se está aquí ahora). */
  readonly alcanzada: boolean;
  readonly actual: boolean;
}

const ESCALERA_F: readonly string[] = [
  'abierta',
  'programada',
  'en_atencion',
  'cierre_solicitado',
  'cerrada',
];

export function etapasFlujoF(estatusActual: string): readonly EtapaFlujo[] {
  // Una incidencia rechazada salió del flujo: nada por delante está alcanzado.
  const indiceActual = ESCALERA_F.indexOf(estatusActual);
  return ESCALERA_F.map((estatus, indice) => ({
    estatus,
    etiqueta: etiquetaEstatus(estatus),
    alcanzada: indiceActual >= 0 && indice <= indiceActual,
    actual: estatus === estatusActual,
  }));
}

/** ¿La incidencia salió del flujo por rechazo (§11.3 F.4)? */
export function estaRechazada(estatus: string): boolean {
  return estatus === 'rechazada';
}

/** ¿El flujo ya terminó y no admite más acciones? */
export function flujoCerrado(estatus: string): boolean {
  return estatus === 'cerrada' || estatus === 'rechazada';
}

/**
 * Acciones que le tocan a este rol sobre una incidencia en este estatus.
 *
 * Del §11.2 "Incidencias" y del §11.3 F:
 *   - `POST /incidencias` — **todos** (F.1).
 *   - `PATCH /incidencias/{id}` programar/asignar — **(S, C)** (F.2).
 *   - `POST /incidencias/{id}/eventos` — comentar o transicionar a
 *     `en_atencion` / `cierre_solicitado`; *"todos los que participan"* (F.3).
 *   - `POST /incidencias/{id}/cerrar` y `/rechazar` — **(S, C)** (F.4).
 */
export type AccionIncidencia = 'programar' | 'atender' | 'solicitar_cierre' | 'cerrar' | 'rechazar';

const PUEDE_RESOLVER: readonly Rol[] = ['supervisor', 'control_obra'];

export function accionesDisponiblesIncidencia(
  rol: Rol,
  estatus: string,
): readonly AccionIncidencia[] {
  if (flujoCerrado(estatus)) return [];

  const acciones: AccionIncidencia[] = [];
  const resuelve = PUEDE_RESOLVER.includes(rol);

  if (resuelve && estatus === 'abierta') acciones.push('programar');
  if (estatus === 'programada') acciones.push('atender');
  if (estatus === 'en_atencion') acciones.push('solicitar_cierre');
  if (resuelve && estatus === 'cierre_solicitado') acciones.push('cerrar');
  if (resuelve) acciones.push('rechazar');

  return acciones;
}

/**
 * El estatus al que lleva cada acción de evento (§11.3 F.3). El contrato lo
 * acota a `en_atencion` o `cierre_solicitado`.
 */
export const ESTATUS_DE_ACCION: Readonly<
  Record<'atender' | 'solicitar_cierre', EstatusIncidencia>
> = {
  atender: 'en_atencion',
  solicitar_cierre: 'cierre_solicitado',
};
