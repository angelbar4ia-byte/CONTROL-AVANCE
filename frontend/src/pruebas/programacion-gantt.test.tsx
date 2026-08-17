/**
 * Gantt y editor de dependencias: render, teclado y resaltado de la ruta
 * crítica.
 *
 * El Gantt es la pantalla nueva de la Fase 3 y su valor está en que se pueda
 * leer y recorrer: cada actividad es un botón con su nombre, sus fechas y su
 * estado en texto, para que la ruta crítica no se comunique **solo** por
 * color (§12.10). No prueban reglas —esas van en `programacion.test.ts`—
 * sino que la UI refleja lo que el motor CPM ya calculó (§6).
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import type { FrenteRespuesta, RutaCriticaRespuesta } from '@/api/generado/modelo';
import { construirEscala } from '@/programacion/escala';
import { agruparPorFrente, construirFilas } from '@/programacion/filas';
import { Gantt } from '@/programacion/Gantt';
import { EditorDependencias } from '@/programacion/Dependencias';

const FRENTES: readonly FrenteRespuesta[] = [
  { id: 'f-pre', clave: 'PRE', nombre: 'Preliminares', etapa: 'Obra negra', orden: 1 },
  { id: 'f-cim', clave: 'CIM', nombre: 'Cimentación', etapa: 'Obra negra', orden: 2 },
];

const RUTA = {
  obra_id: 'o1',
  fecha_inicio: '2026-04-06',
  fecha_corte: '2026-04-15',
  fin_programado: '2026-04-24',
  programa_obra_id: 'p1',
  version: 2,
  actividades: [
    {
      actividad_id: 'a1',
      descripcion: 'Trazo y nivelación',
      frente_id: 'f-pre',
      duracion_dias: '4',
      dependencias: [],
      inicio_temprano: '2026-04-06',
      fin_temprano: '2026-04-09',
      inicio_tardio: '2026-04-06',
      fin_tardio: '2026-04-09',
      holgura: 0,
      desfase: 0,
      es_critica: true,
      bloqueada: false,
      avance_pct: '100',
    },
    {
      actividad_id: 'a2',
      descripcion: 'Instalación provisional',
      frente_id: 'f-cim',
      duracion_dias: '3',
      dependencias: [{ ref: 'a1', tipo: 'FS', lag_dias: 0 }],
      inicio_temprano: '2026-04-10',
      fin_temprano: '2026-04-12',
      inicio_tardio: '2026-04-17',
      fin_tardio: '2026-04-19',
      holgura: 7,
      desfase: 0,
      es_critica: false,
      bloqueada: false,
      avance_pct: '20',
    },
  ],
} as RutaCriticaRespuesta;

function pintar(onSeleccionar = vi.fn()) {
  const filas = construirFilas(null, RUTA);
  const escala = construirEscala(
    filas.map((fila) => ({ inicio: fila.inicio, fin: fila.fin })),
    RUTA.fecha_corte,
  );
  if (escala === null) throw new Error('la escala no debería ser nula con estas fechas');

  const { container } = render(
    <Gantt
      grupos={agruparPorFrente(filas, FRENTES)}
      escala={escala}
      fechaCorte={RUTA.fecha_corte}
      seleccionada={null}
      onSeleccionar={onSeleccionar}
    />,
  );
  return { container, onSeleccionar };
}

describe('Gantt (§11.2 "ruta crítica resaltada")', () => {
  it('agrupa las actividades por frente en el orden del catálogo', () => {
    pintar();
    const grupos = screen.getAllByRole('heading', { level: 3 });
    expect(grupos.map((grupo) => grupo.textContent)).toEqual([
      expect.stringContaining('Obra negra · Preliminares'),
      expect.stringContaining('Obra negra · Cimentación'),
    ]);
    expect(grupos[0]?.textContent).toContain('1 en ruta crítica');
  });

  it('cada actividad es un botón con sus fechas, su duración y su estado en texto', () => {
    pintar();
    const critica = screen.getByRole('button', { name: /Trazo y nivelación/ });
    expect(critica).toHaveTextContent('06 abr 26');
    expect(critica).toHaveTextContent('09 abr 26');
    expect(critica).toHaveTextContent('En ruta crítica');
  });

  it('muestra la holgura que reportó el motor, sin recalcularla', () => {
    pintar();
    const holgada = screen.getByRole('button', { name: /Instalación provisional/ });
    expect(holgada).toHaveTextContent('holgura 7.00 d');
    expect(holgada).not.toHaveTextContent('En ruta crítica');
  });

  it('resalta con el tono de peligro solo la barra de la ruta crítica', () => {
    const { container } = pintar();
    expect(container.querySelectorAll('.gantt__bar').length).toBe(2);
    expect(container.querySelectorAll('.gantt__bar--danger').length).toBe(1);
  });

  it('marca la semana de la fecha de corte en el encabezado', () => {
    const { container } = pintar();
    const marcadas = container.querySelectorAll('.gantt__week.is-now');
    expect(marcadas.length).toBe(1);
    expect(marcadas[0]?.textContent).toBe('13 abr');
  });

  it('seleccionar una actividad avisa al padre con la fila completa', () => {
    const { onSeleccionar } = pintar();
    fireEvent.click(screen.getByRole('button', { name: /Instalación provisional/ }));
    expect(onSeleccionar).toHaveBeenCalledTimes(1);
    expect(onSeleccionar.mock.calls[0]?.[0]).toMatchObject({
      actividadId: 'a2',
      esCritica: false,
      holguraDias: 7,
    });
  });

  it('una actividad sin fechas se lista igual, avisando que no tiene barra', () => {
    const filas = construirFilas(null, {
      ...RUTA,
      actividades: [
        ...RUTA.actividades,
        {
          ...RUTA.actividades[1]!,
          actividad_id: 'a3',
          descripcion: 'Acabados',
          inicio_temprano: '',
          fin_temprano: '',
        },
      ],
    } as RutaCriticaRespuesta);

    const escala = construirEscala(
      filas.map((fila) => ({ inicio: fila.inicio, fin: fila.fin })),
      RUTA.fecha_corte,
    );

    render(
      <Gantt
        grupos={agruparPorFrente(filas, FRENTES)}
        escala={escala!}
        fechaCorte={RUTA.fecha_corte}
        seleccionada={null}
        onSeleccionar={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /Acabados/ })).toBeInTheDocument();
    expect(screen.getByText('sin fechas')).toBeInTheDocument();
  });
});

describe('editor de dependencias (§7.5)', () => {
  it('agrega y quita predecesoras sin tocar el resto', () => {
    const onCambio = vi.fn();
    render(
      <EditorDependencias
        idBase="prueba"
        dependencias={[]}
        onCambio={onCambio}
        vacio="Sin predecesoras."
      />,
    );

    expect(screen.getByText('Sin predecesoras.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar predecesora' }));
    expect(onCambio).toHaveBeenCalledWith([{ ref: '', tipo: 'FS', lagDias: '0' }]);
  });

  it('con catálogo ofrece un select y conserva una ref que ya no está en él', () => {
    render(
      <EditorDependencias
        idBase="prueba"
        dependencias={[{ ref: 'vieja', tipo: 'FS', lagDias: '0' }]}
        onCambio={vi.fn()}
        opciones={[{ valor: 'a1', etiqueta: 'Trazo y nivelación' }]}
        vacio="Sin predecesoras."
      />,
    );

    const select = screen.getByLabelText('Predecesora');
    expect(select).toHaveValue('vieja');
    expect(screen.getByRole('option', { name: 'Trazo y nivelación' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'vieja' })).toBeInTheDocument();
  });

  it('sin catálogo captura la ref como texto (programa base, §7.5)', () => {
    render(
      <EditorDependencias
        idBase="prueba"
        dependencias={[{ ref: '', tipo: 'FS', lagDias: '0' }]}
        onCambio={vi.fn()}
        vacio="Sin predecesoras."
        pistaRef="La ref es el prototipo_nodo_id."
      />,
    );

    expect(screen.getByPlaceholderText('uuid de la predecesora')).toBeInTheDocument();
    expect(screen.getByText('La ref es el prototipo_nodo_id.')).toBeInTheDocument();
  });
});
