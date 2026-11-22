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
  cambiarBajada: vi.fn(),
  quitarBajada: vi.fn(),
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
  useCambiarBajadaApiV1BajadasDeRellenoBajadaIdPut: () => ({ mutateAsync: m.cambiarBajada, isPending: false }),
  useQuitarBajadaApiV1BajadasDeRellenoBajadaIdDelete: () => ({ mutateAsync: m.quitarBajada, isPending: false }),
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

const PARAMETROS = {
  espesor_m: 0.09, pendiente_pct: 0, recorrido_m: 0, compensar_espesores: true, abundamiento_pct: 0, mortero_m3_por_m2: 0.0735, pendiente_zona_pct: 2, espesor_bajada_m: 0.05,
  mortero_espesor_m: 0.05, factor_abundamiento: 1,
};
const CONCEPTO_ARENILLA = { clave: 'EJ-830', descripcion: 'Arenilla de relleno', unidad: 'm³', estado: 'propuesto', provisional: true };
const CONCEPTO_AZOTEA = { clave: 'ALB-03014', descripcion: 'Relleno en azotea', unidad: 'm²', estado: 'catalogo', provisional: false };
const CONCEPTO_COMPACTADO = { clave: 'EJ-810', descripcion: 'Relleno compactado', unidad: 'm³', estado: 'propuesto', provisional: true };

const RELLENO = (extra: Record<string, unknown> = {}) => ({
  id: 'r1', clave: 'REL-AZOTEA', nombre: 'Relleno de azotea', tipo: 'azotea', parametros: PARAMETROS, ...PARAMETROS, espesor_de_la_zona_m: 0.12, espesor_maximo_de_la_zona_m: 0.2,
  area_m2: 32, volumen_m3: 4.8, volumen_suelto_m3: null, espesor_medio_m: 0.15, extra_de_pendiente_m: 0, trazo_id: null, espacio_id: null, origen: 'zona',
  modo: 'uniforme', dinamico: null, bajadas: [],
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

function pintar(rol: string | null, puedeEditar: boolean, colocando: unknown = null) {
  const onCambio = vi.fn();
  const onError = vi.fn();
  const onColocar = vi.fn();
  render(
    <RellenosDeLaZona zona={ZONA} puedeEditar={puedeEditar} rol={rol} espacios={ESPACIOS} colocando={colocando as never} onColocar={onColocar} onCambio={onCambio} onError={onError} />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Rellenos de Azotea 3.00' }));
  return { onCambio, onError, onColocar };
}

/** Un relleno de azotea con dos bajadas (una con línea trazada): arenilla de espesor variable + mortero de 5 cm. */
const CON_BAJADAS = (extra: Record<string, unknown> = {}) =>
  RELLENO({
    modo: 'bajadas', area_m2: 32, volumen_m3: 3.3, espesor_medio_m: 0.103,
    conceptos: [
      { parte: 'relleno', elemento_clave: 'REL-AZOTEA', ref: null, concepto: CONCEPTO_AZOTEA, toma: ['mortero'], cantidad: 32, unidad: 'm²', nota: '', propuesta: null },
      { parte: 'arenilla', elemento_clave: 'REL-AZOTEA', ref: null, concepto: CONCEPTO_ARENILLA, toma: ['volumen'], cantidad: 3.3, unidad: 'm³', nota: '', propuesta: null },
    ],
    bajadas: [
      { id: 'b1', trazo_id: 't1', linea_trazo_id: null, rotulo: 'BAP-1', x: 0, y: -4, linea: null },
      { id: 'b2', trazo_id: 't2', linea_trazo_id: 'l2', rotulo: null, x: 8, y: 0, linea: [[0, 0], [8, 0]] },
    ],
    dinamico: {
      estado: 'calculado', pendiente_pct: 2, espesor_en_bajada_m: 0.05, mortero_espesor_m: 0.05, volumen_arenilla_m3: 3.3, espesor_arenilla_medio_m: 0.103,
      espesor_arenilla_maximo_m: 0.21, volumen_mortero_m3: 1.6, metodo: 'Integral numérica determinista: área exacta por espesor medio.', celda_m: 0.0566, muestras: 10000,
      error_estimado_m3: 0.0012, error_relativo: 0.00036,
      bajadas: [
        { id: 'b1', x: 0, y: -4, rotulo: 'BAP-1', linea_trazada: false, area_m2: 20, distancia_maxima_m: 6, espesor_maximo_m: 0.17, fuera_de_la_zona: false },
        { id: 'b2', x: 8, y: 0, rotulo: null, linea_trazada: true, area_m2: 12, distancia_maxima_m: 8, espesor_maximo_m: 0.21, fuera_de_la_zona: false },
      ],
      guias: [],
    },
    ...extra,
  });

beforeEach(() => {
  for (const f of [m.agregar, m.cambiar, m.quitar, m.proponer, m.cambiarBajada, m.quitarBajada]) f.mockReset();
  m.cambiarBajada.mockResolvedValue({});
  m.quitarBajada.mockResolvedValue(undefined);
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
        data: { elemento_clave: 'REL-AZOTEA', espesor_m: 0.12, pendiente_pct: 2, recorrido_m: 5, mortero_m3_por_m2: 0.0735, compensar_espesores: false, pendiente_zona_pct: 2, espesor_bajada_m: 0.05, mortero_espesor_m: 0.05 },
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

  it('sin bajadas el relleno de azotea se pinta como siempre y ofrece colocar la primera bajada', () => {
    const { onColocar } = pintar('control_obra', true);
    expect(screen.queryByTestId('relleno-dinamico')).not.toBeInTheDocument();
    expect(screen.getByText(/Sin bajadas: el relleno es parejo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Colocar bajada pluvial del relleno 1' }));
    expect(onColocar).toHaveBeenCalledWith({ tipo: 'bajada', rellenoId: 'r1' });
  });

  it('con bajadas pinta las dos capas, el método y su error, y cada bajada con lo que drena', () => {
    m.calculo.current = CALCULO({ rellenos: [CON_BAJADAS()] });
    pintar('control_obra', true);
    expect(screen.getByTestId('relleno-de-la-zona-resumen')).toHaveTextContent('3.300 m³ de EJ-830');
    expect(screen.getByTestId('relleno-de-la-zona-resumen')).toHaveTextContent('32.00 m² de ALB-03014');
    const dinamico = screen.getByTestId('relleno-dinamico');
    expect(dinamico).toHaveTextContent('arenilla de espesor variable (5.0 cm en cada bajada + 2.00 % por metro');
    expect(dinamico).toHaveTextContent('máximo 21.0 cm');
    expect(dinamico).toHaveTextContent('mortero de 5.0 cm = 1.600 m³');
    expect(screen.getByTestId('relleno-dinamico-metodo')).toHaveTextContent('Integral numérica determinista');
    expect(screen.getByTestId('relleno-dinamico-metodo')).toHaveTextContent('error estimado 0.0012 m³');
    const filas = screen.getAllByTestId('bajada-del-relleno');
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveAttribute('data-linea', 'generada');
    expect(filas[0]).toHaveTextContent('drena 20.00 m²');
    expect(filas[1]).toHaveAttribute('data-linea', 'trazada');
    expect(filas[1]).toHaveTextContent('Bajada 2');
  });

  it('Control de obra traza la línea de pendiente, la quita, cambia el rótulo y quita la bajada', async () => {
    m.calculo.current = CALCULO({ rellenos: [CON_BAJADAS()] });
    const { onColocar, onCambio } = pintar('control_obra', true);
    fireEvent.click(screen.getByRole('button', { name: 'Trazar la línea de pendiente de la bajada 1 del relleno 1' }));
    expect(onColocar).toHaveBeenCalledWith({ tipo: 'pendiente', bajadaId: 'b1', rotulo: 'BAP-1' });
    fireEvent.click(screen.getByRole('button', { name: 'Quitar la línea de la bajada 2 del relleno 1' }));
    await waitFor(() => expect(m.cambiarBajada).toHaveBeenCalledWith({ bajadaId: 'b2', data: { linea_trazo_id: null, rotulo: null } }));
    const rotulo = screen.getByLabelText('Rótulo de la bajada 1 del relleno 1');
    fireEvent.change(rotulo, { target: { value: 'BAP-NORTE' } });
    fireEvent.blur(rotulo);
    await waitFor(() => expect(m.cambiarBajada).toHaveBeenCalledWith({ bajadaId: 'b1', data: { linea_trazo_id: null, rotulo: 'BAP-NORTE' } }));
    fireEvent.click(screen.getByRole('button', { name: 'Quitar la bajada 2 del relleno 1' }));
    await waitFor(() => expect(m.quitarBajada).toHaveBeenCalledWith({ bajadaId: 'b2' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith('Bajada quitada del relleno.'));
  });

  it('el botón de colocar queda activo mientras el plano pide una bajada de ese relleno; quien solo lee no ve botones de bajadas', () => {
    m.calculo.current = CALCULO({ rellenos: [CON_BAJADAS()] });
    pintar('control_obra', true, { tipo: 'bajada', rellenoId: 'r1' });
    expect(screen.getByRole('button', { name: 'Colocar bajada pluvial del relleno 1' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('quien solo lee ve las bajadas pero no las edita', () => {
    m.calculo.current = CALCULO({ rellenos: [CON_BAJADAS()] });
    pintar('costos', false);
    expect(screen.getAllByTestId('bajada-del-relleno')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /Colocar bajada pluvial/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Quitar la bajada/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Pendiente de la zona del relleno 1')).toBeDisabled();
  });

  it('sin escala calibrada el relleno con bajadas no da cantidades y lo dice', () => {
    m.calculo.current = CALCULO({
      rellenos: [CON_BAJADAS({ area_m2: 0, volumen_m3: 0, dinamico: { estado: 'sin_escala', bajadas: [], guias: [] } })],
    });
    pintar('control_obra', true);
    expect(screen.getByTestId('relleno-dinamico')).toHaveAttribute('data-estado', 'sin_escala');
    expect(screen.getByTestId('relleno-dinamico')).toHaveTextContent('calibrar la escala');
  });

  it('guarda la pendiente de la zona, el espesor en la bajada y el mortero de la plantilla', async () => {
    pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Pendiente de la zona del relleno 1'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText('Espesor en la bajada del relleno 1'), { target: { value: '0.06' } });
    fireEvent.change(screen.getByLabelText('Mortero de la plantilla del relleno 1'), { target: { value: '0.04' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }));
    await waitFor(() =>
      expect(m.cambiar).toHaveBeenCalledWith({
        rellenoId: 'r1', data: expect.objectContaining({ pendiente_zona_pct: 1.5, espesor_bajada_m: 0.06, mortero_espesor_m: 0.04 }),
      }),
    );
  });

  it('el compactado se edita con el factor de abundamiento', async () => {
    m.calculo.current = CALCULO({
      rellenos: [
        RELLENO({
          id: 'r2', clave: 'REL-COMPACTADO', nombre: 'Relleno compactado', tipo: 'compactado', conciliacion: null, volumen_suelto_m3: 6.25,
          conceptos: [{ parte: 'relleno', elemento_clave: 'REL-COMPACTADO', ref: null, concepto: CONCEPTO_COMPACTADO, toma: ['volumen'], cantidad: 6.25, unidad: 'm³', nota: '', propuesta: { estado: 'pendiente' } }],
        }),
      ],
    });
    pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Factor de abundamiento del relleno 1'), { target: { value: '1.25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }));
    await waitFor(() => expect(m.cambiar).toHaveBeenCalledWith({ rellenoId: 'r2', data: expect.objectContaining({ elemento_clave: 'REL-COMPACTADO', factor_abundamiento: 1.25 }) }));
    expect(screen.queryByRole('group', { name: /Bajadas pluviales del relleno/ })).not.toBeInTheDocument();
  });

  it('propone el concepto de la arenilla cuando falta', async () => {
    m.calculo.current = CALCULO({ rellenos: [CON_BAJADAS()] });
    pintar('costos', false);
    fireEvent.click(screen.getByRole('button', { name: 'Proponer el concepto de la arenilla' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ zonaId: 'z1' }));
  });
});
