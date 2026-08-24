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

import type {
  NodoPrototipoRespuesta,
  PartidaRespuesta,
  PresupuestoRespuesta,
} from '@/api/generado/modelo';
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

  describe('con presupuesto', () => {
    const PARTIDA: PartidaRespuesta = {
      id: 'partida-1',
      prototipo_nodo_id: 'est-1',
      unidad_clave: 'M2',
      cantidad: '12.5',
      precio_unitario: '1500',
      importe: '18750',
      orden: 1,
    };

    function presupuestoCon(partidas: PartidaRespuesta[]): PresupuestoRespuesta {
      return {
        id: 'presupuesto-1',
        prototipo_id: 'proto-1',
        prototipo_clave: 'CAS-1',
        version: 3,
        origen: 'excel',
        monto_total: '99999',
        created_at: '2026-01-01T00:00:00Z',
        partidas,
      };
    }

    it('muestra la cabecera de columnas', () => {
      render(
        <ArbolPrototipo nodos={armarArbolPrototipo([NIV, ECO, EST])} expandirTodo />,
      );
      expect(screen.getByText('Unidad')).toBeInTheDocument();
      expect(screen.getByText('Cantidad')).toBeInTheDocument();
      expect(screen.getByText('P.U.')).toBeInTheDocument();
      expect(screen.getByText('Importe')).toBeInTheDocument();
    });

    it('muestra unidad, cantidad, PU e importe del concepto con partida', () => {
      render(
        <ArbolPrototipo
          nodos={armarArbolPrototipo([NIV, ECO, EST])}
          presupuesto={presupuestoCon([PARTIDA])}
          expandirTodo
        />,
      );

      expect(screen.getByText('M2')).toBeInTheDocument();
      expect(screen.getByText('12.50')).toBeInTheDocument();
      expect(screen.getByText('$1,500.00')).toBeInTheDocument();
      // Aparece tres veces: la fila del concepto y el acumulado de su etapa
      // y su nivel (solo hay un concepto, así que los tres totales igualan).
      expect(screen.getAllByText('$18,750.00')).toHaveLength(3);
    });

    it('sin partida para su nodo, el concepto cae a su cantidad cruda del árbol', () => {
      render(
        <ArbolPrototipo
          nodos={armarArbolPrototipo([NIV, ECO, EST])}
          presupuesto={presupuestoCon([])}
          expandirTodo
        />,
      );

      expect(screen.getByText('1.00')).toBeInTheDocument();
      expect(screen.queryByText('$1,500.00')).toBeNull();
    });

    it('nivel y etapa no muestran unidad/cantidad/PU propios, solo el importe acumulado', () => {
      render(
        <ArbolPrototipo
          nodos={armarArbolPrototipo([NIV, ECO, EST])}
          presupuesto={presupuestoCon([PARTIDA])}
          expandirTodo
        />,
      );

      // "M2" y el P.U. son del concepto, uno solo — nivel/etapa no lo repiten.
      expect(screen.getAllByText('M2')).toHaveLength(1);
      expect(screen.getAllByText('$1,500.00')).toHaveLength(1);
    });

    it('muestra el total del presupuesto vigente en el pie', () => {
      render(
        <ArbolPrototipo
          nodos={armarArbolPrototipo([NIV, ECO, EST])}
          presupuesto={presupuestoCon([PARTIDA])}
          expandirTodo
        />,
      );

      expect(screen.getByText(/versión 3/)).toBeInTheDocument();
      expect(screen.getByText('$99,999.00')).toBeInTheDocument();
    });
  });
});
