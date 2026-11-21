/**
 * Los cimientos de la zona de losa en el panel de zonas (Fase 4b): solo se pinta lo que responde el servidor; Control de obra cambia (cotas, punto de nivel, caras,
 * dentellón y espacio) y quita cimientos; los demás roles solo leen. Cada concepto dice en qué partida se mide.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calculo: { current: undefined as unknown, error: null as unknown },
  cambiar: vi.fn(),
  quitar: vi.fn(),
}));

vi.mock('@/api/generado/cimientos/cimientos', () => ({
  useCalculoDeLosCimientosApiV1ZonasDeLosaZonaIdCimientosCalculoGet: () => ({ data: m.calculo.current, isLoading: false, isError: m.calculo.error !== null, error: m.calculo.error }),
  useCambiarCimientoApiV1CimientosDeZonaCimientoIdPut: () => ({ mutateAsync: m.cambiar, isPending: false }),
  useQuitarCimientoApiV1CimientosDeZonaCimientoIdDelete: () => ({ mutateAsync: m.quitar, isPending: false }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { CimientosDeLaZona } from '@/cuantificador/CimientosDeLaZona';

const ZONA = { id: 'z1', plano_id: 'p1', nombre: 'Cimentación', nivel: null, cota_piso_m: '0.000', losas: [] } as never;
const ESPACIOS = [{ id: 'esp1', nombre: 'Cimiento norte' }, { id: 'esp2', nombre: 'Cimiento sur' }] as never;
const PUNTOS = [{ trazo_id: 'pn1', cota_m: '-0.600', rotulo: 'Desplante CIM-1' }];
const MCT = { clave: 'MCT-01011', descripcion: 'MURO DE MAMPOSTERÍA DE PIEDRA DE CERRO', unidad: 'm3', estado: 'catalogo', provisional: false };

const CIMIENTO = (extra: Record<string, unknown> = {}, calculo: Record<string, unknown> | null = {}) => ({
  id: 'c1', trazo_id: 'l1', punto_nivel_id: null, espacio_id: null, origen_de_cotas: { desplante: 'explicita', corona: 'zona' }, longitud_m: 10, error: null,
  calculo:
    calculo === null
      ? null
      : {
          clave: 'CIM-01010', cotas: { desplante_m: -0.8, corona_m: 0, altura_m: 0.8 }, longitud_m: 10,
          seccion: { alto_m: 0.8, corona_m: 0.4, base_m: 0.93, espesor_medio_m: 0.665, caras: 1, manual: false },
          escarpio: { minimo: 1.5, real: 1.51, cumple: true }, dentellon: { aplica: false, opcion: false, b2_m: 0.4, b1_m: 0.3, h_m: 0.6 },
          volumen_m3_ml: 0.532, volumen_m3: 5.32, insumos: { piedra_a_comprar_m3: 8, cemento_kg: 443, arena_m3: 2.17, agua_l: 420 },
          conceptos: [{ parte: 'cimiento', elemento_clave: 'CIM-01010', ref: null, concepto: MCT, toma: ['longitud', 'altura'], cantidad: 5.32, unidad: 'm3', nota: '' }],
          por_espacio: [], no_incluye: [], mano_de_obra: { estado: 'sin_mano_de_obra', nota: '' }, advertencias: ['Aviso del muro.'], pendientes: [],
          ...calculo,
        },
  ...extra,
});

const CALCULO = (extra: Record<string, unknown> = {}) => ({
  zona: { id: 'z1', plano_id: 'p1', nombre: 'Cimentación', nivel: null, cota_piso_m: 0 },
  escala_definida: true,
  cimientos: [CIMIENTO()],
  totales: { longitud_m: 10, volumen_m3: 5.32, conceptos: [{ concepto: MCT, unidad: 'm3', cantidad: 5.32, propuesta: null }] },
  por_espacio: [
    {
      espacio_id: 'esp1', espacio_nombre: 'Cimiento norte',
      conceptos: [
        {
          parte: 'cimiento', elemento_clave: 'CIM-01010', ref: null, concepto: MCT, toma: [], cantidad: 5.32, unidad: 'm3', nota: '',
          resolucion: { estado: 'cuenta', cuenta: true, aviso: null, concepto_id: 'c1', partida_id: 'pa1', partida_nombre: 'Muro de piedra (Cimiento norte)' },
        },
      ],
    },
    {
      espacio_id: null, espacio_nombre: null,
      conceptos: [
        {
          parte: 'cimiento', elemento_clave: 'CIM-01010', ref: null, concepto: MCT, toma: [], cantidad: 1, unidad: 'm3', nota: '',
          resolucion: { estado: 'sin_espacio', cuenta: false, aviso: 'Sin espacio.', concepto_id: 'c1', partida_id: null, partida_nombre: null },
        },
      ],
    },
  ],
  advertencias: [],
  ...extra,
});

function pintar(puedeEditar: boolean) {
  const onCambio = vi.fn();
  const onError = vi.fn();
  render(<CimientosDeLaZona zona={ZONA} puntos={PUNTOS} puedeEditar={puedeEditar} espacios={ESPACIOS} onCambio={onCambio} onError={onError} />);
  fireEvent.click(screen.getByRole('button', { name: 'Cimientos de Cimentación' }));
  return { onCambio, onError };
}

beforeEach(() => {
  m.cambiar.mockReset();
  m.quitar.mockReset();
  m.cambiar.mockResolvedValue({});
  m.quitar.mockResolvedValue(undefined);
  m.calculo.current = CALCULO();
  m.calculo.error = null;
});

describe('CimientosDeLaZona', () => {
  it('está cerrado hasta que se abre y pinta las cotas, la altura, el volumen y lo que paga cada espacio en su partida', () => {
    render(<CimientosDeLaZona zona={ZONA} puntos={PUNTOS} puedeEditar onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByTestId('cuerpo-de-los-cimientos')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cimientos de Cimentación' }));
    const resumen = screen.getByTestId('cimiento-de-la-zona-resumen');
    expect(resumen).toHaveTextContent('Desplante -0.80 m (tecleada)');
    expect(resumen).toHaveTextContent('corona 0.00 m (del piso de la zona)');
    expect(resumen).toHaveTextContent('altura 0.80 m');
    expect(resumen).toHaveTextContent('5.320 m³ de MCT-01011');
    expect(screen.getByTestId('cimientos-resumen')).toHaveTextContent('10.00 m');
    const tomas = screen.getByRole('table', { name: 'Lo que paga el cimiento de cada espacio' });
    expect(tomas.querySelector('[data-espacio="Cimiento norte"]')).toHaveTextContent('Muro de piedra (Cimiento norte)');
    expect(tomas.querySelector('[data-espacio="sin espacio"]')).toHaveAttribute('data-estado-de-partida', 'sin_espacio');
    expect(screen.getByText('Aviso del muro.')).toBeInTheDocument();
  });

  it('guarda las cotas tecleadas y el punto de nivel, asigna el espacio y quita el cimiento', async () => {
    const { onCambio } = pintar(true);
    fireEvent.change(screen.getByLabelText('Cota de desplante del cimiento 1'), { target: { value: '-1.5' } });
    fireEvent.change(screen.getByLabelText('Cota de la corona del cimiento 1'), { target: { value: '-0.1' } });
    fireEvent.change(screen.getByLabelText('Caras del cimiento 1'), { target: { value: '2' } });
    fireEvent.click(screen.getByLabelText('Dentellón del cimiento 1'));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar el cimiento 1' }));
    await waitFor(() =>
      expect(m.cambiar).toHaveBeenCalledWith({ cimientoId: 'c1', data: { trazo_id: 'l1', cota_desplante_m: -1.5, cota_corona_m: -0.1, caras: 2, dentellon: true } }),
    );
    await waitFor(() => expect(onCambio).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Cota de desplante del cimiento 1'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Punto de nivel del cimiento 1'), { target: { value: 'pn1' } });
    fireEvent.change(screen.getByLabelText('Espacio del cimiento 1'), { target: { value: 'esp2' } });
    await waitFor(() =>
      expect(m.cambiar).toHaveBeenLastCalledWith({ cimientoId: 'c1', data: expect.objectContaining({ punto_nivel_id: 'pn1', espacio_id: 'esp2' }) }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el cimiento 1' }));
    await waitFor(() => expect(m.quitar).toHaveBeenCalledWith({ cimientoId: 'c1' }));
  });

  it('una cota que no es un número no se manda y un error del servidor se avisa', async () => {
    const { onError } = pintar(true);
    fireEvent.change(screen.getByLabelText('Cota de la corona del cimiento 1'), { target: { value: 'arriba' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar el cimiento 1' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('no es un número válido')));
    expect(m.cambiar).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Cota de la corona del cimiento 1'), { target: { value: '' } });
    m.cambiar.mockRejectedValue(new Error('La corona debe estar por encima del desplante: el cimiento tiene altura.'));
    fireEvent.click(screen.getByRole('button', { name: 'Guardar el cimiento 1' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('por encima del desplante')));
  });

  it('un cimiento con un dato que no vale muestra su motivo y se puede quitar', async () => {
    m.calculo.current = CALCULO({
      cimientos: [CIMIENTO({ error: 'La corona debe estar por encima del desplante: el cimiento tiene altura.' }, null)],
      advertencias: ['Un cimiento no se puede calcular: la corona debe estar por encima.'],
    });
    pintar(true);
    expect(screen.getByTestId('cimiento-error')).toHaveTextContent('por encima del desplante');
    expect(screen.getAllByRole('alert').length).toBeGreaterThanOrEqual(2);
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el cimiento 1' }));
    await waitFor(() => expect(m.quitar).toHaveBeenCalledWith({ cimientoId: 'c1' }));
  });

  it('con el desplante de un punto de nivel lo dice; quien no es Control de obra solo lee', () => {
    m.calculo.current = CALCULO({ cimientos: [CIMIENTO({ punto_nivel_id: 'pn1', origen_de_cotas: { desplante: 'punto_de_nivel', corona: 'zona' } })] });
    pintar(false);
    expect(screen.getByTestId('cimiento-de-la-zona-resumen')).toHaveTextContent('(de un punto de nivel exterior)');
    expect(screen.getByLabelText('Cota de desplante del cimiento 1')).toBeDisabled();
    expect(screen.getByLabelText('Espacio del cimiento 1')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Quitar el cimiento 1' })).not.toBeInTheDocument();
  });

  it('una zona sin cimientos lo dice', () => {
    m.calculo.current = CALCULO({ cimientos: [], por_espacio: [], totales: { longitud_m: 0, volumen_m3: 0, conceptos: [] } });
    pintar(true);
    expect(screen.getByText(/La zona no tiene cimientos/)).toBeInTheDocument();
  });
});
