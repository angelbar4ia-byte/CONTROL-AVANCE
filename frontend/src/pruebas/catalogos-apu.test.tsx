/**
 * Explosión del APU y tablas de catálogo: render y navegación con teclado.
 *
 * El editor de APU es la pantalla nueva de la Fase 2 y su valor está en
 * poder recorrer el árbol: cada nodo con hijos es un botón con
 * `aria-expanded`, así que estas pruebas fijan el patrón de disclosure. No
 * prueban reglas —esas van en `catalogos.test.ts`— sino que la UI las
 * respeta: que el destajo se marque como lo marcó el backend y que la
 * prioridad de CLAVE (§3.3) se vea en la tabla.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import type {
  ConceptoRespuesta,
  FamiliaRespuesta,
  InsumoRespuesta,
  LineaExplosionRespuesta,
  UnidadRespuesta,
} from '@/api/generado/modelo';
import { ArbolExplosion } from '@/catalogos/ArbolExplosion';
import { armarArbolExplosion } from '@/catalogos/explosion';
import { buscarPorClave } from '@/catalogos/busqueda';
import { TablaConceptos, TablaInsumos } from '@/catalogos/Tablas';

const LINEAS: readonly LineaExplosionRespuesta[] = [
  {
    ruta: ['EST-01'],
    nivel: 1,
    tipo_hijo: 'concepto',
    referencia: 'AUX-01',
    categoria: 'auxiliar',
    cantidad_unitaria: '0.03',
    cantidad: '0.03',
    costo_unitario: '2500.0000',
    importe: '75.0000',
    es_destajo: false,
  },
  {
    ruta: ['EST-01', 'AUX-01'],
    nivel: 2,
    tipo_hijo: 'insumo',
    referencia: 'MOA-01',
    categoria: 'mano_obra',
    cantidad_unitaria: '1',
    cantidad: '0.03',
    costo_unitario: '400.0000',
    importe: '12.0000',
    es_destajo: true,
  },
  {
    ruta: ['EST-01'],
    nivel: 1,
    tipo_hijo: 'insumo',
    referencia: 'MAT-CEMENTO',
    categoria: 'material',
    cantidad_unitaria: '2',
    cantidad: '2',
    costo_unitario: '250.0000',
    importe: '500.0000',
    es_destajo: false,
  },
];

const UNIDADES: readonly UnidadRespuesta[] = [
  { id: 'u1', clave: 'M2', nombre: 'Metro cuadrado' },
];

const FAMILIAS: readonly FamiliaRespuesta[] = [
  { id: 'f1', clave: 'FAM-PET', nombre: 'Pétreos', iva_aplica: false },
  { id: 'f2', clave: 'FAM-ACE', nombre: 'Acero', iva_aplica: true },
];

describe('ArbolExplosion (§7.3)', () => {
  function pintar() {
    render(<ArbolExplosion nodos={armarArbolExplosion(LINEAS)} clave="EST-01" />);
  }

  it('arranca plegado: el auxiliar oculta su composición', () => {
    pintar();

    const auxiliar = screen.getByRole('button', { name: /AUX-01/ });
    expect(auxiliar).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('MOA-01')).toBeNull();
  });

  it('despliega el auxiliar y muestra la mano de obra que trae dentro', () => {
    pintar();

    fireEvent.click(screen.getByRole('button', { name: /AUX-01/ }));

    expect(screen.getByText('MOA-01')).toBeInTheDocument();
    expect(screen.getByText('Mano de obra')).toBeInTheDocument();
  });

  it('marca como destajo solo lo que el backend marcó (§7.3)', () => {
    pintar();
    fireEvent.click(screen.getByRole('button', { name: /AUX-01/ }));

    // Una sola línea trae `es_destajo`: la MO de dentro del auxiliar.
    expect(screen.getAllByText('destajo')).toHaveLength(1);
  });

  it('los insumos hoja no son desplegables', () => {
    pintar();
    expect(screen.queryByRole('button', { name: /MAT-CEMENTO/ })).toBeNull();
    expect(screen.getByText('MAT-CEMENTO')).toBeInTheDocument();
  });

  it('muestra el importe que vino calculado, sin recomponerlo', () => {
    pintar();
    expect(screen.getByText('$500.00')).toBeInTheDocument();
  });

  it('un concepto sin composición lo dice en vez de quedarse en blanco', () => {
    render(<ArbolExplosion nodos={[]} clave="EST-99" />);
    expect(screen.getByText(/no tiene composición cargada/)).toBeInTheDocument();
  });
});

describe('TablaInsumos: IVA por familia con override (§3.5)', () => {
  const insumos: readonly InsumoRespuesta[] = [
    {
      id: 'i1',
      tipo: 'material',
      clave: 'MAT-GRAVA',
      descripcion: 'Grava',
      familia_id: 'f1',
      unidad_id: 'u1',
      costo_base: '300',
      iva_aplica: null,
    },
    {
      id: 'i2',
      tipo: 'material',
      clave: 'MAT-VARILLA',
      descripcion: 'Varilla del 3',
      familia_id: 'f2',
      unidad_id: 'u1',
      costo_base: '180',
      iva_aplica: false,
    },
  ];

  function pintar(texto = '') {
    render(
      <TablaInsumos
        resultados={buscarPorClave(insumos, texto, (insumo) => insumo.descripcion)}
        unidades={UNIDADES}
        familias={FAMILIAS}
        cargando={false}
        vacia="No hay materiales con estos filtros."
      />,
    );
  }

  it('la familia exenta se refleja sin marcar override', () => {
    pintar();

    const fila = screen.getByText('MAT-GRAVA').closest('tr');
    expect(fila).not.toBeNull();
    expect(fila).toHaveTextContent('Exento');
    expect(fila?.textContent).not.toContain('override');
  });

  it('un insumo que contradice a su familia se marca como override', () => {
    pintar();

    const fila = screen.getByText('MAT-VARILLA').closest('tr');
    expect(fila).toHaveTextContent('Exento');
    expect(fila).toHaveTextContent('override');
  });

  it('la clave de la familia y de la unidad se muestran, no sus uuid', () => {
    pintar();
    expect(screen.getAllByText('FAM-PET')).toHaveLength(1);
    expect(screen.getAllByText('M2')).toHaveLength(2);
  });

  it('sin resultados avisa en vez de dejar la tabla muda', () => {
    pintar('no-existe');
    expect(screen.getByText('No hay materiales con estos filtros.')).toBeInTheDocument();
  });
});

describe('TablaConceptos: prioridad de CLAVE y acceso al APU (§3.3, §11.2)', () => {
  const conceptos: readonly ConceptoRespuesta[] = [
    { id: 'c1', tipo: 'concepto', clave: 'EST-MURO', descripcion: 'Muro de block', unidad_id: 'u1' },
    { id: 'c2', tipo: 'auxiliar', clave: 'AUX-01', descripcion: 'Mortero para muro' },
  ];

  function pintar(props: { texto?: string; onAbrirAPU?: () => void } = {}) {
    const onAbrirAPU = props.onAbrirAPU ?? vi.fn();
    render(
      <TablaConceptos
        resultados={buscarPorClave(conceptos, props.texto ?? '', (c) => c.descripcion)}
        unidades={UNIDADES}
        familias={FAMILIAS}
        cargando={false}
        conceptoAbierto={null}
        onAbrirAPU={onAbrirAPU}
      />,
    );
    return { onAbrirAPU };
  }

  it('marca la fila que casó por descripción y no por clave (§3.3)', () => {
    // "muro" está en la clave de uno y solo en la descripción del otro.
    pintar({ texto: 'muro' });

    const porClave = screen.getByText(/EST-MURO/).closest('tr');
    const porDescripcion = screen.getByText(/AUX-01/).closest('tr');

    expect(porClave?.textContent).not.toContain('desc');
    expect(porDescripcion).toHaveTextContent('desc');
  });

  it('abre el APU del concepto elegido', () => {
    const onAbrirAPU = vi.fn();
    pintar({ onAbrirAPU });

    fireEvent.click(screen.getAllByRole('button', { name: 'Ver APU' })[0]!);
    expect(onAbrirAPU).toHaveBeenCalledWith(conceptos[0]);
  });

  it('sin permiso de APU no se ofrece el botón (§11.2: CPU es C y SI)', () => {
    render(
      <TablaConceptos
        resultados={buscarPorClave(conceptos, '', (c) => c.descripcion)}
        unidades={UNIDADES}
        familias={FAMILIAS}
        cargando={false}
        conceptoAbierto={null}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Ver APU' })).toBeNull();
  });

  it('muestra el tipo del concepto, que es lo que permite anidar (§7.3)', () => {
    pintar();
    expect(screen.getByText('Auxiliar')).toBeInTheDocument();
    expect(screen.getByText('Concepto')).toBeInTheDocument();
  });
});
