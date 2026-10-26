/**
 * Reflejo de UX del estado por parte (migración 0075; D-571 a D-579): qué paso sigue y quién lo
 * da. La regla real la impone el backend.
 */

import { describe, expect, it } from 'vitest';

import {
  ESTADOS,
  accionSiguiente,
  estadosAnteriores,
  etiquetaDeDias,
  etiquetaDeEstado,
  puedeConfigurar,
  puedeAccion,
  tonoDeEstado,
} from '@/partes/reglas';
import { navegacionDe, rutaPermitida, type Rol } from '@/shell/navegacion';

const ROLES: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente', 'costos'];

describe('el camino de una parte', () => {
  it('cada estado tiene su paso siguiente, hasta asignar', () => {
    expect(ESTADOS.map(accionSiguiente)).toEqual([
      'enviar_a_presupuesto',
      'autorizar',
      'validar',
      'enviar_a_programa',
      'programar',
      'asignar',
      null,
    ]);
  });

  it('volver es libre hasta asignar y solo hacia atrás', () => {
    expect(estadosAnteriores('cuantificando')).toEqual([]);
    expect(estadosAnteriores('autorizada')).toEqual(['cuantificando', 'enviada_presupuesto', 'por_validar']);
    expect(estadosAnteriores('programada')).toHaveLength(5);
    expect(estadosAnteriores('asignada')).toEqual([]);
  });

  it('se traduce a etiqueta y tono', () => {
    expect(etiquetaDeEstado('enviada_programa')).toBe('En programa');
    expect(etiquetaDeEstado('raro')).toBe('raro');
    expect(tonoDeEstado('asignada')).toBe('ok');
    expect(tonoDeEstado('raro')).toBe('outline');
  });
});

describe('quién da cada paso', () => {
  it('control de obra da todos', () => {
    for (const a of ['enviar_a_presupuesto', 'autorizar', 'validar', 'enviar_a_programa', 'programar', 'asignar', 'devolver'] as const) {
      expect(puedeAccion('control_obra', a)).toBe(true);
    }
  });

  it('el supervisor solo programa; el residente y el super intendente, nada', () => {
    expect(puedeAccion('supervisor', 'programar')).toBe(true);
    expect(puedeAccion('supervisor', 'autorizar')).toBe(false);
    expect(puedeAccion('supervisor', 'asignar')).toBe(false);
    for (const rol of ['residente', 'super_intendente', null] as const) {
      expect(puedeAccion(rol, 'programar')).toBe(false);
    }
  });
});

describe('Costos', () => {
  it('manda a presupuesto y autoriza; no valida, no programa, no asigna, no devuelve', () => {
    expect(puedeAccion('costos', 'enviar_a_presupuesto')).toBe(true);
    expect(puedeAccion('costos', 'autorizar')).toBe(true);
    for (const a of ['validar', 'enviar_a_programa', 'programar', 'asignar', 'devolver'] as const) {
      expect(puedeAccion('costos', a)).toBe(false);
    }
  });
});

describe('navegación', () => {
  it('los cuatro roles llegan a las partes', () => {
    for (const rol of ROLES) {
      expect(rutaPermitida(rol, '/partes')).toBe(true);
      expect(navegacionDe(rol).flatMap((s) => s.items.map((i) => i.a))).toContain('/partes');
    }
  });
});

describe('alertas y configuración', () => {
  it('dice cuándo necesita el programa la parte', () => {
    expect(etiquetaDeDias(0)).toBe('hoy');
    expect(etiquetaDeDias(1)).toBe('mañana');
    expect(etiquetaDeDias(10)).toBe('en 10 días');
    expect(etiquetaDeDias(-1)).toBe('desde ayer');
    expect(etiquetaDeDias(-3)).toBe('hace 3 días');
  });

  it('el candado y los umbrales los edita Control (o la superintendencia)', () => {
    expect(puedeConfigurar('control_obra')).toBe(true);
    expect(puedeConfigurar('super_intendente')).toBe(true);
    for (const rol of ['residente', 'supervisor', 'costos', null] as const) {
      expect(puedeConfigurar(rol)).toBe(false);
    }
  });
});
