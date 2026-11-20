/**
 * Una línea del plano como elemento de la losa (fase 2): en el detalle de la línea elegida, Control de obra la mide como una trabe, contratrabe o
 * nervadura de una zona; la medida deriva de la línea. Costos y los demás no ven la acción.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  agregar: vi.fn(),
  zonas: { current: undefined as unknown },
}));

vi.mock('@/api/generado/zonas-de-losa/zonas-de-losa', () => ({
  getResolverMuroApiV1TrazosTrazoIdZonasDeLosaGetQueryKey: (id: string) => ['resolver', id],
  getZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGetQueryKey: (id: string) => ['zonas', id],
  useZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGet: () => ({ data: m.zonas.current }),
  useResolverMuroApiV1TrazosTrazoIdZonasDeLosaGet: () => ({ data: undefined }),
  useAplicarZonaAlMuroApiV1TrazosTrazoIdZonasDeLosaAplicarPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useBorrarZonaApiV1ZonasDeLosaZonaIdDelete: () => ({ mutateAsync: vi.fn() }),
  useCambiarZonaApiV1ZonasDeLosaZonaIdPut: () => ({ mutateAsync: vi.fn() }),
  useCrearZonaApiV1PlanosPlanoIdZonasDeLosaPost: () => ({ mutateAsync: vi.fn() }),
  useFijarLosaApiV1TrazosTrazoIdLosaPut: () => ({ mutateAsync: vi.fn() }),
  useFijarNivelExteriorApiV1TrazosTrazoIdNivelExteriorPut: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock('@/api/generado/losas/losas', () => ({
  useAgregarElementoApiV1ZonasDeLosaZonaIdElementosPost: () => ({ mutateAsync: m.agregar, isPending: false }),
  useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet: () => ({
    data: { elementos_permitidos: [{ clave: 'T-1-15x25', tiene_concepto_de_colado: true }, { clave: 'CT1-15x25', tiene_concepto_de_colado: true }] },
  }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { ZonaDeLosaDelTrazo } from '@/cuantificador/ZonasDeLosa';

const ZONAS = {
  plano_id: 'p1', escala_definida: true, puntos_de_nivel: [],
  zonas: [
    { id: 'z1', nombre: 'Entrepiso 3.00', altura_libre_m: '3.000', espesor_m: '0.120' },
    { id: 'z2', nombre: 'Entrepiso 4.20', altura_libre_m: '4.200', espesor_m: '0.200' },
  ],
};

function pintar(puedeEditar: boolean, tipo = 'LineString') {
  const onCambio = vi.fn();
  const onError = vi.fn();
  render(
    <ZonaDeLosaDelTrazo
      trazoId="t1" planoId="p1" tipoDeGeometria={tipo} esMuro={false} losaZonaId={null} losaEspesorM={null} nivelExteriorM={null} rotulo={null}
      puedeEditar={puedeEditar} onCambio={onCambio} onError={onError}
    />,
  );
  return { onCambio, onError };
}

beforeEach(() => {
  m.agregar.mockReset();
  m.agregar.mockResolvedValue({});
  m.zonas.current = ZONAS;
});

describe('Una línea como elemento de la losa', () => {
  it('Control de obra la mide como un elemento de una zona: manda la línea, no una cantidad', async () => {
    const { onCambio } = pintar(true);
    const bloque = screen.getByTestId('elemento-de-losa-de-la-linea');
    expect(bloque).toHaveTextContent('la matriz cambia');
    fireEvent.change(screen.getByLabelText('Zona del elemento de losa'), { target: { value: 'z2' } });
    fireEvent.change(screen.getByLabelText('Elemento de losa de la línea'), { target: { value: 'CT1-15x25' } });
    fireEvent.change(screen.getByLabelText('Pago del elemento de la línea'), { target: { value: 'propio' } });
    fireEvent.click(screen.getByRole('button', { name: 'Medir con esta línea' }));
    await waitFor(() =>
      expect(m.agregar).toHaveBeenCalledWith({ zonaId: 'z2', data: { elemento_clave: 'CT1-15x25', modo: 'ml', pago: 'propio', trazo_id: 't1' } }),
    );
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(expect.stringContaining('CT1-15x25 medido con esta línea')));
  });

  it('por pieza manda el modo pieza con la misma línea', async () => {
    pintar(true);
    fireEvent.change(screen.getByLabelText('Se mide por la línea'), { target: { value: 'pieza' } });
    fireEvent.click(screen.getByRole('button', { name: 'Medir con esta línea' }));
    await waitFor(() =>
      expect(m.agregar).toHaveBeenCalledWith({ zonaId: 'z1', data: { elemento_clave: 'T-1-15x25', modo: 'pieza', pago: 'en_la_losa', trazo_id: 't1' } }),
    );
  });

  it('un error del servidor se avisa y quien no edita no ve la acción; un polígono tampoco la trae', async () => {
    m.agregar.mockRejectedValue(new Error('La línea es de otro plano que la zona.'));
    const { onError } = pintar(true);
    fireEvent.click(screen.getByRole('button', { name: 'Medir con esta línea' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith('La línea es de otro plano que la zona.'));
  });

  it('solo Control de obra la ve y solo con zonas en el plano', () => {
    pintar(false);
    expect(screen.queryByTestId('elemento-de-losa-de-la-linea')).not.toBeInTheDocument();
  });

  it('sin zonas en el plano no hay nada que medir', () => {
    m.zonas.current = { ...ZONAS, zonas: [] };
    pintar(true);
    expect(screen.queryByTestId('elemento-de-losa-de-la-linea')).not.toBeInTheDocument();
  });
});
