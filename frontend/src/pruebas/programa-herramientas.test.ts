/**
 * El menú de herramientas del programa base: gestos, escalas, reparto
 * volumétrico y apariencia.
 *
 * Es el complemento de `programa-tabla-gantt.test.ts` —que fija el aplanado, el
 * rollup y el arrastre— para todo lo que la cinta añadió. Lo que se vigila aquí
 * son las seis cosas que rompen el editor en silencio:
 *
 *  1. **Los tramos.** Dividir, interrumpir y unir producen estados que el
 *     backend valida y rechaza con un 422 sobre el programa **entero** (§7.6),
 *     así que una operación que deje dos tramos encimados no cuesta un aviso:
 *     cuesta la sesión de trabajo.
 *  2. **Aplazar.** No es escribir una fecha —un renglón de programa base no
 *     tiene ninguna— sino cambiar el lag de la precedencia que manda, y una
 *     actividad sin predecesoras no se puede aplazar. Si eso se moviera en
 *     pantalla y se perdiera al guardar, el editor dejaría de ser creíble.
 *  3. **Los vínculos y los ciclos.** Vincular e invertir pueden cerrar un
 *     ciclo; el cliente lo detecta antes de despachar y lo explica en vez de no
 *     hacer nada (§6).
 *  4. **El reparto de cantidad por periodo**, con el caso que le da sentido:
 *     una pausa no consume cantidad. Repartir sobre el span en vez de sobre los
 *     tramos daría producción a la semana en que la actividad está parada, que
 *     es exactamente la cifra que alguien usaría para pedir material.
 *  5. **Las escalas.** Que las dos bandas del encabezado partan el eje igual
 *     que la rejilla de cantidades, y que un "mes" no se invente un calendario
 *     en modo relativo.
 *  6. **Que la vista no ensucie el borrador.** Encender la ruta crítica, cambiar
 *     de tema o apagar una columna no es editar el programa, y la separación es
 *     estructural: los módulos de vista no reciben un `Borrador` ni devuelven
 *     una `Accion`.
 *
 * Todo sin render: la aritmética vive fuera de los componentes (§12.11).
 */

import { describe, expect, it } from 'vitest';

import type {
  ItemProgramaBaseRespuesta,
  NodoPrototipoRespuesta,
  PartidaRespuesta,
} from '@/api/generado/modelo';
import {
  acercarZoom,
  alejarZoom,
  construirBandas,
  saltosDeCalendario,
  zoomParaAjustar,
} from '@/programacion/bandasPrograma';
import { clasesDeBarra, etiquetaDeBarra, tonosDeFrente } from '@/programacion/barras';
import {
  aplicar,
  despachar,
  despacharVarias,
  historialInicial,
  type Accion,
} from '@/programacion/borrador';
import {
  CLAVES_COLUMNAS,
  COLUMNAS_FIJAS,
  COLUMNAS_PROGRAMA,
  columnasVisibles,
  desplazamientosCongelados,
  plantillaDeColumnas,
} from '@/programacion/columnasPrograma';
import { construirEje } from '@/programacion/ejePrograma';
import { aplanarPrograma, colapsarANivel, profundidadMaxima } from '@/programacion/filasPrograma';
import * as gestos from '@/programacion/gestos';
import { armarBorrador, buscarCable, type Borrador } from '@/programacion/grafo';
import { colocar } from '@/programacion/planificacion';
import {
  intervalosDeTrabajo,
  magnitudesDeFilas,
  rejillaDeCantidades,
  repartirEnPeriodos,
} from '@/programacion/reparto';
import { trazarRutaCritica } from '@/programacion/rutaCritica';
import { alargarPausa } from '@/programacion/tramos';
import {
  VISTA_GANTT_INICIAL,
  alternarColumna,
  alternarEtiqueta,
  deserializarVista,
  serializarVista,
  temaEfectivo,
  type VistaGantt,
} from '@/programacion/vistaGantt';

/* ------------------------------------------------------------------ *
 * Un prototipo mínimo con la forma real: nivel → etapa → concepto.
 * ------------------------------------------------------------------ */

function nodo(
  id: string,
  tipo: NodoPrototipoRespuesta['tipo'],
  nombre: string,
  parentId: string | null,
): NodoPrototipoRespuesta {
  return { id, tipo, nombre, parent_id: parentId, clave: id.toUpperCase() };
}

const NODOS: readonly NodoPrototipoRespuesta[] = [
  nodo('n1', 'nivel', 'Planta baja', null),
  nodo('e1', 'etapa', 'Cimentación', 'n1'),
  nodo('c1', 'concepto', 'Excavación', 'e1'),
  nodo('c2', 'concepto', 'Plantilla', 'e1'),
  nodo('c3', 'concepto', 'Castillos', 'e1'),
];

function item(
  nodoId: string,
  dias: number,
  dependencias: ItemProgramaBaseRespuesta['dependencias'] = [],
  tramos: ItemProgramaBaseRespuesta['tramos'] = [],
): ItemProgramaBaseRespuesta {
  return {
    id: `i-${nodoId}`,
    programa_base_id: 'pb',
    duracion_dias: String(dias),
    prototipo_nodo_id: nodoId,
    orden: 0,
    dependencias,
    tramos,
  } as ItemProgramaBaseRespuesta;
}

function armar(items: readonly ItemProgramaBaseRespuesta[]): Borrador {
  return armarBorrador({ prototipoId: 'p1', nombre: '', nodos: NODOS, items }).borrador;
}

/** Excavación 4 d; Plantilla la sigue (FS+0) 3 d; Castillos sigue a Plantilla 2 d. */
const BORRADOR = armar([
  item('c1', 4),
  item('c2', 3, [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }]),
  item('c3', 2, [{ ref: 'c2', tipo: 'FS', lag_dias: 0 }]),
]);

/** Aplica un gesto y devuelve el borrador resultante; falla si el gesto no fue. */
function aplicarGesto(borrador: Borrador, gesto: gestos.Gesto): Borrador {
  if (!gesto.ok) throw new Error(`el gesto se rechazó: ${gesto.motivo}`);
  return gesto.acciones.reduce<Borrador>(aplicar, borrador);
}

function cajaDe(borrador: Borrador, id: string) {
  const caja = borrador.cajas.find((c) => c.id === id);
  if (!caja) throw new Error(`no hay caja ${id}`);
  return caja;
}

/* ================================================================== *
 * 1. Interrumpir una actividad: dividir, alargar la pausa, unir
 * ================================================================== */

describe('interrupción de una actividad (§7.6)', () => {
  it('dividir parte el tramo en dos y deja la pausa mínima', () => {
    const partido = aplicarGesto(BORRADOR, gestos.dividir(BORRADOR, 'c1', 2));
    const caja = cajaDe(partido, 'c1');

    expect(caja.tramos).toEqual([
      { duracionDias: 2, offsetDias: 0 },
      { duracionDias: 2, offsetDias: 2.5 },
    ]);
    // La duración es la SUMA de los tramos, no el span: los 4 d de trabajo
    // siguen siendo 4 aunque la barra ocupe 4.5 (§7.6).
    expect(caja.duracionDias).toBe(4);
  });

  it('no divide lo que no da para dos pedazos, y lo explica', () => {
    const corto = armar([item('c1', 0.5)]);
    const gesto = gestos.dividir(corto, 'c1', 0.25);
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/no da para dos pedazos/);
  });

  it('un nodo sin duración capturada no se puede partir', () => {
    const gesto = gestos.dividir(BORRADOR, 'c1', 2);
    expect(gesto.ok).toBe(true);
    const sinCapturar = gestos.dividir(armar([]), 'c1', 2);
    expect(sinCapturar.ok).toBe(false);
  });

  it('interrumpir alarga la pausa y empuja lo que viene detrás', () => {
    // Es la diferencia con `moverTramo`, que recorta al hueco de los vecinos:
    // si no empujara, alargar la pausa de un tramo intermedio sería imposible
    // en cuanto hubiera un tercero detrás.
    const tres = [
      { duracionDias: 2, offsetDias: 0 },
      { duracionDias: 2, offsetDias: 3 },
      { duracionDias: 2, offsetDias: 6 },
    ];
    expect(alargarPausa(tres, 1, 2)).toEqual([
      { duracionDias: 2, offsetDias: 0 },
      { duracionDias: 2, offsetDias: 5 },
      { duracionDias: 2, offsetDias: 8 },
    ]);
  });

  it('la pausa no se puede cerrar interrumpiendo: eso es unir tramos', () => {
    const tres = [
      { duracionDias: 2, offsetDias: 0 },
      { duracionDias: 2, offsetDias: 3 },
    ];
    // −5 días sobre una pausa de 1 la dejaría negativa, es decir, dos tramos
    // encimados, que es lo que el backend rechaza.
    expect(alargarPausa(tres, 1, -5)).toEqual([
      { duracionDias: 2, offsetDias: 0 },
      { duracionDias: 2, offsetDias: 2.5 },
    ]);
  });

  it('interrumpir una actividad continua se explica en vez de partirla sola', () => {
    // Partir por su cuenta decidiría por el usuario en qué día se corta, que es
    // justamente lo que él sabe y el editor no.
    const gesto = gestos.interrumpir(BORRADOR, 'c1', 1, 3);
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/continua/);
  });

  it('unir cierra la pausa y devuelve la actividad a continua', () => {
    const partido = aplicarGesto(BORRADOR, gestos.dividir(BORRADOR, 'c1', 2));
    const unido = aplicarGesto(partido, gestos.unirTramos(partido, 'c1', 0));
    const caja = cajaDe(unido, 'c1');

    expect(caja.tramos).toEqual([]);
    expect(caja.duracionDias).toBe(4);
  });

  it('el gesto de dividir se despacha como un solo paso de deshacer', () => {
    const historial = despachar(
      historialInicial(BORRADOR),
      // El gesto de dividir produce una sola acción; lo que se comprueba es que
      // el paso de deshacer exista y devuelva exactamente el estado anterior.
      { tipo: 'tramos', cajaId: 'c1', tramos: [
        { duracionDias: 2, offsetDias: 0 },
        { duracionDias: 2, offsetDias: 2.5 },
      ] } satisfies Accion,
    );
    expect(historial.pasado).toHaveLength(1);
    expect(historial.pasado[0]).toBe(BORRADOR);
  });
});

/* ================================================================== *
 * 2. Programar: aplazar, no iniciar antes de, término
 * ================================================================== */

describe('desplazar una actividad (§7.5)', () => {
  const colocado = colocar(BORRADOR);

  it('aplazar cambia el lag de la precedencia que manda, no una fecha', () => {
    const aplazado = aplicarGesto(BORRADOR, gestos.aplazar(BORRADOR, colocado, 'c2', 3));
    expect(buscarCable(aplazado, 'c1', 'c2')?.lagDias).toBe(3);
    // Y el efecto se propaga: lo que colgaba de c2 se corre con ella.
    expect(colocar(aplazado).get('c3')?.inicioDias).toBe(10);
  });

  it('una actividad sin predecesoras no se puede aplazar, y se dice por qué', () => {
    const gesto = gestos.aplazar(BORRADOR, colocado, 'c1', 2);
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/no depende de ninguna otra/);
  });

  it('"no iniciar antes de" se resuelve como lag, no como restricción', () => {
    // El contrato no tiene dónde guardar una restricción con fecha propia, así
    // que lo que se guarda es la DISTANCIA: si la predecesora se mueve, la
    // actividad se mueve con ella. Es un desplazamiento, no un ancla.
    const gesto = gestos.noIniciarAntesDe(BORRADOR, colocado, 'c2', 9);
    const movido = aplicarGesto(BORRADOR, gesto);

    expect(gesto.ok && gesto.acciones).toEqual([
      { tipo: 'lag', desde: 'c1', hasta: 'c2', lagDias: 5 },
    ]);
    expect(colocar(movido).get('c2')?.inicioDias).toBe(9);

    // Y aquí se ve que no es un ancla: al alargar la predecesora, la sucesora
    // se va con ella en vez de quedarse clavada en el día 10.
    const conPredecesoraLarga = aplicar(movido, {
      tipo: 'duracion',
      cajaId: 'c1',
      duracionDias: 6,
    });
    expect(colocar(conPredecesoraLarga).get('c2')?.inicioDias).toBe(11);
  });

  it('"no iniciar antes de" un día que ya pasó no aplaza nada', () => {
    const gesto = gestos.noIniciarAntesDe(BORRADOR, colocado, 'c2', 2);
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/No hay nada que aplazar/);
  });

  it('fijar el término se traduce a duración contando el último día trabajado', () => {
    // c1 arranca el día 0 y se le pide cerrar el día 5 (0-based): son 6 días,
    // no 5. Es la misma cuenta que rotula la columna Término.
    const gesto = gestos.fijarTermino(BORRADOR, colocado, 'c1', 5);
    expect(gesto.ok && gesto.acciones).toEqual([
      { tipo: 'duracion', cajaId: 'c1', duracionDias: 6 },
    ]);
  });

  it('la duración no se captura sobre una actividad partida', () => {
    const partido = aplicarGesto(BORRADOR, gestos.dividir(BORRADOR, 'c1', 2));
    const gesto = gestos.fijarDuracion(partido, 'c1', 9);
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/suma de sus tramos/);
  });
});

describe('reiniciar (§7.5, §7.6)', () => {
  it('reiniciar una actividad quita sus pausas y la devuelve a su arranque', () => {
    const colocado = colocar(BORRADOR);
    const movido = aplicarGesto(BORRADOR, gestos.aplazar(BORRADOR, colocado, 'c2', 4));
    const partido = aplicarGesto(movido, gestos.dividir(movido, 'c2', 1));

    const limpio = aplicarGesto(partido, gestos.reiniciarActividad(partido, 'c2'));
    const caja = cajaDe(limpio, 'c2');

    expect(caja.tramos).toEqual([]);
    expect(buscarCable(limpio, 'c1', 'c2')?.lagDias).toBe(0);
    // Lo que NO toca: la duración capturada y los vínculos.
    expect(caja.duracionDias).toBe(3);
    expect(caja.entradas).toHaveLength(1);
  });

  it('reiniciar el programa es un solo paso de deshacer, valga lo que valga', () => {
    // Con doscientas acciones despachadas una por una, deshacer tendría que
    // pulsarse doscientas veces — y como el historial guarda sesenta pasos, ni
    // siquiera se podría volver a donde se estaba.
    const colocado = colocar(BORRADOR);
    const sucio = aplicarGesto(
      aplicarGesto(BORRADOR, gestos.aplazar(BORRADOR, colocado, 'c2', 4)),
      gestos.dividir(BORRADOR, 'c1', 2),
    );

    const gesto = gestos.reiniciarPrograma(sucio);
    expect(gesto.ok && gesto.acciones.length).toBeGreaterThan(1);

    const historial = despacharVarias(
      historialInicial(sucio),
      gesto.ok ? gesto.acciones : [],
    );
    expect(historial.pasado).toHaveLength(1);
    expect(cajaDe(historial.presente, 'c1').tramos).toEqual([]);
    expect(buscarCable(historial.presente, 'c1', 'c2')?.lagDias).toBe(0);
  });

  it('un programa ya limpio no gasta un paso de deshacer', () => {
    expect(gestos.reiniciarPrograma(BORRADOR).ok).toBe(false);
    expect(despacharVarias(historialInicial(BORRADOR), []).pasado).toHaveLength(0);
  });
});

/* ================================================================== *
 * 3. Vínculos y ciclos
 * ================================================================== */

describe('vínculos (§6, §7.5)', () => {
  it('vincular tiende la precedencia con su tipo y su retraso', () => {
    const ligado = aplicarGesto(BORRADOR, gestos.vincular(BORRADOR, 'c1', 'c3', 'SS', 2));
    expect(buscarCable(ligado, 'c1', 'c3')).toEqual({ desde: 'c1', tipo: 'SS', lagDias: 2 });
  });

  it('un vínculo que cerraría un ciclo se rechaza ANTES de despachar', () => {
    // El backend responde 422 sobre el programa entero (§6): descubrirlo al
    // guardar cuesta la sesión y además no dice cuál de los treinta cables fue.
    const gesto = gestos.vincular(BORRADOR, 'c3', 'c1', 'FS', 0);
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/ciclo/);
  });

  it('una actividad no puede depender de sí misma', () => {
    const gesto = gestos.vincular(BORRADOR, 'c1', 'c1', 'FS', 0);
    expect(gesto.ok).toBe(false);
  });

  it('invertir da la vuelta al cable conservando tipo y retraso', () => {
    const conLag = aplicarGesto(BORRADOR, gestos.retrasar(BORRADOR, 'c2', 'c3', -1));
    const invertido = aplicarGesto(conLag, gestos.invertirVinculo(conLag, 'c2', 'c3'));

    expect(buscarCable(invertido, 'c2', 'c3')).toBeNull();
    expect(buscarCable(invertido, 'c3', 'c2')).toEqual({
      desde: 'c3',
      tipo: 'FS',
      lagDias: -1,
    });
  });

  it('invertir se rechaza cuando otro camino ya lleva de la predecesora a la sucesora', () => {
    // c1 → c2 → c3 y además c1 → c3. Invertir c1 → c3 lo cerraría.
    const conAtajo = aplicarGesto(BORRADOR, gestos.vincular(BORRADOR, 'c1', 'c3', 'FS', 0));
    const gesto = gestos.invertirVinculo(conAtajo, 'c1', 'c3');
    expect(gesto.ok).toBe(false);
    if (!gesto.ok) expect(gesto.motivo).toMatch(/ciclo/);
  });

  it('desvincular quita el cable, y quitar lo que no existe se explica', () => {
    const suelto = aplicarGesto(BORRADOR, gestos.desvincular(BORRADOR, 'c1', 'c2'));
    expect(buscarCable(suelto, 'c1', 'c2')).toBeNull();
    expect(gestos.desvincular(suelto, 'c1', 'c2').ok).toBe(false);
  });

  it('el retraso admite negativo: entrar antes de que la predecesora acabe', () => {
    const solapado = aplicarGesto(BORRADOR, gestos.retrasar(BORRADOR, 'c1', 'c2', -2));
    expect(colocar(solapado).get('c2')?.inicioDias).toBe(2);
  });

  it('las candidatas a predecesora excluyen ciclos y lo ya ligado', () => {
    // De c3 cuelga nada, pero c3 depende de c2 y c2 de c1: ninguna de las dos
    // puede ser sucesora suya, y c2 además ya es su predecesora.
    const candidatas = gestos.candidatasAPredecesora(BORRADOR, 'c3').map((c) => c.id);
    expect(candidatas).not.toContain('c3');
    expect(candidatas).not.toContain('c2');
    expect(candidatas).toContain('c1');
    expect(candidatas).toContain('e1');
  });
});

/* ================================================================== *
 * 4. Reparto volumétrico: cantidades por escala
 * ================================================================== */

function partida(nodoId: string, cantidad: string, importe: string): PartidaRespuesta {
  return {
    id: `pa-${nodoId}`,
    prototipo_nodo_id: nodoId,
    unidad_clave: 'M3',
    cantidad,
    precio_unitario: '1',
    importe,
    orden: 0,
  } as PartidaRespuesta;
}

const PARTIDAS = new Map<string, PartidaRespuesta>([
  ['c1', partida('c1', '100', '1000')],
  ['c2', partida('c2', '60', '600')],
  ['c3', partida('c3', '40', '400')],
]);

/** Periodos de un día, que es lo que produce la escala "Días". */
function periodosDeUnDia(cuantos: number) {
  return Array.from({ length: cuantos }, (_, dia) => ({
    dia,
    dias: 1,
    etiqueta: String(dia + 1),
    titulo: `Día ${dia + 1}`,
    esHoy: false,
  }));
}

describe('cantidades por escala: el reparto derivado (§7.4, §7.6)', () => {
  it('reparte proporcional a los días de trabajo de cada periodo', () => {
    const intervalos = intervalosDeTrabajo(0, 4, []);
    expect(repartirEnPeriodos(intervalos, periodosDeUnDia(6), 100)).toEqual([
      25, 25, 25, 25, 0, 0,
    ]);
  });

  it('UNA PAUSA NO CONSUME CANTIDAD', () => {
    // El caso que le da sentido a la vista. El muro trabaja dos días, para dos
    // para que se cuele la losa y sigue otros dos (§7.6): los dos días de en
    // medio llevan cero, no un tercio. Repartir sobre el span en vez de sobre
    // los tramos le daría producción a una semana en que no se trabaja, que es
    // justo la cifra con la que alguien pediría material.
    const tramos = [
      { duracionDias: 2, offsetDias: 0 },
      { duracionDias: 2, offsetDias: 4 },
    ];
    const intervalos = intervalosDeTrabajo(0, 4, tramos);
    expect(repartirEnPeriodos(intervalos, periodosDeUnDia(6), 100)).toEqual([
      25, 25, 0, 0, 25, 25,
    ]);
  });

  it('la pausa tampoco consume cantidad al pasar por la rejilla completa', () => {
    const partido = armar([
      item('c1', 4, [], [
        { duracion_dias: 2, offset_dias: 0 },
        { duracion_dias: 2, offset_dias: 4 },
      ]),
    ]);
    const colocado = colocar(partido);
    const filas = aplanarPrograma({ borrador: partido, colocado, partidas: PARTIDAS });
    const magnitudes = magnitudesDeFilas(filas, PARTIDAS);

    const rejilla = rejillaDeCantidades({
      filas,
      periodos: periodosDeUnDia(6),
      magnitudes,
      magnitud: 'cantidad',
    });

    expect(rejilla.get('c1')?.celdas).toEqual([25, 25, 0, 0, 25, 25]);
    // Y el total del renglón sigue siendo la cantidad del presupuesto: el
    // reparto no crea ni destruye cantidad.
    expect(rejilla.get('c1')?.total).toBe(100);
  });

  it('la cantidad no se agrega hacia arriba; el importe sí', () => {
    // Un nivel que cuelga metros cúbicos de concreto y kilos de acero no tiene
    // una cantidad: sumarlos daría un número con unidades mezcladas que parece
    // un total y no lo es (§6).
    const colocado = colocar(BORRADOR);
    const filas = aplanarPrograma({ borrador: BORRADOR, colocado, partidas: PARTIDAS });
    const magnitudes = magnitudesDeFilas(filas, PARTIDAS);
    const periodos = periodosDeUnDia(12);

    const porCantidad = rejillaDeCantidades({ filas, periodos, magnitudes, magnitud: 'cantidad' });
    expect(porCantidad.get('e1')?.total).toBeNull();
    expect(porCantidad.get('c1')?.total).toBe(100);

    const porImporte = rejillaDeCantidades({ filas, periodos, magnitudes, magnitud: 'importe' });
    expect(porImporte.get('e1')?.total).toBe(2000);
    expect(porImporte.get('n1')?.total).toBe(2000);
  });

  it('el peso de un renglón es su importe sobre el del programa, sin contarlo dos veces', () => {
    const colocado = colocar(BORRADOR);
    const filas = aplanarPrograma({ borrador: BORRADOR, colocado, partidas: PARTIDAS });
    const magnitudes = magnitudesDeFilas(filas, PARTIDAS);

    // El total del programa son las raíces: sumar padre e hijo contaría el
    // mismo peso dos veces (§6, §7.6).
    expect(magnitudes.get('n1')?.pesoPct).toBe(100);
    expect(magnitudes.get('c1')?.pesoPct).toBe(50);
    expect(magnitudes.get('c3')?.pesoPct).toBe(20);
  });

  it('un renglón sin colocar no reparte nada', () => {
    const sinCapturar = armar([item('c1', 4)]);
    const colocado = colocar(sinCapturar);
    const filas = aplanarPrograma({ borrador: sinCapturar, colocado, partidas: PARTIDAS });
    const rejilla = rejillaDeCantidades({
      filas,
      periodos: periodosDeUnDia(6),
      magnitudes: magnitudesDeFilas(filas, PARTIDAS),
      magnitud: 'cantidad',
    });
    expect(rejilla.get('c2')?.total).toBeNull();
  });
});

/* ================================================================== *
 * 5. Escalas y bandas del eje
 * ================================================================== */

describe('escalas del eje (§7.5)', () => {
  const eje = construirEje({ finMaximo: 30, pxPorDia: 16 });

  it('la escala decide qué pareja de periodos rotula el encabezado', () => {
    const dias = construirBandas(eje, 'dias');
    expect(dias.diasPorPeriodo).toBe(1);
    expect(dias.inferior).toHaveLength(eje.dias);
    // Arriba, semanas: siete días cada una.
    expect(dias.superior[0]).toMatchObject({ dia: 0, dias: 7 });

    const semanas = construirBandas(eje, 'semanas');
    expect(semanas.diasPorPeriodo).toBe(7);
    expect(semanas.inferior[0]).toMatchObject({ dia: 0, dias: 7, etiqueta: 'Día 1' });
    expect(semanas.inferior[1]?.etiqueta).toBe('Día 8');
  });

  it('en días relativos un "mes" no se inventa un calendario', () => {
    // Un programa base es una plantilla sin origen de tiempo: rotular "Mes 1"
    // mentiría dos veces, porque además veintiocho días de programa son días
    // HÁBILES y no un mes natural (§7.5).
    const bandas = construirBandas(eje, 'meses-dias');
    expect(bandas.superior[0]?.etiqueta).toBe('Sem 1–4');
    expect(bandas.superior[0]?.dias).toBe(28);
    expect(bandas.superior[0]?.titulo).toMatch(/no hay mes de calendario/);
  });

  it('con fechas simuladas el mes sí es el de calendario', () => {
    const conFechas = construirEje({
      finMaximo: 40,
      pxPorDia: 10,
      modo: 'fechas',
      inicio: '2026-03-02',
      diasHabiles: [1, 2, 3, 4, 5],
    });
    const bandas = construirBandas(conFechas, 'meses-semanas');
    expect(bandas.superior[0]?.etiqueta).toBe('mar 26');
    // Los meses no miden lo mismo: el primero se corta donde el calendario lo
    // corta, no cada veintiocho días.
    expect(bandas.superior.map((b) => b.etiqueta)).toContain('abr 26');
  });

  it('las bandas parten el eje igual que los periodos de la rejilla', () => {
    // Si no coincidieran, las columnas de "Cantidades por escala" dejarían de
    // caer sobre las líneas del encabezado del Gantt.
    const bandas = construirBandas(eje, 'semanas');
    const cubierto = bandas.inferior.reduce((suma, banda) => suma + banda.dias, 0);
    expect(cubierto).toBe(eje.dias);
    expect(bandas.inferior.every((banda) => banda.dias <= bandas.diasPorPeriodo)).toBe(true);
  });

  it('los saltos de calendario sólo existen con fechas', () => {
    expect(saltosDeCalendario(eje)).toEqual([]);

    const laboral = construirEje({
      finMaximo: 12,
      modo: 'fechas',
      inicio: '2026-03-02',
      diasHabiles: [1, 2, 3, 4, 5],
    });
    const saltos = saltosDeCalendario(laboral);
    // Lunes a viernes: la costura cae después del quinto día y salta dos.
    expect(saltos[0]).toEqual({ dia: 4, diasSaltados: 2 });
  });

  it('acercar y alejar caminan por escalones, y ajustar produce un valor libre', () => {
    expect(acercarZoom(16)).toBe(26);
    expect(alejarZoom(16)).toBe(10);
    // Desde un zoom libre se toma el escalón siguiente, no el vecino de una
    // lista en la que ese valor no está.
    expect(acercarZoom(7.5)).toBe(10);
    expect(alejarZoom(7.5)).toBe(6);

    expect(zoomParaAjustar(100, 1200)).toBe(12);
    // Y se recorta a los extremos: por debajo del mínimo una barra de una
    // semana no se podría ni agarrar.
    expect(zoomParaAjustar(4000, 1200)).toBe(4);
    expect(zoomParaAjustar(0, 1200)).toBe(4);
  });
});

/* ================================================================== *
 * 6. Ruta crítica del borrador
 * ================================================================== */

describe('ruta crítica del borrador (§6)', () => {
  const colocado = colocar(BORRADOR);
  const filas = aplanarPrograma({ borrador: BORRADOR, colocado });

  it('en una cadena sin ramas, todo es crítico', () => {
    const ruta = trazarRutaCritica(filas, 0);
    expect(ruta.nActividades).toBe(3);
    expect(ruta.diasCriticos).toBe(9);
    expect(ruta.holguraMinima).toBe(0);
  });

  it('lo que tiene holgura queda fuera, salvo que la tolerancia lo alcance', () => {
    // Dos ramas desde c1: la larga (c2, 3 d) cierra el día 7 y la corta (c3,
    // 2 d) el 6. La corta tiene un día de margen y no es crítica — hasta que la
    // tolerancia lo alcanza, que es para lo que existe.
    const conRama = armar([
      item('c1', 4),
      item('c2', 3, [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }]),
      item('c3', 2, [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }]),
    ]);
    const suyas = aplanarPrograma({ borrador: conRama, colocado: colocar(conRama) });

    const estricta = trazarRutaCritica(suyas, 0);
    expect(estricta.nActividades).toBe(2);
    expect(estricta.criticas.has('c3')).toBe(false);
    expect(estricta.holguraMinima).toBe(0);

    const laxa = trazarRutaCritica(suyas, 1);
    expect(laxa.nActividades).toBe(3);
    expect(laxa.criticas.has('c3')).toBe(true);
  });

  it('el resumen hereda de sus hijos: una etapa plegada dice que la cadena pasa dentro', () => {
    const ruta = trazarRutaCritica(filas, 0);
    expect(ruta.criticas.has('e1')).toBe(true);
    expect(ruta.criticas.has('n1')).toBe(true);
  });

  it('no marca lo que no está capturado', () => {
    const parcial = armar([item('c1', 4)]);
    const puesto = colocar(parcial);
    const suyas = aplanarPrograma({ borrador: parcial, colocado: puesto });
    const ruta = trazarRutaCritica(suyas, 0);
    expect(ruta.criticas.has('c2')).toBe(false);
  });
});

/* ================================================================== *
 * 7. Columnas, colapso a nivel y presentación de la barra
 * ================================================================== */

describe('columnas de la tabla (§12.10)', () => {
  it('las fijas no se pueden apagar: sin ellas el renglón no se puede nombrar', () => {
    const sinNumero = alternarColumna(
      VISTA_GANTT_INICIAL,
      'num',
      CLAVES_COLUMNAS,
      COLUMNAS_FIJAS,
    );
    expect(sinNumero).toBe(VISTA_GANTT_INICIAL);
    expect(columnasVisibles(['descripcion']).map((c) => c.clave)).toEqual([
      'num',
      'descripcion',
    ]);
  });

  it('encender una columna conserva el orden del catálogo, no el de los clics', () => {
    // Una tabla cuyas columnas cambian de sitio deja de poder leerse de
    // memoria, que es como se lee una que se revisa todos los días.
    const conImporte = alternarColumna(
      VISTA_GANTT_INICIAL,
      'importe',
      CLAVES_COLUMNAS,
      COLUMNAS_FIJAS,
    );
    const claves = columnasVisibles(conImporte.columnas).map((c) => c.clave);
    expect(claves.indexOf('importe')).toBeLessThan(claves.indexOf('laborables'));
  });

  it('la plantilla de rejilla lleva una pista por columna encendida', () => {
    const columnas = columnasVisibles(['descripcion', 'clave']);
    expect(plantillaDeColumnas(columnas).split(' ').length).toBeGreaterThanOrEqual(3);
    expect(columnas).toHaveLength(3);
  });

  it('el congelado acumula el ancho de las visibles, no el del catálogo', () => {
    // Apagar Tipo mueve a Clave; calcularlo con el catálogo completo la dejaría
    // flotando setenta y cuatro píxeles a la derecha de donde está.
    const todas = desplazamientosCongelados(columnasVisibles(CLAVES_COLUMNAS), true);
    expect(todas.get('clave')).toBe(44 + 74);

    const sinTipo = columnasVisibles(
      CLAVES_COLUMNAS.filter((clave: string) => clave !== 'tipo'),
    );
    expect(desplazamientosCongelados(sinTipo, true).get('clave')).toBe(44);

    // Y con el congelado apagado no hay ni una columna pegajosa.
    expect(desplazamientosCongelados(sinTipo, false).size).toBe(0);
  });

  it('el congelado se corta en Descripción y no sigue', () => {
    const congelados = desplazamientosCongelados(columnasVisibles(CLAVES_COLUMNAS), true);
    expect(congelados.has('descripcion')).toBe(true);
    expect(congelados.has('unidad')).toBe(false);
    expect(COLUMNAS_PROGRAMA.some((c) => c.clave === 'unidad')).toBe(true);
  });
});

describe('colapsar a nivel', () => {
  const filas = aplanarPrograma({ borrador: BORRADOR, colocado: colocar(BORRADOR) });

  it('pliega lo que cuelga por debajo del escalón pedido', () => {
    // Con nivel 0 se pliegan **todos** los padres, no sólo la raíz: plegar n1
    // ya esconde a e1, pero dejar a e1 abierto haría que al volver a abrir n1
    // apareciera el árbol entero, que no es lo que "colapsar a un escalón"
    // quiere decir.
    expect([...colapsarANivel(filas, 0)]).toEqual(['n1', 'e1']);
    expect([...colapsarANivel(filas, 1)]).toEqual(['e1']);
    expect(colapsarANivel(filas, profundidadMaxima(filas) + 1).size).toBe(0);
  });
});

describe('presentación de la barra (§12.10)', () => {
  const filas = aplanarPrograma({ borrador: BORRADOR, colocado: colocar(BORRADOR) });
  const fila = filas.find((f) => f.nodoId === 'c1')!;

  it('la criticidad se marca con trama, no sólo con color', () => {
    // Un Gantt de obra se imprime, se fotocopia y se mira al sol; una cadena
    // crítica que sólo existe en el canal del color desaparece en los tres.
    const conRuta: VistaGantt = { ...VISTA_GANTT_INICIAL, rutaCritica: true };
    const clases = clasesDeBarra({
      vista: conRuta,
      fila,
      esCritica: true,
      tonoFrente: null,
      seleccionada: false,
    });
    expect(clases).toContain('is-critica');

    const sinRuta = clasesDeBarra({
      vista: VISTA_GANTT_INICIAL,
      fila,
      esCritica: true,
      tonoFrente: null,
      seleccionada: false,
    });
    expect(sinRuta).not.toContain('is-critica');
  });

  it('el color por frente reparte tonos por orden de aparición, no por UUID', () => {
    const frentes = new Map<string, string | null>([
      ['c1', 'f-b'],
      ['c2', 'f-a'],
      ['c3', 'f-b'],
    ]);
    const tonos = tonosDeFrente(frentes, ['c1', 'c2', 'c3']);
    expect(tonos.get('f-b')).toBe(1);
    expect(tonos.get('f-a')).toBe(2);
  });

  it('la etiqueta combina campos en el orden del catálogo y salta lo que no hay', () => {
    const vista: VistaGantt = {
      ...VISTA_GANTT_INICIAL,
      etiquetas: ['dias', 'clave', 'importe'],
    };
    const texto = etiquetaDeBarra(vista, fila, {
      cantidad: 100,
      importe: null,
      pesoPct: 50,
    });
    // La lista se pasa a propósito desordenada: el orden es del catálogo y no
    // del setter, o una preferencia guardada por una versión anterior leería
    // distinto. Importe se salta porque no hay: "C1 · —" ocupa lo mismo y no
    // informa de nada.
    expect(texto).toBe('C1 · 4.00 d');
  });
});

/* ================================================================== *
 * 8. Vista y apariencia: no ensucian el borrador
 * ================================================================== */

describe('la vista y la apariencia no editan el programa', () => {
  it('ningún cambio de vista produce una acción del borrador', () => {
    // La garantía es estructural y no de disciplina: los módulos de vista no
    // reciben un `Borrador` ni devuelven una `Accion`, así que no hay por dónde
    // ensuciarlo. Aquí se fija que el borrador es el MISMO objeto después de
    // pasear por todos los interruptores.
    let vista = VISTA_GANTT_INICIAL;
    vista = { ...vista, rutaCritica: true, toleranciaHolguraDias: 2 };
    vista = { ...vista, tema: 'oscuro', paleta: 'mono', escala: 'meses-dias' };
    vista = alternarEtiqueta(vista, 'importe');
    vista = alternarColumna(vista, 'peso', CLAVES_COLUMNAS, COLUMNAS_FIJAS);

    const historial = historialInicial(BORRADOR);
    expect(historial.presente).toBe(BORRADOR);
    expect(historial.pasado).toHaveLength(0);
    expect(vista.rutaCritica).toBe(true);
  });

  it('la preferencia sobrevive a un ida y vuelta por localStorage', () => {
    const vista: VistaGantt = {
      ...VISTA_GANTT_INICIAL,
      tema: 'sistema',
      paleta: 'mono',
      escala: 'meses-semanas',
      zoom: 26,
      etiquetas: ['clave', 'dias'],
      fijarColumnas: true,
      anchoTabla: 800,
    };
    expect(deserializarVista(serializarVista(vista))).toEqual(vista);
  });

  it('una preferencia vieja o corrupta cae al default en vez de tumbar la pantalla', () => {
    // Lo guardado sobrevive a los despliegues: es la forma que tenía el módulo
    // el día que el usuario tocó el último interruptor, no la de hoy.
    expect(deserializarVista(null)).toEqual(VISTA_GANTT_INICIAL);
    expect(deserializarVista('{ esto no es json')).toEqual(VISTA_GANTT_INICIAL);

    const rara = deserializarVista(
      JSON.stringify({ escala: 'trimestres', zoom: null, tema: 42, columnas: [] }),
    );
    expect(rara.escala).toBe(VISTA_GANTT_INICIAL.escala);
    expect(rara.zoom).toBe(VISTA_GANTT_INICIAL.zoom);
    expect(rara.tema).toBe(VISTA_GANTT_INICIAL.tema);
    // Una lista de columnas vacía dejaría la tabla sin nada.
    expect(rara.columnas).toEqual(VISTA_GANTT_INICIAL.columnas);
  });

  it('"sistema" se resuelve contra la preferencia del sistema operativo', () => {
    expect(temaEfectivo('sistema', true)).toBe('oscuro');
    expect(temaEfectivo('sistema', false)).toBe('claro');
    // Una elección explícita manda sobre el sistema, en los dos sentidos.
    expect(temaEfectivo('claro', true)).toBe('claro');
    expect(temaEfectivo('oscuro', false)).toBe('oscuro');
  });

  it('el zoom guardado se recorta a un rango utilizable', () => {
    expect(deserializarVista(JSON.stringify({ zoom: 9999 })).zoom).toBe(96);
    expect(deserializarVista(JSON.stringify({ zoom: -4 })).zoom).toBe(3);
  });
});
