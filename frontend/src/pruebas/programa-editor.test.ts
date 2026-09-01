/**
 * Editor gráfico de programas base: grafo, ciclos, tramos, acomodo y borrador.
 *
 * Lo que se fija aquí es **comportamiento del editor**, no el CPM. La ruta
 * crítica, la holgura y las fechas las calcula el motor del backend (§6) y
 * este editor no las toca. Lo que sí decide en el cliente —y por eso se
 * prueba— es lo que el backend rechazaría con un 422 *sin escribir nada*: un
 * ciclo de precedencias y unos tramos que se traslapan. Descubrir cualquiera
 * de los dos al guardar cuesta la sesión de trabajo completa, así que estas
 * pruebas existen para que el canvas no pueda construir ese estado.
 *
 * El resto fija la traducción en los dos sentidos entre el contrato y el
 * canvas —renglón ↔ caja ↔ cable— que es donde un cambio de contrato rompe la
 * pantalla en silencio.
 */

import { describe, expect, it } from 'vitest';

import type {
  ItemProgramaBaseRespuesta,
  NodoPrototipoRespuesta,
} from '@/api/generado/modelo';
import { acomodarEnCapas } from '@/programacion/acomodo';
import {
  aplicar,
  deshacer,
  despachar,
  historialInicial,
  marcar,
  puedeDeshacer,
  puedeRehacer,
  rehacer,
} from '@/programacion/borrador';
import { buscarCiclo, cerrariaCiclo, ordenTopologico } from '@/programacion/ciclos';
import {
  armarBorrador,
  aristas,
  esForaneo,
  esRenglon,
  idsVisibles,
  itemsDelBorrador,
  opcionesDeEtapas,
  opcionesDeNodos,
  spanDeCaja,
  type Borrador,
  type Caja,
} from '@/programacion/grafo';
import { colocar, duracionDelPrograma, traslapesConTrabajo } from '@/programacion/planificacion';
import { anclajesDe } from '@/programacion/reglas';
import {
  finDe,
  moverTramo,
  normalizarTramos,
  partirTramo,
  redimensionarTramo,
  spanDe,
  trabajoDe,
  unirTramo,
  validarTramos,
  type Tramo,
} from '@/programacion/tramos';

/* ------------------------------------------------------------------ árbol */

function nodo(
  id: string,
  tipo: NodoPrototipoRespuesta['tipo'],
  parcial: Partial<NodoPrototipoRespuesta> = {},
): NodoPrototipoRespuesta {
  return { id, tipo, nombre: id, ...parcial };
}

/**
 * Un prototipo mínimo pero realista: un nivel con dos etapas, y dos conceptos
 * en cada una. Es la forma que tiene el árbol WBS de una vivienda (§7.4).
 */
const ARBOL: readonly NodoPrototipoRespuesta[] = [
  nodo('n1', 'nivel', { nombre: 'Planta baja' }),
  nodo('e1', 'etapa', { parent_id: 'n1', nombre: 'Cimentación', clave: 'CIM', etapa_id: 'cat-cim' }),
  nodo('c1', 'concepto', { parent_id: 'e1', nombre: 'Excavación', clave: 'EX-01', etapa_id: 'cat-cim' }),
  nodo('c2', 'concepto', { parent_id: 'e1', nombre: 'Zapatas', clave: 'ZA-01', etapa_id: 'cat-cim' }),
  nodo('e2', 'etapa', { parent_id: 'n1', nombre: 'Albañilería', clave: 'ALB', etapa_id: 'cat-alb' }),
  nodo('c3', 'concepto', { parent_id: 'e2', nombre: 'Muro de tabique', clave: 'MU-01', etapa_id: 'cat-alb' }),
  nodo('c4', 'concepto', { parent_id: 'e2', nombre: 'Losa', clave: 'LO-01', etapa_id: 'cat-alb' }),
];

function item(
  id: string,
  nodoId: string,
  parcial: Partial<ItemProgramaBaseRespuesta> = {},
): ItemProgramaBaseRespuesta {
  return {
    id,
    programa_base_id: 'pb1',
    prototipo_nodo_id: nodoId,
    etapa_id: null,
    frente_id: null,
    duracion_dias: '5',
    dependencias: [],
    tramos: [],
    orden: 0,
    ...parcial,
  };
}

function armar(items: readonly ItemProgramaBaseRespuesta[] = []) {
  return armarBorrador({ prototipoId: 'p1', nombre: '', nodos: ARBOL, items });
}

/* ------------------------------------------------- caja ↔ renglón ↔ cable */

describe('el grafo son los nodos del WBS y sus dependencias (§7.4, §7.5)', () => {
  it('toda etapa y todo concepto es una caja; el nivel no', () => {
    const { borrador } = armar();
    expect(borrador.cajas.map((caja) => caja.id)).toEqual(['e1', 'c1', 'c2', 'e2', 'c3', 'c4']);
    expect(borrador.cajas.filter((caja) => caja.tipo === 'etapa').map((c) => c.id)).toEqual([
      'e1',
      'e2',
    ]);
  });

  it('un prototipo sin programa arranca desde su árbol, con las duraciones por llenar', () => {
    // Es el estado vacío completo: hay cajas que colocar y cablear desde el
    // primer segundo, ninguna con duración y ninguna que viaje al POST.
    const { borrador } = armar();
    expect(borrador.cajas.every((caja) => caja.duracionDias === null)).toBe(true);
    expect(borrador.cajas.some(esRenglon)).toBe(false);
    expect(itemsDelBorrador(borrador).items).toEqual([]);
  });

  it('la caja se identifica con el prototipo_nodo_id y el cable con la ref', () => {
    // La ref de un programa base ES el prototipo_nodo_id de la predecesora
    // (§7.5): sin traducción, el mismo id en el árbol y en el POST.
    const { borrador } = armar([
      item('i1', 'c1', { duracion_dias: '3' }),
      item('i2', 'c2', {
        duracion_dias: '4',
        dependencias: [{ ref: 'c1', tipo: 'FS', lag_dias: 2 }],
      }),
    ]);

    const c2 = borrador.cajas.find((caja) => caja.id === 'c2');
    expect(c2?.entradas).toEqual([{ desde: 'c1', tipo: 'FS', lagDias: 2 }]);
    expect(aristas(borrador)).toEqual([{ desde: 'c1', hasta: 'c2' }]);
  });

  it('un concepto cuelga del nodo etapa, no del catálogo de etapas', () => {
    // Dos etapas del mismo tipo constructivo comparten `etapa_id`; lo que
    // agrupa el canvas es el nodo del árbol.
    const { borrador } = armar();
    const c3 = borrador.cajas.find((caja) => caja.id === 'c3');
    expect(c3?.etapaNodoId).toBe('e2');
    expect(c3?.etapaId).toBe('cat-alb');
    expect(borrador.cajas.find((caja) => caja.id === 'e1')?.etapaNodoId).toBeNull();
  });

  it('un renglón que apunta a un nodo que ya no está en el árbol se reporta, no se pierde', () => {
    const { borrador, huerfanos } = armar([item('i9', 'fantasma', { duracion_dias: '2' })]);
    expect(huerfanos.map((h) => h.id)).toEqual(['i9']);
    expect(borrador.cajas.some((caja) => caja.id === 'fantasma')).toBe(false);
  });

  it('vuelve a salir como items del contrato, con el orden renumerado', () => {
    const { borrador } = armar([
      item('i1', 'c1', { duracion_dias: '3', orden: 7 }),
      item('i2', 'c2', {
        duracion_dias: '4',
        orden: 9,
        dependencias: [{ ref: 'c1', tipo: 'SS', lag_dias: -1 }],
      }),
    ]);

    const { items } = itemsDelBorrador(borrador);
    expect(items.map((i) => [i.prototipo_nodo_id, i.orden])).toEqual([
      ['c1', 0],
      ['c2', 1],
    ]);
    expect(items[1]?.dependencias).toEqual([{ ref: 'c1', tipo: 'SS', lag_dias: -1 }]);
    // `etapa_id` se rellena desde el nodo: viaja hasta la actividad al
    // instanciar la obra, así que perderlo aquí lo pierde para siempre.
    expect(items[0]?.etapa_id).toBe('cat-cim');
  });

  it('una dependencia hacia una caja sin duración no viaja, y se avisa', () => {
    // Mandarla sería una `ref` que el motor no puede resolver; callarlo
    // dejaría al usuario creyendo que guardó una precedencia que no existe.
    const { borrador } = armar([
      item('i2', 'c2', {
        duracion_dias: '4',
        dependencias: [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }],
      }),
    ]);

    const { items, avisos } = itemsDelBorrador(borrador);
    expect(items).toHaveLength(1);
    expect(items[0]?.dependencias).toEqual([]);
    expect(avisos.map((aviso) => aviso.clase)).toContain('ref-fuera');
    expect(avisos.map((aviso) => aviso.clase)).toContain('sin-duracion');
  });

  it('los tramos viajan y la duración es su suma (§7.6)', () => {
    const { borrador } = armar([
      item('i3', 'c3', {
        duracion_dias: '14',
        tramos: [
          { duracion_dias: 10, offset_dias: 0 },
          { duracion_dias: 4, offset_dias: 15 },
        ],
      }),
    ]);

    const caja = borrador.cajas.find((c) => c.id === 'c3')!;
    expect(caja.tramos).toHaveLength(2);
    expect(spanDeCaja(caja)).toBe(19);

    const { items } = itemsDelBorrador(borrador);
    expect(items[0]?.duracion_dias).toBe(14);
    expect(items[0]?.tramos).toEqual([
      { duracion_dias: 10, offset_dias: 0 },
      { duracion_dias: 4, offset_dias: 15 },
    ]);
  });
});

/* ---------------------------------------------------------------- vistas */

describe('granularidad del canvas', () => {
  const { borrador } = armar([
    item('i1', 'c1', { duracion_dias: '3' }),
    item('i3', 'c3', {
      duracion_dias: '4',
      // Cable entre conceptos de etapas distintas: requisito explícito.
      dependencias: [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }],
    }),
  ]);

  it('arranca en etapas: diez cajas legibles, no trescientos conceptos', () => {
    expect([...idsVisibles(borrador, { modo: 'etapas' })].sort()).toEqual(['e1', 'e2']);
  });

  it('el interruptor de conceptos abre todos los de todas las etapas', () => {
    expect([...idsVisibles(borrador, { modo: 'conceptos' })].sort()).toEqual([
      'c1',
      'c2',
      'c3',
      'c4',
    ]);
  });

  it('al entrar a una etapa se ven también los conceptos de otra que estén cableados', () => {
    // Un cable cuyo otro extremo no se ve no se puede ni revisar ni quitar.
    const vista = { modo: 'conceptos-de', etapaNodoId: 'e2' } as const;
    expect([...idsVisibles(borrador, vista)].sort()).toEqual(['c1', 'c3', 'c4']);

    const c1 = borrador.cajas.find((caja) => caja.id === 'c1')!;
    const c3 = borrador.cajas.find((caja) => caja.id === 'c3')!;
    expect(esForaneo(c1, vista)).toBe(true);
    expect(esForaneo(c3, vista)).toBe(false);
  });
});

/* ----------------------------------------------------------------- ciclos */

describe('detección de ciclos en el cliente (§6)', () => {
  const cadena = [
    { desde: 'a', hasta: 'b' },
    { desde: 'b', hasta: 'c' },
  ];

  it('un cable que cierra el camino de vuelta no se deja tender', () => {
    expect(cerrariaCiclo(cadena, 'c', 'a')).toBe(true);
    expect(cerrariaCiclo(cadena, 'a', 'c')).toBe(false);
  });

  it('una actividad no puede depender de sí misma', () => {
    expect(cerrariaCiclo([], 'a', 'a')).toBe(true);
  });

  it('el orden topológico deja las predecesoras antes y desaparece con el ciclo', () => {
    expect(ordenTopologico(['c', 'b', 'a'], cadena)).toEqual(['a', 'b', 'c']);
    expect(ordenTopologico(['a', 'b', 'c'], [...cadena, { desde: 'c', hasta: 'a' }])).toBeNull();
  });

  it('nombra el ciclo que ya venía en un programa importado', () => {
    const ciclo = buscarCiclo(['a', 'b', 'c'], [...cadena, { desde: 'c', hasta: 'a' }]);
    expect(ciclo?.[0]).toBe(ciclo?.[ciclo.length - 1]);
    expect(new Set(ciclo)).toEqual(new Set(['a', 'b', 'c']));
    expect(buscarCiclo(['a', 'b', 'c'], cadena)).toBeNull();
  });

  it('ignora una arista con un extremo fuera del grafo en vez de inventarle nodo', () => {
    expect(ordenTopologico(['a'], [{ desde: 'a', hasta: 'viejo' }])).toEqual(['a']);
  });
});

/* ----------------------------------------------------------------- tramos */

describe('tramos: el editor no puede construir lo que el backend rechaza (§7.6)', () => {
  const partido: readonly Tramo[] = [
    { duracionDias: 10, offsetDias: 0 },
    { duracionDias: 4, offsetDias: 15 },
  ];

  it('el span encadena a las sucesoras y el trabajo es lo que se paga', () => {
    expect(spanDe(14, partido)).toBe(19);
    expect(trabajoDe(14, partido)).toBe(14);
    expect(spanDe(6, [])).toBe(6);
    expect(finDe(partido[1]!)).toBe(19);
  });

  it('un solo tramo no es una interrupción: es la actividad continua', () => {
    expect(normalizarTramos([{ duracionDias: 8, offsetDias: 0 }])).toEqual([]);
  });

  it('partir deja los dos pedazos positivos y corre lo que sigue', () => {
    const tres = partirTramo(partido, 0, 5, 2);
    expect(tres).toEqual([
      { duracionDias: 5, offsetDias: 0 },
      { duracionDias: 5, offsetDias: 7 },
      { duracionDias: 4, offsetDias: 17 },
    ]);
    expect(validarTramos(tres)).toBeNull();
    // El trabajo no cambia al partir: partir no crea ni destruye días.
    expect(trabajoDe(0, tres)).toBe(trabajoDe(0, partido));
  });

  it('unir cierra la pausa y arrastra el resto, sin abrir un hueco nuevo', () => {
    const unido = unirTramo(partido, 0);
    expect(unido).toEqual([]);
    const tres = partirTramo(partido, 0, 5, 2);
    expect(unirTramo(tres, 0)).toEqual([
      { duracionDias: 10, offsetDias: 0 },
      { duracionDias: 4, offsetDias: 15 },
    ]);
  });

  it('mover se recorta al hueco: nunca pisa al vecino', () => {
    // Arrastrar muy a la izquierda topa con el cierre del anterior.
    expect(moverTramo(partido, 1, 3)).toEqual([
      { duracionDias: 10, offsetDias: 0 },
      { duracionDias: 4, offsetDias: 10 },
    ]);
    // El primero está clavado en el día 0: un hueco por delante no es una
    // interrupción, es una fecha de inicio más tarde.
    expect(moverTramo(partido, 0, 5)).toEqual(partido);
    expect(validarTramos(moverTramo(partido, 1, 3))).toBeNull();
  });

  it('redimensionar tampoco alcanza a traslapar', () => {
    const tres = partirTramo(partido, 0, 5, 2);
    // El primero puede crecer hasta el arranque del segundo (día 7) y no más.
    expect(redimensionarTramo(tres, 0, 40)[0]).toEqual({ duracionDias: 7, offsetDias: 0 });
    expect(validarTramos(redimensionarTramo(tres, 0, 40))).toBeNull();
    // El último no tiene tope por la derecha.
    expect(redimensionarTramo(partido, 1, 9)[1]).toEqual({ duracionDias: 9, offsetDias: 15 });
  });

  it('reconoce los tres estados ilegales que el backend rechaza', () => {
    expect(
      validarTramos([
        { duracionDias: 5, offsetDias: 2 },
        { duracionDias: 5, offsetDias: 9 },
      ]),
    ).toMatch(/primer tramo/);
    expect(
      validarTramos([
        { duracionDias: 5, offsetDias: 0 },
        { duracionDias: 5, offsetDias: 3 },
      ]),
    ).toMatch(/traslapan/);
    expect(validarTramos([{ duracionDias: 0, offsetDias: 0 }, ...partido])).toMatch(/positiva/);
    expect(validarTramos(partido)).toBeNull();
  });
});

/* -------------------------------------------- colocación y aviso de tramo */

describe('las cuatro ligas y el aviso de tramo (§7.6)', () => {
  function conCajas(cajas: readonly Partial<Caja>[]): Borrador {
    return {
      prototipoId: 'p1',
      nombre: '',
      cajas: cajas.map((parcial, indice) => ({
        id: `k${indice}`,
        tipo: 'concepto' as const,
        clave: null,
        nombre: `k${indice}`,
        etapaId: null,
        etapaNodoId: null,
        duracionDias: 5,
        frenteId: null,
        tramos: [],
        entradas: [],
        orden: indice,
        x: 0,
        y: 0,
        ...parcial,
      })),
    };
  }

  it('cada tipo coloca la sucesora donde dice su semántica', () => {
    for (const [tipo, inicioEsperado] of [
      ['FS', 10],
      ['SS', 0],
      ['FF', 6],
      ['SF', 0],
    ] as const) {
      const borrador = conCajas([
        { id: 'a', duracionDias: 10 },
        { id: 'b', duracionDias: 4, entradas: [{ desde: 'a', tipo, lagDias: 0 }] },
      ]);
      expect(colocar(borrador).get('b')?.inicioDias).toBe(inicioEsperado);
    }
  });

  it('el lag corre la sucesora, y nada arranca antes del día 0', () => {
    const conLag = conCajas([
      { id: 'a', duracionDias: 10 },
      { id: 'b', duracionDias: 4, entradas: [{ desde: 'a', tipo: 'FS', lagDias: 3 }] },
    ]);
    expect(colocar(conLag).get('b')?.inicioDias).toBe(13);
    expect(duracionDelPrograma(colocar(conLag))).toBe(17);

    const negativo = conCajas([
      { id: 'a', duracionDias: 10 },
      { id: 'b', duracionDias: 4, entradas: [{ desde: 'a', tipo: 'SS', lagDias: -8 }] },
    ]);
    expect(colocar(negativo).get('b')?.inicioDias).toBe(0);
  });

  it('el anclaje que dibuja el cable es la sigla del tipo', () => {
    expect(anclajesDe('FS')).toEqual({ salida: 'fin', entrada: 'inicio' });
    expect(anclajesDe('SS')).toEqual({ salida: 'inicio', entrada: 'inicio' });
    expect(anclajesDe('FF')).toEqual({ salida: 'fin', entrada: 'fin' });
    expect(anclajesDe('SF')).toEqual({ salida: 'inicio', entrada: 'fin' });
  });

  it('avisa cuando la sucesora cae sobre el trabajo del muro y no sobre su pausa', () => {
    // El muro trabaja 10 días, para 5, y sigue 4. La losa que arranca el día 6
    // cabe en la pausa; la que arranca el día 2 pisa el primer tramo.
    const muro = {
      id: 'muro',
      duracionDias: 14,
      tramos: [
        { duracionDias: 10, offsetDias: 0 },
        { duracionDias: 4, offsetDias: 15 },
      ],
    };
    const enLaPausa = conCajas([
      muro,
      { id: 'losa', duracionDias: 4, entradas: [{ desde: 'muro', tipo: 'SS', lagDias: 11 }] },
    ]);
    expect(traslapesConTrabajo(enLaPausa, colocar(enLaPausa))).toEqual([]);

    const encima = conCajas([
      muro,
      { id: 'losa', duracionDias: 4, entradas: [{ desde: 'muro', tipo: 'SS', lagDias: 2 }] },
    ]);
    expect(traslapesConTrabajo(encima, colocar(encima))).toEqual([
      { cajaId: 'losa', predecesoraId: 'muro', diasPisados: 4 },
    ]);
  });

  it('sin tramos no avisa: una SS que traslapa es lo normal, no un problema', () => {
    const borrador = conCajas([
      { id: 'a', duracionDias: 10 },
      { id: 'b', duracionDias: 8, entradas: [{ desde: 'a', tipo: 'SS', lagDias: 1 }] },
    ]);
    expect(traslapesConTrabajo(borrador, colocar(borrador))).toEqual([]);
  });

  it('con ciclo no coloca nada: no hay orden en que recorrer el grafo', () => {
    const borrador = conCajas([
      { id: 'a', entradas: [{ desde: 'b', tipo: 'FS', lagDias: 0 }] },
      { id: 'b', entradas: [{ desde: 'a', tipo: 'FS', lagDias: 0 }] },
    ]);
    expect(colocar(borrador).size).toBe(0);
  });
});

/* ---------------------------------------------------------------- acomodo */

describe('auto-acomodo por precedencia', () => {
  it('ninguna caja queda a la izquierda de una predecesora suya', () => {
    const cajas = [
      { id: 'a', orden: 0 },
      { id: 'b', orden: 1 },
      { id: 'c', orden: 2 },
    ];
    const posiciones = acomodarEnCapas(cajas, [
      { desde: 'a', hasta: 'b' },
      { desde: 'b', hasta: 'c' },
    ]);
    expect(posiciones.get('a')!.x).toBeLessThan(posiciones.get('b')!.x);
    expect(posiciones.get('b')!.x).toBeLessThan(posiciones.get('c')!.x);
  });

  it('la capa es el camino más largo, no el más corto', () => {
    // `c` depende de `a` directo y de `a→b`: va detrás de `b`, no junto a él.
    const posiciones = acomodarEnCapas(
      [
        { id: 'a', orden: 0 },
        { id: 'b', orden: 1 },
        { id: 'c', orden: 2 },
      ],
      [
        { desde: 'a', hasta: 'b' },
        { desde: 'a', hasta: 'c' },
        { desde: 'b', hasta: 'c' },
      ],
    );
    expect(posiciones.get('c')!.x).toBeGreaterThan(posiciones.get('b')!.x);
  });

  it('las cajas sueltas de una capa se apilan en el orden del árbol', () => {
    const posiciones = acomodarEnCapas(
      [
        { id: 'b', orden: 5 },
        { id: 'a', orden: 1 },
      ],
      [],
    );
    expect(posiciones.get('a')!.x).toBe(posiciones.get('b')!.x);
    expect(posiciones.get('a')!.y).toBeLessThan(posiciones.get('b')!.y);
  });

  it('es estable: acomodar dos veces da lo mismo', () => {
    const cajas = [
      { id: 'a', orden: 0 },
      { id: 'b', orden: 1 },
    ];
    const aristasPrueba = [{ desde: 'a', hasta: 'b' }];
    expect([...acomodarEnCapas(cajas, aristasPrueba)]).toEqual([
      ...acomodarEnCapas(cajas, aristasPrueba),
    ]);
  });

  it('con un ciclo sigue devolviendo una posición por caja', () => {
    const posiciones = acomodarEnCapas(
      [
        { id: 'a', orden: 0 },
        { id: 'b', orden: 1 },
      ],
      [
        { desde: 'a', hasta: 'b' },
        { desde: 'b', hasta: 'a' },
      ],
    );
    expect(posiciones.size).toBe(2);
  });
});

/* --------------------------------------------------------------- borrador */

describe('borrador local e historial', () => {
  const base = armar([item('i1', 'c1', { duracion_dias: '3' })]).borrador;

  it('capturar una duración convierte una caja propuesta en renglón', () => {
    const despues = aplicar(base, { tipo: 'duracion', cajaId: 'c2', duracionDias: 6 });
    expect(despues.cajas.find((caja) => caja.id === 'c2')?.duracionDias).toBe(6);
    expect(itemsDelBorrador(despues).items).toHaveLength(2);
  });

  it('vaciar la duración saca el renglón del POST sin borrar la caja', () => {
    const despues = aplicar(base, { tipo: 'duracion', cajaId: 'c1', duracionDias: null });
    expect(despues.cajas.some((caja) => caja.id === 'c1')).toBe(true);
    expect(itemsDelBorrador(despues).items).toEqual([]);
  });

  it('el cable que cerraría un ciclo no se pega, aunque nadie lo haya comprobado antes', () => {
    const conCable = aplicar(base, { tipo: 'conectar', desde: 'c1', hasta: 'c2', tipoLiga: 'FS' });
    const cerrado = aplicar(conCable, {
      tipo: 'conectar',
      desde: 'c2',
      hasta: 'c1',
      tipoLiga: 'FS',
    });
    expect(cerrado).toBe(conCable);
    expect(buscarCiclo(cerrado.cajas.map((c) => c.id), aristas(cerrado))).toBeNull();
  });

  it('no duplica un cable que ya existe entre las dos mismas cajas', () => {
    const uno = aplicar(base, { tipo: 'conectar', desde: 'c1', hasta: 'c2', tipoLiga: 'FS' });
    expect(aplicar(uno, { tipo: 'conectar', desde: 'c1', hasta: 'c2', tipoLiga: 'SS' })).toBe(uno);
  });

  it('con tramos la duración es la suma y no se puede capturar aparte (§7.6)', () => {
    const partido = aplicar(base, {
      tipo: 'tramos',
      cajaId: 'c1',
      tramos: [
        { duracionDias: 10, offsetDias: 0 },
        { duracionDias: 4, offsetDias: 15 },
      ],
    });
    expect(partido.cajas.find((c) => c.id === 'c1')?.duracionDias).toBe(14);
    // Intentar teclear otra cifra no hace nada: sería la que discrepara.
    expect(aplicar(partido, { tipo: 'duracion', cajaId: 'c1', duracionDias: 99 })).toBe(partido);
  });

  it('un arrastre completo es un solo paso atrás, no uno por píxel', () => {
    // `marcar` al empezar el arrastre; los `mover` de en medio no apilan.
    let historial = marcar(historialInicial(base));
    for (const x of [10, 20, 30]) {
      historial = despachar(historial, { tipo: 'mover', cajaId: 'c1', x, y: 0 });
    }
    expect(historial.pasado).toHaveLength(1);
    expect(deshacer(historial).presente).toBe(base);
  });

  it('deshacer y rehacer recorren los gestos completos', () => {
    let historial = historialInicial(base);
    historial = despachar(historial, { tipo: 'duracion', cajaId: 'c2', duracionDias: 4 });
    historial = despachar(historial, { tipo: 'conectar', desde: 'c1', hasta: 'c2', tipoLiga: 'FS' });

    expect(puedeDeshacer(historial)).toBe(true);
    expect(puedeRehacer(historial)).toBe(false);

    const atras = deshacer(deshacer(historial));
    expect(atras.presente).toBe(base);
    expect(puedeRehacer(atras)).toBe(true);
    expect(rehacer(rehacer(atras)).presente).toEqual(historial.presente);
  });

  it('una acción que no cambia nada no gasta un paso del historial', () => {
    const historial = despachar(historialInicial(base), {
      tipo: 'desconectar',
      desde: 'c1',
      hasta: 'c2',
    });
    expect(puedeDeshacer(historial)).toBe(false);
  });
});

/* ------------------------------------------------ el alta sin teclear UUID */

describe('el alta ya no pide UUIDs (§7.4)', () => {
  it('ofrece las etapas y los conceptos del árbol, sangrados por profundidad', () => {
    const opciones = opcionesDeNodos(ARBOL);
    expect(opciones.map((opcion) => opcion.valor)).toEqual(['e1', 'c1', 'c2', 'e2', 'c3', 'c4']);
    // La sangría son espacios duros: en un <option> el espacio normal colapsa.
    expect(opciones[0]?.etiqueta).toBe('\u00a0\u00a0CIM · Cimentación');
    expect(opciones[1]?.etiqueta).toBe('\u00a0\u00a0\u00a0\u00a0EX-01 · Excavación');
  });

  it('las etapas constructivas del catálogo se listan una sola vez', () => {
    const repetida = [...ARBOL, nodo('e3', 'etapa', { parent_id: 'n1', etapa_id: 'cat-cim' })];
    expect(opcionesDeEtapas(repetida).map((opcion) => opcion.valor)).toEqual([
      'cat-cim',
      'cat-alb',
    ]);
  });
});
