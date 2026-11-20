/**
 * La matriz de la zona de losa en el panel de zonas (fase 2): solo se pinta lo que responde el servidor; Control de obra cambia el tipo, el uso y los
 * elementos (a mano o con una línea del plano); Costos y los demás solo leen y Costos propone los conceptos que faltan.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  matriz: { current: undefined as unknown, error: null as unknown, parametros: [] as unknown[] },
  ficha: { current: undefined as unknown },
  agregar: vi.fn(),
  cambiarElemento: vi.fn(),
  quitar: vi.fn(),
  proponer: vi.fn(),
  cambiarZona: vi.fn(),
}));

vi.mock('@/api/generado/losas/losas', () => ({
  getMatrizDeLaZonaApiV1ZonasDeLosaZonaIdMatrizGetQueryKey: (id: string) => ['matriz', id],
  useMatrizDeLaZonaApiV1ZonasDeLosaZonaIdMatrizGet: (_id: string, params: unknown) => {
    m.matriz.parametros.push(params);
    return { data: m.matriz.current, isLoading: false, isError: m.matriz.error !== null, error: m.matriz.error };
  },
  useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet: () => ({ data: m.ficha.current }),
  useAgregarElementoApiV1ZonasDeLosaZonaIdElementosPost: () => ({ mutateAsync: m.agregar, isPending: false }),
  useCambiarElementoApiV1ElementosDeLosaElementoIdPut: () => ({ mutateAsync: m.cambiarElemento, isPending: false }),
  useQuitarElementoApiV1ElementosDeLosaElementoIdDelete: () => ({ mutateAsync: m.quitar, isPending: false }),
  useProponerConceptosDeLaZonaApiV1ZonasDeLosaZonaIdMatrizProponerConceptosPost: () => ({ mutateAsync: m.proponer, isPending: false }),
}));
vi.mock('@/api/generado/zonas-de-losa/zonas-de-losa', () => ({
  useCambiarZonaApiV1ZonasDeLosaZonaIdPut: () => ({ mutateAsync: m.cambiarZona, isPending: false }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { MatrizDeLaZona } from '@/cuantificador/MatrizDeLaZona';

const ZONA = {
  id: 'z1', plano_id: 'p1', nombre: 'Entrepiso 3.00', nivel: 'PB', cota_piso_m: '0.000', altura_libre_m: '3.000', espesor_m: '0.120', tipo_de_losa: 'maciza',
  uso_de_losa: 'entrepiso', cota_inferior_m: '3.000', cota_superior_m: '3.120', losas: [], created_at: '2026-11-20T00:00:00Z', updated_at: '2026-11-20T00:00:00Z',
} as never;

const ELEMENTO = (extra: Record<string, unknown> = {}) => ({
  id: 'e1', clave: 'T-1-15x25', nombre: 'Trabe', categoria: 'trabes', modo: 'ml', cantidad: 10.5, largo_m: null, longitud_ml: 10.5, origen: 'manual', trazo_id: null,
  longitud_del_trazo_m: null, pago: 'en_la_losa', seccion: { ancho_cm: 15, peralte_cm: 25 }, acero_kg: 30, concreto_m3: 0.4, cimbra_m2: 6.8, advertencias: [], ...extra,
});

const MATRIZ = (extra: Record<string, unknown> = {}) => ({
  clave: 'LOSA-MACIZA', nombre: 'Losa maciza', tipo: 'maciza', uso: 'entrepiso', espesor_m: 0.12, capa_de_compresion_cm: null, area_m2: 32, losas: [],
  concreto: { clave: 'CON-00003', descripcion: 'C', geometrico_m3: 5.44, con_desperdicio_m3: 5.712, desperdicio_pct: 5 }, cimbra: { clave: 'MAD-00001', descripcion: 'CIMBRA', m2: 32 },
  parrilla: null, elementos: [ELEMENTO()], totales: {}, insumos: [],
  conceptos: [
    {
      parte: 'losa', elemento_clave: 'LOSA-MACIZA', ref: null, toma: ['concreto'], cantidad: 32, unidad: 'm²', nota: '', propuesta: null,
      concepto: { clave: 'EJ-800', descripcion: 'Losa maciza por m²', unidad: 'm²', estado: 'propuesto', provisional: true },
    },
    {
      parte: 'acero', elemento_clave: 'T-1-15x25', ref: 'e1', toma: ['acero'], cantidad: 10.5, unidad: 'ml', nota: '', propuesta: null,
      concepto: { clave: 'AUX-00008', descripcion: 'Trabe T-1', unidad: 'ml', estado: 'catalogo', provisional: false },
    },
    {
      parte: 'colado', elemento_clave: 'T-1-15x25', ref: 'e1', toma: ['concreto', 'cimbra'], cantidad: 10.5, unidad: 'ml', nota: '',
      propuesta: { id: 'p1', estado: 'autorizada', version: 1, elemento_clave: 'T-1-15x25' },
      concepto: { clave: 'EJ-703', descripcion: 'Colado y cimbra', unidad: 'ml', estado: 'propuesto', provisional: true },
    },
  ],
  mano_de_obra: { estado: 'sin_mano_de_obra', nota: 'Sin mano de obra ni precios.', destajos_candidatos: [] },
  advertencias: ['Solape informado.'], pendientes: [], drivers_usados: [], zona: null, escala_definida: true, conciliacion: null, ...extra,
});

function pintar(rol: string | null, puedeEditar: boolean) {
  const onCambio = vi.fn();
  const onError = vi.fn();
  render(<MatrizDeLaZona zona={ZONA} puedeEditar={puedeEditar} rol={rol} onCambio={onCambio} onError={onError} />);
  fireEvent.click(screen.getByRole('button', { name: 'Matriz de conceptos de Entrepiso 3.00' }));
  return { onCambio, onError };
}

beforeEach(() => {
  for (const f of [m.agregar, m.cambiarElemento, m.quitar, m.proponer, m.cambiarZona]) f.mockReset();
  m.agregar.mockResolvedValue({});
  m.cambiarElemento.mockResolvedValue({});
  m.quitar.mockResolvedValue(undefined);
  m.proponer.mockResolvedValue({ creadas: ['a'], omitidas: [] });
  m.cambiarZona.mockResolvedValue({});
  m.matriz.current = MATRIZ();
  m.matriz.error = null;
  m.matriz.parametros = [];
  m.ficha.current = { elementos_permitidos: [{ clave: 'T-1-15x25', tiene_concepto_de_colado: true }, { clave: 'N-1-12x25', tiene_concepto_de_colado: true }] };
});

describe('MatrizDeLaZona', () => {
  it('está cerrada hasta que se abre y pinta la matriz que responde el servidor', () => {
    render(<MatrizDeLaZona zona={ZONA} puedeEditar rol="control_obra" onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByTestId('cuerpo-de-la-matriz')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Matriz de conceptos de Entrepiso 3.00' }));
    expect(screen.getByTestId('matriz-resumen')).toHaveTextContent('Área 32.00 m²');
    expect(screen.getByTestId('matriz-resumen')).toHaveTextContent('5.712 m³');
    const tabla = screen.getByTestId('conceptos-de-la-zona');
    expect(tabla.querySelector('[data-concepto="EJ-800"]')).toHaveAttribute('data-estado', 'sin_proponer');
    expect(tabla.querySelector('[data-concepto="AUX-00008"]')).toHaveAttribute('data-estado', 'catalogo');
    expect(tabla.querySelector('[data-concepto="EJ-703"]')).toHaveAttribute('data-estado', 'autorizada');
    expect(tabla.querySelector('[data-concepto="EJ-703"]')).toHaveTextContent('autorizado · versión 1');
    expect(screen.getByTestId('matriz-sin-mano-de-obra')).toHaveTextContent('Sin mano de obra ni precios.');
    const elemento = screen.getByTestId('elemento-de-la-zona');
    expect(elemento).toHaveTextContent('10.50 ml');
  });

  it('Control de obra cambia el tipo y el uso sin pisar el resto de la zona', async () => {
    pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Tipo de losa de la zona'), { target: { value: 'nervada' } });
    await waitFor(() =>
      expect(m.cambiarZona).toHaveBeenCalledWith({
        zonaId: 'z1',
        data: {
          nombre: 'Entrepiso 3.00', nivel: 'PB', cota_piso_m: '0.000', altura_libre_m: '3.000', espesor_m: '0.120', tipo_de_losa: 'nervada', uso_de_losa: 'entrepiso',
        },
      }),
    );
    fireEvent.change(screen.getByLabelText('Uso de la losa de la zona'), { target: { value: 'azotea' } });
    await waitFor(() => expect(m.cambiarZona).toHaveBeenLastCalledWith({ zonaId: 'z1', data: expect.objectContaining({ tipo_de_losa: 'maciza', uso_de_losa: 'azotea' }) }));
  });

  it('agrega un elemento a mano con su modo, su largo y su pago, cambia su pago y lo quita', async () => {
    pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Elemento por agregar'), { target: { value: 'N-1-12x25' } });
    fireEvent.change(screen.getByLabelText('Se mide por'), { target: { value: 'pieza' } });
    fireEvent.change(screen.getByLabelText('Cantidad del elemento'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Largo de la pieza'), { target: { value: '5.5' } });
    fireEvent.change(screen.getByLabelText('Pago del elemento por agregar'), { target: { value: 'propio' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar elemento' }));
    await waitFor(() =>
      expect(m.agregar).toHaveBeenCalledWith({ zonaId: 'z1', data: { elemento_clave: 'N-1-12x25', modo: 'pieza', cantidad: 4, largo_m: 5.5, pago: 'propio' } }),
    );
    fireEvent.change(screen.getByLabelText('Pago de T-1-15x25'), { target: { value: 'propio' } });
    await waitFor(() =>
      expect(m.cambiarElemento).toHaveBeenCalledWith({
        elementoId: 'e1', data: { elemento_clave: 'T-1-15x25', modo: 'ml', pago: 'propio', cantidad: 10.5, largo_m: null },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Quitar T-1-15x25 de la matriz' }));
    await waitFor(() => expect(m.quitar).toHaveBeenCalledWith({ elementoId: 'e1' }));
  });

  it('un elemento medido de una línea del plano conserva su línea al cambiar el pago y dice de dónde sale la medida', async () => {
    m.matriz.current = MATRIZ({ elementos: [ELEMENTO({ origen: 'trazo', trazo_id: 't9', cantidad: 6, longitud_ml: 6, longitud_del_trazo_m: 6 })] });
    pintar('control_obra', true);
    expect(screen.getByTestId('elemento-de-la-zona')).toHaveTextContent('de la línea del plano (6.00 m)');
    fireEvent.change(screen.getByLabelText('Pago de T-1-15x25'), { target: { value: 'propio' } });
    await waitFor(() =>
      expect(m.cambiarElemento).toHaveBeenCalledWith({ elementoId: 'e1', data: { elemento_clave: 'T-1-15x25', modo: 'ml', pago: 'propio', trazo_id: 't9' } }),
    );
  });

  it('una cantidad que no vale no se manda', async () => {
    const { onError } = pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Cantidad del elemento'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar elemento' }));
    await waitFor(() => expect(onError).toHaveBeenCalled());
    expect(m.agregar).not.toHaveBeenCalled();
  });

  it('Costos lee la matriz sin poder editar y propone los conceptos que faltan', async () => {
    const { onCambio } = pintar('costos', false);
    expect(screen.queryByRole('group', { name: 'Agregar un elemento a la zona' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quitar T-1-15x25 de la matriz' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Tipo de losa de la zona')).toBeDisabled();
    expect(screen.getByLabelText('Pago de T-1-15x25')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Proponer los conceptos que faltan (1)' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ zonaId: 'z1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(expect.stringContaining('Se propusieron 1 concepto nuevo')));
  });

  it('un residente no ve el botón de proponer', () => {
    pintar('residente', false);
    expect(screen.queryByRole('button', { name: /Proponer los conceptos que faltan/ })).not.toBeInTheDocument();
  });

  it('concilia con un concepto del catálogo: manda la clave en mayúsculas y pinta las marcas', async () => {
    const { rerender } = render(<MatrizDeLaZona zona={ZONA} puedeEditar rol="control_obra" onCambio={vi.fn()} onError={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Matriz de conceptos de Entrepiso 3.00' }));
    fireEvent.change(screen.getByLabelText('Clave del concepto del catálogo'), { target: { value: ' est-21011 ' } });
    m.matriz.current = MATRIZ({
      conciliacion: {
        concepto: { clave: 'EST-21011', descripcion: 'Losa maciza de 12 cm (125 m2)', unidad: 'act' }, nota: 'El concepto del catálogo es un lote por prototipo.',
        filas: [
          { clave: 'MAD-00001', descripcion: 'CIMBRA 3 MTS', unidad: 'm²', catalogo: 125, elemento: 32, diferencia: -0.74, diferencia_pct: -74, marca: '≠' },
          { clave: 'ACE-00099', descripcion: 'MALLA', unidad: 'kg', catalogo: 5, elemento: null, diferencia: null, diferencia_pct: null, marca: 'solo_catalogo' },
        ],
        mano_de_obra: [], resumen: {}, coincide: false,
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Conciliar' }));
    rerender(<MatrizDeLaZona zona={ZONA} puedeEditar rol="control_obra" onCambio={vi.fn()} onError={vi.fn()} />);
    expect(m.matriz.parametros.at(-1)).toEqual({ concepto_clave: 'EST-21011' });
    const c = screen.getByTestId('conciliacion-de-la-zona');
    expect(c).toHaveAttribute('data-concepto-conciliado', 'EST-21011');
    expect(within(c).getByText('solo en el catálogo')).toBeInTheDocument();
    expect(c.querySelector('[data-marca="≠"]')).toBeInTheDocument();
  });

  it('un error del servidor se muestra', () => {
    m.matriz.current = undefined;
    m.matriz.error = new Error('El concepto EST-X no está en el catálogo vigente.');
    pintar('control_obra', true);
    expect(screen.getByRole('alert')).toHaveTextContent('no está en el catálogo vigente');
  });

  it('un plano sin escala calibrada lo avisa', () => {
    m.matriz.current = MATRIZ({ escala_definida: false });
    pintar('control_obra', true);
    expect(screen.getByText(/no tiene escala calibrada: se toma 1 unidad de plano = 1 m/)).toBeInTheDocument();
  });

  describe('por espacio (0143)', () => {
    const ESPACIOS = [
      { id: 'r', nombre: 'Recámara 1' },
      { id: 'b', nombre: 'Baño' },
    ] as never;
    const fila = (clave: string, cantidad: number, resolucion: Record<string, unknown>) => ({
      parte: 'acero', elemento_clave: 'T-1-15x25', ref: 'e1', toma: ['acero'], cantidad, unidad: 'ml', nota: '',
      concepto: { clave, descripcion: 'Trabe T-1', unidad: 'ml', estado: 'catalogo', provisional: false }, resolucion,
    });
    const POR_ESPACIO = [
      {
        espacio_id: 'r', espacio_nombre: 'Recámara 1', area_m2: 12, longitud_de_elementos_ml: 5, concreto_m3: 1, cimbra_m2: 12, acero_de_elementos_kg: 3,
        conceptos: [
          fila('AUX-00008', 5, { estado: 'cuenta', cuenta: true, aviso: null, concepto_id: 'c1', partida_id: 'p1', partida_nombre: 'Acero recámara' }),
          fila('AUX-00009', 0, { estado: 'sin_cantidad', cuenta: false, aviso: null, concepto_id: null, partida_id: null, partida_nombre: null }),
        ],
      },
      {
        espacio_id: null, espacio_nombre: null, area_m2: 0, longitud_de_elementos_ml: 3, concreto_m3: 0, cimbra_m2: 0, acero_de_elementos_kg: 1,
        conceptos: [fila('AUX-00008', 3, { estado: 'sin_espacio', cuenta: false, aviso: 'Sin espacio', concepto_id: 'c1', partida_id: null, partida_nombre: null })],
      },
    ];

    function pintarConEspacios(puedeEditar: boolean) {
      m.matriz.current = MATRIZ({ elementos: [ELEMENTO({ espacio_id: 'r' })], por_espacio: POR_ESPACIO });
      render(<MatrizDeLaZona zona={ZONA} puedeEditar={puedeEditar} rol="control_obra" espacios={ESPACIOS} onCambio={vi.fn()} onError={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Matriz de conceptos de Entrepiso 3.00' }));
    }

    it('cada elemento elige su espacio y se conserva al cambiar el pago', async () => {
      pintarConEspacios(true);
      const sel = screen.getByLabelText('Espacio de T-1-15x25');
      expect(sel).toHaveValue('r');
      fireEvent.change(sel, { target: { value: 'b' } });
      await waitFor(() =>
        expect(m.cambiarElemento).toHaveBeenCalledWith({
          elementoId: 'e1', data: { elemento_clave: 'T-1-15x25', modo: 'ml', pago: 'en_la_losa', espacio_id: 'b', cantidad: 10.5, largo_m: null },
        }),
      );
      fireEvent.change(screen.getByLabelText('Pago de T-1-15x25'), { target: { value: 'propio' } });
      await waitFor(() =>
        expect(m.cambiarElemento).toHaveBeenLastCalledWith({
          elementoId: 'e1', data: { elemento_clave: 'T-1-15x25', modo: 'ml', pago: 'propio', espacio_id: 'r', cantidad: 10.5, largo_m: null },
        }),
      );
      fireEvent.change(sel, { target: { value: '' } });
      await waitFor(() => expect(m.cambiarElemento).toHaveBeenLastCalledWith({ elementoId: 'e1', data: expect.objectContaining({ espacio_id: null }) }));
    });

    it('un elemento nuevo puede nacer en un espacio', async () => {
      pintarConEspacios(true);
      fireEvent.change(screen.getByLabelText('Espacio del elemento por agregar'), { target: { value: 'b' } });
      fireEvent.click(screen.getByRole('button', { name: 'Agregar elemento' }));
      await waitFor(() =>
        expect(m.agregar).toHaveBeenCalledWith({ zonaId: 'z1', data: { elemento_clave: 'T-1-15x25', modo: 'ml', cantidad: 10, largo_m: null, pago: 'en_la_losa', espacio_id: 'b' } }),
      );
    });

    it('la matriz por espacio dice en qué partida cuenta cada concepto y por qué no cuenta el resto', () => {
      pintarConEspacios(true);
      const tabla = screen.getByTestId('matriz-por-espacio');
      const filas = within(tabla).getAllByRole('row').slice(1);
      expect(filas).toHaveLength(2); // la de cantidad cero no se pinta
      expect(filas[0]).toHaveAttribute('data-espacio', 'Recámara 1');
      expect(filas[0]).toHaveTextContent('Acero recámara');
      expect(filas[1]).toHaveAttribute('data-espacio', 'sin espacio');
      expect(filas[1]).toHaveTextContent('sin espacio: no se escribe');
    });

    it('los demás roles leen: el espacio del elemento va deshabilitado', () => {
      pintarConEspacios(false);
      expect(screen.getByLabelText('Espacio de T-1-15x25')).toBeDisabled();
    });

    it('sin espacios en la obra y sin nada asignado no aparece nada de espacios', () => {
      pintar('control_obra', true);
      expect(screen.queryByLabelText('Espacio de T-1-15x25')).not.toBeInTheDocument();
      expect(screen.queryByTestId('matriz-por-espacio')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Espacio del elemento por agregar')).not.toBeInTheDocument();
    });
  });
});
