/**
 * Pendientes por autorizar: casillas, «seleccionar todos» y aprobación en lote (§10.3).
 * Lo resuelto no se marca; «no críticos» no toca los críticos; antes de aprobar se confirma.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const lote = vi.hoisted(() => ({ mutate: vi.fn() }));
const PENDIENTES = vi.hoisted(() => [
  { id: 'a', tipo: 'cpu_nuevo', entidad: 'concepto', valor_origen: 'CAR-1', propuesta: {}, critico: false, resuelto: false },
  { id: 'b', tipo: 'cpu_nuevo', entidad: 'concepto', valor_origen: 'CAR-2', propuesta: {}, critico: false, resuelto: false },
  { id: 'c', tipo: 'mapeo_no_reconocido', entidad: 'unidad', valor_origen: 'M3X', propuesta: {}, critico: true, resuelto: false },
  { id: 'd', tipo: 'cpu_nuevo', entidad: 'concepto', valor_origen: 'CAR-4', propuesta: {}, critico: false, resuelto: true, resolucion: { accion: 'aprobado' } },
]);

vi.mock('@/api/generado/cargas/cargas', () => ({
  useBandejaGlobalApiV1PendientesGet: () => ({ data: PENDIENTES, isLoading: false, error: null, refetch: vi.fn() }),
  useResolverPendienteApiV1PendientesPendienteIdResolverPost: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useAprobarPendientesEnLoteApiV1PendientesAprobarLotePost: () => ({ mutate: lote.mutate, isPending: false, error: null }),
}));

import Pendientes from '@/pendientes/Pendientes';

describe('aprobar pendientes en lote', () => {
  it('«seleccionar todos» marca solo los abiertos y el botón cuenta lo marcado', () => {
    render(<Pendientes />);
    const aprobar = screen.getByRole('button', { name: /Aprobar seleccionados/ }) as HTMLButtonElement;
    expect(aprobar.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('Seleccionar todos los pendientes abiertos'));
    expect(screen.getByRole('button', { name: 'Aprobar seleccionados (3)' })).toBeTruthy();
    expect(screen.queryByLabelText('Seleccionar CAR-4')).toBeNull(); // el resuelto no se marca
  });

  it('pide confirmación, avisa cuántos son críticos y manda solo los marcados', () => {
    lote.mutate.mockClear();
    render(<Pendientes />);
    fireEvent.click(screen.getByLabelText('Seleccionar CAR-1'));
    fireEvent.click(screen.getByLabelText('Seleccionar M3X'));
    fireEvent.click(screen.getByRole('button', { name: 'Aprobar seleccionados (2)' }));
    expect(lote.mutate).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog').textContent).toMatch(/Aprobar 2 pendientes\?.*1 es crítico/);
    fireEvent.click(screen.getByRole('button', { name: 'Sí, aprobar' }));
    expect(lote.mutate).toHaveBeenCalledWith({ data: { ids: ['a', 'c'] } });
  });

  it('«no críticos» cuenta solo los abiertos no críticos y deja los críticos', () => {
    lote.mutate.mockClear();
    render(<Pendientes />);
    fireEvent.click(screen.getByRole('button', { name: 'Aprobar no críticos (2)' }));
    expect(screen.getByRole('alertdialog').textContent).toMatch(/Los críticos se quedan abiertos/);
    fireEvent.click(screen.getByRole('button', { name: 'Sí, aprobar' }));
    expect(lote.mutate).toHaveBeenCalledWith({ data: { solo_no_criticos: true } });
  });
});
