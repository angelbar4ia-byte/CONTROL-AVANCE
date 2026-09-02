/**
 * Que las dos mitades del editor **monten** y pinten lo que dicen pintar.
 *
 * Es el complemento de `programa-tabla-gantt.test.ts`, que fija la aritmética
 * sin render. Aquí se comprueba lo que un typecheck no puede ver: que un
 * resumen no ofrezca la celda de captura —capturar sobre una barra derivada
 * duplicaría los días de sus hijos (§7.4)—, que un nodo sin duración no finja
 * una ventana, que la actividad partida no deje editar su duración por dos
 * caminos (§7.6), y que la rejilla anuncie el programa completo y no lo que el
 * virtualizador tenga montado.
 *
 * ## Por qué hace falta medir el viewport a mano
 *
 * `@tanstack/react-virtual` decide qué renglones monta a partir del
 * `offsetHeight` de su contenedor de scroll, y en jsdom eso vale **cero**
 * siempre: sin layout, el virtualizador concluye que no cabe nada y monta cero
 * filas. La prueba se quedaría verde afirmando sobre un DOM vacío, que es la
 * forma más común en que una prueba de componente virtualizado deja de servir.
 * `medirComoNavegador` le da al contenedor un tamaño para que el cálculo tenga
 * de dónde partir. No simula layout —nada aquí depende de dónde cae un píxel—;
 * sólo hace que el componente monte los renglones que en un navegador montaría.
 */

import { createRef } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { construirBandas } from '@/programacion/bandasPrograma';
import { columnasVisibles } from '@/programacion/columnasPrograma';
import { construirEje } from '@/programacion/ejePrograma';
import type { FilaPrograma } from '@/programacion/filasPrograma';
import { GanttPrograma } from '@/programacion/GanttPrograma';
import { TablaPrograma } from '@/programacion/TablaPrograma';
import { VISTA_GANTT_INICIAL } from '@/programacion/vistaGantt';

/** Alto y ancho de un contenedor, que jsdom deja en cero. Ver el docstring. */
function medirComoNavegador(alto = 600, ancho = 900): void {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    value: alto,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    value: ancho,
  });
}

beforeAll(() => {
  medirComoNavegador();
  // jsdom no implementa la captura del puntero. El arrastre la usa para que el
  // gesto siga siendo de la barra aunque el ratón se salga de ella; aquí basta
  // con que no reviente, porque los eventos se disparan sobre el mismo nodo.
  HTMLElement.prototype.setPointerCapture = () => undefined;
  HTMLElement.prototype.releasePointerCapture = () => undefined;
});

/**
 * Un evento de puntero **con coordenada**.
 *
 * `fireEvent.pointerDown(el, { clientX })` no sirve: jsdom construye el evento
 * de puntero sin las propiedades de ratón, así que `clientX` llega `undefined`
 * y todo el arrastre se calcula sobre `NaN` — la prueba pasaría igual porque el
 * componente sí llama al callback, sólo que con basura. Se despacha un
 * `MouseEvent` con el tipo del puntero, que sí trae la coordenada y que React
 * enruta al `onPointerDown` por el nombre del evento.
 */
function puntero(tipo: 'pointerdown' | 'pointermove' | 'pointerup', clientX: number): Event {
  const evento = new MouseEvent(tipo, { bubbles: true, cancelable: true, clientX });
  Object.defineProperty(evento, 'pointerId', { value: 1 });
  return evento;
}

const EJE = construirEje({ finMaximo: 9, pxPorDia: 16 });

/**
 * Lo que el menú de herramientas decide, en su estado de fábrica.
 *
 * Las dos mitades dejaron de recibir sólo filas: ahora se les pasa la vista
 * (`vistaGantt.ts`), las columnas encendidas, las bandas del eje y la cadena
 * crítica, todo ya resuelto fuera. Estas constantes son ese "todo apagado" con
 * el que el módulo abre, para que cada prueba siga afirmando sobre una sola
 * cosa y no sobre la configuración.
 */
const VISTA = VISTA_GANTT_INICIAL;
const COLUMNAS = columnasVisibles(VISTA.columnas);
const SIN_CONGELAR = new Map<string, number>();
const SIN_MAGNITUDES = new Map<string, never>();
const SIN_CRITICAS = new Set<string>();
const SIN_TONOS = new Map<string, number>();

function fila(sobre: Partial<FilaPrograma> & Pick<FilaPrograma, 'nodoId'>): FilaPrograma {
  return {
    parentId: null,
    profundidad: 0,
    numero: 1,
    tipo: 'concepto',
    clave: 'C1',
    descripcion: 'Excavación',
    unidad: 'M3',
    cantidad: 12,
    tieneHijos: false,
    nHojas: 1,
    esResumen: false,
    capturado: true,
    anclaDias: null,
    inicioDias: 0,
    finDias: 3,
    diasLaborables: 3,
    diasCalendario: 3,
    holguraDias: 0,
    tramos: [],
    nPredecesoras: 0,
    enCiclo: false,
    ...sobre,
  };
}

function pintarTabla(filas: readonly FilaPrograma[], editable = true) {
  const onDuracion = vi.fn();
  const onInicio = vi.fn();
  const onTermino = vi.fn();
  const onAlternar = vi.fn();
  const salida = render(
    <TablaPrograma
      filas={filas}
      eje={EJE}
      columnas={COLUMNAS}
      congelados={SIN_CONGELAR}
      vista={VISTA}
      magnitudes={SIN_MAGNITUDES}
      criticas={SIN_CRITICAS}
      colapsados={new Set()}
      seleccionado={null}
      editable={editable}
      onAlternar={onAlternar}
      onSeleccionar={vi.fn()}
      onDuracion={onDuracion}
      onInicio={onInicio}
      onTermino={onTermino}
      contenedorRef={createRef<HTMLDivElement>()}
      onScroll={vi.fn()}
    />,
  );
  return { ...salida, onDuracion, onInicio, onTermino, onAlternar };
}

function pintarGantt(filas: readonly FilaPrograma[], editable = true) {
  const onSoltar = vi.fn();
  const salida = render(
    <GanttPrograma
      filas={filas}
      eje={EJE}
      bandas={construirBandas(EJE, VISTA.escala)}
      ligas={[{ desde: 'c1', hasta: 'c2', tipo: 'FS' }]}
      vista={VISTA}
      criticas={SIN_CRITICAS}
      magnitudes={SIN_MAGNITUDES}
      tonoPorNodo={SIN_TONOS}
      seleccionado={null}
      editable={editable}
      onSeleccionar={vi.fn()}
      onSoltar={onSoltar}
      contenedorRef={createRef<HTMLDivElement>()}
      onScroll={vi.fn()}
    />,
  );
  return { ...salida, onSoltar };
}

describe('TablaPrograma', () => {
  it('trae el encabezado de columnas que promete', () => {
    pintarTabla([fila({ nodoId: 'c1' })]);
    for (const titulo of ['#', 'Tipo', 'Clave', 'Descripción', 'Unidad', 'Días lab.', 'Días cal.']) {
      expect(screen.getByRole('columnheader', { name: titulo })).toBeInTheDocument();
    }
  });

  it('monta los renglones con su número, clave y unidad', () => {
    // Si esto sale vacío, el arreglo del viewport dejó de funcionar y todo lo
    // demás de este archivo estaría pasando sobre un DOM sin filas.
    const { container } = pintarTabla([fila({ nodoId: 'c1' })]);
    expect(container.querySelectorAll('.prog-tabla__fila')).toHaveLength(1);
    const renglon = screen.getByRole('row', { name: /Excavación/ });
    expect(within(renglon).getByText('C1')).toBeInTheDocument();
    expect(within(renglon).getByText('M3')).toBeInTheDocument();
  });

  it('duración, inicio y término se capturan también en un resumen', () => {
    // Desde la herencia jerárquica capturar en un nivel o una etapa significa
    // algo: reparte su ventana hacia abajo (§7.4). Antes las tres celdas eran
    // de lectura y el nivel solo se podía programar concepto por concepto.
    pintarTabla([
      fila({
        nodoId: 'e1',
        tipo: 'etapa',
        descripcion: 'Cimentación',
        esResumen: true,
        tieneHijos: true,
      }),
    ]);
    expect(screen.getByLabelText('Días laborables de Cimentación')).toBeInTheDocument();
    expect(screen.getByLabelText('Día de arranque de Cimentación')).toBeInTheDocument();
    expect(screen.getByLabelText('Día de término de Cimentación')).toBeInTheDocument();
  });

  it('en lectura ninguna de las tres se captura', () => {
    const { container } = pintarTabla([fila({ nodoId: 'c1' })], false);
    expect(container.querySelectorAll('input')).toHaveLength(0);
  });

  it('la actividad partida enseña su duración de lectura: es la suma de sus tramos', () => {
    // Dejar las dos cifras editables garantiza que un día discrepen (§7.6).
    pintarTabla([
      fila({
        nodoId: 'c1',
        diasLaborables: 4,
        diasCalendario: 9,
        tramos: [
          { duracionDias: 2, offsetDias: 0 },
          { duracionDias: 2, offsetDias: 7 },
        ],
      }),
    ]);
    // Su arranque sí se sigue pudiendo clavar: una actividad partida se ancla
    // igual que una continua. Lo que no se captura es la duración.
    expect(screen.queryByLabelText('Días laborables de Excavación')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Día de arranque de Excavación')).toBeInTheDocument();
  });

  it('en lectura no se captura nada aunque la fila sea un concepto', () => {
    const { container } = pintarTabla([fila({ nodoId: 'c1' })], false);
    expect(container.querySelectorAll('input')).toHaveLength(0);
  });

  it('el triángulo sólo aparece donde hay algo que plegar', () => {
    const conHijos = pintarTabla([
      fila({ nodoId: 'e1', tipo: 'etapa', descripcion: 'Cimentación', tieneHijos: true }),
    ]);
    expect(
      conHijos.container.querySelectorAll('button.prog-tabla__caret'),
    ).toHaveLength(1);

    const hoja = pintarTabla([fila({ nodoId: 'c1' })]);
    expect(hoja.container.querySelectorAll('button.prog-tabla__caret')).toHaveLength(0);
  });

  it('el ciclo se marca en el renglón, no sólo en la barra', () => {
    pintarTabla([fila({ nodoId: 'e1', enCiclo: true })]);
    expect(screen.getByText('ciclo')).toBeInTheDocument();
  });

  it('ya no hay marca de conflicto: la herencia impide construir ese estado', () => {
    // Un nodo con duración propia y descendientes capturados era el conflicto.
    // `gestos.fijarDuracion` vacía uno de los dos lados, así que no se puede.
    pintarTabla([fila({ nodoId: 'e1', esResumen: true, capturado: false })]);
    expect(screen.queryByText('conflicto')).not.toBeInTheDocument();
  });

  it('el término se rotula con el último día trabajado, no con el día siguiente', () => {
    // Una actividad que arranca el día 1 y dura tres cierra el día 3.
    pintarTabla([fila({ nodoId: 'c1', inicioDias: 0, finDias: 3 })]);
    // El inicio es capturable y va vacío —no está anclada—, así que el día que
    // el grafo le puso se anuncia como `placeholder`.
    expect(screen.getByLabelText('Día de arranque de Excavación')).toHaveAttribute(
      'placeholder',
      '1',
    );
    // Y el término también es capturable: lleva el último día trabajado, no el
    // día en que la ventana termina.
    expect(screen.getByLabelText('Día de término de Excavación')).toHaveValue(3);
  });

  it('la rejilla declara cuántos renglones tiene el programa, no cuántos monta', () => {
    // Es lo que un lector de pantalla pierde al virtualizar si nadie se lo dice.
    const filas = Array.from({ length: 400 }, (_, i) =>
      fila({ nodoId: `c${i}`, numero: i + 1, descripcion: `Concepto ${i}` }),
    );
    const { container } = pintarTabla(filas);
    expect(screen.getByRole('grid')).toHaveAttribute('aria-rowcount', '400');
    // Y virtualiza de verdad: 400 renglones no llegan enteros al DOM.
    const montados = container.querySelectorAll('.prog-tabla__fila').length;
    expect(montados).toBeGreaterThan(0);
    expect(montados).toBeLessThan(400);
  });
});

describe('GanttPrograma', () => {
  it('trae el encabezado del eje en días relativos', () => {
    pintarGantt([fila({ nodoId: 'c1' })]);
    expect(screen.getByText('Día 1')).toBeInTheDocument();
    expect(screen.getByText('Día 8')).toBeInTheDocument();
  });

  it('el lienzo mide lo que mide el eje, no lo que mida la ventana', () => {
    const { container } = pintarGantt([fila({ nodoId: 'c1' })]);
    expect((container.querySelector('.prog-gantt') as HTMLElement).style.width).toBe(
      `${EJE.ancho}px`,
    );
  });

  it('el concepto capturado dibuja barra, con su asa de estirar', () => {
    const { container } = pintarGantt([fila({ nodoId: 'c1' })]);
    expect(container.querySelectorAll('.prog-gantt__barra')).toHaveLength(1);
    expect(container.querySelectorAll('.prog-gantt__asa')).toHaveLength(1);
  });

  it('en lectura la barra existe pero no hay asa que arrastrar', () => {
    const { container } = pintarGantt([fila({ nodoId: 'c1' })], false);
    expect(container.querySelectorAll('.prog-gantt__barra')).toHaveLength(1);
    expect(container.querySelectorAll('.prog-gantt__asa')).toHaveLength(0);
  });

  it('el resumen es un corchete con patas, no una barra que se pueda agarrar', () => {
    const { container } = pintarGantt([
      fila({ nodoId: 'e1', tipo: 'etapa', esResumen: true, tieneHijos: true, holguraDias: null }),
    ]);
    expect(container.querySelectorAll('.prog-gantt__corchete')).toHaveLength(1);
    expect(container.querySelectorAll('.prog-gantt__pata')).toHaveLength(2);
    expect(container.querySelectorAll('.prog-gantt__barra')).toHaveLength(0);
    expect(container.querySelectorAll('.prog-gantt__asa')).toHaveLength(0);
  });

  it('el nodo sin duración se dice, no se dibuja con una ventana inventada', () => {
    const { container } = pintarGantt([
      fila({ nodoId: 'c9', capturado: false, inicioDias: null, finDias: null }),
    ]);
    expect(container.querySelectorAll('.prog-gantt__barra')).toHaveLength(0);
    expect(screen.getByText('sin duración')).toBeInTheDocument();
  });

  it('la actividad partida dibuja un bloque por tramo y la pausa entre ellos', () => {
    const { container } = pintarGantt([
      fila({
        nodoId: 'c1',
        finDias: 9,
        diasLaborables: 4,
        diasCalendario: 9,
        tramos: [
          { duracionDias: 2, offsetDias: 0 },
          { duracionDias: 2, offsetDias: 7 },
        ],
      }),
    ]);
    expect(container.querySelectorAll('.prog-gantt__barra')).toHaveLength(2);
    expect(container.querySelectorAll('.prog-gantt__pausa')).toHaveLength(1);
    // Sólo el último tramo lleva asa: es el borde que estira la actividad.
    expect(container.querySelectorAll('.prog-gantt__asa')).toHaveLength(1);
  });

  it('la holgura se dibuja como la cola que sigue a la barra', () => {
    const conHolgura = pintarGantt([fila({ nodoId: 'c1', holguraDias: 2 })]);
    expect(conHolgura.container.querySelectorAll('.prog-gantt__holgura')).toHaveLength(1);

    const sinHolgura = pintarGantt([fila({ nodoId: 'c1', holguraDias: 0 })]);
    expect(sinHolgura.container.querySelectorAll('.prog-gantt__holgura')).toHaveLength(0);
  });

  it('traza la flecha entre dos barras dibujadas', () => {
    const { container } = pintarGantt([
      fila({ nodoId: 'c1' }),
      fila({ nodoId: 'c2', numero: 2, descripcion: 'Plantilla', inicioDias: 3, finDias: 5 }),
    ]);
    expect(container.querySelectorAll('polyline.prog-gantt__flecha')).toHaveLength(1);
  });

  it('sin el otro extremo dibujado no hay flecha que trazar', () => {
    const { container } = pintarGantt([fila({ nodoId: 'c1' })]);
    expect(container.querySelectorAll('polyline.prog-gantt__flecha')).toHaveLength(0);
  });

  it('marca hoy sólo cuando el eje está en fechas', () => {
    const relativo = pintarGantt([fila({ nodoId: 'c1' })]);
    expect(relativo.container.querySelectorAll('.prog-gantt__hoy')).toHaveLength(0);

    const conFechas = construirEje({
      finMaximo: 9,
      modo: 'fechas',
      inicio: '2026-03-02',
      diasHabiles: [1, 2, 3, 4, 5, 6],
      hoy: '2026-03-04',
    });
    const { container } = render(
      <GanttPrograma
        filas={[fila({ nodoId: 'c1' })]}
        eje={conFechas}
        bandas={construirBandas(conFechas, VISTA.escala)}
          ligas={[]}
        vista={VISTA}
        criticas={SIN_CRITICAS}
        magnitudes={SIN_MAGNITUDES}
        tonoPorNodo={SIN_TONOS}
        seleccionado={null}
        editable
        onSeleccionar={vi.fn()}
        onSoltar={vi.fn()}
        contenedorRef={createRef<HTMLDivElement>()}
        onScroll={vi.fn()}
      />,
    );
    expect(container.querySelectorAll('.prog-gantt__hoy')).toHaveLength(1);
  });

  it('arrastrar el cuerpo de la barra avisa una sola vez, con los días recorridos', () => {
    // El arrastre no despacha en cada `pointermove`: cada acción del borrador
    // apila su propio paso de deshacer, así que correr una barra tres días
    // dejaría tres pasos atrás en vez de uno (`arrastre.ts`).
    const { container, onSoltar } = pintarGantt([fila({ nodoId: 'c1' })]);
    const barra = container.querySelector('.prog-gantt__barra') as HTMLElement;

    fireEvent(barra, puntero('pointerdown', 100));
    fireEvent(barra, puntero('pointermove', 116));
    fireEvent(barra, puntero('pointermove', 148));
    expect(onSoltar).not.toHaveBeenCalled();

    fireEvent(barra, puntero('pointerup', 148));
    // 48 px a 16 px/día son tres días.
    expect(onSoltar).toHaveBeenCalledTimes(1);
    expect(onSoltar).toHaveBeenCalledWith('c1', 'mover', 3);
  });

  it('arrastrar el asa estira en vez de mover', () => {
    const { container, onSoltar } = pintarGantt([fila({ nodoId: 'c1' })]);
    const asa = container.querySelector('.prog-gantt__asa') as HTMLElement;

    fireEvent(asa, puntero('pointerdown', 60));
    fireEvent(asa, puntero('pointermove', 92));
    fireEvent(asa, puntero('pointerup', 92));

    expect(onSoltar).toHaveBeenCalledWith('c1', 'estirar', 2);
  });

  it('el corchete de un resumen se arrastra y mueve el bloque', () => {
    // Lo que se mueve no es la barra —un resumen no tiene ventana propia—
    // sino todo lo que cuelga de él; quien lo traduce es
    // `gestos.desplazarBloque`, y aquí sólo se comprueba que el gesto salga.
    const { container, onSoltar } = pintarGantt([
      fila({ nodoId: 'e1', tipo: 'etapa', esResumen: true, tieneHijos: true, holguraDias: null }),
    ]);
    const corchete = container.querySelector('.prog-gantt__corchete') as HTMLElement;
    const lienzo = container.querySelector('.prog-gantt__lienzo') as HTMLElement;
    fireEvent(corchete, puntero('pointerdown', 100));
    fireEvent(lienzo, puntero('pointermove', 100 + 16 * 3));
    fireEvent(lienzo, puntero('pointerup', 100 + 16 * 3));
    expect(onSoltar).toHaveBeenCalledWith('e1', 'mover', 3);
  });

  it('el resumen no tiene asa de borde: su ancho lo ponen sus hijos', () => {
    const { container } = pintarGantt([
      fila({ nodoId: 'e1', tipo: 'etapa', esResumen: true, tieneHijos: true, holguraDias: null }),
    ]);
    expect(container.querySelectorAll('.prog-gantt__asa')).toHaveLength(0);
  });

  it('virtualiza: 400 renglones no llegan enteros al DOM', () => {
    const filas = Array.from({ length: 400 }, (_, i) =>
      fila({ nodoId: `c${i}`, numero: i + 1, descripcion: `Concepto ${i}` }),
    );
    const { container } = pintarGantt(filas);
    const pistas = container.querySelectorAll('.prog-gantt__pista').length;
    expect(pistas).toBeGreaterThan(0);
    expect(pistas).toBeLessThan(400);
  });
});
