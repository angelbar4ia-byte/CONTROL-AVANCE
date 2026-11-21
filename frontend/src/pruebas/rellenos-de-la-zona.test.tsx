/**
 * Los rellenos de la zona de losa en el panel de zonas (Fase 3): solo se pinta lo que responde el servidor; Control de obra agrega, cambia (parámetros y
 * espacio) y quita rellenos; los demás roles solo leen y Costos propone el concepto del compactado. Cada concepto dice en qué partida se mide.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calculo: { current: undefined as unknown, error: null as unknown, parametros: [] as unknown[] },
  agregar: vi.fn(),
  cambiar: vi.fn(),
  quitar: vi.fn(),
  proponer: vi.fn(),
}));

vi.mock('@/api/generado/rellenos/rellenos', () => ({
  getCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGetQueryKey: (id: string) => ['calculo', id],
  useCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGet: (_id: string, params: unknown) => {
    m.calculo.parametros.push(params);
    return { data: m.calculo.current, isLoading: false, isError: m.calculo.error !== null, error: m.calculo.error };
  },
  useAgregarRellenoApiV1ZonasDeLosaZonaIdRellenosPost: () => ({ mutateAsync: m.agregar, isPending: false }),
  useCambiarRellenoApiV1RellenosDeZonaRellenoIdPut: () => ({ mutateAsync: m.cambiar, isPending: false }),
  useQuitarRellenoApiV1RellenosDeZonaRellenoIdDelete: () => ({ mutateAsync: m.quitar, isPending: false }),
  useProponerConceptosDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosPropuestasPost: () => ({ mutateAsync: m.proponer, isPending: false }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { RellenosDeLaZona } from '@/cuantificador/RellenosDeLaZona';

const ZONA = {
  id: 'z1', plano_id: 'p1', nombre: 'Azotea 3.00', nivel: 'PB', cota_piso_m: '0.000', altura_libre_m: '3.000', espesor_m: '0.120', tipo_de_losa: 'maciza',
  uso_de_losa: 'azotea', cota_inferior_m: '3.000', cota_superior_m: '3.120', created_at: '2026-11-20T00:00:00Z', updated_at: '2026-11-20T00:00:00Z',
  losas: [
    { trazo_id: 'lo1', espesor_propio_m: null, espesor_m: '0.120' },
    { trazo_id: 'lo2', espesor_propio_m: '0.200', espesor_m: '0.200' },
  ],
} as never;
const ESPACIOS = [{ id: 'esp1', nombre: 'Recámara 1' }, { id: 'esp2', nombre: 'Baño' }] as never;

const PARAMETROS = { espesor_m: 0.09, pendiente_pct: 0, recorrido_m: 0, compensar_espesores: true, abundamiento_pct: 0, mortero_m3_por_m2: 0.0735 };
const CONCEPTO_AZOTEA = { clave: 'ALB-03014', descripcion: 'Relleno en azotea', unidad: 'm²', estado: 'catalogo', provisional: false };
const CONCEPTO_COMPACTADO = { clave: 'EJ-810', descripcion: 'Relleno compactado', unidad: 'm³', estado: 'propuesto', provisional: true };

const RELLENO = (extra: Record<string, unknown> = {}) => ({
  id: 'r1', clave: 'REL-AZOTEA', nombre: 'Relleno de azotea', tipo: 'azotea', parametros: PARAMETROS, ...PARAMETROS, espesor_de_la_zona_m: 0.12, espesor_maximo_de_la_zona_m: 0.2,
  area_m2: 32, volumen_m3: 4.8, volumen_suelto_m3: null, espesor_medio_m: 0.15, extra_de_pendiente_m: 0, trazo_id: null, espacio_id: null, origen: 'zona',
  poligonos: [
    { id: 'lo1', area_m2: 24, espesor_de_losa_m: 0.12, subzona: false, compensacion_m: 0.08, espesor_m: 0.17, volumen_m3: 4.08, espacio_id: null },
    { id: 'lo2', area_m2: 8, espesor_de_losa_m: 0.2, subzona: true, compensacion_m: 0, espesor_m: 0.09, volumen_m3: 0.72, espacio_id: null },
  ],
  insumos: [],
  conceptos: [{ parte: 'relleno', elemento_clave: 'REL-AZOTEA', ref: null, concepto: CONCEPTO_AZOTEA, toma: ['tezontle'], cantidad: 32, unidad: 'm²', nota: '', propuesta: null }],
  por_espacio: [],
  mano_de_obra: { estado: 'sin_mano_de_obra', nota: '', destajos_candidatos: [] }, advertencias: ['Las subzonas más delgadas reciben la diferencia.'], pendientes: [],
  conciliacion: {
    concepto: { clave: 'ALB-03014', descripcion: 'Relleno en azotea', unidad: 'm²' }, nota: 'El concepto del catálogo es por m².', resumen: {}, coincide: false, mano_de_obra: [],
    filas: [{ clave: 'PET-00069', descripcion: 'TEZONTLE', unidad: 'SERV', catalogo: 0.012857, elemento: 0.021428, diferencia: 0.667, diferencia_pct: 66.7, marca: '≠' }],
  },
  ...extra,
});

const CALCULO = (extra: Record<string, unknown> = {}) => ({
  zona: { id: 'z1', plano_id: 'p1', nombre: 'Azotea 3.00', nivel: 'PB', espesor_m: 0.12, espesor_maximo_m: 0.2 },
  escala_definida: true,
  rellenos: [RELLENO()],
  totales: { area_m2: 32, volumen_m3: 4.8, conceptos: [{ concepto: CONCEPTO_AZOTEA, unidad: 'm²', cantidad: 32, propuesta: null }] },
  por_espacio: [
    {
      espacio_id: 'esp1', espacio_nombre: 'Recámara 1', area_m2: 24, volumen_m3: 4.08,
      conceptos: [
        {
          parte: 'relleno', elemento_clave: 'REL-AZOTEA', ref: null, concepto: CONCEPTO_AZOTEA, toma: [], cantidad: 24, unidad: 'm²', nota: '', propuesta: null,
          resolucion: { estado: 'cuenta', cuenta: true, aviso: null, concepto_id: 'c1', partida_id: 'pa1', partida_nombre: 'Relleno en azotea (Recámara 1)' },
        },
      ],
    },
    {
      espacio_id: null, espacio_nombre: null, area_m2: 8, volumen_m3: 0.72,
      conceptos: [
        {
          parte: 'relleno', elemento_clave: 'REL-AZOTEA', ref: null, concepto: CONCEPTO_AZOTEA, toma: [], cantidad: 8, unidad: 'm²', nota: '', propuesta: null,
          resolucion: { estado: 'sin_espacio', cuenta: false, aviso: 'Sin espacio: asigna el polígono.', concepto_id: 'c1', partida_id: null, partida_nombre: null },
        },
      ],
    },
  ],
  advertencias: [],
  ...extra,
});

function pintar(rol: string | null, puedeEditar: boolean) {
  const onCambio = vi.fn();
  const onError = vi.fn();
  render(<RellenosDeLaZona zona={ZONA} puedeEditar={puedeEditar} rol={rol} espacios={ESPACIOS} onCambio={onCambio} onError={onError} />);
  fireEvent.click(screen.getByRole('button', { name: 'Rellenos de Azotea 3.00' }));
  return { onCambio, onError };
}

beforeEach(() => {
  for (const f of [m.agregar, m.cambiar, m.quitar, m.proponer]) f.mockReset();
  m.agregar.mockResolvedValue({});
  m.cambiar.mockResolvedValue({});
  m.quitar.mockResolvedValue(undefined);
  m.proponer.mockResolvedValue({ creadas: ['a'], omitidas: [] });
  m.calculo.current = CALCULO();
  m.calculo.error = null;
  m.calculo.parametros = [];
});

describe('RellenosDeLaZona', () => {
  it('está cerrado hasta que se abre y pide el cálculo con la conciliación', () => {
    render(<RellenosDeLaZona zona={ZONA} puedeEditar rol="control_obra" onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByTestId('cuerpo-de-los-rellenos')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Rellenos de Azotea 3.00' }));
    expect(m.calculo.parametros).toContainEqual({ conciliar: true });
    expect(screen.getByTestId('rellenos-resumen')).toHaveTextContent('área 32.00 m²');
    expect(screen.getByTestId('relleno-de-la-zona-resumen')).toHaveTextContent('4.800 m³');
    expect(screen.getByTestId('relleno-de-la-zona-resumen')).toHaveTextContent('32.00 m² de ALB-03014');
  });

  it('pinta el espesor de cada polígono con su compensación, la conciliación contra el catálogo y lo que paga cada espacio en su partida', () => {
    pintar('control_obra', true);
    const tabla = screen.getByRole('table', { name: 'Espesor por polígono del relleno 1' });
    expect(tabla).toHaveTextContent('subzona');
    expect(tabla).toHaveTextContent('8.0 cm');
    const conciliacion = screen.getByTestId('conciliacion-del-relleno');
    expect(conciliacion).toHaveAttribute('data-concepto-conciliado', 'ALB-03014');
    expect(conciliacion.querySelector('[data-marca="≠"]')).toHaveTextContent('PET-00069');
    const tomas = screen.getByRole('table', { name: 'Lo que paga el relleno de cada espacio' });
    expect(tomas.querySelector('[data-espacio="Recámara 1"]')).toHaveTextContent('Relleno en azotea (Recámara 1)');
    expect(tomas.querySelector('[data-espacio="sin espacio"]')).toHaveAttribute('data-estado-de-partida', 'sin_espacio');
    expect(tomas.querySelector('[data-espacio="sin espacio"]')).toHaveTextContent('sin espacio: no se escribe');
    expect(screen.getByText('Las subzonas más delgadas reciben la diferencia.')).toBeInTheDocument();
  });

  it('Control de obra agrega un relleno de toda la zona o de un polígono, con su espacio', async () => {
    const { onCambio } = pintar('control_obra', true);
    fireEvent.click(screen.getByRole('button', { name: 'Agregar el relleno' }));
    await waitFor(() => expect(m.agregar).toHaveBeenCalledWith({ zonaId: 'z1', data: { elemento_clave: 'REL-AZOTEA' } }));
    await waitFor(() => expect(onCambio).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Elemento del relleno'), { target: { value: 'REL-COMPACTADO' } });
    fireEvent.change(screen.getByLabelText('Lo que cubre el relleno'), { target: { value: 'lo2' } });
    fireEvent.change(screen.getByLabelText('Espacio del relleno'), { target: { value: 'esp2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar el relleno' }));
    await waitFor(() =>
      expect(m.agregar).toHaveBeenLastCalledWith({ zonaId: 'z1', data: { elemento_clave: 'REL-COMPACTADO', trazo_id: 'lo2', espacio_id: 'esp2' } }),
    );
  });

  it('guarda los parámetros sin tocar el espacio, asigna el espacio con todos los parámetros y quita el relleno', async () => {
    pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Espesor mínimo del relleno 1'), { target: { value: '0.12' } });
    fireEvent.change(screen.getByLabelText('Pendiente del relleno 1'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Recorrido de la pendiente del relleno 1'), { target: { value: '5' } });
    fireEvent.click(screen.getByLabelText('Adaptarse a los espesores de losa en el relleno 1'));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }));
    await waitFor(() =>
      expect(m.cambiar).toHaveBeenCalledWith({
        rellenoId: 'r1',
        data: { elemento_clave: 'REL-AZOTEA', espesor_m: 0.12, pendiente_pct: 2, recorrido_m: 5, mortero_m3_por_m2: 0.0735, compensar_espesores: false },
      }),
    );
    fireEvent.change(screen.getByLabelText('Espacio del relleno 1'), { target: { value: 'esp2' } });
    await waitFor(() => expect(m.cambiar).toHaveBeenLastCalledWith({ rellenoId: 'r1', data: expect.objectContaining({ espacio_id: 'esp2' }) }));
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el relleno 1' }));
    await waitFor(() => expect(m.quitar).toHaveBeenCalledWith({ rellenoId: 'r1' }));
  });

  it('un parámetro que no es un número no se manda y se avisa', async () => {
    const { onError } = pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Espesor mínimo del relleno 1'), { target: { value: 'mucho' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('no es un número válido')));
    expect(m.cambiar).not.toHaveBeenCalled();
  });

  it('un error del servidor al agregar se avisa (p. ej. dos veces lo mismo)', async () => {
    const { onError } = pintar('control_obra', true);
    m.agregar.mockRejectedValue(new Error('REL-AZOTEA: hay dos rellenos sobre el mismo polígono; se contaría dos veces.'));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar el relleno' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('se contaría dos veces')));
  });

  it('quien no es Control de obra solo lee: no hay formulario ni botones de edición', () => {
    pintar('costos', false);
    expect(screen.queryByRole('group', { name: 'Agregar un relleno a la zona' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quitar el relleno 1' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Espesor mínimo del relleno 1')).toBeDisabled();
    expect(screen.getByLabelText('Espacio del relleno 1')).toBeDisabled();
  });

  it('Costos propone el concepto del compactado que falta y lo dice', async () => {
    m.calculo.current = CALCULO({
      rellenos: [
        RELLENO({
          id: 'r2', clave: 'REL-COMPACTADO', nombre: 'Relleno compactado', tipo: 'compactado', conciliacion: null, volumen_suelto_m3: 5.5,
          conceptos: [{ parte: 'relleno', elemento_clave: 'REL-COMPACTADO', ref: null, concepto: CONCEPTO_COMPACTADO, toma: ['volumen'], cantidad: 5, unidad: 'm³', nota: '', propuesta: null }],
        }),
      ],
    });
    const { onCambio } = pintar('costos', false);
    expect(screen.getByTestId('relleno-de-la-zona-resumen')).toHaveTextContent('suelto 5.500 m³');
    fireEvent.click(screen.getByRole('button', { name: 'Proponer el concepto del relleno compactado' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ zonaId: 'z1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(expect.stringContaining('Se propuso el concepto nuevo')));
  });

  it('una zona sin rellenos lo dice', () => {
    m.calculo.current = CALCULO({ rellenos: [], por_espacio: [], totales: { area_m2: 0, volumen_m3: 0, conceptos: [] } });
    pintar('control_obra', true);
    expect(screen.getByText(/La zona no tiene rellenos/)).toBeInTheDocument();
  });
});
