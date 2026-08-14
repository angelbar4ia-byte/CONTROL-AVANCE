/**
 * Reflejo de UX del flujo de cierre (§4, §11.3 C) — `src/cierres/reglas.ts`.
 *
 * `validar ≠ autorizar` (§4): estas pruebas fijan que cada rol solo ve la
 * acción que le toca, para que un futuro cambio no vuelva a mezclar los dos
 * botones en un solo "aprobar".
 */

import { describe, expect, it } from 'vitest';

import { accionesDisponibles, tonoEstatusCierre } from '@/cierres/reglas';

describe('accionesDisponibles (§4: validar ≠ autorizar)', () => {
  it('el Supervisor autoriza o rechaza una solicitud "solicitada"', () => {
    const acciones = accionesDisponibles('supervisor', 'solicitada');
    expect(acciones).toContain('autorizar');
    expect(acciones).toContain('rechazar');
    expect(acciones).not.toContain('validar');
  });

  it('el Supervisor no actúa sobre una solicitud ya "autorizada"', () => {
    expect(accionesDisponibles('supervisor', 'autorizada')).toEqual([]);
  });

  it('Control de obra valida o rechaza una solicitud "autorizada"', () => {
    const acciones = accionesDisponibles('control_obra', 'autorizada');
    expect(acciones).toContain('validar');
    expect(acciones).toContain('rechazar');
    expect(acciones).not.toContain('autorizar');
  });

  it('Control de obra no actúa sobre una solicitud "solicitada" (no autoriza, §4)', () => {
    expect(accionesDisponibles('control_obra', 'solicitada')).toEqual([]);
  });

  it('nadie actúa sobre una solicitud ya "validada" o "rechazada"', () => {
    expect(accionesDisponibles('supervisor', 'validada')).toEqual([]);
    expect(accionesDisponibles('control_obra', 'rechazada')).toEqual([]);
  });

  it('el Residente y el Super intendente no accionan cierres', () => {
    expect(accionesDisponibles('residente', 'solicitada')).toEqual([]);
    expect(accionesDisponibles('super_intendente', 'autorizada')).toEqual([]);
  });
});

describe('tonoEstatusCierre (§8.2)', () => {
  it('mapea los 4 estatus canónicos a un tono', () => {
    expect(tonoEstatusCierre('solicitada')).toBe('warn');
    expect(tonoEstatusCierre('autorizada')).toBe('info');
    expect(tonoEstatusCierre('validada')).toBe('ok');
    expect(tonoEstatusCierre('rechazada')).toBe('danger');
  });
});
