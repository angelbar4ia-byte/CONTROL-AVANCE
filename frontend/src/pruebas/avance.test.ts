/**
 * Reflejo de UX de captura de avance (§6) — `src/avance/reglas.ts`.
 *
 * Estas pruebas cubren solo la retroalimentación visual; la regla real la
 * aplica el backend (ver docstring del módulo).
 */

import { describe, expect, it } from 'vitest';

import {
  advertenciasAvance,
  etiquetaConfirmacion,
  puedeConfirmar,
  tonoConfirmacion,
  tonoEstatusActividad,
} from '@/avance/reglas';

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

describe('confirmar el avance antes de estimar (D-534)', () => {
  const conAvance = { cant_ejecutada: '60' };

  it('confirma solo el residente', () => {
    expect(puedeConfirmar('residente', conAvance, 'sin_confirmar')).toBe(true);
    for (const rol of ['supervisor', 'control_obra', 'super_intendente', null]) {
      expect(puedeConfirmar(rol, conAvance, 'sin_confirmar')).toBe(false);
    }
  });

  it('sin avance no hay nada que confirmar, y lo ya confirmado tal cual no se ofrece', () => {
    expect(puedeConfirmar('residente', { cant_ejecutada: '0' }, 'sin_confirmar')).toBe(false);
    expect(puedeConfirmar('residente', conAvance, 'confirmada')).toBe(false);
    // Si el avance cambió después de confirmar, hay que volver a confirmar.
    expect(puedeConfirmar('residente', conAvance, 'desactualizada')).toBe(true);
  });

  it('el estado se traduce a etiqueta y tono', () => {
    expect(etiquetaConfirmacion('confirmada')).toBe('confirmado');
    expect(etiquetaConfirmacion('desactualizada')).toBe('cambió tras confirmar');
    expect(etiquetaConfirmacion('sin_confirmar')).toBe('sin confirmar');
    expect(tonoConfirmacion('confirmada')).toBe('ok');
    expect(tonoConfirmacion('desactualizada')).toBe('warn');
    expect(tonoConfirmacion('sin_confirmar')).toBe('outline');
  });
});
