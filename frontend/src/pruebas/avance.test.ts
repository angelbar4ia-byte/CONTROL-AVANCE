/**
 * Reflejo de UX de captura de avance (§6) — `src/avance/reglas.ts`.
 *
 * Estas pruebas cubren solo la retroalimentación visual; la regla real la
 * aplica el backend (ver docstring del módulo).
 */

import { describe, expect, it } from 'vitest';

import { advertenciasAvance, tonoEstatusActividad } from '@/avance/reglas';

describe('advertenciasAvance (§6, reflejo de UX)', () => {
  it('sin cant_base conocida, no advierte sobre el límite de programada', () => {
    const r = advertenciasAvance({ cantBase: null, cantProgramada: 1000, cantEjecutada: 10 });
    expect(r.cantProgramadaExcedeBase).toBe(false);
  });

  it('advierte cuando cant_programada excede cant_base × 1.2', () => {
    const r = advertenciasAvance({ cantBase: 100, cantProgramada: 121, cantEjecutada: 0 });
    expect(r.cantProgramadaExcedeBase).toBe(true);
  });

  it('no advierte cuando cant_programada está justo en el límite', () => {
    const r = advertenciasAvance({ cantBase: 100, cantProgramada: 120, cantEjecutada: 0 });
    expect(r.cantProgramadaExcedeBase).toBe(false);
  });

  it('lo ejecutado de más no es un error: se avisa cuánto va a comprobación', () => {
    const r = advertenciasAvance({ cantBase: null, cantProgramada: 50, cantEjecutada: 51 });
    expect(r.excedente).toBe(1);
  });

  it('sin excedente, el aviso dice cero', () => {
    expect(advertenciasAvance({ cantBase: null, cantProgramada: 50, cantEjecutada: 50 }).excedente).toBe(0);
    expect(advertenciasAvance({ cantBase: null, cantProgramada: 50, cantEjecutada: 10 }).excedente).toBe(0);
  });

  it('sin cant_programada capturada, no avisa de excedente', () => {
    const r = advertenciasAvance({ cantBase: null, cantProgramada: null, cantEjecutada: 999 });
    expect(r.excedente).toBe(0);
  });
});

describe('tonoEstatusActividad (§8.2)', () => {
  it('mapea los 7 estatus canónicos a un tono', () => {
    expect(tonoEstatusActividad('programada')).toBe('outline');
    expect(tonoEstatusActividad('en_proceso')).toBe('info');
    expect(tonoEstatusActividad('casi')).toBe('warn');
    expect(tonoEstatusActividad('pendiente_cierre')).toBe('accent');
    expect(tonoEstatusActividad('concluida')).toBe('ok');
    expect(tonoEstatusActividad('retrasada')).toBe('danger');
    expect(tonoEstatusActividad('extra_catalogo')).toBe('outline');
  });

  it('cae a "outline" ante un estatus desconocido, sin romper', () => {
    expect(tonoEstatusActividad('algo-inesperado')).toBe('outline');
  });
});
