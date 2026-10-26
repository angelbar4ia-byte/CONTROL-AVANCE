/**
 * Reflejo de UX del cierre de un frente (migración 0071; D-515/D-522): qué acción le
 * toca a cada rol y cómo se ve cada estado. La regla real la impone el backend.
 */

import { describe, expect, it } from 'vitest';

import {
  accionesDeFrente,
  etiquetaEstatusDeFrente,
  tonoEstatusDeFrente,
} from '@/cierresFrente/reglas';
import { navegacionDe, rutaPermitida, type Rol } from '@/shell/navegacion';

const ROLES: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];

function frente(avance: string, estatus: string | null = null) {
  return { avance_pct: avance, umbral_pct: '90', cierre_estatus: estatus };
}

describe('accionesDeFrente', () => {
  it('el residente solicita a partir del 90 % y solo si no hay un cierre vivo', () => {
    expect(accionesDeFrente('residente', frente('90'))).toEqual(['solicitar']);
    expect(accionesDeFrente('residente', frente('89.99'))).toEqual([]);
    for (const vivo of ['solicitado', 'aprobado', 'validado']) {
      expect(accionesDeFrente('residente', frente('95', vivo))).toEqual([]);
    }
    // Un rechazado no estorba: vuelve a solicitar cuando corrija.
    expect(accionesDeFrente('residente', frente('95', 'rechazado'))).toEqual(['solicitar']);
  });

  it('el supervisor aprueba o rechaza lo solicitado', () => {
    expect(accionesDeFrente('supervisor', frente('95', 'solicitado'))).toEqual(['aprobar', 'rechazar']);
    expect(accionesDeFrente('supervisor', frente('95', 'aprobado'))).toEqual([]);
    expect(accionesDeFrente('supervisor', frente('95'))).toEqual([]);
  });

  it('control de obra valida o rechaza lo aprobado, nunca lo que no se aprobó', () => {
    expect(accionesDeFrente('control_obra', frente('95', 'aprobado'))).toEqual(['validar', 'rechazar']);
    expect(accionesDeFrente('control_obra', frente('95', 'solicitado'))).toEqual([]);
  });

  it('el super intendente solo lee', () => {
    for (const estatus of [null, 'solicitado', 'aprobado', 'validado']) {
      expect(accionesDeFrente('super_intendente', frente('95', estatus))).toEqual([]);
    }
    expect(accionesDeFrente(null, frente('95'))).toEqual([]);
  });
});

describe('estados', () => {
  it('se traducen a etiqueta y tono', () => {
    expect(etiquetaEstatusDeFrente(null)).toBe('Abierto');
    expect(etiquetaEstatusDeFrente('validado')).toBe('Cerrado');
    expect(etiquetaEstatusDeFrente('solicitado')).toBe('Cierre solicitado');
    expect(tonoEstatusDeFrente('validado')).toBe('ok');
    expect(tonoEstatusDeFrente('rechazado')).toBe('danger');
    expect(tonoEstatusDeFrente(null)).toBe('outline');
  });
});

describe('navegación', () => {
  it('los cuatro roles llegan al cierre de frentes', () => {
    for (const rol of ROLES) {
      expect(rutaPermitida(rol, '/cierre-frentes')).toBe(true);
      expect(navegacionDe(rol).flatMap((s) => s.items.map((i) => i.a))).toContain('/cierre-frentes');
    }
  });
});
