/**
 * Reglas de UX de la pantalla de insumos programados (§7.3, §7.5, §4).
 *
 * **Aquí no se calcula nada de la tabla.** Las cantidades, el reparto por
 * periodo y la anticipación los resuelve el backend
 * (`domain/insumos/programado.py`) y esta pantalla los muestra. Si algún día
 * aparece aquí una multiplicación de cantidad por rendimiento, esa es la señal
 * de que la regla se duplicó — es el mismo criterio que `materiales/reglas.ts`.
 *
 * Lo que sí vive aquí es de presentación: qué modos de alcance ofrecerle a cada
 * rol, cómo se arma el rango de fechas y cómo se rotulan las cosas. Módulo puro
 * (§12.11): sin React y sin fetch, para poder fijarlo con pruebas.
 */

import type { Rol } from '@/shell/navegacion';

/** Sobre qué se pregunta "¿qué necesito?". */
export type ModoAlcance = 'obra' | 'residente' | 'supervisor' | 'todas' | 'prototipo';

/**
 * Los modos que un rol puede elegir (§4, cadena de mando de la 0042).
 *
 * Sigue el organigrama y no los permisos de lectura: el residente pregunta por
 * una obra suya o por todas las suyas; el supervisor puede además agrupar por
 * residente; Control y el Super intendente, por supervisor. Nadie ve de más
 * por elegir un modo — RLS acota igual—, así que lo que esta lista evita es
 * ofrecer un filtro que siempre saldría vacío.
 *
 * `prototipo` es la simulación y la ven los cuatro: preguntar "¿qué lleva una
 * casa de este modelo?" no depende de tener obras asignadas.
 */
export function modosDeAlcance(rol: Rol): readonly ModoAlcance[] {
  if (rol === 'residente') return ['obra', 'todas', 'prototipo'];
  if (rol === 'supervisor') return ['obra', 'residente', 'todas', 'prototipo'];
  return ['obra', 'residente', 'supervisor', 'todas', 'prototipo'];
}

const ETIQUETA_MODO: Record<ModoAlcance, string> = {
  obra: 'Una obra',
  residente: 'Por residente',
  supervisor: 'Por supervisor',
  todas: 'Todas mis obras',
  prototipo: 'Simular un prototipo',
};

export function etiquetaModo(modo: ModoAlcance): string {
  return ETIQUETA_MODO[modo];
}

/** ¿Este rol ve importes? Espejo de `_VE_DINERO` en el endpoint (§4). */
export function veImportes(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}

export type Granularidad = 'semana' | 'mes';

export interface RangoConsultado {
  readonly desde: string;
  readonly hasta: string;
}

/**
 * El rango por default: de hoy hacia adelante.
 *
 * Se mira hacia el futuro porque la pregunta es qué **falta** por comprar, no
 * qué se gastó — para eso está el consumo del almacén (§7.7). Doce semanas es
 * lo que cabe en pantalla sin scroll horizontal incómodo y cubre el horizonte
 * con el que se cotiza; tres meses cuando se agrupa por mes.
 */
export function rangoPorDefecto(hoy: Date, granularidad: Granularidad): RangoConsultado {
  const dias = granularidad === 'mes' ? 180 : 84;
  const fin = new Date(hoy);
  fin.setDate(fin.getDate() + dias);
  return { desde: aIso(hoy), hasta: aIso(fin) };
}

/** `YYYY-MM-DD` en hora local, que es lo que el input de fecha usa. */
export function aIso(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0');
  const dia = String(fecha.getDate()).padStart(2, '0');
  return `${fecha.getFullYear()}-${mes}-${dia}`;
}

/** ¿El rango es utilizable? Uno al revés no da columnas, da un 422. */
export function rangoValido(rango: RangoConsultado): boolean {
  return rango.desde !== '' && rango.hasta !== '' && rango.desde <= rango.hasta;
}

export interface FiltroInsumos {
  readonly modo: ModoAlcance;
  readonly obraId: string;
  readonly residenteId: string;
  readonly supervisorId: string;
  readonly prototipoId: string;
  readonly nCasas: number;
  readonly tipos: readonly string[];
  readonly diasAnticipacion: number;
  readonly granularidad: Granularidad;
  readonly rango: RangoConsultado;
}

export function filtroInicial(rol: Rol, hoy: Date): FiltroInsumos {
  const modos = modosDeAlcance(rol);
  return {
    // Arranca en la simulación cuando es lo único con datos no se puede saber
    // desde aquí; el default es "una obra", que es la pregunta más común.
    modo: modos[0] ?? 'obra',
    obraId: '',
    residenteId: '',
    supervisorId: '',
    prototipoId: '',
    nCasas: 1,
    tipos: [],
    diasAnticipacion: 0,
    granularidad: 'semana',
    rango: rangoPorDefecto(hoy, 'semana'),
  };
}

/**
 * ¿Ya se puede consultar, o falta elegir algo?
 *
 * Un modo que necesita un id y no lo tiene no dispara la consulta: pedir
 * "todas las obras" sin querer, por no haber elegido todavía, traería una tabla
 * enorme que nadie pidió.
 */
export function listoParaConsultar(filtro: FiltroInsumos): boolean {
  if (!rangoValido(filtro.rango)) return false;
  if (filtro.modo === 'obra') return filtro.obraId !== '';
  if (filtro.modo === 'residente') return filtro.residenteId !== '';
  if (filtro.modo === 'supervisor') return filtro.supervisorId !== '';
  if (filtro.modo === 'prototipo') return filtro.prototipoId !== '' && filtro.nCasas >= 1;
  return true;
}

/**
 * Los parámetros de la consulta. Solo viaja lo que el modo elegido usa.
 *
 * Mandar `obra_id` y `residente_id` a la vez no es más específico: el endpoint
 * los aplica como filtros que se acumulan, y el resultado sería la
 * intersección — casi siempre vacía, y sin decir por qué.
 */
export function parametrosDeConsulta(filtro: FiltroInsumos): Record<string, unknown> {
  const base: Record<string, unknown> = {
    desde: filtro.rango.desde,
    hasta: filtro.rango.hasta,
    granularidad: filtro.granularidad,
  };
  if (filtro.diasAnticipacion > 0) base.dias_anticipacion = filtro.diasAnticipacion;
  if (filtro.tipos.length > 0) base.tipo = [...filtro.tipos];

  if (filtro.modo === 'obra') base.obra_id = filtro.obraId;
  if (filtro.modo === 'residente') base.residente_id = filtro.residenteId;
  if (filtro.modo === 'supervisor') base.supervisor_id = filtro.supervisorId;
  if (filtro.modo === 'prototipo') {
    base.prototipo_id = filtro.prototipoId;
    base.n_casas = filtro.nCasas;
  }
  return base;
}

const ETIQUETA_TIPO: Record<string, string> = {
  material: 'Material',
  mano_obra: 'Mano de obra',
  equipo: 'Equipo',
  herramienta: 'Herramienta',
};

/** Los cuatro del §8.2, en el orden en que se ofrecen. */
export const TIPOS_INSUMO: readonly string[] = [
  'material',
  'mano_obra',
  'equipo',
  'herramienta',
];

export function etiquetaTipo(tipo: string): string {
  return ETIQUETA_TIPO[tipo] ?? tipo;
}

/** Alterna un tipo en el filtro, sin mutar la lista recibida. */
export function alternarTipo(
  tipos: readonly string[],
  tipo: string,
): readonly string[] {
  return tipos.includes(tipo)
    ? tipos.filter((t) => t !== tipo)
    : [...tipos, tipo];
}
