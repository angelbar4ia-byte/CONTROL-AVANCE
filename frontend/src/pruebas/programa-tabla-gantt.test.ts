/**
 * Editor de programa base en tabla + Gantt: aplanado, rollup, arrastre, eje y
 * sincronía de scroll.
 *
 * Lo que se fija aquí es **comportamiento**, no pintura. Cinco cosas, y las
 * cinco son las que rompen la vista en silencio:
 *
 *  1. El **aplanado con colapso**: que plegar una etapa esconda también los
 *     conceptos que cuelgan de sus niveles, y que la numeración de renglón sea
 *     la del árbol completo y no la de lo que se ve —si se renumerara al
 *     plegar, el número dejaría de servir para nombrar una actividad en voz
 *     alta.
 *  2. El **rollup**: que la barra resumen abarque a sus hijos y que sus dos
 *     cifras de días —laborables y calendario— sean las que dicen `tramos.ts`
 *     y no la misma repetida.
 *  3. El **arrastre**: que mover cambie el lag de la predecesora que manda —la
 *     única forma de expresarlo en un contrato sin fechas—, que estirar cambie
 *     la duración, y que los dos topen donde el modelo topa.
 *  4. El **cambio de eje**: que los días relativos no dependan de ningún reloj
 *     y que la simulación de fechas salte los días inhábiles.
 *  5. La **sincronía de scroll**: que el eco no rebote entre las dos mitades.
 *
 * Todo se prueba sin render: la aritmética vive fuera de los componentes
 * (§12.11), que es justamente lo que permite fijarla aquí.
 */

import { describe, expect, it } from 'vitest';

import type { ItemProgramaBaseRespuesta, NodoPrototipoRespuesta } from '@/api/generado/modelo';
import {
  diasDeDesplazamiento,
  empezarArrastre,
  ataduraDe,
  previsualizar,
  resolverArrastre,
} from '@/programacion/arrastre';
import { comoPolilinea, trazarConectores } from '@/programacion/conectores';
import {
  ALTO_FILA,
  calendarioDelPrograma,
  construirEje,
  diaDeX,
  etiquetaDeDia,
  indiceDeFecha,
  xDeDia,
} from '@/programacion/ejePrograma';
import {
  aplanarPrograma,
  colapsadosDeEntrada,
  filtrarPorTexto,
  holguraDelBorrador,
  resumirDescendientes,
  resumirFilas,
  todosLosPadres,
} from '@/programacion/filasPrograma';
import { armarBorrador, type Borrador } from '@/programacion/grafo';
import { alternarColapso, visiblesEnJerarquia } from '@/programacion/jerarquia';
import { colocar, duracionDelPrograma } from '@/programacion/planificacion';
import { SINCRONIA_INICIAL, alDesplazar, reiniciarSincronia } from '@/programacion/sincronia';

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

/** Planta baja con dos etapas; la primera con dos conceptos, la segunda con uno. */
const NODOS: readonly NodoPrototipoRespuesta[] = [
  nodo('n1', 'nivel', 'Planta baja', null),
  nodo('e1', 'etapa', 'Cimentación', 'n1'),
  nodo('c1', 'concepto', 'Excavación', 'e1'),
  nodo('c2', 'concepto', 'Plantilla', 'e1'),
  nodo('e2', 'etapa', 'Estructura', 'n1'),
  nodo('c3', 'concepto', 'Castillos', 'e2'),
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

/** Excavación 3 d; Plantilla la sigue (FS+0) 2 d; Castillos sigue a Plantilla 4 d. */
const BORRADOR = armar([
  item('c1', 3),
  item('c2', 2, [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }]),
  item('c3', 4, [{ ref: 'c2', tipo: 'FS', lag_dias: 0 }]),
]);

function filasDe(borrador: Borrador) {
  const colocado = colocar(borrador);
  return { colocado, filas: aplanarPrograma({ borrador, colocado }) };
}

/* ------------------------------------------------------------------ *
 * 1. Aplanado, numeración y colapso
 * ------------------------------------------------------------------ */

describe('aplanado del árbol a renglones (§7.4)', () => {
  it('sale en preorden, padre antes que hijos, con su profundidad', () => {
    const { filas } = filasDe(BORRADOR);
    expect(filas.map((fila) => fila.nodoId)).toEqual(['n1', 'e1', 'c1', 'c2', 'e2', 'c3']);
    expect(filas.map((fila) => fila.profundidad)).toEqual([0, 1, 2, 2, 1, 2]);
  });

  it('numera sobre el árbol completo, no sobre lo que se ve', () => {
    // Es lo que permite decir "el 6" en voz alta y que los dos estén viendo lo
    // mismo aunque uno tenga la primera etapa plegada.
    const { filas } = filasDe(BORRADOR);
    expect(filas.map((fila) => fila.numero)).toEqual([1, 2, 3, 4, 5, 6]);

    const visibles = visiblesEnJerarquia(filas, new Set(['e1']));
    expect(visibles.map((fila) => fila.numero)).toEqual([1, 2, 5, 6]);
  });

  it('colapsar un nivel esconde a sus nietos, no sólo a sus hijos', () => {
    // El caso que un recorrido de un solo eslabón se come: al plegar el nivel,
    // sus etapas se van pero los conceptos quedarían sueltos sin encabezado.
    const { filas } = filasDe(BORRADOR);
    const visibles = visiblesEnJerarquia(filas, new Set(['n1']));
    expect(visibles.map((fila) => fila.nodoId)).toEqual(['n1']);
  });

  it('alternar el colapso no muta el conjunto que recibe', () => {
    const previos = new Set(['e1']);
    const siguientes = alternarColapso(previos, 'e2');
    expect([...previos]).toEqual(['e1']);
    expect([...siguientes].sort()).toEqual(['e1', 'e2']);
    expect([...alternarColapso(siguientes, 'e1')]).toEqual(['e2']);
  });

  it('el colapso de entrada sigue la profundidad de captura, y con concepto no pliega nada', () => {
    const { filas } = filasDe(BORRADOR);
    expect([...colapsadosDeEntrada(filas, 'etapa')].sort()).toEqual(['e1', 'e2']);
    expect([...colapsadosDeEntrada(filas, 'nivel')]).toEqual(['n1']);
    expect(colapsadosDeEntrada(filas, 'concepto').size).toBe(0);
  });

  it('plegar todo son los nodos con hijos, no todos los nodos', () => {
    const { filas } = filasDe(BORRADOR);
    expect([...todosLosPadres(filas)].sort()).toEqual(['e1', 'e2', 'n1']);
  });

  it('el filtro por texto conserva la rama, no sólo la hoja', () => {
    const { filas } = filasDe(BORRADOR);
    const encontradas = filtrarPorTexto(filas, 'castillos');
    // El concepto no sirve de nada sin saber de qué etapa y de qué nivel cuelga.
    expect(encontradas.map((fila) => fila.nodoId)).toEqual(['n1', 'e2', 'c3']);
    expect(filtrarPorTexto(filas, '').length).toBe(filas.length);
  });

  it('el filtro también busca por clave', () => {
    const { filas } = filasDe(BORRADOR);
    expect(filtrarPorTexto(filas, 'C3').map((fila) => fila.nodoId)).toEqual(['n1', 'e2', 'c3']);
  });
});

/* ------------------------------------------------------------------ *
 * 2. Rollup de las barras resumen
 * ------------------------------------------------------------------ */

describe('rollup de las barras resumen (§7.4)', () => {
  it('el resumen abarca a sus hijos y no es una fila propia', () => {
    const { filas } = filasDe(BORRADOR);
    const porId = new Map(filas.map((fila) => [fila.nodoId, fila]));

    // c1: 0→3, c2: 3→5, c3: 5→9.
    expect(porId.get('e1')).toMatchObject({ esResumen: true, inicioDias: 0, finDias: 5 });
    expect(porId.get('e2')).toMatchObject({ esResumen: true, inicioDias: 5, finDias: 9 });
    expect(porId.get('n1')).toMatchObject({ esResumen: true, inicioDias: 0, finDias: 9 });

    // Y no entra al POST como renglón propio: no tiene duración capturada.
    expect(porId.get('n1')?.capturado).toBe(false);
    expect(porId.get('c1')?.esResumen).toBe(false);
  });

  it('cuenta las hojas capturadas que cuelgan de él, a cualquier distancia', () => {
    const { filas } = filasDe(BORRADOR);
    const porId = new Map(filas.map((fila) => [fila.nodoId, fila]));
    expect(porId.get('n1')?.nHojas).toBe(3);
    expect(porId.get('e1')?.nHojas).toBe(2);
  });

  it('un nodo sin descendientes capturados no es resumen aunque tenga hijos', () => {
    // La propuesta: el árbol está entero en el borrador desde el primer
    // segundo, pero sin duraciones no hay nada que resumir.
    const { filas } = filasDe(armar([]));
    expect(filas.every((fila) => !fila.esResumen)).toBe(true);
    expect(filas.every((fila) => fila.inicioDias === null)).toBe(true);
  });

  it('días laborables es la suma de las hojas; días calendario es la ventana', () => {
    // Castillos arranca en el 5 sólo porque espera a Plantilla; su etapa mide
    // 4 días de trabajo pero su ventana también, porque no hay hueco dentro.
    // El nivel, en cambio, suma 9 de trabajo en 9 de ventana.
    const { filas } = filasDe(BORRADOR);
    const porId = new Map(filas.map((fila) => [fila.nodoId, fila]));
    expect(porId.get('n1')?.diasLaborables).toBe(9);
    expect(porId.get('n1')?.diasCalendario).toBe(9);
  });

  it('el resumen mide el span que ocupa, no la suma del trabajo de sus hojas', () => {
    // Excavación 0→3 y Castillos 10→14 con un lag de 7. La suma del trabajo
    // son 7 días, pero el nivel **ocupa** 14: con el reparto en paralelo de
    // `fijarDuracion` las ramas corren a la vez, así que la cifra que dice
    // algo del resumen es su ventana, no cuánto trabajo cuelga de él.
    const separado = armar([
      item('c1', 3),
      item('c3', 4, [{ ref: 'c1', tipo: 'FS', lag_dias: 7 }]),
    ]);
    const { filas } = filasDe(separado);
    const nivel = filas.find((fila) => fila.nodoId === 'n1');
    expect(nivel?.diasLaborables).toBe(14);
    expect(nivel?.diasCalendario).toBe(14);
  });

  it('el resumen no anuncia holgura: la holgura es de la actividad que lo cierra', () => {
    const { filas } = filasDe(BORRADOR);
    expect(filas.find((fila) => fila.nodoId === 'n1')?.holguraDias).toBeNull();
    expect(filas.find((fila) => fila.nodoId === 'c1')?.holguraDias).not.toBeNull();
  });

  it('la plantilla gruesa sigue siendo una barra normal mientras sus hijos no se capturen', () => {
    // `prototipo_nodo_id` puede apuntar a la etapa entera: es una actividad
    // como cualquiera hasta que alguien capture debajo (§7.5).
    const gruesa = armar([item('e1', 10)]);
    const soloEtapa = filasDe(gruesa).filas.find((fila) => fila.nodoId === 'e1');
    expect(soloEtapa).toMatchObject({ esResumen: false, capturado: true });
    expect(soloEtapa?.diasLaborables).toBe(10);
  });

  it('con hijos capturados el resumen manda y su cifra propia deja de dibujarse', () => {
    // Este dato ya no lo puede producir la pantalla —`fijarDuracion` vacía uno
    // de los dos lados—, pero un programa guardado antes de la herencia sí lo
    // trae. Se dibuja el resumen y no se marca nada: no hay decisión pendiente.
    const ambas = armar([item('e1', 10), item('c1', 3)]);
    const etapa = filasDe(ambas).filas.find((fila) => fila.nodoId === 'e1');
    expect(etapa).toMatchObject({ esResumen: true, capturado: true });
    expect(etapa?.diasLaborables).toBe(3);
  });

  it('los tramos separan trabajo de calendario en la propia actividad (§7.6)', () => {
    // Dos semanas de muro, para, y sigue: 4 días de trabajo en 9 de ventana.
    const partido = armar([
      item('c1', 4, [], [
        { duracion_dias: 2, offset_dias: 0 },
        { duracion_dias: 2, offset_dias: 7 },
      ]),
    ]);
    const fila = filasDe(partido).filas.find((f) => f.nodoId === 'c1');
    expect(fila?.diasLaborables).toBe(4);
    expect(fila?.diasCalendario).toBe(9);
  });

  it('resumirDescendientes no devuelve entrada para una hoja', () => {
    const colocado = colocar(BORRADOR);
    const resumenes = resumirDescendientes(BORRADOR, colocado);
    expect(resumenes.has('c1')).toBe(false);
    expect(resumenes.has('e1')).toBe(true);
  });

  it('el resumen del encabezado cuenta lo capturado, no lo propuesto', () => {
    const { filas } = filasDe(BORRADOR);
    expect(resumirFilas(filas)).toMatchObject({
      nNodos: 6,
      nCapturados: 3,
      nResumenes: 3,
      diasTotales: 9,
    });
  });
});

/* ------------------------------------------------------------------ *
 * Holgura del borrador
 * ------------------------------------------------------------------ */

describe('holgura del borrador (pasada hacia atrás)', () => {
  it('una cadena sin ramas no tiene holgura: todo es crítico', () => {
    const holguras = holguraDelBorrador(BORRADOR, colocar(BORRADOR));
    expect(holguras.get('c1')).toBe(0);
    expect(holguras.get('c2')).toBe(0);
    expect(holguras.get('c3')).toBe(0);
  });

  it('la rama corta tiene la holgura que le sobra frente a la larga', () => {
    // c1 (3 d) y c2 (1 d) arrancan juntas; c3 espera a las dos. La corta puede
    // correrse dos días sin empujar nada.
    const enParalelo = armar([
      item('c1', 3),
      item('c2', 1),
      item('c3', 4, [
        { ref: 'c1', tipo: 'FS', lag_dias: 0 },
        { ref: 'c2', tipo: 'FS', lag_dias: 0 },
      ]),
    ]);
    const holguras = holguraDelBorrador(enParalelo, colocar(enParalelo));
    expect(holguras.get('c1')).toBe(0);
    expect(holguras.get('c2')).toBe(2);
    expect(holguras.get('c3')).toBe(0);
  });

  it('con un ciclo no hay nada que recorrer y devuelve vacío', () => {
    const enCiclo = armar([
      item('c1', 2, [{ ref: 'c2', tipo: 'FS', lag_dias: 0 }]),
      item('c2', 2, [{ ref: 'c1', tipo: 'FS', lag_dias: 0 }]),
    ]);
    expect(holguraDelBorrador(enCiclo, colocar(enCiclo)).size).toBe(0);
  });
});

/* ------------------------------------------------------------------ *
 * 3. Arrastrar: mover y estirar
 * ------------------------------------------------------------------ */

describe('arrastrar una barra (§7.5, §7.6)', () => {
  const colocado = colocar(BORRADOR);
  const c2 = BORRADOR.cajas.find((caja) => caja.id === 'c2')!;
  const c1 = BORRADOR.cajas.find((caja) => caja.id === 'c1')!;

  it('la atadura es la predecesora que produce el arranque, no la primera', () => {
    // c3 espera a las dos, pero sólo una la está deteniendo de verdad.
    const dosPredecesoras = armar([
      item('c1', 3),
      item('c2', 8),
      item('c3', 2, [
        { ref: 'c1', tipo: 'FS', lag_dias: 0 },
        { ref: 'c2', tipo: 'FS', lag_dias: 0 },
      ]),
    ]);
    const caja = dosPredecesoras.cajas.find((c) => c.id === 'c3')!;
    expect(ataduraDe(caja, colocar(dosPredecesoras))?.desde).toBe('c2');
  });

  it('mover cambia el lag de la predecesora que manda', () => {
    // Es la única forma de expresar un retraso en un contrato sin fechas.
    const arrastre = empezarArrastre(c2, colocado, 'mover', 0);
    const resultado = resolverArrastre(BORRADOR, arrastre, 3);
    expect(resultado).toEqual({
      ok: true,
      dias: 3,
      accion: { tipo: 'lag', desde: 'c1', hasta: 'c2', lagDias: 3 },
    });
  });

  it('mover a la izquierda resta del lag y admite negativos', () => {
    // Un lag negativo es el traslape de MS Project: la sucesora entra antes de
    // que cierre la predecesora. `colocar` recorta al día 0 lo que se pase.
    const conLag = armar([
      item('c1', 3),
      item('c2', 2, [{ ref: 'c1', tipo: 'FS', lag_dias: 5 }]),
    ]);
    const caja = conLag.cajas.find((c) => c.id === 'c2')!;
    const arrastre = empezarArrastre(caja, colocar(conLag), 'mover', 0);
    const resultado = resolverArrastre(conLag, arrastre, -7);
    expect(resultado.ok && resultado.accion).toEqual({
      tipo: 'lag',
      desde: 'c1',
      hasta: 'c2',
      lagDias: -2,
    });
  });

  it('arrastrar una actividad sin predecesoras mueve su ancla de arranque', () => {
    // Hasta la 0043 esto era un rechazo: el renglón no tenía dónde guardar un
    // día. Ahora sí — `inicio_dias` — y la barra se mueve de verdad.
    const arrastre = empezarArrastre(c1, colocado, 'mover', 0);
    const resultado = resolverArrastre(BORRADOR, arrastre, 4);
    expect(resultado.ok && resultado.accion).toEqual({
      tipo: 'inicio',
      cajaId: 'c1',
      inicioDias: 4,
    });
  });

  it('estirar cambia la duración de la actividad', () => {
    const arrastre = empezarArrastre(c1, colocado, 'estirar', 0);
    expect(resolverArrastre(BORRADOR, arrastre, 2)).toEqual({
      ok: true,
      dias: 2,
      accion: { tipo: 'duracion', cajaId: 'c1', duracionDias: 5 },
    });
  });

  it('estirar hacia adentro topa en un día y no llega a cero', () => {
    const arrastre = empezarArrastre(c1, colocado, 'estirar', 0);
    const resultado = resolverArrastre(BORRADOR, arrastre, -99);
    expect(resultado.ok && resultado.accion).toEqual({
      tipo: 'duracion',
      cajaId: 'c1',
      duracionDias: 1,
    });
  });

  it('con la actividad partida, estirar toca el último tramo y no la duración', () => {
    // La duración de una actividad partida es la suma de sus tramos y no se
    // captura por separado: dejar las dos cifras editables las haría discrepar.
    const partido = armar([
      item('c1', 4, [], [
        { duracion_dias: 2, offset_dias: 0 },
        { duracion_dias: 2, offset_dias: 5 },
      ]),
    ]);
    const caja = partido.cajas.find((c) => c.id === 'c1')!;
    const arrastre = empezarArrastre(caja, colocar(partido), 'estirar', 0);
    const resultado = resolverArrastre(partido, arrastre, 3);
    expect(resultado.ok && resultado.accion).toEqual({
      tipo: 'tramos',
      cajaId: 'c1',
      tramos: [
        { duracionDias: 2, offsetDias: 0 },
        { duracionDias: 5, offsetDias: 5 },
      ],
    });
  });

  it('un gesto que no mueve nada no produce acción ni aviso', () => {
    // Es el caso normal a mitad de un arrastre: no hay nada que explicar y no
    // debe gastarse un paso de deshacer.
    const arrastre = empezarArrastre(c2, colocado, 'mover', 0);
    expect(resolverArrastre(BORRADOR, arrastre, 0)).toEqual({ ok: false, motivo: null });
  });

  it('el desplazamiento se cuadricula al día según el zoom', () => {
    expect(diasDeDesplazamiento(48, 16)).toBe(3);
    expect(diasDeDesplazamiento(-40, 16)).toBe(-3);
    // Menos de medio día de arrastre no mueve nada.
    expect(diasDeDesplazamiento(7, 16)).toBe(0);
    expect(diasDeDesplazamiento(10, 0)).toBe(0);
  });

  it('la previsualización corre o estira la ventana sin tocar el modelo', () => {
    const puesto = { inicioDias: 3, finDias: 5 };
    expect(previsualizar(puesto, 'mover', 2)).toEqual({ inicioDias: 5, finDias: 7 });
    expect(previsualizar(puesto, 'estirar', 3)).toEqual({ inicioDias: 3, finDias: 8 });
    // Nada arranca antes que el programa, ni siquiera en la vista previa.
    expect(previsualizar(puesto, 'mover', -9)).toEqual({ inicioDias: 0, finDias: 2 });
    expect(previsualizar(puesto, 'estirar', -9)).toEqual({ inicioDias: 3, finDias: 4 });
  });
});

/* ------------------------------------------------------------------ *
 * 4. Eje: días relativos y fechas simuladas
 * ------------------------------------------------------------------ */

describe('eje de días relativos y fechas simuladas (§7.5)', () => {
  const eje = construirEje({ finMaximo: 9, pxPorDia: 16 });

  it('el lienzo cubre el programa con cola y en bloques de siete', () => {
    expect(eje.dias % 7).toBe(0);
    expect(eje.dias).toBeGreaterThanOrEqual(9);
    expect(eje.ancho).toBe(eje.dias * 16);
    expect(eje.bloques[0]).toMatchObject({ dia: 0, etiqueta: 'Día 1' });
  });

  it('los días relativos no dependen de ningún reloj ni de ninguna fecha', () => {
    // Es lo que hace de un programa base una plantilla reusable en 40 casas.
    expect(eje.modo).toBe('relativo');
    expect(eje.diaDeHoy).toBeNull();
    expect(eje.fechas).toEqual([]);
    expect(etiquetaDeDia(eje, 0)).toBe('Día 1');
    expect(etiquetaDeDia(eje, 4)).toBe('Día 5');
    expect(etiquetaDeDia(eje, null)).toBe('—');
  });

  it('pedir fechas sin arranque cae a relativo en vez de inventar una', () => {
    const sinInicio = construirEje({ finMaximo: 5, modo: 'fechas', inicio: null });
    expect(sinInicio.modo).toBe('relativo');
  });

  it('la simulación de fechas salta los días inhábiles', () => {
    // Lunes a sábado, la semana normal de obra en México: el domingo no cuenta.
    // 2026-03-02 es lunes.
    const conFechas = construirEje({
      finMaximo: 8,
      modo: 'fechas',
      inicio: '2026-03-02',
      diasHabiles: [1, 2, 3, 4, 5, 6],
    });
    expect(conFechas.modo).toBe('fechas');
    expect(conFechas.fechas.slice(0, 7)).toEqual([
      '2026-03-02',
      '2026-03-03',
      '2026-03-04',
      '2026-03-05',
      '2026-03-06',
      '2026-03-07',
      // Salta el domingo 8.
      '2026-03-09',
    ]);
    expect(etiquetaDeDia(conFechas, 6)).toBe('2026-03-09');
  });

  it('arrancar en un día inhábil empuja al siguiente hábil, no adelanta el trabajo', () => {
    // Domingo 2026-03-08 con semana de lunes a sábado.
    const fechas = calendarioDelPrograma('2026-03-08', [1, 2, 3, 4, 5, 6], 3);
    expect(fechas).toEqual(['2026-03-09', '2026-03-10', '2026-03-11']);
  });

  it('semana natural son los siete días corridos', () => {
    expect(calendarioDelPrograma('2026-03-06', [1, 2, 3, 4, 5, 6, 7], 3)).toEqual([
      '2026-03-06',
      '2026-03-07',
      '2026-03-08',
    ]);
    // Un conjunto vacío no existe y cae a natural (`normalizarDias`).
    expect(calendarioDelPrograma('2026-03-06', [], 2)).toEqual(['2026-03-06', '2026-03-07']);
    expect(calendarioDelPrograma(null, [1], 3)).toEqual([]);
  });

  it('hoy se marca sólo si cae en un día hábil del lienzo', () => {
    const base = {
      finMaximo: 20,
      modo: 'fechas' as const,
      inicio: '2026-03-02',
      diasHabiles: [1, 2, 3, 4, 5, 6],
    };
    expect(construirEje({ ...base, hoy: '2026-03-04' }).diaDeHoy).toBe(2);
    // Domingo: no es un día del programa.
    expect(construirEje({ ...base, hoy: '2026-03-08' }).diaDeHoy).toBeNull();
    // Antes del arranque.
    expect(construirEje({ ...base, hoy: '2026-01-01' }).diaDeHoy).toBeNull();
  });

  it('indiceDeFecha encuentra el día por bisección y rechaza lo que no está', () => {
    const fechas = calendarioDelPrograma('2026-03-02', [1, 2, 3, 4, 5, 6], 12);
    expect(indiceDeFecha(fechas, '2026-03-02')).toBe(0);
    expect(indiceDeFecha(fechas, '2026-03-13')).toBe(10);
    expect(indiceDeFecha(fechas, '2026-03-08')).toBeNull();
    expect(indiceDeFecha([], '2026-03-02')).toBeNull();
    expect(indiceDeFecha(fechas, 'no-es-fecha')).toBeNull();
  });

  it('cambiar de zoom no cambia el día, sólo su ancho en píxeles', () => {
    // El mismo día 5 cae en dos coordenadas distintas y las dos se convierten
    // de vuelta al mismo día: es lo que hace que el arrastre se sienta igual de
    // fino a cualquier escala.
    const fino = construirEje({ finMaximo: 9, pxPorDia: 6 });
    const grueso = construirEje({ finMaximo: 9, pxPorDia: 40 });
    expect(xDeDia(fino, 5)).toBe(30);
    expect(xDeDia(grueso, 5)).toBe(200);
    expect(diaDeX(fino, 30)).toBe(5);
    expect(diaDeX(grueso, 200)).toBe(5);
    expect(fino.dias).toBe(grueso.dias);
  });

  it('el programa vacío sigue teniendo lienzo que mirar', () => {
    const vacio = construirEje({ finMaximo: 0 });
    expect(vacio.dias).toBeGreaterThanOrEqual(28);
    expect(duracionDelPrograma(new Map())).toBe(0);
  });
});

/* ------------------------------------------------------------------ *
 * 5. Sincronía de scroll
 * ------------------------------------------------------------------ */

describe('scroll sincronizado entre las dos mitades (§12.9)', () => {
  it('un scroll genuino se propaga al otro lado', () => {
    const paso = alDesplazar(SINCRONIA_INICIAL, 'tabla', 240);
    expect(paso.escribirEn).toBe('gantt');
    expect(paso.scrollTop).toBe(240);
  });

  it('el eco se consume y no rebota: es lo que corta el bucle', () => {
    // Escribir `scrollTop` dispara el `scroll` del elemento escrito. Sin este
    // corte los dos lados se perseguirían y ninguno llegaría.
    const primero = alDesplazar(SINCRONIA_INICIAL, 'tabla', 240);
    const eco = alDesplazar(primero.estado, 'gantt', 240);
    expect(eco.escribirEn).toBeNull();
    expect(eco.estado.ecoPendiente).toBeNull();
  });

  it('después del eco, el otro lado vuelve a poder mandar', () => {
    const uno = alDesplazar(SINCRONIA_INICIAL, 'tabla', 240);
    const dos = alDesplazar(uno.estado, 'gantt', 240);
    const tres = alDesplazar(dos.estado, 'gantt', 300);
    expect(tres.escribirEn).toBe('tabla');
    expect(tres.scrollTop).toBe(300);
  });

  it('no se reescribe un desplazamiento que ya está puesto', () => {
    const uno = alDesplazar(SINCRONIA_INICIAL, 'gantt', 100);
    const dos = alDesplazar(uno.estado, 'tabla', 100);
    const tres = alDesplazar(dos.estado, 'tabla', 100);
    expect(tres.escribirEn).toBeNull();
  });

  it('una ráfaga de scroll alterno nunca deja los dos lados separados', () => {
    // La simulación completa: dos elementos con su `scrollTop`, el eco que
    // dispara cada escritura, y una rueda que sube y baja.
    const alto = { tabla: 0, gantt: 0 };
    let estado = SINCRONIA_INICIAL;

    function rueda(lado: 'tabla' | 'gantt', top: number): void {
      alto[lado] = top;
      const paso = alDesplazar(estado, lado, top);
      estado = paso.estado;
      if (paso.escribirEn === null) return;
      alto[paso.escribirEn] = paso.scrollTop;
      // La escritura dispara el `scroll` del elemento escrito: el eco.
      const devuelta = alDesplazar(estado, paso.escribirEn, paso.scrollTop);
      estado = devuelta.estado;
      expect(devuelta.escribirEn).toBeNull();
    }

    for (const [lado, top] of [
      ['tabla', 120],
      ['tabla', 360],
      ['gantt', 90],
      ['tabla', 0],
      ['gantt', 1200],
    ] as const) {
      rueda(lado, top);
      expect(alto.tabla).toBe(alto.gantt);
    }
  });

  it('reiniciar suelta el eco pendiente: plegar cambia la altura de la lista', () => {
    const uno = alDesplazar(SINCRONIA_INICIAL, 'tabla', 240);
    expect(uno.estado.ecoPendiente).toBe('gantt');
    const limpio = reiniciarSincronia(0);
    expect(limpio.ecoPendiente).toBeNull();
    expect(alDesplazar(limpio, 'gantt', 240).escribirEn).toBe('tabla');
  });
});

/* ------------------------------------------------------------------ *
 * Flechas de dependencia
 * ------------------------------------------------------------------ */

describe('flechas de dependencia', () => {
  const anclas = new Map([
    ['c1', { fila: 0, x0: 0, x1: 48 }],
    ['c2', { fila: 1, x0: 48, x1: 80 }],
    ['lejos', { fila: 400, x0: 200, x1: 260 }],
  ]);
  const geometria = { altoFila: ALTO_FILA, desdeFila: 0, hastaFila: 20 };

  it('una FS sale del fin de la predecesora y entra al inicio de la sucesora', () => {
    const [flecha] = trazarConectores(
      [{ desde: 'c1', hasta: 'c2', tipo: 'FS' }],
      anclas,
      geometria,
    );
    expect(flecha?.id).toBe('c1->c2');
    expect(flecha?.puntos[0]).toEqual([48, ALTO_FILA / 2]);
    expect(flecha?.puntos[flecha.puntos.length - 1]).toEqual([48, ALTO_FILA + ALTO_FILA / 2]);
    expect(comoPolilinea(flecha!)).toContain('48,14');
  });

  it('una SS sale del inicio de las dos', () => {
    const [flecha] = trazarConectores(
      [{ desde: 'c1', hasta: 'c2', tipo: 'SS' }],
      anclas,
      geometria,
    );
    expect(flecha?.puntos[0]?.[0]).toBe(0);
    expect(flecha?.puntos[flecha.puntos.length - 1]?.[0]).toBe(48);
  });

  it('no se traza una liga con un extremo plegado: no hay barra a la que apuntar', () => {
    expect(trazarConectores([{ desde: 'c1', hasta: 'oculto', tipo: 'FS' }], anclas, geometria))
      .toEqual([]);
  });

  it('con los dos extremos fuera de la ventana montada no se dibuja nada', () => {
    // Es lo que impide que dibujar doscientas flechas anule la virtualización.
    const fuera = trazarConectores(
      [{ desde: 'lejos', hasta: 'lejos', tipo: 'FS' }],
      anclas,
      { altoFila: ALTO_FILA, desdeFila: 0, hastaFila: 20 },
    );
    expect(fuera).toEqual([]);
  });

  it('con un solo extremo dentro sí se dibuja: sale de la ventana hacia el borde', () => {
    const dentro = trazarConectores(
      [{ desde: 'c1', hasta: 'lejos', tipo: 'FS' }],
      anclas,
      geometria,
    );
    expect(dentro).toHaveLength(1);
  });

  it('cuando la sucesora queda detrás, el trazo rodea en vez de devolverse', () => {
    const alReves = new Map([
      ['a', { fila: 0, x0: 200, x1: 260 }],
      ['b', { fila: 1, x0: 0, x1: 40 }],
    ]);
    const [flecha] = trazarConectores(
      [{ desde: 'a', hasta: 'b', tipo: 'FS' }],
      alReves,
      geometria,
    );
    // Seis puntos, no cuatro: el camino directo no existe y hay que rodear.
    expect(flecha?.puntos).toHaveLength(6);
  });

  it('la liga en ciclo se marca de alerta para que se vea cuál quitar', () => {
    const [flecha] = trazarConectores(
      [{ desde: 'c1', hasta: 'c2', tipo: 'FS', alerta: true }],
      anclas,
      geometria,
    );
    expect(flecha?.alerta).toBe(true);
  });
});
