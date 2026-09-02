/**
 * Las reglas de presentación de la planeación por obra (§8.3, §4).
 *
 * Estas pruebas protegen la frontera entre lo que la pantalla puede decidir y
 * lo que no. **La cuenta de cuadrillas no está aquí**: vive en
 * `domain/planeacion/cuadrillas.py` y la fija `test_cuadrillas.py`. Si alguna
 * de estas pruebas empezara a dividir jornadas entre días hábiles, esa sería la
 * señal de que la regla se duplicó.
 *
 * Lo que sí se fija:
 *
 *  1. **El renglón sin frente no se contrata.** No hay a qué colgarle el trato:
 *     ofrecer el botón guardaría contra un `frente_id` vacío y el `PUT` daría
 *     422 sin decir por qué.
 *  2. **"Sin decidir" no es "va corto".** Antes de cotizar nadie decidió nada;
 *     pintarlo como falta llenaría la tabla de alertas el primer día.
 *  3. **La comparación es contra el pico**, no contra el promedio: quien presta
 *     dos cuadrillas todo el mes no resuelve la semana que pide cinco.
 */

import { describe, expect, it } from 'vitest';

import {
  cobertura,
  esContratable,
  listoParaConsultar,
  parametrosDeConsulta,
  puedePlanear,
  SIN_FRENTE,
  textoDeCobertura,
  totalDeJornadas,
  type FiltroPlaneacion,
} from '@/planeacion/reglas';

const FILTRO: FiltroPlaneacion = {
  obraId: '11111111-1111-1111-1111-111111111111',
  granularidad: 'semana',
  rango: { desde: '2026-05-11', hasta: '2026-08-03' },
};

describe('a qué renglón se le puede asignar contratista', () => {
  it('al renglón que agrupa lo que no tiene frente, no', () => {
    // Es trabajo real, pero sin frente no hay a qué colgarle el trato: lo que
    // se hace con él es ir a mapear sus etapas.
    expect(esContratable(SIN_FRENTE)).toBe(false);
  });

  it('a un frente del catálogo, sí', () => {
    expect(esContratable('22222222-2222-2222-2222-222222222222')).toBe(true);
  });
});

describe('cómo se lee la decisión contra la sugerencia', () => {
  it('sin cuadrillas planeadas dice «sin decidir», no que va corto', () => {
    // Antes de cotizar nadie decidió nada. Marcarlo como falta llenaría la
    // tabla de alertas el primer día y nadie volvería a mirarlas.
    expect(cobertura(5, null)).toBe('sin_decidir');
    expect(cobertura(5, undefined)).toBe('sin_decidir');
  });

  it('menos cuadrillas que el pico va corto', () => {
    expect(cobertura(5, 3)).toBe('corto');
  });

  it('igualar el pico alcanza', () => {
    expect(cobertura(5, 5)).toBe('suficiente');
  });

  it('se compara contra el pico y no contra el promedio', () => {
    // Un frente que pide 8 una semana y 1 las otras tiene promedio bajo, pero
    // se contrata por la semana de 8: con 2 cuadrillas va corto.
    expect(cobertura(8, 2)).toBe('corto');
  });

  it('dice cuántas faltan, no solo que faltan', () => {
    // "Faltan 3" es accionable; "insuficiente" obliga a restar a mano.
    expect(textoDeCobertura(5, 2)).toBe('Faltan 3');
  });

  it('redondea hacia arriba lo que falta: media cuadrilla no se contrata', () => {
    expect(textoDeCobertura(4.3, 2)).toBe('Faltan 3');
  });
});

describe('cuándo se dispara la consulta', () => {
  it('sin obra no se consulta', () => {
    // La planeación es siempre de una obra: el contratista de un frente puede
    // ser otro en la obra de al lado, así que no hay respuesta agregada.
    expect(listoParaConsultar({ ...FILTRO, obraId: '' })).toBe(false);
  });

  it('con el rango al revés tampoco: sería un 422', () => {
    expect(
      listoParaConsultar({
        ...FILTRO,
        rango: { desde: '2026-08-03', hasta: '2026-05-11' },
      }),
    ).toBe(false);
  });

  it('con obra y rango válido, sí', () => {
    expect(listoParaConsultar(FILTRO)).toBe(true);
  });
});

describe('lo que viaja al endpoint', () => {
  it('manda el rango y la granularidad, y nada más', () => {
    // La obra va en la ruta, no en el query: mandarla dos veces invitaría a que
    // un día no coincidieran.
    expect(parametrosDeConsulta(FILTRO)).toEqual({
      desde: '2026-05-11',
      hasta: '2026-08-03',
      granularidad: 'semana',
    });
  });
});

describe('quién planifica', () => {
  it('el residente, que es quien está en la obra', () => {
    expect(puedePlanear('residente')).toBe(true);
  });

  it('el supervisor y Control también: ven las mismas obras y a veces contratan', () => {
    expect(puedePlanear('supervisor')).toBe(true);
    expect(puedePlanear('control_obra')).toBe(true);
  });
});

describe('el total de la obra', () => {
  it('suma todos los frentes, incluido el que no tiene frente', () => {
    // Si el renglón sin frente se descartara del total, la suma de la tabla no
    // cuadraría con la obra y nadie sabría que falta capturar algo.
    expect(
      totalDeJornadas([
        { total_jornadas: 1623.6 },
        { total_jornadas: 2245.3 },
        { total_jornadas: 935 },
      ]),
    ).toBeCloseTo(4803.9, 1);
  });
});
