/**
 * Reglas de la pantalla de mejora de procesos (§7.9, §5.1).
 *
 * Módulo puro —sin React, sin red— por la misma razón que `revisiones/reglas.ts`:
 * es lo que se puede probar sin montar nada, y lo que no debe repetirse dentro
 * del JSX.
 *
 * Los cuatro estatus son los del backend
 * (`domain/shared/diccionario.py::EstatusProceso`). Aquí solo se les pone
 * etiqueta y tono; si alguien agrega uno allá y no aquí, `etiquetaEstatus`
 * devuelve el valor crudo en vez de mentir con una etiqueta ajena.
 */

import type { Rol } from '@/shell/navegacion';

/** §11.2: el alta y el cambio de etapa son del Super intendente. */
export function puedeEditarProcesos(rol: Rol): boolean {
  return rol === 'super_intendente';
}

export const ESTATUS_PROCESO = [
  'propuesto',
  'en_curso',
  'adoptado',
  'descartado',
] as const;

export type EstatusProceso = (typeof ESTATUS_PROCESO)[number];

const ETIQUETAS: Readonly<Record<string, string>> = {
  propuesto: 'Propuesto',
  en_curso: 'En curso',
  adoptado: 'Adoptado',
  descartado: 'Descartado',
};

export function etiquetaEstatus(valor: string): string {
  return ETIQUETAS[valor] ?? valor;
}

/**
 * Tono del badge. `descartado` es neutro y no `danger`: descartar un proceso
 * que se probó no es un error, es el resultado de haberlo probado — y pintarlo
 * en rojo desalienta justo lo que un tablero de mejora quiere provocar.
 */
export function tonoEstatus(valor: string): string {
  switch (valor) {
    case 'adoptado':
      return 'badge--ok';
    case 'en_curso':
      return 'badge--info';
    case 'descartado':
      return 'badge--outline';
    default:
      return 'badge--warn';
  }
}

/**
 * Orden del tablero: lo que está en movimiento arriba.
 *
 * `en_curso` primero porque es lo que alguien está probando ahora y necesita
 * seguimiento; `descartado` al final, que es archivo. Dentro de cada grupo el
 * orden lo pone el servidor (`updated_at desc`) y no se reordena aquí.
 */
export function ordenDeEstatus(valor: string): number {
  const orden: Readonly<Record<string, number>> = {
    en_curso: 0,
    propuesto: 1,
    adoptado: 2,
    descartado: 3,
  };
  return orden[valor] ?? 9;
}

export interface FormularioProceso {
  readonly nombre: string;
  readonly descripcion: string;
}

/**
 * Un proceso necesita nombre. La descripción es opcional en el contrato y la
 * pantalla no la exige: obligar a redactar el "por qué" antes de anotar la
 * idea es la forma más segura de que la idea no se anote.
 */
export function procesoCompleto(formulario: FormularioProceso): boolean {
  return formulario.nombre.trim().length > 0;
}
