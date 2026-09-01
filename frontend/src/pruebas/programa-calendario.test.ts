/**
 * Semana laboral o natural del cronograma (§7.5), del lado del cliente.
 *
 * La equivalencia "natural ⇔ los siete días" está en los dos lados: el
 * backend la deriva para responder `tipo`, y el editor la necesita **antes**
 * de guardar, cuando todavía no hay respuesta. Estas pruebas fijan que la
 * copia del cliente diga lo mismo que la del servidor.
 */

import { describe, expect, it } from 'vitest';

import {
  SEMANA_LABORAL,
  SEMANA_NATURAL,
  alternarDia,
  descripcionDeSemana,
  inicialDeDia,
  mismosDias,
  nombreDeDia,
  normalizarDias,
  tipoDeSemana,
} from '@/programacion/calendario';

describe('tipo de semana derivado del conjunto de días', () => {
  it('los siete días son semana natural: es el default y el caso de siempre', () => {
    expect(tipoDeSemana(SEMANA_NATURAL)).toBe('natural');
    expect(SEMANA_NATURAL).toHaveLength(7);
  });

  it('lunes a sábado es laboral, que es la semana normal de obra en México', () => {
    expect(tipoDeSemana(SEMANA_LABORAL)).toBe('laboral');
    expect(SEMANA_LABORAL).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('cualquier subconjunto es laboral, no solo lunes a viernes', () => {
    expect(tipoDeSemana([1, 2, 3, 4, 5])).toBe('laboral');
    expect(tipoDeSemana([1, 3, 5])).toBe('laboral');
    expect(tipoDeSemana([7])).toBe('laboral');
  });
});

describe('normalización de los días que llegan del contrato', () => {
  it('ordena y quita repetidos', () => {
    expect(normalizarDias([6, 1, 3, 1])).toEqual([1, 3, 6]);
  });

  it('descarta lo que cae fuera del rango ISO en vez de mandarlo al backend', () => {
    expect(normalizarDias([0, 1, 2, 8, 9])).toEqual([1, 2]);
  });

  it('sin calendario —programa nuevo, o campo ausente— es semana natural', () => {
    expect(normalizarDias(null)).toEqual(SEMANA_NATURAL);
    expect(normalizarDias(undefined)).toEqual(SEMANA_NATURAL);
  });

  it('un conjunto vacío cae a natural: un cronograma sin días no termina nunca', () => {
    expect(normalizarDias([])).toEqual(SEMANA_NATURAL);
    expect(normalizarDias([0, 99])).toEqual(SEMANA_NATURAL);
  });
});

describe('alternar un día', () => {
  it('quitar un día deja el resto ordenado', () => {
    expect(alternarDia(SEMANA_NATURAL, 7)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('agregar un día lo mete en su lugar, no al final', () => {
    expect(alternarDia([1, 2, 6], 4)).toEqual([1, 2, 4, 6]);
  });

  it('no deja quitar el último día hábil: el backend lo rechaza', () => {
    expect(alternarDia([3], 3)).toEqual([3]);
  });

  it('ir de natural a laboral y de vuelta regresa al mismo conjunto', () => {
    const sinDomingo = alternarDia(SEMANA_NATURAL, 7);
    expect(mismosDias(alternarDia(sinDomingo, 7), SEMANA_NATURAL)).toBe(true);
  });
});

describe('comparación de conjuntos (decide si el borrador está sucio)', () => {
  it('mismos días es true aunque sean arreglos distintos', () => {
    expect(mismosDias([1, 2, 3], [1, 2, 3])).toBe(true);
  });

  it('distinto largo o distinto día es false', () => {
    expect(mismosDias([1, 2, 3], [1, 2])).toBe(false);
    expect(mismosDias([1, 2, 3], [1, 2, 4])).toBe(false);
  });
});

describe('etiquetas legibles', () => {
  it('la descripción distingue las dos semanas', () => {
    expect(descripcionDeSemana(SEMANA_NATURAL)).toContain('natural');
    expect(descripcionDeSemana(SEMANA_LABORAL)).toContain('laboral');
  });

  it('la laboral enseña qué días son, porque no siempre son los mismos', () => {
    expect(descripcionDeSemana(SEMANA_LABORAL)).toContain('LMMJVS');
  });

  it('lunes y martes comparten inicial, y el nombre largo los desambigua', () => {
    expect(inicialDeDia(1)).toBe('L');
    expect(inicialDeDia(2)).toBe('M');
    expect(inicialDeDia(3)).toBe('M');
    expect(nombreDeDia(2)).toBe('martes');
    expect(nombreDeDia(3)).toBe('miércoles');
  });

  it('los siete días tienen inicial y nombre', () => {
    for (const dia of SEMANA_NATURAL) {
      expect(inicialDeDia(dia)).toHaveLength(1);
      expect(nombreDeDia(dia)).not.toBe(String(dia));
    }
  });
});
