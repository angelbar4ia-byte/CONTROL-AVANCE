/**
 * Gantt jerárquico: el cronograma como árbol WBS (§7.4, §6, §11.2).
 *
 * `programacion-gantt.test.tsx` cubre el Gantt plano; esto cubre la otra vista:
 * que el árbol que devuelve `GET /obras/{id}/programa/arbol` se aplane en
 * renglones con su sangría, que colapsar una etapa esconda **toda** su rama,
 * que la profundidad de captura guardada (0041) decida qué se ve al abrir, y
 * que la barra resumen se dibuje como lectura —con su porcentaje ponderado— sin
 * ofrecer el panel de ajuste que sí tiene una actividad.
 *
 * El árbol de las pruebas es el del pedido:
 *
 *     ESTRUCTURA PB  (etapa)
 *       └ PLANTA BAJA (nivel)
 *           ├ muro
 *           └ castillo
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import type { ArbolDeProgramaRespuesta, RutaCriticaRespuesta } from '@/api/generado/modelo';
import { construirEscala } from '@/programacion/escala';
import { construirFilas } from '@/programacion/filas';
import { Gantt } from '@/programacion/Gantt';
import {
  alternarColapso,
  colapsadosPorDefecto,
  construirFilasJerarquia,
  filtrarJerarquiaPorTexto,
  resumirJerarquia,
  visiblesEnJerarquia,
} from '@/programacion/jerarquia';

const RUTA = {
  obra_id: 'o1',
  fecha_inicio: '2026-04-06',
  fecha_corte: '2026-04-15',
  fin_programado: '2026-04-26',
  programa_obra_id: 'p1',
  version: 1,
  calendario: { dias_habiles: [1, 2, 3, 4, 5, 6, 7], tipo: 'natural' },
  actividades: [
    {
      actividad_id: 'a-muro',
      descripcion: 'Muro de tabique',
      frente_id: null,
      duracion_dias: '15',
      dependencias: [],
      tramos: [],
      inicio_temprano: '2026-04-06',
      fin_temprano: '2026-04-21',
      inicio_tardio: '2026-04-06',
      fin_tardio: '2026-04-21',
      holgura: 0,
      desfase: 0,
      es_critica: true,
      bloqueada: false,
      avance_pct: '20',
    },
    {
      actividad_id: 'a-castillo',
      descripcion: 'Castillo ahogado',
      frente_id: null,
      duracion_dias: '5',
      dependencias: [],
      tramos: [],
      inicio_temprano: '2026-04-21',
      fin_temprano: '2026-04-26',
      inicio_tardio: '2026-04-21',
      fin_tardio: '2026-04-26',
      holgura: 0,
      desfase: 0,
      es_critica: false,
      bloqueada: false,
      avance_pct: '0',
    },
  ],
} as unknown as RutaCriticaRespuesta;

function arbol(
  cambios: Partial<ArbolDeProgramaRespuesta> = {},
): ArbolDeProgramaRespuesta {
  return {
    obra_id: 'o1',
    prototipo_id: 'proto-1',
    profundidad_captura: 'concepto',
    calendario: { dias_habiles: [1, 2, 3, 4, 5, 6, 7], tipo: 'natural' },
    n_conflictos: 0,
    nodos: [
      {
        nodo_id: 'n-etapa',
        tipo: 'etapa',
        nombre: 'ESTRUCTURA PB',
        parent_id: null,
        profundidad: 0,
        actividades: ['a-muro', 'a-castillo'],
        fecha_inicio: '2026-04-06',
        fecha_termino: '2026-04-26',
        duracion_dias: '20',
        duracion_hojas_dias: '20',
        avance_pct: '18.50',
        importe: '132000',
        conflicto: null,
      },
      {
        nodo_id: 'n-nivel',
        tipo: 'nivel',
        nombre: 'PLANTA BAJA',
        parent_id: 'n-etapa',
        profundidad: 1,
        actividades: ['a-muro', 'a-castillo'],
        fecha_inicio: '2026-04-06',
        fecha_termino: '2026-04-26',
        duracion_dias: '20',
        duracion_hojas_dias: '20',
        avance_pct: '18.50',
        importe: '132000',
        conflicto: null,
      },
      {
        nodo_id: 'n-muro',
        tipo: 'concepto',
        nombre: 'Muro de tabique',
        parent_id: 'n-nivel',
        profundidad: 2,
        actividades: ['a-muro'],
        fecha_inicio: '2026-04-06',
        fecha_termino: '2026-04-21',
        duracion_dias: '15',
        duracion_hojas_dias: '15',
        avance_pct: '20',
        importe: '122000',
        conflicto: null,
      },
      {
        nodo_id: 'n-castillo',
        tipo: 'concepto',
        nombre: 'Castillo ahogado',
        parent_id: 'n-nivel',
        profundidad: 2,
        actividades: ['a-castillo'],
        fecha_inicio: '2026-04-21',
        fecha_termino: '2026-04-26',
        duracion_dias: '5',
        duracion_hojas_dias: '5',
        avance_pct: '0',
        importe: '10000',
        conflicto: null,
      },
    ],
    ...cambios,
  } as unknown as ArbolDeProgramaRespuesta;
}

const FILAS = construirFilas(null, RUTA);

describe('aplanar el árbol WBS en renglones', () => {
  it('conserva el orden del recorrido en profundidad', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    expect(filas.map((f) => f.nodoId)).toEqual([
      'n-etapa',
      'n-nivel',
      'n-muro',
      'n-castillo',
    ]);
    expect(filas.map((f) => f.profundidad)).toEqual([0, 1, 2, 2]);
  });

  it('marca como resumen a nivel y etapa, y sólo a esos', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const porId = new Map(filas.map((f) => [f.nodoId, f]));
    expect(porId.get('n-etapa')?.esResumen).toBe(true);
    expect(porId.get('n-nivel')?.esResumen).toBe(true);
    expect(porId.get('n-muro')?.esResumen).toBe(false);
  });

  it('casa cada concepto con su actividad para no perder la criticidad', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const muro = filas.find((f) => f.nodoId === 'n-muro');
    expect(muro?.fila?.actividadId).toBe('a-muro');
    expect(muro?.fila?.esCritica).toBe(true);
    // Un resumen no tiene "la" actividad: la barra se deriva de todas.
    expect(filas.find((f) => f.nodoId === 'n-etapa')?.fila).toBeNull();
  });

  it('un concepto sin su actividad se dibuja igual con lo del árbol', () => {
    // Esconderlo dejaría un hueco en la jerarquía y una etapa que no cuadra.
    const filas = construirFilasJerarquia(arbol(), []);
    const muro = filas.find((f) => f.nodoId === 'n-muro');
    expect(muro).toBeDefined();
    expect(muro?.fila).toBeNull();
    expect(muro?.duracionDias).toBe(15);
  });

  it('sin árbol no hay renglones', () => {
    expect(construirFilasJerarquia(null, FILAS)).toEqual([]);
  });
});

describe('profundidad de captura y colapso', () => {
  it('capturar por etapa colapsa lo que cuelga de las etapas', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const colapsados = colapsadosPorDefecto(filas, 'etapa');
    expect([...colapsados]).toEqual(['n-etapa']);

    const visibles = visiblesEnJerarquia(filas, colapsados);
    expect(visibles.map((f) => f.nodoId)).toEqual(['n-etapa']);
  });

  it('colapsar una etapa esconde toda su rama, no sólo a sus hijos directos', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const visibles = visiblesEnJerarquia(filas, new Set(['n-etapa']));
    // Los conceptos cuelgan del nivel, no de la etapa: sin propagar el
    // escondido quedarían sueltos y sin encabezado.
    expect(visibles.map((f) => f.nodoId)).toEqual(['n-etapa']);
  });

  it('capturar por concepto no colapsa nada: es el árbol completo', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    expect(colapsadosPorDefecto(filas, 'concepto').size).toBe(0);
    expect(visiblesEnJerarquia(filas, new Set()).length).toBe(4);
  });

  it('la profundidad es un default, no una jaula: se puede expandir', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const inicial = colapsadosPorDefecto(filas, 'etapa');
    const expandido = alternarColapso(inicial, 'n-etapa');

    expect(visiblesEnJerarquia(filas, expandido).length).toBe(4);
    // No se mutó el conjunto original.
    expect(inicial.has('n-etapa')).toBe(true);
  });

  it('alternar dos veces vuelve al estado anterior', () => {
    const uno = alternarColapso(new Set(), 'n-nivel');
    expect(uno.has('n-nivel')).toBe(true);
    expect(alternarColapso(uno, 'n-nivel').has('n-nivel')).toBe(false);
  });
});

describe('filtro por texto sobre el árbol', () => {
  it('conserva los ancestros de lo que coincide', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const encontrados = filtrarJerarquiaPorTexto(filas, 'castillo');
    // La hoja sola no diría dónde está: se devuelve la rama.
    expect(encontrados.map((f) => f.nodoId)).toEqual([
      'n-etapa',
      'n-nivel',
      'n-castillo',
    ]);
  });

  it('sin texto devuelve todo y sin coincidencias devuelve nada', () => {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    expect(filtrarJerarquiaPorTexto(filas, '  ')).toHaveLength(4);
    expect(filtrarJerarquiaPorTexto(filas, 'plafón')).toHaveLength(0);
  });
});

describe('resumen del árbol', () => {
  it('cuenta resúmenes y conflictos, y toma el avance de la raíz', () => {
    const conConflicto = arbol({
      n_conflictos: 1,
      nodos: arbol().nodos.map((nodo) =>
        nodo.nodo_id === 'n-etapa'
          ? {
              ...nodo,
              conflicto: {
                nodo_id: 'n-etapa',
                nombre: 'ESTRUCTURA PB',
                dias_capturados: '20',
                dias_derivados: '23',
                actividades: ['a-muro', 'a-castillo'],
              },
            }
          : nodo,
      ),
    });

    const resumen = resumirJerarquia(construirFilasJerarquia(conConflicto, FILAS));
    expect(resumen.nNodos).toBe(4);
    expect(resumen.nResumenes).toBe(2);
    expect(resumen.nConflictos).toBe(1);
    expect(resumen.avanceRaiz).toBeCloseTo(18.5);
  });
});

describe('render del Gantt jerárquico', () => {
  function pintar(profundidad: 'concepto' | 'etapa' = 'concepto', onProgramar?: () => void) {
    const filas = construirFilasJerarquia(arbol(), FILAS);
    const colapsados = colapsadosPorDefecto(filas, profundidad);
    const visibles = visiblesEnJerarquia(filas, colapsados);
    const escala = construirEscala(
      visibles.map((f) => ({ inicio: f.inicio, fin: f.fin })),
      '2026-04-15',
    );
    if (escala === null) throw new Error('El árbol de prueba sí tiene fechas.');

    return render(
      <Gantt
        jerarquia={visibles}
        escala={escala}
        fechaCorte="2026-04-15"
        seleccionada={null}
        onSeleccionar={vi.fn()}
        colapsados={colapsados}
        onAlternar={vi.fn()}
        onProgramarNodo={onProgramar}
      />,
    );
  }

  it('dibuja la barra resumen de la etapa con su avance ponderado', () => {
    pintar();
    expect(screen.getByText('ESTRUCTURA PB')).toBeInTheDocument();
    // El avance del resumen no es el promedio de sus hojas: lo pondera el
    // backend por importe (§6) y aquí sólo se muestra.
    expect(screen.getByTitle(/ESTRUCTURA PB.*ponderado por importe/)).toBeInTheDocument();
  });

  it('el resumen no ofrece el panel de ajuste de una actividad', () => {
    pintar();
    // El concepto sí es un botón que abre su panel; el resumen no, porque no
    // es una fila de `actividad` (§11.3 A.2).
    expect(screen.getByRole('button', { name: /Muro de tabique/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^ESTRUCTURA PB/ })).toBeNull();
  });

  it('el resumen ofrece "Programar" sólo cuando el rol edita', () => {
    const alProgramar = vi.fn();
    pintar('concepto', alProgramar);
    const botones = screen.getAllByRole('button', { name: 'Programar' });
    expect(botones.length).toBe(2); // la etapa y el nivel
    fireEvent.click(botones[0]!);
    expect(alProgramar).toHaveBeenCalledTimes(1);
  });

  it('sin permiso de edición no hay botón de programar', () => {
    pintar();
    expect(screen.queryByRole('button', { name: 'Programar' })).toBeNull();
  });

  it('colapsado por etapa sólo se ve la etapa, y el control dice que se puede abrir', () => {
    pintar('etapa');
    expect(screen.getByText('ESTRUCTURA PB')).toBeInTheDocument();
    expect(screen.queryByText('PLANTA BAJA')).toBeNull();
    expect(
      screen.getByRole('button', { name: 'Expandir ESTRUCTURA PB' }),
    ).toHaveAttribute('aria-expanded', 'false');
  });

  it('marca el nodo en conflicto sin resolverlo', () => {
    const conConflicto = arbol({
      nodos: arbol().nodos.map((nodo) =>
        nodo.nodo_id === 'n-etapa'
          ? {
              ...nodo,
              conflicto: {
                nodo_id: 'n-etapa',
                nombre: 'ESTRUCTURA PB',
                dias_capturados: '20',
                dias_derivados: '23',
                actividades: ['a-muro', 'a-castillo'],
              },
            }
          : nodo,
      ),
    });
    const filas = construirFilasJerarquia(conConflicto, FILAS);
    const escala = construirEscala(
      filas.map((f) => ({ inicio: f.inicio, fin: f.fin })),
      null,
    );
    if (escala === null) throw new Error('El árbol de prueba sí tiene fechas.');

    render(
      <Gantt
        jerarquia={filas}
        escala={escala}
        fechaCorte={null}
        seleccionada={null}
        onSeleccionar={vi.fn()}
      />,
    );

    expect(screen.getByText('conflicto')).toBeInTheDocument();
    // Las dos cifras están a la vista: la decisión es del usuario (§7.5).
    expect(screen.getByTitle(/declara 20 días.*ocupan 23/)).toBeInTheDocument();
  });
});
