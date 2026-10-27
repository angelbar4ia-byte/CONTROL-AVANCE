/**
 * Traducción entre el formulario de programación (todo `string`) y el DTO del
 * contrato (§11.2 `PATCH /actividades/{id}/programacion`; "DTOs en el borde"
 * — AGENTS.md).
 *
 * Puro y sin reglas: no valida que el fin sea posterior al inicio ni que las
 * dependencias no formen un ciclo. Eso lo decide el dominio y el endpoint
 * responde 422 sin escribir nada ("El cronograma tiene dependencias
 * circulares o la programación es inválida; nada se escribió", §6, §7.5).
 *
 * El contrato es explícito sobre el PATCH: *"Solo se cambia lo que llega. Una
 * lista vacía de `dependencias` **sí** es un cambio: deja la actividad sin
 * predecesoras"*. Por eso se manda un **diff** y no el objeto completo:
 * mandarlo entero borraría la diferencia entre "no lo toques" (`undefined`) y
 * "límpialo" (`null` / `[]`).
 */

import type { DependenciaDTO, ProgramacionActividadPeticion } from '@/api/generado/modelo';
import type { FilaGantt } from './filas';

export interface FormularioDependencia {
  readonly ref: string;
  readonly tipo: string;
  readonly lagDias: string;
}

export interface FormularioProgramacion {
  readonly fechaInicio: string;
  readonly fechaTermino: string;
  readonly duracionDias: string;
  readonly frenteId: string;
  readonly dependencias: readonly FormularioDependencia[];
}

/** Vuelca la fila del Gantt a los campos del formulario. */
export function formularioDeFila(fila: FilaGantt): FormularioProgramacion {
  return {
    fechaInicio: fila.inicio ?? '',
    fechaTermino: fila.fin ?? '',
    duracionDias: String(fila.duracionDias),
    frenteId: fila.frenteId ?? '',
    dependencias: fila.dependencias.map((dependencia) => ({
      ref: dependencia.ref,
      tipo: dependencia.tipo ?? 'FS',
      lagDias: String(dependencia.lag_dias ?? 0),
    })),
  };
}

function textoOpcional(valor: string): string | null {
  const limpio = valor.trim();
  return limpio === '' ? null : limpio;
}

function numeroOpcional(valor: string): number | null {
  const limpio = valor.trim();
  if (limpio === '') return null;
  const n = Number(limpio);
  return Number.isFinite(n) ? n : null;
}

/**
 * Dependencias del formulario en el shape del contrato. Los renglones sin
 * `ref` se descartan: son los que el usuario agregó y todavía no llenó.
 */
export function dependenciasDelFormulario(
  dependencias: readonly FormularioDependencia[],
): readonly DependenciaDTO[] {
  const limpias: DependenciaDTO[] = [];
  for (const dependencia of dependencias) {
    const ref = dependencia.ref.trim();
    if (ref === '') continue;
    limpias.push({
      ref,
      tipo: dependencia.tipo.trim() === '' ? 'FS' : dependencia.tipo.trim(),
      lag_dias: numeroOpcional(dependencia.lagDias) ?? 0,
    });
  }
  return limpias;
}

function mismasDependencias(
  actuales: readonly DependenciaDTO[],
  nuevas: readonly DependenciaDTO[],
): boolean {
  if (actuales.length !== nuevas.length) return false;
  return actuales.every((actual, indice) => {
    const nueva = nuevas[indice];
    if (!nueva) return false;
    return (
      actual.ref === nueva.ref &&
      (actual.tipo ?? 'FS') === (nueva.tipo ?? 'FS') &&
      (actual.lag_dias ?? 0) === (nueva.lag_dias ?? 0)
    );
  });
}

/** Solo los campos que cambiaron respecto a la actividad actual. */
export function cambiosDeProgramacion(
  fila: FilaGantt,
  formulario: FormularioProgramacion,
): ProgramacionActividadPeticion {
  const cambios: {
    -readonly [K in keyof ProgramacionActividadPeticion]: ProgramacionActividadPeticion[K];
  } = {};

  const fechaInicio = textoOpcional(formulario.fechaInicio);
  if (fechaInicio !== fila.inicio) cambios.fecha_inicio = fechaInicio;

  const fechaTermino = textoOpcional(formulario.fechaTermino);
  if (fechaTermino !== fila.fin) cambios.fecha_termino = fechaTermino;

  const duracion = numeroOpcional(formulario.duracionDias);
  if (duracion !== null && duracion !== fila.duracionDias) cambios.duracion_dias = duracion;

  const frenteId = textoOpcional(formulario.frenteId);
  if (frenteId !== fila.frenteId) cambios.frente_id = frenteId;

  const dependencias = dependenciasDelFormulario(formulario.dependencias);
  if (!mismasDependencias(fila.dependencias, dependencias)) {
    cambios.dependencias = [...dependencias];
  }

  return cambios;
}

/**
 * Lo que un rol de alcance `fechas` puede mandar: solo las fechas. El backend
 * rechaza con 403 una petición que traiga algo más, así que no se manda ni por
 * descuido (un campo que el formulario no mostró pero que difiere de la fila).
 */
export function soloFechas(
  cambios: ProgramacionActividadPeticion,
): ProgramacionActividadPeticion {
  const fechas: {
    -readonly [K in keyof ProgramacionActividadPeticion]: ProgramacionActividadPeticion[K];
  } = {};
  if ('fecha_inicio' in cambios) fechas.fecha_inicio = cambios.fecha_inicio;
  if ('fecha_termino' in cambios) fechas.fecha_termino = cambios.fecha_termino;
  return fechas;
}

export function hayCambios(cambios: ProgramacionActividadPeticion): boolean {
  return Object.keys(cambios).length > 0;
}

/**
 * Refs que no corresponden a ninguna actividad de la obra. El motor las
 * ignora al recalcular (§6, `refs_no_resueltas` en `POST
 * /obras/{id}/programa`), así que conviene avisar antes de guardar.
 */
export function refsDesconocidas(
  dependencias: readonly FormularioDependencia[],
  actividadesConocidas: ReadonlySet<string>,
): readonly string[] {
  const sueltas: string[] = [];
  for (const dependencia of dependencias) {
    const ref = dependencia.ref.trim();
    if (ref === '' || actividadesConocidas.has(ref) || sueltas.includes(ref)) continue;
    sueltas.push(ref);
  }
  return sueltas;
}

/**
 * Una actividad no puede depender de sí misma: sería un ciclo de largo 1 y el
 * backend responde 422 sin escribir (§6). Se detecta en el formulario para no
 * gastar el viaje.
 */
export function dependeDeSiMisma(
  actividadId: string,
  dependencias: readonly FormularioDependencia[],
): boolean {
  return dependencias.some((dependencia) => dependencia.ref.trim() === actividadId);
}
