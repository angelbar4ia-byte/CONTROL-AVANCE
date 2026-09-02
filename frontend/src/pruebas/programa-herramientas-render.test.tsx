/**
 * Que la cinta y la rejilla volumétrica **monten** y respeten la línea que
 * separa las dos clases de herramienta.
 *
 * La regla que se vigila aquí no se puede fijar con un typecheck ni con una
 * prueba de módulo puro: que un control de vista —la ruta crítica, el tema, una
 * columna— **no llame a ninguna de las acciones que editan el programa**. Es la
 * diferencia entre una pantalla que se queda en "sin guardar" porque alguien
 * cambió de tema y una que no, y sólo se ve montando la cinta y pulsando.
 *
 * De la rejilla se fija lo mismo por el otro lado: que sea de sólo lectura. El
 * reparto por periodo es derivado (`reparto.ts`) y no existe como dato en el
 * contrato, así que ninguna celda puede ser un campo — un campo ahí dejaría al
 * usuario capturando números que el `POST` tira en silencio.
 *
 * Ver `programa-tabla-render.test.tsx` para el porqué de `medirComoNavegador`:
 * en jsdom el contenedor de scroll mide cero y un virtualizador concluye que no
 * cabe nada, con lo que la prueba se quedaría verde sobre un DOM vacío.
 */

import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { BandaEje } from '@/programacion/bandasPrograma';
import {
  BarraHerramientasGantt,
  type AccionesHerramientas,
  type SeleccionHerramientas,
} from '@/programacion/BarraHerramientasGantt';
import type { FilaPrograma } from '@/programacion/filasPrograma';
import { RejillaCantidades } from '@/programacion/RejillaCantidades';
import type { RenglonRejilla } from '@/programacion/reparto';
import { RUTA_CRITICA_VACIA } from '@/programacion/rutaCritica';
import { VISTA_GANTT_INICIAL } from '@/programacion/vistaGantt';

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    value: 600,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    value: 900,
  });
});

/** Las quince herramientas que editan el programa, todas espiadas. */
function accionesEspiadas(): AccionesHerramientas & { readonly todas: readonly ReturnType<typeof vi.fn>[] } {
  const espias = {
    aplazar: vi.fn(),
    noIniciarAntesDe: vi.fn(),
    fijarDuracion: vi.fn(),
    fijarInicio: vi.fn(),
    fijarTermino: vi.fn(),
    dividir: vi.fn(),
    interrumpir: vi.fn(),
    unirTramos: vi.fn(),
    reiniciarActividad: vi.fn(),
    reiniciarPrograma: vi.fn(),
    vincular: vi.fn(),
    desvincular: vi.fn(),
    invertir: vi.fn(),
    retipar: vi.fn(),
    retrasar: vi.fn(),
  };
  return { ...espias, todas: Object.values(espias) };
}

const SELECCION: SeleccionHerramientas = {
  nodoId: 'c1',
  etiqueta: 'C1 · Excavación',
  esResumen: false,
  capturado: true,
  inicioDias: 0,
  terminoDias: 3,
  diasLaborables: 4,
  nTramos: 0,
  predecesoras: [{ desde: 'c0', etiqueta: 'C0 · Trazo', tipo: 'FS', lagDias: 0 }],
  candidatas: [{ id: 'c2', etiqueta: 'C2 · Plantilla' }],
};

function pintarCinta(seleccion: SeleccionHerramientas | null = SELECCION) {
  const acciones = accionesEspiadas();
  const onVista = vi.fn();
  const salida = render(
    <BarraHerramientasGantt
      vista={VISTA_GANTT_INICIAL}
      onVista={onVista}
      acciones={acciones}
      seleccion={seleccion}
      rotularDia={(dia) => `Día ${dia + 1}`}
      ruta={RUTA_CRITICA_VACIA}
      diasHabiles={[1, 2, 3, 4, 5, 6, 7]}
      onDiasHabiles={vi.fn()}
      onAlternarDia={vi.fn()}
      inicioSimulado="2026-03-02"
      onInicioSimulado={vi.fn()}
      onAjustarZoom={vi.fn()}
      profundidadMaxima={2}
      onColapsarANivel={vi.fn()}
      densidad="comfy"
      onDensidad={vi.fn()}
      puedeDeshacer
      puedeRehacer={false}
      onDeshacer={vi.fn()}
      onRehacer={vi.fn()}
      editable
    />,
  );
  return { ...salida, acciones, onVista };
}

/** Abre una pestaña de la cinta por su nombre. */
function abrir(nombre: string): void {
  fireEvent.click(screen.getByRole('tab', { name: nombre }));
}

describe('la cinta de herramientas', () => {
  it('abre en Programar y las siete pestañas están todas', () => {
    pintarCinta();
    for (const nombre of [
      'Programar',
      'Vínculos',
      'Ruta crítica',
      'Escalas',
      'Barras',
      'Área de trabajo',
      'Apariencia',
    ]) {
      expect(screen.getByRole('tab', { name: nombre })).toBeInTheDocument();
    }
    expect(screen.getByRole('tab', { name: 'Programar' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('sólo el grupo activo ocupa sitio: cambiar de pestaña cambia los controles', () => {
    pintarCinta();
    expect(screen.getByRole('button', { name: 'Aplazar' })).toBeInTheDocument();

    abrir('Barras');
    expect(screen.queryByRole('button', { name: 'Aplazar' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Contorno' })).toBeInTheDocument();
  });

  it('deshacer y rehacer viven fuera de las pestañas', () => {
    // Esconderlos detrás de una obligaría a volver a Programar para deshacer un
    // vínculo, que es exactamente el gesto que se acaba de hacer en otra.
    pintarCinta();
    abrir('Apariencia');
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Rehacer' })).toBeDisabled();
  });

  it('NINGÚN control de vista o apariencia toca el programa', () => {
    // La regla del módulo: encender la ruta crítica, cambiar de tema o apagar
    // una columna no es editar el programa, y no puede dejar la pantalla en
    // "sin guardar".
    const { acciones, onVista } = pintarCinta();

    abrir('Ruta crítica');
    fireEvent.click(screen.getByRole('button', { name: 'Trazar ruta crítica' }));

    abrir('Barras');
    fireEvent.click(screen.getByRole('button', { name: 'Delgada' }));
    fireEvent.click(screen.getByRole('button', { name: 'Criticidad' }));

    abrir('Área de trabajo');
    fireEvent.click(screen.getByRole('button', { name: 'Cantidades por escala' }));
    fireEvent.click(screen.getByRole('button', { name: 'Fijar columnas' }));

    abrir('Apariencia');
    fireEvent.click(screen.getByRole('button', { name: 'Oscuro' }));
    fireEvent.click(screen.getByRole('button', { name: 'Monocromática' }));

    // Los siete controles pulsados avisaron de un cambio de vista, y cambiar
    // de pestaña no cuenta como ninguno: la pestaña activa es dónde estaba la
    // mano, no una preferencia.
    expect(onVista.mock.calls.length).toBe(7);
    for (const espia of acciones.todas) expect(espia).not.toHaveBeenCalled();
  });

  it('las de programar sí llaman a su herramienta, y sólo a la suya', () => {
    const { acciones, onVista } = pintarCinta();
    fireEvent.click(screen.getByRole('button', { name: 'Aplazar' }));

    expect(acciones.aplazar).toHaveBeenCalledTimes(1);
    expect(acciones.aplazar).toHaveBeenCalledWith(1);
    expect(acciones.dividir).not.toHaveBeenCalled();
    // Y no se cuela en las preferencias: un gesto del programa no es una vista.
    expect(onVista).not.toHaveBeenCalled();
  });

  it('"no iniciar antes de" manda el día 0-based que el modelo usa', () => {
    // La cinta rotula 1-based porque así los cuenta el jefe de obra;
    // internamente el arranque es el 0, que es lo que devuelve `colocar`.
    const { acciones } = pintarCinta();
    fireEvent.change(screen.getByLabelText('Día antes del cual no debe iniciar'), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }));
    expect(acciones.noIniciarAntesDe).toHaveBeenCalledWith(9);
  });

  it('sin renglón elegido, las herramientas de la actividad no se ofrecen', () => {
    pintarCinta(null);
    expect(screen.getByRole('button', { name: /Dividir/ })).toBeDisabled();
    expect(screen.getByText(/Elige un renglón de la tabla/)).toBeInTheDocument();
  });

  it('sobre un resumen no se programa: se dice y no se deja', () => {
    // La barra de un nivel o una etapa es derivada de sus hijos (§7.4).
    pintarCinta({ ...SELECCION, esResumen: true });
    expect(screen.getByRole('button', { name: /Dividir/ })).toBeDisabled();
    expect(screen.getByText(/es un resumen/)).toBeInTheDocument();
  });

  it('interrumpir y unir tramos sólo se ofrecen sobre una actividad partida', () => {
    const continua = pintarCinta();
    expect(screen.getByRole('button', { name: 'Interrumpir' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Unir tramos' })).toBeDisabled();
    continua.unmount();

    const { acciones } = pintarCinta({ ...SELECCION, nTramos: 3 });
    fireEvent.change(screen.getByLabelText('Número de tramo sobre el que se opera'), {
      target: { value: '2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Interrumpir' }));
    // El campo "Tramo" nombra el tramo cuya pausa se toca: el 2 es el índice 1,
    // y unirlo cierra la pausa entre el 1 y el 2, o sea el índice 0.
    expect(acciones.interrumpir).toHaveBeenCalledWith(1, 1);

    fireEvent.click(screen.getByRole('button', { name: 'Unir tramos' }));
    expect(acciones.unirTramos).toHaveBeenCalledWith(0);
  });

  it('vincular exige elegir la predecesora y manda el tipo por defecto', () => {
    const { acciones } = pintarCinta();
    abrir('Vínculos');

    const vincular = screen.getByRole('button', { name: /Vincular/ });
    expect(vincular).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Actividad predecesora'), {
      target: { value: 'c2' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Vincular/ }));
    expect(acciones.vincular).toHaveBeenCalledWith('c2', 'FS', 0);
  });

  it('desvincular e invertir operan sobre el vínculo elegido', () => {
    const { acciones } = pintarCinta();
    abrir('Vínculos');

    fireEvent.click(screen.getByRole('button', { name: /Invertir/ }));
    expect(acciones.invertir).toHaveBeenCalledWith('c0');

    fireEvent.click(screen.getByRole('button', { name: /Desvincular/ }));
    expect(acciones.desvincular).toHaveBeenCalledWith('c0');
  });

  it('sin predecesoras no hay vínculo sobre el que operar', () => {
    pintarCinta({ ...SELECCION, predecesoras: [] });
    abrir('Vínculos');
    expect(screen.getByRole('button', { name: /Invertir/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Desvincular/ })).toBeDisabled();
  });
});

/* ================================================================== *
 * La rejilla volumétrica
 * ================================================================== */

function fila(sobre: Partial<FilaPrograma> & Pick<FilaPrograma, 'nodoId'>): FilaPrograma {
  return {
    parentId: null,
    profundidad: 0,
    numero: 1,
    tipo: 'concepto',
    clave: 'C1',
    descripcion: 'Excavación',
    unidad: 'M3',
    cantidad: 100,
    tieneHijos: false,
    nHojas: 1,
    esResumen: false,
    capturado: true,
    anclaDias: null,
    inicioDias: 0,
    finDias: 6,
    diasLaborables: 4,
    diasCalendario: 6,
    holguraDias: 0,
    tramos: [],
    nPredecesoras: 0,
    enCiclo: false,
    ...sobre,
  };
}

const PERIODOS: readonly BandaEje[] = [0, 7, 14].map((dia) => ({
  dia,
  dias: 7,
  etiqueta: `Día ${dia + 1}`,
  titulo: `Semana que arranca el día ${dia + 1}`,
  esHoy: false,
}));

describe('rejilla de cantidades por escala', () => {
  const renglones = new Map<string, RenglonRejilla>([
    ['c1', { nodoId: 'c1', celdas: [40, 0, 60], total: 100 }],
    ['e1', { nodoId: 'e1', celdas: [null, null, null], total: null }],
  ]);

  function pintar() {
    return render(
      <RejillaCantidades
        filas={[fila({ nodoId: 'c1' }), fila({ nodoId: 'e1', esResumen: true, numero: 2 })]}
        periodos={PERIODOS}
        rejilla={renglones}
        magnitud="cantidad"
        seleccionado={null}
        onSeleccionar={vi.fn()}
        contenedorRef={createRef<HTMLDivElement>()}
        onScroll={vi.fn()}
      />,
    );
  }

  it('trae una columna por periodo más el total', () => {
    const { container } = pintar();
    expect(container.querySelectorAll('.prog-cant__th')).toHaveLength(PERIODOS.length + 1);
    expect(screen.getByRole('columnheader', { name: 'Total' })).toBeInTheDocument();
  });

  it('es de SÓLO LECTURA: ninguna celda es un campo', () => {
    // El reparto es derivado y no existe como dato en el contrato: un campo
    // aquí dejaría al usuario capturando números que el POST tira en silencio.
    const { container } = pintar();
    expect(container.querySelectorAll('input')).toHaveLength(0);
    expect(container.querySelectorAll('button')).toHaveLength(0);
  });

  it('distingue un cero de un hueco', () => {
    // El cero es "esa semana no se trabaja" —cae en una pausa (§7.6)— y el
    // hueco es "no hay cifra que repartir", que es el resumen en cantidad.
    const { container } = pintar();
    expect(container.querySelectorAll('.prog-cant__celda.is-cero')).toHaveLength(1);

    const renglonResumen = container.querySelectorAll('.prog-cant__fila')[1];
    expect(renglonResumen?.textContent).toBe('');
  });

  it('virtualiza igual que el Gantt al que sustituye', () => {
    const muchas = Array.from({ length: 300 }, (_, i) =>
      fila({ nodoId: `c${i}`, numero: i + 1 }),
    );
    const { container } = render(
      <RejillaCantidades
        filas={muchas}
        periodos={PERIODOS}
        rejilla={new Map()}
        magnitud="importe"
        seleccionado={null}
        onSeleccionar={vi.fn()}
        contenedorRef={createRef<HTMLDivElement>()}
        onScroll={vi.fn()}
      />,
    );
    const pintadas = container.querySelectorAll('.prog-cant__fila').length;
    expect(pintadas).toBeGreaterThan(0);
    expect(pintadas).toBeLessThan(300);
  });
});
