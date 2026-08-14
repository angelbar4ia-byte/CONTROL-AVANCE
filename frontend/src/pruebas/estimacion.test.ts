/**
 * Reflejo de UX del flujo de estimación (§4, §11.3 E) — `src/estimacion/reglas.ts`.
 */

import { describe, expect, it } from 'vitest';

import {
  accionesDisponiblesEstimacion,
  etiquetaModo,
  puedeGenerar,
  tonoEstatusEstimacion,
} from '@/estimacion/reglas';

describe('puedeGenerar (§11.3 E.1: R, S)', () => {
  it('Residente y Supervisor pueden generar', () => {
    expect(puedeGenerar('residente')).toBe(true);
    expect(puedeGenerar('supervisor')).toBe(true);
  });

  it('Control de obra y Super intendente no generan', () => {
    expect(puedeGenerar('control_obra')).toBe(false);
    expect(puedeGenerar('super_intendente')).toBe(false);
  });
});

describe('accionesDisponiblesEstimacion (§6: borrador → enviada → validada)', () => {
  it('Residente/Supervisor envían un borrador', () => {
    expect(accionesDisponiblesEstimacion('residente', 'borrador')).toEqual(['enviar']);
    expect(accionesDisponiblesEstimacion('supervisor', 'borrador')).toEqual(['enviar']);
  });

  it('Control de obra valida una enviada', () => {
    expect(accionesDisponiblesEstimacion('control_obra', 'enviada')).toEqual(['validar']);
  });

  it('Control de obra no envía, y R/S no validan (§4)', () => {
    expect(accionesDisponiblesEstimacion('control_obra', 'borrador')).toEqual([]);
    expect(accionesDisponiblesEstimacion('residente', 'enviada')).toEqual([]);
  });

  it('nadie actúa sobre una estimación ya validada', () => {
    expect(accionesDisponiblesEstimacion('control_obra', 'validada')).toEqual([]);
    expect(accionesDisponiblesEstimacion('residente', 'validada')).toEqual([]);
  });
});

describe('tonoEstatusEstimacion y etiquetaModo (§8.2)', () => {
  it('mapea los 3 estatus canónicos a un tono', () => {
    expect(tonoEstatusEstimacion('borrador')).toBe('outline');
    expect(tonoEstatusEstimacion('enviada')).toBe('info');
    expect(tonoEstatusEstimacion('validada')).toBe('ok');
  });

  it('etiqueta los 3 modos de pago', () => {
    expect(etiquetaModo('destajo')).toBe('Destajo');
    expect(etiquetaModo('concepto')).toBe('Concepto');
    expect(etiquetaModo('subcontrato')).toBe('Subcontrato');
  });
});
