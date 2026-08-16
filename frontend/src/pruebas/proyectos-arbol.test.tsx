/**
 * Árbol Proyecto → Cluster → Obra: render y navegación con teclado.
 *
 * El árbol es la pantalla nueva de la Fase 1 y su valor está en poder
 * recorrerlo: cada agrupador es un botón con `aria-expanded`, así que estas
 * pruebas fijan el patrón de disclosure y la selección de obra. No prueban
 * reglas —esas van en `proyectos.test.ts`— sino que la UI las respeta.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import type { ClusterRespuesta, ObraRespuesta, ProyectoRespuesta } from '@/api/generado/modelo';
import { construirArbol } from '@/proyectos/arbol';
import { ArbolProyecto } from '@/proyectos/ArbolProyecto';

const PROYECTOS: readonly ProyectoRespuesta[] = [
  { id: 'p1', clave: 'ALAMOS', nombre: 'Los Álamos' },
];

const CLUSTERS: readonly ClusterRespuesta[] = [
  { id: 'c1', proyecto_id: 'p1', clave: 'FRESNO', nombre: 'Manzana 1' },
];

const OBRAS: readonly ObraRespuesta[] = [
  {
    id: 'o1',
    cluster_id: 'c1',
    prototipo_id: 'pr1',
    clave: 'FRESNO 01',
    residente_id: null,
    estatus: 'en_proceso',
    fecha_inicio: null,
    fecha_fin: null,
    avance_pct: '42.5',
    m2: null,
    es_urba: false,
  },
];

function pintar(props: Partial<Parameters<typeof ArbolProyecto>[0]> = {}) {
  const onSeleccionarObra = vi.fn();
  render(
    <ArbolProyecto
      arbol={construirArbol(PROYECTOS, CLUSTERS, OBRAS)}
      obraSeleccionada={null}
      onSeleccionarObra={onSeleccionarObra}
      {...props}
    />,
  );
  return { onSeleccionarObra };
}

describe('ArbolProyecto', () => {
  it('abre los proyectos y deja los clusters plegados', () => {
    pintar();

    const proyecto = screen.getByRole('button', { name: /ALAMOS/ });
    expect(proyecto).toHaveAttribute('aria-expanded', 'true');

    const cluster = screen.getByRole('button', { name: /FRESNO Manzana 1/ });
    expect(cluster).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /FRESNO 01/ })).toBeNull();
  });

  it('despliega el cluster al activarlo y muestra la obra con su avance', () => {
    pintar();

    fireEvent.click(screen.getByRole('button', { name: /FRESNO Manzana 1/ }));

    const obra = screen.getByRole('button', { name: /FRESNO 01/ });
    expect(obra).toBeInTheDocument();
    expect(obra).toHaveTextContent('42.5%');
    expect(obra).toHaveTextContent('En proceso');
  });

  it('con expandirTodo muestra las obras sin desplegar a mano (filtro activo)', () => {
    const { onSeleccionarObra } = pintar({ expandirTodo: true });

    fireEvent.click(screen.getByRole('button', { name: /FRESNO 01/ }));
    expect(onSeleccionarObra).toHaveBeenCalledWith(OBRAS[0]);
  });

  it('solo ofrece las altas cuando el rol puede hacerlas (§11.2)', () => {
    pintar({ expandirTodo: true });
    expect(screen.queryByTitle('Nuevo cluster en este proyecto')).toBeNull();
    expect(screen.queryByTitle('Nueva obra en este cluster')).toBeNull();
  });

  it('muestra las acciones de alta cuando se pasan los callbacks', () => {
    const onNuevoCluster = vi.fn();
    const onNuevaObra = vi.fn();
    render(
      <ArbolProyecto
        arbol={construirArbol(PROYECTOS, CLUSTERS, OBRAS)}
        obraSeleccionada={null}
        onSeleccionarObra={vi.fn()}
        onNuevoCluster={onNuevoCluster}
        onNuevaObra={onNuevaObra}
        expandirTodo
      />,
    );

    fireEvent.click(screen.getByTitle('Nuevo cluster en este proyecto'));
    fireEvent.click(screen.getByTitle('Nueva obra en este cluster'));

    expect(onNuevoCluster).toHaveBeenCalledWith('p1');
    expect(onNuevaObra).toHaveBeenCalledWith('c1');
  });

  it('avisa cuando no hay nada en el alcance', () => {
    render(
      <ArbolProyecto
        arbol={construirArbol([], [], [])}
        obraSeleccionada={null}
        onSeleccionarObra={vi.fn()}
      />,
    );
    expect(screen.getByText(/No hay proyectos en tu alcance/)).toBeInTheDocument();
  });
});
