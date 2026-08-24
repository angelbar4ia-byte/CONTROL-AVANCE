/**
 * Árbol WBS del prototipo: armado (`arbolPrototipo.ts`) y render
 * (`ArbolPrototipo.tsx`) — nivel → etapa → concepto (§7.4).
 *
 * Mismo patrón que `proyectos-arbol.test.tsx`: las reglas de armado se
 * prueban aparte de la UI, y la UI se prueba por su patrón de disclosure,
 * no por reimplementar el armado.
 */

import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import type { NodoPrototipoRespuesta } from '@/api/generado/modelo';
import { armarArbolPrototipo, contarNodosDelArbol } from '@/proyectos/nodosPrototipo';
import { ArbolPrototipo } from '@/proyectos/ArbolPrototipo';

function nodo(datos: Partial<NodoPrototipoRespuesta> & { id: string }): NodoPrototipoRespuesta {
  return {
    parent_id: null,
    tipo: 'nivel',
    nombre: datos.id,
    clave: null,
    orden: 0,
    ...datos,
  };
}

const NIV = nodo({ id: 'niv-1', tipo: 'nivel', clave: 'NIV-1', nombre: 'Cimentación', orden: 1 });
const ECO = nodo({
  id: 'eco-1',
  parent_id: 'niv-1',
  tipo: 'etapa',
  clave: 'ECO-1',
  nombre: 'Estructura',
  orden: 1,
});
const EST = nodo({
  id: 'est-1',
  parent_id: 'eco-1',
  tipo: 'concepto',
  clave: 'EST-01',
  nombre: 'Losa de cimentación',
  orden: 1,
  cantidad: '1',
});

describe('armarArbolPrototipo', () => {
  it('anida por parent_id en recorrido padre-antes-que-hijos', () => {
    const arbol = armarArbolPrototipo([NIV, ECO, EST]);

    expect(arbol).toHaveLength(1);
    expect(arbol[0]?.nodo.id).toBe('niv-1');
    expect(arbol[0]?.hijos).toHaveLength(1);
    expect(arbol[0]?.hijos[0]?.nodo.id).toBe('eco-1');
    expect(arbol[0]?.hijos[0]?.hijos[0]?.nodo.id).toBe('est-1');
  });

  it('cuelga de la raíz un nodo cuyo padre no vino en la lista', () => {
    const huerfano = nodo({ id: 'eco-2', parent_id: 'niv-fuera-de-alcance', tipo: 'etapa' });
    const arbol = armarArbolPrototipo([NIV, huerfano]);

    expect(arbol.map((n) => n.nodo.id).sort()).toEqual(['eco-2', 'niv-1']);
  });

  it('cuenta todos los nodos, incluyendo los anidados', () => {
    expect(contarNodosDelArbol(armarArbolPrototipo([NIV, ECO, EST]))).toBe(3);
  });

  it('con la lista vacía da un árbol vacío', () => {
    expect(armarArbolPrototipo([])).toEqual([]);
  });
});

describe('ArbolPrototipo', () => {
  it('arranca plegado: el concepto no se ve hasta desplegar', () => {
    render(<ArbolPrototipo nodos={armarArbolPrototipo([NIV, ECO, EST])} />);

    expect(screen.getByRole('button', { name: /Cimentación/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.queryByText('Estructura')).toBeNull();
  });

  it('despliega nivel → etapa → concepto al ir abriendo cada uno', () => {
    render(<ArbolPrototipo nodos={armarArbolPrototipo([NIV, ECO, EST])} />);

    fireEvent.click(screen.getByRole('button', { name: /Cimentación/ }));
    fireEvent.click(screen.getByRole('button', { name: /Estructura/ }));

    expect(screen.getByText('Losa de cimentación')).toBeInTheDocument();
  });

  it('expandirTodo muestra el concepto sin desplegar a mano', () => {
    render(<ArbolPrototipo nodos={armarArbolPrototipo([NIV, ECO, EST])} expandirTodo />);
    expect(screen.getByText('Losa de cimentación')).toBeInTheDocument();
  });

  it('pinta el contenido de `extra` junto al nodo que corresponde', () => {
    render(
      <ArbolPrototipo
        nodos={armarArbolPrototipo([NIV, ECO, EST])}
        expandirTodo
        extra={(n) => (n.id === 'est-1' ? <span>5 d</span> : null)}
      />,
    );
    expect(screen.getByText('5 d')).toBeInTheDocument();
  });

  it('avisa cuando el prototipo no tiene ingeniería cargada', () => {
    render(<ArbolPrototipo nodos={[]} />);
    expect(screen.getByText(/no tiene ingeniería cargada todavía/)).toBeInTheDocument();
  });
});
