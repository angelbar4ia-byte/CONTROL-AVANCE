/**
 * Reglas de UX de la planeación por obra (§8.3, §7.6, §4).
 *
 * **Aquí no se calculan cuadrillas.** La división —jornadas entre días
 * hábiles— vive en `domain/planeacion/cuadrillas.py` y esta pantalla la
 * muestra. Si algún día aparece aquí una división entre `dias_habiles`, esa es
 * la señal de que la regla se duplicó: es el mismo criterio que
 * `insumos/reglas.ts`.
 *
 * Lo que sí vive aquí es de presentación: cómo se rotula un frente que todavía
 * no tiene contratista, cuándo la sugerencia y la decisión no coinciden, y qué
 * se ofrece a cada rol. Módulo puro (§12.11): sin React y sin fetch.
 */

import type { Rol } from '@/shell/navegacion';

export {
  aIso,
  rangoPorDefecto,
  rangoValido,
  type Granularidad,
  type RangoConsultado,
} from '@/insumos/reglas';

/**
 * La clave del renglón que agrupa lo que no tiene frente.
 *
 * Espejo de `SIN_FRENTE` en `consultar_planeacion.py`. No se descarta: es
 * trabajo real que alguien tiene que hacer, y esconderlo haría que el total de
 * la obra no cuadrara con la suma de sus frentes.
 */
export const SIN_FRENTE = '';

/**
 * ¿Este renglón se puede contratar?
 *
 * El de "sin frente asignado" no: no hay a qué colgarle el trato. Lo que se
 * hace con él es ir a **Frentes de obra** y mapear sus etapas, y el renglón lo
 * dice en vez de ofrecer un botón que no guardaría nada.
 */
export function esContratable(frenteId: string): boolean {
  return frenteId !== SIN_FRENTE;
}

/** ¿Quién decide con qué gente se cumple la meta? (§4) */
export function puedePlanear(rol: Rol): boolean {
  return (
    rol === 'residente' ||
    rol === 'supervisor' ||
    rol === 'control_obra' ||
    rol === 'super_intendente'
  );
}

/**
 * Cómo se lee la diferencia entre lo que el cálculo pide y lo que se decidió.
 *
 * El pico es la cifra con la que se contrata: quien presta dos cuadrillas todo
 * el mes no resuelve la semana que pide cinco. Por eso se compara contra el
 * pico y no contra el promedio.
 *
 * `sin_decidir` no es una falta: es el estado normal antes de cotizar.
 */
export type Cobertura = 'sin_decidir' | 'corto' | 'suficiente';

export function cobertura(
  picoCuadrillas: number,
  cuadrillasPlan: number | null | undefined,
): Cobertura {
  if (cuadrillasPlan === null || cuadrillasPlan === undefined) return 'sin_decidir';
  return cuadrillasPlan < picoCuadrillas ? 'corto' : 'suficiente';
}

const CLASE_COBERTURA: Record<Cobertura, string> = {
  sin_decidir: 'badge badge--outline',
  corto: 'badge badge--warn',
  suficiente: 'badge badge--ok',
};

export function claseDeCobertura(estado: Cobertura): string {
  return CLASE_COBERTURA[estado];
}

/**
 * El texto del renglón, que es donde se lee la decisión.
 *
 * Dice cuántas faltan y no solo que faltan: "faltan 3" es accionable —son tres
 * cuadrillas que hay que conseguir— y "insuficiente" obliga a restar a mano.
 */
export function textoDeCobertura(
  picoCuadrillas: number,
  cuadrillasPlan: number | null | undefined,
): string {
  const estado = cobertura(picoCuadrillas, cuadrillasPlan);
  if (estado === 'sin_decidir') return 'Sin decidir';
  if (estado === 'suficiente') return 'Alcanza';
  const faltan = Math.ceil(picoCuadrillas - (cuadrillasPlan ?? 0));
  return `Faltan ${faltan}`;
}

export interface FiltroPlaneacion {
  readonly obraId: string;
  readonly granularidad: 'semana' | 'mes';
  readonly rango: { readonly desde: string; readonly hasta: string };
}

/**
 * ¿Ya se puede consultar?
 *
 * La planeación es siempre **de una obra**: la pregunta "cuántas cuadrillas
 * necesito" no tiene respuesta agregada, porque el contratista de un frente
 * puede ser otro en la obra de al lado.
 */
export function listoParaConsultar(filtro: FiltroPlaneacion): boolean {
  return (
    filtro.obraId !== '' &&
    filtro.rango.desde !== '' &&
    filtro.rango.hasta !== '' &&
    filtro.rango.desde <= filtro.rango.hasta
  );
}

/** Lo que viaja al endpoint. */
export function parametrosDeConsulta(
  filtro: FiltroPlaneacion,
): Record<string, unknown> {
  return {
    desde: filtro.rango.desde,
    hasta: filtro.rango.hasta,
    granularidad: filtro.granularidad,
  };
}

/**
 * El total de jornadas de la obra en el rango, sumando todos los frentes.
 *
 * Se enseña al pie para que el renglón "sin frente" se pueda leer como
 * proporción: 2 245 de 4 975 jornadas sin mapear es un dato distinto a 2 245 de
 * 400 000.
 */
export function totalDeJornadas(
  frentes: readonly { readonly total_jornadas: number }[],
): number {
  return frentes.reduce((suma, f) => suma + f.total_jornadas, 0);
}
