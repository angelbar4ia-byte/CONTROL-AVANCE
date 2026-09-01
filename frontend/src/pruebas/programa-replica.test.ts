/**
 * Replicar el programa base a las obras del prototipo (§7.5, §11.2).
 *
 * Prueba la lógica sin render de `replica.ts`: qué casas quedan elegidas, en
 * qué tandas se mandan, cómo avanza la barra y cómo se lee el parte final. Lo
 * que decide si una obra se puede programar es del backend y no se imita aquí
 * —eso lo cubre `tests/integracion/test_replicar_programa_endtoend.py`—; lo que
 * se fija es que la pantalla presente ese resultado sin perder ni reordenar
 * nada.
 */

import { describe, expect, it } from 'vitest';

import {
  TAMANO_DE_LOTE,
  alternarObra,
  avisoDeSeleccion,
  lotesDe,
  obrasElegidas,
  partesParaReporte,
  progresoDe,
  recuentoDe,
  todasLasObras,
  type ObraElegible,
  type ParteDeObra,
} from '@/programacion/replica';

function obra(clave: string, version: number | null = null): ObraElegible {
  return { obra_id: `id-${clave}`, clave, version_cronograma: version };
}

const CLUSTER: ObraElegible[] = [
  obra('FRESNO 01'),
  obra('FRESNO 02', 3),
  obra('FRESNO 03'),
  obra('FRESNO 04', 1),
];

function parte(clave: string, extra: Partial<ParteDeObra> = {}): ParteDeObra {
  return {
    obra_id: `id-${clave}`,
    clave,
    programada: true,
    version: 1,
    n_actividades: 12,
    sin_item: [],
    refs_no_resueltas: [],
    motivo: null,
    ...extra,
  };
}

describe('troceo del lote', () => {
  it('parte la lista en tandas del tamaño pedido y no pierde ni repite nada', () => {
    const lotes = lotesDe([1, 2, 3, 4, 5, 6, 7], 3);
    expect(lotes).toEqual([
      [1, 2, 3],
      [4, 5, 6],
      [7],
    ]);
    expect(lotes.flat()).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('un cluster de 40 casas sale en tandas, no en una sola petición larga', () => {
    const cuarenta = Array.from({ length: 40 }, (_, i) => `obra-${i}`);
    const lotes = lotesDe(cuarenta);
    expect(lotes).toHaveLength(40 / TAMANO_DE_LOTE);
    expect(lotes.flat()).toEqual(cuarenta);
  });

  it('una lista vacía no produce ninguna petición', () => {
    expect(lotesDe([])).toEqual([]);
  });

  it('un tamaño absurdo no cuelga el bucle: se acota a uno por tanda', () => {
    expect(lotesDe([1, 2], 0)).toEqual([[1], [2]]);
    expect(lotesDe([1, 2], -5)).toEqual([[1], [2]]);
  });
});

describe('selección de obras', () => {
  it('alternar marca y desmarca sin mutar el conjunto anterior', () => {
    const vacia: ReadonlySet<string> = new Set();
    const conUna = alternarObra(vacia, 'id-FRESNO 01');

    expect(conUna.has('id-FRESNO 01')).toBe(true);
    expect(vacia.size).toBe(0);
    expect(alternarObra(conUna, 'id-FRESNO 01').size).toBe(0);
  });

  it('todas selecciona el cluster completo', () => {
    expect(todasLasObras(CLUSTER).size).toBe(4);
  });

  it('las elegidas salen en el orden de la lista, no en el de los clics', () => {
    // Se marcan de atrás para adelante: el parte que devuelve el servidor
    // respeta el orden en que se pidieron, y quien lo lee va bajando por la
    // lista que tiene enfrente.
    let seleccion: ReadonlySet<string> = new Set();
    for (const clave of ['FRESNO 03', 'FRESNO 01', 'FRESNO 04']) {
      seleccion = alternarObra(seleccion, `id-${clave}`);
    }

    expect(obrasElegidas(CLUSTER, seleccion)).toEqual([
      'id-FRESNO 01',
      'id-FRESNO 03',
      'id-FRESNO 04',
    ]);
  });

  it('ignora ids seleccionados que ya no están en la lista', () => {
    const seleccion = new Set(['id-FRESNO 01', 'id-DEMOLIDA']);
    expect(obrasElegidas(CLUSTER, seleccion)).toEqual(['id-FRESNO 01']);
  });
});

describe('aviso de versión nueva (§7.5)', () => {
  it('cuenta cuántas de las elegidas ya traen cronograma', () => {
    const seleccion = todasLasObras(CLUSTER);
    expect(avisoDeSeleccion(CLUSTER, seleccion)).toEqual({
      total: 4,
      conCronograma: 2,
    });
  });

  it('solo cuenta las elegidas, no todas las del prototipo', () => {
    const seleccion = new Set(['id-FRESNO 01']);
    expect(avisoDeSeleccion(CLUSTER, seleccion)).toEqual({
      total: 1,
      conCronograma: 0,
    });
  });

  it('sin selección no hay nada que advertir', () => {
    expect(avisoDeSeleccion(CLUSTER, new Set())).toEqual({
      total: 0,
      conCronograma: 0,
    });
  });
});

describe('avance mientras corre', () => {
  it('va del 0 al 100 conforme se cierran las tandas', () => {
    expect(progresoDe(0, 40).pct).toBe(0);
    expect(progresoDe(10, 40).pct).toBe(25);
    expect(progresoDe(40, 40).pct).toBe(100);
  });

  it('sin obras no hay barra que pintar en vez de dividir entre cero', () => {
    expect(progresoDe(0, 0)).toEqual({ hechas: 0, total: 0, pct: 0 });
  });

  it('acota: la barra nunca se pasa ni se va en negativo', () => {
    expect(progresoDe(99, 40).pct).toBe(100);
    expect(progresoDe(-3, 40).pct).toBe(0);
  });
});

describe('lectura del parte', () => {
  const PARTES: ParteDeObra[] = [
    parte('FRESNO 01'),
    parte('FRESNO 02', {
      programada: false,
      version: null,
      n_actividades: 0,
      motivo: 'La obra no tiene actividades: genérala desde su prototipo.',
    }),
    parte('FRESNO 03', { sin_item: ['act-1', 'act-2'] }),
    parte('FRESNO 04', { refs_no_resueltas: ['nodo-x'] }),
  ];

  it('cuenta programadas, fallidas y las que dejaron huecos de plantilla', () => {
    expect(recuentoDe(PARTES)).toEqual({
      programadas: 3,
      fallidas: 1,
      conHuecos: 2,
    });
  });

  it('un hueco de plantilla no es un fallo: la obra sí quedó programada (§7.5)', () => {
    const conHueco = recuentoDe([parte('FRESNO 03', { sin_item: ['act-1'] })]);
    expect(conHueco.fallidas).toBe(0);
    expect(conHueco.programadas).toBe(1);
    expect(conHueco.conHuecos).toBe(1);
  });

  it('el reporte pone arriba lo que hay que atender', () => {
    const orden = partesParaReporte(PARTES).map((p) => p.clave);
    expect(orden[0]).toBe('FRESNO 02');
    // Y dentro de cada grupo se conserva el orden de la petición.
    expect(orden).toEqual(['FRESNO 02', 'FRESNO 01', 'FRESNO 03', 'FRESNO 04']);
  });

  it('no pierde ningún renglón al reordenar: 40 pedidas, 40 reportadas', () => {
    expect(partesParaReporte(PARTES)).toHaveLength(PARTES.length);
  });

  it('un lote entero en verde no cambia el orden', () => {
    const buenas = [parte('A'), parte('B'), parte('C')];
    expect(partesParaReporte(buenas).map((p) => p.clave)).toEqual(['A', 'B', 'C']);
  });
});
