/**
 * Las escaleras de la zona de losa en el panel de zonas (Fase 4a): solo se pinta lo que responde el servidor; Control de obra agrega, cambia (cotas, parámetros y
 * espacio) y quita escaleras; los demás roles solo leen y Costos propone el concepto del descanso. Cada concepto dice en qué partida se mide.
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

vi.mock('@/api/generado/escaleras/escaleras', () => ({
  getCalculoDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasCalculoGetQueryKey: (id: string) => ['calculo', id],
  useCalculoDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasCalculoGet: (_id: string, params: unknown) => {
    m.calculo.parametros.push(params);
    return { data: m.calculo.current, isLoading: false, isError: m.calculo.error !== null, error: m.calculo.error };
  },
  useAgregarEscaleraApiV1ZonasDeLosaZonaIdEscalerasPost: () => ({ mutateAsync: m.agregar, isPending: false }),
  useCambiarEscaleraApiV1EscalerasDeZonaEscaleraIdPut: () => ({ mutateAsync: m.cambiar, isPending: false }),
  useQuitarEscaleraApiV1EscalerasDeZonaEscaleraIdDelete: () => ({ mutateAsync: m.quitar, isPending: false }),
  useProponerConceptosDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasPropuestasPost: () => ({ mutateAsync: m.proponer, isPending: false }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { EscalerasDeLaZona } from '@/cuantificador/EscalerasDeLaZona';

const zona = (id: string, nombre: string, cota: string) =>
  ({
    id, plano_id: 'p1', nombre, nivel: 'PB', cota_piso_m: cota, altura_libre_m: '3.000', espesor_m: '0.120', tipo_de_losa: 'maciza', uso_de_losa: 'entrepiso',
    cota_inferior_m: '3.000', cota_superior_m: '3.120', created_at: '2026-11-21T00:00:00Z', updated_at: '2026-11-21T00:00:00Z', losas: [],
  }) as never;
const ZONA = zona('z1', 'Planta baja', '0.000');
const ARRIBA = zona('z2', 'Planta alta', '3.120');
const ESPACIOS = [{ id: 'esp1', nombre: 'Escalera 1' }, { id: 'esp2', nombre: 'Hall' }] as never;

const PARAMETROS = { peldanos: null, contrahuella_max_m: 0.18, huella_m: 0.25, ancho_m: 1.2, espesor_m: 0.12, rampas: 1, largo_descanso_m: null };
const ESCALON = { clave: 'EST-01510', descripcion: 'Escalera forjada de una rampa', unidad: 'pza', estado: 'catalogo', provisional: false };
const DESCANSO = { clave: 'EJ-820', descripcion: 'Descanso de escalera', unidad: 'm²', estado: 'propuesto', provisional: true };
const GEOMETRIA = {
  peldanos: 18, origen_de_peldanos: 'desnivel', contrahuella_m: 0.1733, huella_m: 0.25, origen_de_huella: 'tecleada', longitud_inclinada_m: 0.304, recorrido_horizontal_m: 4.25,
  rampas: [{ numero: 1, peldanos: 18, recorrido_m: 4.25, altura_m: 3.12 }], descansos: 0, largo_del_descanso_m: 1.2, area_de_descanso_m2: 0, superficie_de_rampa_m2: 6.57,
  volumen_de_rampa_m3: 0.788, volumen_de_descanso_m3: 0, escalones_de_catalogo: 18,
};

const ESCALERA = (extra: Record<string, unknown> = {}, calculo: Record<string, unknown> = {}) => ({
  id: 'e1', trazo_id: null, espacio_id: null, zona_llegada_id: null, origen_de_cotas: { arranque: 'zona', llegada: 'losa_de_la_zona' }, error: null,
  calculo: {
    clave: 'ESC-FORJADA', nombre: 'Escalera forjada', parametros: PARAMETROS, cotas: { arranque_m: 0, llegada_m: 3.12, desnivel_m: 3.12 }, geometria: GEOMETRIA, insumos: [],
    conceptos: [{ parte: 'escalon', elemento_clave: 'ESC-FORJADA', ref: null, concepto: ESCALON, toma: ['peldaños', 'ancho'], cantidad: 18, unidad: 'pza', nota: '', propuesta: null }],
    por_espacio: [], mano_de_obra: { estado: 'sin_mano_de_obra', nota: '', destajos_candidatos: [] }, advertencias: ['La contrahuella queda al límite.'], pendientes: [],
    ...calculo,
  },
  conciliacion: {
    concepto: { clave: 'EST-01510', descripcion: 'Escalera forjada de una rampa', unidad: 'pza' }, nota: 'El concepto del catálogo es por pieza.', resumen: {}, coincide: false, mano_de_obra: [],
    filas: [
      { clave: 'CON-00004', descripcion: 'CONCRETO', unidad: 'm3', catalogo: 0.060583, elemento: 0.0438, diferencia: -0.28, diferencia_pct: -27.7, marca: '≠' },
      { clave: 'PET-00001', descripcion: 'TABIQUE', unidad: 'pza', catalogo: 10, elemento: null, diferencia: null, diferencia_pct: null, marca: 'solo_catalogo' },
    ],
  },
  ...extra,
});

const CALCULO = (extra: Record<string, unknown> = {}) => ({
  zona: { id: 'z1', plano_id: 'p1', nombre: 'Planta baja', nivel: 'PB', cota_piso_m: 0, cota_de_la_losa_m: 3.12 },
  escala_definida: true,
  escaleras: [ESCALERA()],
  totales: { peldanos: 18, escalones_de_catalogo: 18, area_de_descanso_m2: 0, conceptos: [{ concepto: ESCALON, unidad: 'pza', cantidad: 18, propuesta: null }] },
  por_espacio: [
    {
      espacio_id: 'esp1', espacio_nombre: 'Escalera 1',
      conceptos: [
        {
          parte: 'escalon', elemento_clave: 'ESC-FORJADA', ref: null, concepto: ESCALON, toma: [], cantidad: 18, unidad: 'pza', nota: '', propuesta: null,
          resolucion: { estado: 'cuenta', cuenta: true, aviso: null, concepto_id: 'c1', partida_id: 'pa1', partida_nombre: 'Escalera forjada (Escalera 1)' },
        },
      ],
    },
    {
      espacio_id: null, espacio_nombre: null,
      conceptos: [
        {
          parte: 'escalon', elemento_clave: 'ESC-FORJADA', ref: null, concepto: ESCALON, toma: [], cantidad: 18, unidad: 'pza', nota: '', propuesta: null,
          resolucion: { estado: 'sin_espacio', cuenta: false, aviso: 'Sin espacio: asigna la escalera.', concepto_id: 'c1', partida_id: null, partida_nombre: null },
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
  render(<EscalerasDeLaZona zona={ZONA} zonas={[ZONA, ARRIBA]} puedeEditar={puedeEditar} rol={rol} espacios={ESPACIOS} onCambio={onCambio} onError={onError} />);
  fireEvent.click(screen.getByRole('button', { name: 'Escaleras de Planta baja' }));
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

describe('EscalerasDeLaZona', () => {
  it('está cerrado hasta que se abre y pide el cálculo con la conciliación', () => {
    render(<EscalerasDeLaZona zona={ZONA} zonas={[ZONA]} puedeEditar rol="control_obra" onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByTestId('cuerpo-de-las-escaleras')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Escaleras de Planta baja' }));
    expect(m.calculo.parametros).toContainEqual({ conciliar: true });
    expect(screen.getByTestId('escaleras-resumen')).toHaveTextContent('18 peldaños');
    expect(screen.getByTestId('escaleras-resumen')).toHaveTextContent('EST-01510 18.00 pza');
    const resumen = screen.getByTestId('escalera-de-la-zona-resumen');
    expect(resumen).toHaveTextContent('Desnivel 3.120 m');
    expect(resumen).toHaveTextContent('arranque del piso de la zona, llegada de la cara alta de la losa');
    expect(resumen).toHaveTextContent('18.00 pza de EST-01510');
  });

  it('pinta las rampas, la conciliación contra el catálogo y lo que paga cada espacio en su partida', () => {
    pintar('control_obra', true);
    expect(screen.getByRole('table', { name: 'Detalle por rampa (escalera 1)' })).toHaveTextContent('4.25 m');
    const conciliacion = screen.getByTestId('conciliacion-de-la-escalera');
    expect(conciliacion).toHaveAttribute('data-concepto-conciliado', 'EST-01510');
    expect(conciliacion.querySelector('[data-marca="≠"]')).toHaveTextContent('CON-00004');
    expect(conciliacion.querySelector('[data-marca="solo_catalogo"]')).toHaveTextContent('PET-00001');
    const tomas = screen.getByRole('table', { name: 'Lo que paga la escalera de cada espacio' });
    expect(tomas.querySelector('[data-espacio="Escalera 1"]')).toHaveTextContent('Escalera forjada (Escalera 1)');
    expect(tomas.querySelector('[data-espacio="sin espacio"]')).toHaveAttribute('data-estado-de-partida', 'sin_espacio');
    expect(tomas.querySelector('[data-espacio="sin espacio"]')).toHaveTextContent('sin espacio: no se escribe');
    expect(screen.getByText('La contrahuella queda al límite.')).toBeInTheDocument();
  });

  it('Control de obra agrega una escalera que llega a otra zona y a su espacio', async () => {
    const { onCambio } = pintar('control_obra', true);
    fireEvent.click(screen.getByRole('button', { name: 'Agregar la escalera' }));
    await waitFor(() => expect(m.agregar).toHaveBeenCalledWith({ zonaId: 'z1', data: {} }));
    await waitFor(() => expect(onCambio).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Zona de llegada de la escalera', { selector: 'select[aria-label="Zona de llegada de la escalera"]' }), { target: { value: 'z2' } });
    fireEvent.change(screen.getByLabelText('Espacio de la escalera nueva'), { target: { value: 'esp2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar la escalera' }));
    await waitFor(() => expect(m.agregar).toHaveBeenLastCalledWith({ zonaId: 'z1', data: { zona_llegada_id: 'z2', espacio_id: 'esp2' } }));
  });

  it('guarda lo tecleado (las cotas y los peldaños vacíos salen de las zonas), asigna el espacio con todos los parámetros y quita la escalera', async () => {
    pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Zona de llegada de la escalera 1'), { target: { value: 'z2' } });
    fireEvent.change(screen.getByLabelText('Ancho de la escalera 1'), { target: { value: '2.4' } });
    fireEvent.change(screen.getByLabelText('Rampas de la escalera 1'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Largo del descanso de la escalera 1'), { target: { value: '1.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar la escalera 1' }));
    await waitFor(() =>
      expect(m.cambiar).toHaveBeenCalledWith({
        escaleraId: 'e1',
        data: { zona_llegada_id: 'z2', huella_m: 0.25, ancho_m: 2.4, rampas: 2, largo_descanso_m: 1.5, espesor_m: 0.12, contrahuella_max_m: 0.18 },
      }),
    );
    fireEvent.change(screen.getByLabelText('Espacio de la escalera 1'), { target: { value: 'esp2' } });
    await waitFor(() => expect(m.cambiar).toHaveBeenLastCalledWith({ escaleraId: 'e1', data: expect.objectContaining({ espacio_id: 'esp2' }) }));
    fireEvent.click(screen.getByRole('button', { name: 'Quitar la escalera 1' }));
    await waitFor(() => expect(m.quitar).toHaveBeenCalledWith({ escaleraId: 'e1' }));
  });

  it('una cota tecleada y la zona de llegada no se mandan juntas', () => {
    pintar('control_obra', true);
    expect(screen.getByLabelText('Cota de llegada de la escalera 1')).not.toBeDisabled();
    fireEvent.change(screen.getByLabelText('Cota de llegada de la escalera 1'), { target: { value: '3.6' } });
    expect(screen.getByLabelText('Zona de llegada de la escalera 1')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Cota de llegada de la escalera 1'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Zona de llegada de la escalera 1'), { target: { value: 'z2' } });
    expect(screen.getByLabelText('Cota de llegada de la escalera 1')).toBeDisabled();
  });

  it('una cota que no es un número no se manda y se avisa', async () => {
    const { onError } = pintar('control_obra', true);
    fireEvent.change(screen.getByLabelText('Cota de arranque de la escalera 1'), { target: { value: 'abajo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar la escalera 1' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('no es un número válido')));
    expect(m.cambiar).not.toHaveBeenCalled();
  });

  it('una escalera que cae en un error muestra su motivo y se puede quitar; la de una línea no deja teclear la huella', async () => {
    m.calculo.current = CALCULO({
      escaleras: [ESCALERA({ error: 'La cota de llegada debe estar por encima de la de arranque: la escalera sube.', calculo: null, conciliacion: null })],
      advertencias: ['Una escalera no se puede calcular: la cota de llegada debe estar por encima.'],
    });
    pintar('control_obra', true);
    expect(screen.getByTestId('escalera-error')).toHaveTextContent('la escalera sube');
    expect(screen.getAllByRole('alert').length).toBeGreaterThanOrEqual(2); // el motivo de la escalera y el aviso de la zona
    fireEvent.click(screen.getByRole('button', { name: 'Quitar la escalera 1' }));
    await waitFor(() => expect(m.quitar).toHaveBeenCalledWith({ escaleraId: 'e1' }));
  });

  it('una escalera con línea del plano lo dice y la huella sale de la línea', () => {
    m.calculo.current = CALCULO({
      escaleras: [ESCALERA({ trazo_id: 'l1' }, { geometria: { ...GEOMETRIA, origen_de_huella: 'linea' } })],
    });
    pintar('control_obra', true);
    expect(screen.getByText('recorrido de una línea del plano')).toBeInTheDocument();
    expect(screen.getByLabelText('Huella de la escalera 1')).toBeDisabled();
  });

  it('un error del servidor al agregar se avisa (p. ej. la línea ya es de otra escalera)', async () => {
    const { onError } = pintar('control_obra', true);
    m.agregar.mockRejectedValue(new Error('Esa línea ya da el recorrido de otra escalera: se contaría dos veces.'));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar la escalera' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('se contaría dos veces')));
  });

  it('quien no es Control de obra solo lee: no hay formulario ni botones de edición', () => {
    pintar('costos', false);
    expect(screen.queryByRole('group', { name: 'Agregar una escalera a la zona' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quitar la escalera 1' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Ancho de la escalera 1')).toBeDisabled();
    expect(screen.getByLabelText('Espacio de la escalera 1')).toBeDisabled();
  });

  it('Costos propone el concepto del descanso que falta y lo dice', async () => {
    m.calculo.current = CALCULO({
      escaleras: [
        ESCALERA(
          {},
          {
            parametros: { ...PARAMETROS, rampas: 2 },
            geometria: { ...GEOMETRIA, descansos: 1, area_de_descanso_m2: 1.44, rampas: [{ numero: 1, peldanos: 9, recorrido_m: 2, altura_m: 1.56 }, { numero: 2, peldanos: 9, recorrido_m: 2, altura_m: 1.56 }] },
            conceptos: [
              { parte: 'escalon', elemento_clave: 'ESC-FORJADA', ref: null, concepto: ESCALON, toma: [], cantidad: 18, unidad: 'pza', nota: '', propuesta: null },
              { parte: 'descanso', elemento_clave: 'ESC-FORJADA', ref: null, concepto: DESCANSO, toma: ['área'], cantidad: 1.44, unidad: 'm²', nota: '', propuesta: null },
            ],
          },
        ),
      ],
    });
    const { onCambio } = pintar('costos', false);
    expect(screen.getByTestId('escalera-de-la-zona-resumen')).toHaveTextContent('descanso 1.44 m²');
    expect(screen.getByText(/EJ-820 · propuesto/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Proponer el concepto del descanso' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ zonaId: 'z1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(expect.stringContaining('Se propuso el concepto nuevo del descanso')));
  });

  it('una zona sin escaleras lo dice', () => {
    m.calculo.current = CALCULO({ escaleras: [], por_espacio: [], totales: { peldanos: 0, escalones_de_catalogo: 0, area_de_descanso_m2: 0, conceptos: [] } });
    pintar('control_obra', true);
    expect(screen.getByText(/La zona no tiene escaleras/)).toBeInTheDocument();
  });
});
