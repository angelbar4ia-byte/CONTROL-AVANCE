/**
 * Reflejo de UX de reprogramar lo contratado (migración 0072; D-533, P-4): qué acción le
 * toca a cada rol en cada paso de la cadena y cómo se ve cada estado. La regla real la
 * impone el backend.
 */

import { describe, expect, it } from 'vitest';

import {
  accionesDeReprogramacion,
  esFechaDeLoContratado,
  estaViva,
  etiquetaEstatusDeReprogramacion,
  puedeProponerReprogramacion,
  quienSigue,
  tonoEstatusDeReprogramacion,
} from '@/reprogramaciones/reglas';
import { navegacionDe, rutaPermitida, type Rol } from '@/shell/navegacion';

const ROLES: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];

describe('quién propone', () => {
  it('proponen el residente y el supervisor; control y super intendente no', () => {
    expect(puedeProponerReprogramacion('residente')).toBe(true);
    expect(puedeProponerReprogramacion('supervisor')).toBe(true);
    expect(puedeProponerReprogramacion('control_obra')).toBe(false);
    expect(puedeProponerReprogramacion('super_intendente')).toBe(false);
    expect(puedeProponerReprogramacion(null)).toBe(false);
  });
});

describe('accionesDeReprogramacion', () => {
  it('el supervisor revisa o rechaza solo lo recién propuesto', () => {
    expect(accionesDeReprogramacion('supervisor', 'propuesta')).toEqual(['revisar', 'rechazar']);
    for (const estatus of ['revisada', 'validada', 'aplicada', 'rechazada']) {
      expect(accionesDeReprogramacion('supervisor', estatus)).toEqual([]);
    }
  });

  it('control valida lo revisado y realiza lo validado, nunca salta un paso', () => {
    expect(accionesDeReprogramacion('control_obra', 'revisada')).toEqual(['validar', 'rechazar']);
    expect(accionesDeReprogramacion('control_obra', 'validada')).toEqual(['aplicar', 'rechazar']);
    // Lo que nadie revisó todavía no es de control.
    expect(accionesDeReprogramacion('control_obra', 'propuesta')).toEqual([]);
    for (const estatus of ['aplicada', 'rechazada']) {
      expect(accionesDeReprogramacion('control_obra', estatus)).toEqual([]);
    }
  });

  it('el residente y el super intendente no tienen paso en la cadena', () => {
    for (const estatus of ['propuesta', 'revisada', 'validada', 'aplicada', 'rechazada']) {
      expect(accionesDeReprogramacion('residente', estatus)).toEqual([]);
      expect(accionesDeReprogramacion('super_intendente', estatus)).toEqual([]);
      expect(accionesDeReprogramacion(null, estatus)).toEqual([]);
    }
  });
});

describe('estados', () => {
  it('se traducen a etiqueta, tono y quién sigue', () => {
    expect(etiquetaEstatusDeReprogramacion('aplicada')).toBe('Aplicada');
    expect(etiquetaEstatusDeReprogramacion('desconocido')).toBe('desconocido');
    expect(tonoEstatusDeReprogramacion('aplicada')).toBe('ok');
    expect(tonoEstatusDeReprogramacion('rechazada')).toBe('danger');
    expect(tonoEstatusDeReprogramacion('desconocido')).toBe('outline');
    expect(quienSigue({ estatus: 'propuesta' })).toMatch(/supervisor/);
    expect(quienSigue({ estatus: 'revisada' })).toMatch(/validación/);
    expect(quienSigue({ estatus: 'validada' })).toMatch(/realice|realiza/);
    expect(quienSigue({ estatus: 'aplicada' })).toBeNull();
  });

  it('estar viva es seguir en la cadena', () => {
    for (const vivo of ['propuesta', 'revisada', 'validada']) expect(estaViva(vivo)).toBe(true);
    for (const cerrado of ['aplicada', 'rechazada']) expect(estaViva(cerrado)).toBe(false);
  });
});

describe('el rechazo de las fechas de lo contratado', () => {
  it('se reconoce por el tipo del problema', () => {
    expect(
      esFechaDeLoContratado({ tipo: 'https://obractrl.mx/problemas/fechas-de-lo-contratado' }),
    ).toBe(true);
    expect(esFechaDeLoContratado({ tipo: 'https://obractrl.mx/problemas/ciclo-en-grafo' })).toBe(
      false,
    );
    expect(esFechaDeLoContratado({})).toBe(false);
    expect(esFechaDeLoContratado(null)).toBe(false);
  });
});

describe('navegación', () => {
  it('los cuatro roles llegan a las reprogramaciones', () => {
    for (const rol of ROLES) {
      expect(rutaPermitida(rol, '/reprogramaciones')).toBe(true);
      expect(navegacionDe(rol).flatMap((s) => s.items.map((i) => i.a))).toContain(
        '/reprogramaciones',
      );
    }
  });
});
