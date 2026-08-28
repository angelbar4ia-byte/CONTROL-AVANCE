/**
 * Árbol WBS del prototipo: armado (`nodosPrototipo.ts`) y render
 * (`ArbolPrototipo.tsx`) — prototipo → nivel → etapa →
 * concepto/concepto auxiliar (§7.4, §10.1).
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
import { armarArbolPrototipo, sumarImportesPorNodo } from '@/proyectos/nodosPrototipo';
import { ArbolPrototipo } from '@/proyectos/ArbolPrototipo';

const PROTOTIPO = { id: 'proto-1', clave: 'CAS-1', nombre: 'Casa modelo' };

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
  concepto_tipo: 'concepto',
});
const AUX = nodo({
  id: 'aux-1',
  parent_id: 'eco-1',
  tipo: 'concepto',
  clave: 'AUX-01',
  nombre: 'Mezcla de mortero',
  orden: 2,
  concepto_tipo: 'auxiliar',
});

describe('armarArbolPrototipo', () => {
  it('la raíz es el prototipo, con nivel → etapa → concepto anidados', () => {
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST]);

    expect(raiz).toEqual({
      id: 'proto-1',
      tipo: 'prototipo',
      clave: 'CAS-1',
      nombre: 'Casa modelo',
      cantidad: null,
      wbs: null,
      hijos: expect.any(Array),
    });
    expect(raiz.hijos).toHaveLength(1);
    expect(raiz.hijos[0]?.id).toBe('niv-1');
    expect(raiz.hijos[0]?.hijos[0]?.id).toBe('eco-1');
    expect(raiz.hijos[0]?.hijos[0]?.hijos[0]?.id).toBe('est-1');
  });

  it('numera cada nodo por su posición entre hermanos, colgada de la del padre', () => {
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST, AUX]);

    expect(raiz.wbs).toBeNull();
    expect(raiz.hijos[0]?.wbs).toBe('1'); // niv-1: único nivel
    expect(raiz.hijos[0]?.hijos[0]?.wbs).toBe('1.1'); // eco-1: única etapa
    expect(raiz.hijos[0]?.hijos[0]?.hijos[0]?.wbs).toBe('1.1.1'); // est-1: 1er concepto
    expect(raiz.hijos[0]?.hijos[0]?.hijos[1]?.wbs).toBe('1.1.2'); // aux-1: 2º concepto
  });

  it('un segundo nivel numera como hermano, no reinicia el prefijo del prototipo', () => {
    const NIV2 = nodo({ id: 'niv-2', tipo: 'nivel', clave: 'NIV-2', nombre: 'Planta baja', orden: 2 });
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, NIV2, ECO, EST]);

    const [uno, dos] = raiz.hijos;
    expect(uno?.wbs).toBe('1');
    expect(dos?.wbs).toBe('2');
  });

  it('distingue concepto auxiliar de concepto normal por concepto_tipo', () => {
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST, AUX]);
    const [normal, auxiliar] = raiz.hijos[0]?.hijos[0]?.hijos ?? [];

    expect(normal?.tipo).toBe('concepto');
    expect(auxiliar?.tipo).toBe('concepto_auxiliar');
  });

  it('cuelga de la raíz del prototipo un nodo cuyo padre no vino en la lista', () => {
    const huerfano = nodo({ id: 'eco-2', parent_id: 'niv-fuera-de-alcance', tipo: 'etapa' });
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, huerfano]);

    expect(raiz.hijos.map((n) => n.id).sort()).toEqual(['eco-2', 'niv-1']);
  });

  it('con la lista de nodos vacía, la raíz no tiene hijos', () => {
    expect(armarArbolPrototipo(PROTOTIPO, []).hijos).toEqual([]);
  });
});

describe('sumarImportesPorNodo', () => {
  it('sube el importe de los conceptos hasta la raíz', () => {
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST]);
    const partidaPorNodo = new Map<string, PartidaRespuesta>([
      [
        'est-1',
        {
          id: 'p1',
          prototipo_nodo_id: 'est-1',
          cantidad: '1',
          precio_unitario: '100',
          importe: '100',
          orden: 1,
        },
      ],
    ]);

    const totales = sumarImportesPorNodo(raiz, partidaPorNodo);
    expect(totales.get('est-1')).toBe(100);
    expect(totales.get('eco-1')).toBe(100);
    expect(totales.get('niv-1')).toBe(100);
    expect(totales.get('proto-1')).toBe(100);
  });

  it('sin partidas, todos los totales son cero', () => {
    const raiz = armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST]);
    const totales = sumarImportesPorNodo(raiz, new Map());
    expect(totales.get('proto-1')).toBe(0);
  });
});

describe('ArbolPrototipo', () => {
  it('la raíz (el prototipo) arranca abierta; nivel y etapa siguen plegados', () => {
    render(<ArbolPrototipo raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])} />);

    expect(screen.getByRole('button', { name: /CAS-1 Casa modelo/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByRole('button', { name: /Cimentación/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.queryByText('Estructura')).toBeNull();
  });

  it('despliega nivel → etapa → concepto al ir abriendo cada uno', () => {
    render(<ArbolPrototipo raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])} />);

    fireEvent.click(screen.getByRole('button', { name: /Cimentación/ }));
    fireEvent.click(screen.getByRole('button', { name: /Estructura/ }));

    expect(screen.getByText('Losa de cimentación')).toBeInTheDocument();
  });

  it('expandirTodo muestra el concepto sin desplegar a mano', () => {
    render(<ArbolPrototipo raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])} expandirTodo />);
    expect(screen.getByText('Losa de cimentación')).toBeInTheDocument();
  });

  it('marca el concepto auxiliar con una etiqueta, distinta del concepto normal', () => {
    render(
      <ArbolPrototipo
        raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST, AUX])}
        expandirTodo
      />,
    );

    expect(screen.getByText('Losa de cimentación')).toBeInTheDocument();
    expect(screen.getByText('Mezcla de mortero')).toBeInTheDocument();
    expect(screen.getByText('auxiliar')).toBeInTheDocument();
  });

  it('pinta el contenido de `extra` junto al nodo que corresponde', () => {
    render(
      <ArbolPrototipo
        raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])}
        expandirTodo
        extra={(n) => (n.id === 'est-1' ? <span>5 d</span> : null)}
      />,
    );
    expect(screen.getByText('5 d')).toBeInTheDocument();
  });

  it('avisa cuando el prototipo no tiene ingeniería cargada', () => {
    render(<ArbolPrototipo raiz={armarArbolPrototipo(PROTOTIPO, [])} />);
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
      render(<ArbolPrototipo raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])} expandirTodo />);
      expect(screen.getByText('Unidad')).toBeInTheDocument();
      expect(screen.getByText('Cantidad')).toBeInTheDocument();
      expect(screen.getByText('P.U.')).toBeInTheDocument();
      expect(screen.getByText('Importe')).toBeInTheDocument();
    });

    it('muestra unidad, cantidad, PU e importe del concepto con partida', () => {
      render(
        <ArbolPrototipo
          raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])}
          presupuesto={presupuestoCon([PARTIDA])}
          expandirTodo
        />,
      );

      expect(screen.getByText('M2')).toBeInTheDocument();
      expect(screen.getByText('12.50')).toBeInTheDocument();
      expect(screen.getByText('$1,500.00')).toBeInTheDocument();
      // El importe del concepto y el de su etapa/nivel coinciden (un solo
      // concepto en el árbol) — el de la raíz usa monto_total, distinto.
      expect(screen.getAllByText('$18,750.00')).toHaveLength(3);
    });

    it('sin partida para su nodo, el concepto cae a su cantidad cruda del árbol', () => {
      render(
        <ArbolPrototipo
          raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])}
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
          raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])}
          presupuesto={presupuestoCon([PARTIDA])}
          expandirTodo
        />,
      );

      // "M2" y el P.U. son del concepto, uno solo — nivel/etapa no lo repiten.
      expect(screen.getAllByText('M2')).toHaveLength(1);
      expect(screen.getAllByText('$1,500.00')).toHaveLength(1);
    });

    it('la raíz (el prototipo) muestra monto_total, no la suma del cliente', () => {
      render(
        <ArbolPrototipo
          raiz={armarArbolPrototipo(PROTOTIPO, [NIV, ECO, EST])}
          presupuesto={presupuestoCon([PARTIDA])}
          expandirTodo
        />,
      );

      // monto_total (99 999) es deliberadamente distinto a la suma real de
      // partidas (18 750): así la prueba distingue "vino del backend" de
      // "se recalculó en el cliente".
      expect(screen.getByText('$99,999.00')).toBeInTheDocument();
    });
  });
});
