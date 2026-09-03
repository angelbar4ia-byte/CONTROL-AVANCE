/**
 * El umbral desde la pantalla del residente (§6, §11.3).
 *
 * Estas funciones **no deciden**: la decisión es del servidor y del CHECK
 * `ck_actividad_programada_vs_base`. Aquí solo se avisa mientras el residente
 * mira su obra, para que no descubra que se le agotó el margen el día que
 * necesita la cantidad — porque para entonces hay gente parada esperando una
 * autorización que tarda.
 *
 * Lo que fijan:
 *
 *  1. **El techo sale de la tolerancia de la actividad**, no de un 20% fijo:
 *     el umbral es por obra desde la migración 0049.
 *  2. **Una cantidad ya autorizada manda sobre el margen.** Control firmó una
 *     cantidad concreta; el porcentaje deja de decidir.
 *  3. **Sin margen no es un error**, es la señal de que hay que pedir. Un error
 *     lo corrige el residente solo; esto necesita a Control.
 */

import { describe, expect, it } from 'vitest';

import type { ActividadRespuesta } from '@/api/generado/modelo';
import { margenDe, sinMargen, techoDe } from '@/extras/reglas';

function actividad(sobre: Partial<ActividadRespuesta> = {}): ActividadRespuesta {
  return {
    id: 'act-1',
    obra_id: 'obra-1',
    descripcion: 'Muro de tabique',
    cant_base: '100',
    cant_programada: '100',
    cant_ejecutada: '0',
    tolerancia_pct: '20',
    avance_pct: '0',
    estatus: 'en_proceso',
    bloqueada: false,
    extra: false,
    es_critica: false,
    duracion_dias: '1',
    modo_pago: 'destajo',
    precio_unitario: '0',
    precio_destajo: '150',
    ...sobre,
  } as ActividadRespuesta;
}

describe('el techo', () => {
  it('es la base más la tolerancia de la actividad', () => {
    expect(techoDe(actividad())).toBe(120);
  });

  it('usa la tolerancia de esa obra, no un 20% fijo', () => {
    // Desde la 0049 el umbral es por obra: una manzana de remodelación no
    // tolera lo mismo que una casa nueva.
    expect(techoDe(actividad({ tolerancia_pct: '5' }))).toBe(105);
  });

  it('una cantidad autorizada manda sobre el margen', () => {
    // Control firmó "súbele a 300": el 20% ya no decide.
    expect(techoDe(actividad({ cant_autorizada: '300' }))).toBe(300);
  });

  it('sin tolerancia en la respuesta cae al default del §6', () => {
    // Una respuesta vieja o un doble de prueba no deben dar techo cero, que
    // marcaría toda la obra como agotada.
    expect(techoDe(actividad({ tolerancia_pct: undefined }))).toBe(120);
  });
});

describe('el margen', () => {
  it('es lo que falta para el techo', () => {
    expect(margenDe(actividad({ cant_programada: '100' }))).toBe(20);
  });

  it('nunca es negativo', () => {
    // Una actividad autorizada y luego reducida podría quedar por encima; un
    // margen negativo se leería como "te sobran -5", que no dice nada.
    expect(margenDe(actividad({ cant_programada: '150', cant_autorizada: '120' }))).toBe(
      0,
    );
  });

  it('agotado es la señal de que hay que pedir, no un error', () => {
    expect(sinMargen(actividad({ cant_programada: '120' }))).toBe(true);
    expect(sinMargen(actividad({ cant_programada: '119' }))).toBe(false);
  });

  it('justo en el techo ya no queda margen', () => {
    // El §6 permite `≤`, así que 120 cabe — pero para pedir 121 hay que ir a
    // Control, y la pantalla lo tiene que decir antes.
    expect(margenDe(actividad({ cant_programada: '120' }))).toBe(0);
  });
});
