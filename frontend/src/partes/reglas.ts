/**
 * Reflejo de UX del estado por parte (migración 0075; cerebro D-571 a D-579).
 *
 *     cuantificando → enviada a presupuesto → por validar → autorizada
 *                   → enviada a programa → programada → asignada
 *
 * No decide nada —las reglas y los permisos los impone el backend—: traduce el estado a una
 * etiqueta y dice qué paso sigue y quién lo da, para no ofrecer un botón que el servidor va a
 * responder con 403/409.
 */

import type { TonoBadge } from '@/lib/tonos';
import type { Rol } from '@/shell/navegacion';

export const ESTADOS = [
  'cuantificando',
  'enviada_presupuesto',
  'por_validar',
  'autorizada',
  'enviada_programa',
  'programada',
  'asignada',
] as const;
export type EstadoDeParte = (typeof ESTADOS)[number];

export type AccionDeParte =
  | 'enviar_a_presupuesto'
  | 'autorizar'
  | 'validar'
  | 'enviar_a_programa'
  | 'programar'
  | 'asignar'
  | 'devolver';

const ETIQUETA_ESTADO: Readonly<Record<string, string>> = {
  cuantificando: 'Cuantificando',
  enviada_presupuesto: 'En presupuesto',
  por_validar: 'Por validar',
  autorizada: 'Autorizada',
  enviada_programa: 'En programa',
  programada: 'Programada',
  asignada: 'Asignada',
};

export function etiquetaDeEstado(estado: string): string {
  return ETIQUETA_ESTADO[estado] ?? estado;
}

const TONO_ESTADO: Readonly<Record<string, TonoBadge>> = {
  cuantificando: 'outline',
  enviada_presupuesto: 'info',
  por_validar: 'warn',
  autorizada: 'accent',
  enviada_programa: 'info',
  programada: 'accent',
  asignada: 'ok',
};

export function tonoDeEstado(estado: string): TonoBadge {
  return TONO_ESTADO[estado] ?? 'outline';
}

export const ETIQUETA_ACCION: Readonly<Record<AccionDeParte, string>> = {
  enviar_a_presupuesto: 'Enviar a presupuesto',
  autorizar: 'Autorizar',
  validar: 'Validar',
  enviar_a_programa: 'Enviar a programar',
  programar: 'Programar',
  asignar: 'Asignar',
  devolver: 'Devolver',
};

const SIGUIENTE: Readonly<Record<string, AccionDeParte>> = {
  cuantificando: 'enviar_a_presupuesto',
  enviada_presupuesto: 'autorizar',
  por_validar: 'validar',
  autorizada: 'enviar_a_programa',
  enviada_programa: 'programar',
  programada: 'asignar',
};

/** El paso que sigue a una parte en ese estado; `null` si ya no tiene (asignada). */
export function accionSiguiente(estado: string): AccionDeParte | null {
  return SIGUIENTE[estado] ?? null;
}

/** Quién puede cada acción (espejo de `PERMISOS` del dominio). */
export function puedeAccion(rol: Rol | null, accion: AccionDeParte): boolean {
  if (rol === 'control_obra') return true;
  // Costos cuantifica y autoriza; Control valida al final (D-571).
  if (rol === 'costos') return accion === 'enviar_a_presupuesto' || accion === 'autorizar';
  return rol === 'supervisor' && accion === 'programar';
}

/** A qué pasos anteriores se puede volver. Una parte asignada ya no se devuelve. */
export function estadosAnteriores(estado: string): readonly EstadoDeParte[] {
  if (estado === 'asignada') return [];
  const i = ESTADOS.indexOf(estado as EstadoDeParte);
  return i <= 0 ? [] : ESTADOS.slice(0, i);
}

export function etiquetaDeTipoDeParte(tipo: string): string {
  return tipo === 'concepto' ? 'Concepto independiente' : tipo === 'etapa' ? 'Etapa' : 'Sin etapa';
}
