/**
 * Las reglas de la bandeja de incidencias: KPIs, vencimiento, chips (§6, §7.8).
 *
 * Lo que fijan:
 *
 *  1. **"Activas" es una pregunta, no un estatus.** Las tres primeras etapas
 *     del flujo requieren acción; `cierre_solicitado` ya no —espera a
 *     Control— y por eso no cuenta ahí.
 *  2. **Los días de atraso se calculan, no se leen.** `dias_retraso` existe en
 *     la base pero nada la escribe: confiarla mostraría siempre cero. Se
 *     deriva de `fecha_limite` contra la fecha de hoy que recibe la función.
 *  3. **Vencida es de lo pendiente, no de lo histórico.** Una incidencia ya
 *     cerrada con la fecha límite en el pasado no está vencida: se resolvió,
 *     tarde o no.
 *  4. **Detiene-ahora exige que el flujo siga abierto.** Una `detiene` ya
 *     cerrada no sigue frenando nada, y contarla dejaría el KPI inflado para
 *     siempre.
 */

import { describe, expect, it } from 'vitest';

import {
  contarPorTipo,
  detieneAhora,
  diasDeAtraso,
  etiquetaDiasDeAtraso,
  incidenciaVencida,
  requiereAccion,
} from '@/incidencias/reglas';

const HOY = new Date(2026, 10, 21); // 21 nov 2026, fija para no depender del reloj real

describe('requiereAccion: la tarjeta «Activas»', () => {
  it('las tres primeras etapas del flujo requieren acción', () => {
    expect(requiereAccion('abierta')).toBe(true);
    expect(requiereAccion('programada')).toBe(true);
    expect(requiereAccion('en_atencion')).toBe(true);
  });

  it('cierre_solicitado ya no: espera a Control, no a que alguien la trabaje', () => {
    expect(requiereAccion('cierre_solicitado')).toBe(false);
  });

  it('lo cerrado tampoco', () => {
    expect(requiereAccion('cerrada')).toBe(false);
    expect(requiereAccion('rechazada')).toBe(false);
  });
});

describe('detieneAhora', () => {
  it('una incidencia que detiene y sigue abierta cuenta', () => {
    expect(detieneAhora('detiene', 'en_atencion')).toBe(true);
  });

  it('una que detiene pero ya se cerró, no', () => {
    // Ya no sigue frenando nada: contarla dejaría el KPI inflado para siempre.
    expect(detieneAhora('detiene', 'cerrada')).toBe(false);
  });

  it('un impacto que no detiene, nunca', () => {
    expect(detieneAhora('retraso', 'en_atencion')).toBe(false);
  });
});

describe('días de atraso: se calculan, no se leen', () => {
  it('sin fecha límite no hay nada que medir', () => {
    expect(diasDeAtraso(null, HOY)).toBeNull();
    expect(diasDeAtraso(undefined, HOY)).toBeNull();
  });

  it('una fecha límite pasada da días positivos', () => {
    expect(diasDeAtraso('2026-11-17', HOY)).toBe(4);
  });

  it('una fecha límite futura da un número negativo', () => {
    expect(diasDeAtraso('2026-11-30', HOY)).toBe(-9);
  });

  it('hoy mismo es cero', () => {
    expect(diasDeAtraso('2026-11-21', HOY)).toBe(0);
  });
});

describe('el rótulo de la columna DÍAS', () => {
  it('vencida se lee "+N d"', () => {
    expect(etiquetaDiasDeAtraso(4)).toBe('+4 d');
  });

  it('en plazo o justo a tiempo se lee "en plazo"', () => {
    expect(etiquetaDiasDeAtraso(-9)).toBe('en plazo');
    expect(etiquetaDiasDeAtraso(0)).toBe('en plazo');
  });

  it('sin fecha límite es un guión', () => {
    expect(etiquetaDiasDeAtraso(null)).toBe('—');
  });
});

describe('vencida: de lo pendiente, no de lo histórico', () => {
  it('pasada la fecha y todavía abierta, vencida', () => {
    expect(incidenciaVencida('2026-11-17', 'en_atencion', HOY)).toBe(true);
  });

  it('pasada la fecha pero ya cerrada, no vencida: se resolvió, tarde o no', () => {
    expect(incidenciaVencida('2026-11-17', 'cerrada', HOY)).toBe(false);
  });

  it('rechazada tampoco cuenta como vencida', () => {
    expect(incidenciaVencida('2026-11-17', 'rechazada', HOY)).toBe(false);
  });

  it('dentro de plazo, no vencida aunque siga abierta', () => {
    expect(incidenciaVencida('2026-11-30', 'abierta', HOY)).toBe(false);
  });
});

describe('los chips por tipo', () => {
  it('cuenta cada tipo y respeta el orden de primera aparición', () => {
    // No alfabético: si el orden saltara con cada filtro, quien mira los
    // chips perdería la referencia de cuál es el más frecuente.
    const conteo = contarPorTipo([
      { tipo: 'falta_material' },
      { tipo: 'error_ejecucion' },
      { tipo: 'falta_material' },
      { tipo: 'retrabajo' },
      { tipo: 'falta_material' },
    ]);
    expect(conteo.map((c) => c.tipo)).toEqual(['falta_material', 'error_ejecucion', 'retrabajo']);
    expect(conteo[0]).toMatchObject({ tipo: 'falta_material', cantidad: 3 });
  });

  it('una lista vacía no produce chips', () => {
    expect(contarPorTipo([])).toEqual([]);
  });
});
