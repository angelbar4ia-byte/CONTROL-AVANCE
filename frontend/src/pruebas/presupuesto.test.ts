/**
 * Cómo se lee una desviación en la pantalla — `src/presupuesto/reglas.ts`
 * (§5.1, §3.6).
 *
 * El cálculo lo hace el dominio y viaja en la respuesta. Lo que se fija aquí es
 * cómo se **presenta**, y hay dos decisiones que importan más de lo que
 * parecen: que gastar de menos porque el trabajo no se hizo no se pinte de
 * verde, y que un porcentaje ausente no se escriba como cero.
 */

import { describe, expect, it } from 'vitest';

import {
  esRelevante,
  etiquetaClasificacion,
  resumirPresupuesto,
  textoPorcentaje,
  tonoClasificacion,
} from '@/presupuesto/reglas';

describe('cómo se ve cada clasificación', () => {
  it('las cinco tienen etiqueta legible', () => {
    for (const clasificacion of [
      'sobre_costo',
      'bajo_costo',
      'no_ejecutado',
      'sin_presupuesto',
      'dentro_de_rango',
    ]) {
      expect(etiquetaClasificacion(clasificacion)).not.toContain('_');
    }
  });

  it('sin ejecutar NO se pinta de verde', () => {
    // El importe es negativo, pero gastar de menos porque el trabajo no se hizo
    // no es un ahorro: pintarlo de verde invitaría a leerlo como uno.
    expect(tonoClasificacion('no_ejecutado')).toBe('warn');
    expect(tonoClasificacion('no_ejecutado')).not.toBe('ok');
  });

  it('un extra autorizado no es un error', () => {
    // Es trabajo legítimo (§11.2). Lo que hay que ver es cuánto suma, no que
    // exista.
    expect(tonoClasificacion('sin_presupuesto')).toBe('info');
    expect(tonoClasificacion('sin_presupuesto')).not.toBe('danger');
  });

  it('el sobre costo sí destaca', () => {
    expect(tonoClasificacion('sobre_costo')).toBe('danger');
  });

  it('una clasificación desconocida no rompe la fila', () => {
    expect(etiquetaClasificacion('inventada')).toBe('inventada');
    expect(tonoClasificacion('inventada')).toBe('neutral');
  });

  it('solo «en rango» deja de ser relevante', () => {
    expect(esRelevante('dentro_de_rango')).toBe(false);
    expect(esRelevante('sobre_costo')).toBe(true);
    expect(esRelevante('no_ejecutado')).toBe(true);
    expect(esRelevante('sin_presupuesto')).toBe(true);
  });
});

describe('el porcentaje que puede no existir', () => {
  it('sin base no es cero por ciento', () => {
    // `null` significa que no había presupuesto contra el cual comparar.
    // Escribir «0 %» diría que el extra no se desvió de nada.
    expect(textoPorcentaje(null)).toBe('sin base');
    expect(textoPorcentaje(undefined)).toBe('sin base');
  });

  it('lleva signo cuando se pasó', () => {
    expect(textoPorcentaje('30')).toBe('+30.0 %');
    expect(textoPorcentaje('-12.5')).toBe('-12.5 %');
  });

  it('un valor no numérico no imprime NaN', () => {
    expect(textoPorcentaje('sin sentido')).toBe('—');
  });
});

describe('resumen de la cabecera', () => {
  const filas = [
    { monto_presupuestado: '100000', monto_ejecutado: '130000', clasificacion: 'sobre_costo' },
    { monto_presupuestado: '50000', monto_ejecutado: '50000', clasificacion: 'dentro_de_rango' },
    { monto_presupuestado: '0', monto_ejecutado: '20000', clasificacion: 'sin_presupuesto' },
  ];

  it('suma las dos caras y cuenta lo que se desvía', () => {
    const resumen = resumirPresupuesto(filas);
    expect(resumen.obras).toBe(3);
    expect(resumen.presupuestado).toBe(150000);
    expect(resumen.ejecutado).toBe(200000);
    expect(resumen.sobreCosto).toBe(1);
    expect(resumen.sinPresupuesto).toBe(1);
  });

  it('la desviación sale de los totales, no de sumar desviaciones', () => {
    // Sumar porcentajes no significa nada, y sumar importes con signos opuestos
    // ya lo hace esta resta.
    expect(resumirPresupuesto(filas).desviacion).toBe(50000);
  });

  it('sin obras, todo en cero', () => {
    const resumen = resumirPresupuesto([]);
    expect(resumen.obras).toBe(0);
    expect(resumen.desviacion).toBe(0);
  });
});
