/**
 * C4: un muro ya medido conserva la versión de la plantilla que eligió. Si hay una más nueva, su ventana ofrece «Actualizar a la versión
 * vigente» (que abre el aviso de qué cambia) y «Eliminar el trazo». Solo se pinta lo que responde el servidor.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  vigente: { current: undefined as unknown },
}));

vi.mock('@/api/generado/artefacto-de-muros/artefacto-de-muros', () => ({
  useCatalogoDelArtefactoApiV1MuroArtefactoCatalogoGet: () => ({ data: { materiales: [], ubicaciones: [], tipos: [] } }),
  useElegirPlantillaDelTrazoApiV1TrazosTrazoIdMuroPlantillaPut: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useListarPlantillasApiV1MuroPlantillasGet: () => ({ data: [] }),
  getVersionVigenteDeLaPlantillaApiV1TrazosTrazoIdMuroPlantillaVigenteGetQueryKey: (id: string) => ['vigente', id],
  useVersionVigenteDeLaPlantillaApiV1TrazosTrazoIdMuroPlantillaVigenteGet: () => ({ data: m.vigente.current }),
}));
vi.mock('@/api/generado/cuantificacion/cuantificacion', () => ({
  getVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGetQueryKey: (id: string) => ['clasificacion', id],
  useFijarClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionPut: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGet: () => ({
    data: { tipo: 'tabique', material: 'tabique_rojo', ubicacion: 'interior', plantilla_id: 'v1', acabado: null },
    isLoading: false,
  }),
}));
vi.mock('@/cuantificador/CambioDePlantilla', () => ({
  CambioDePlantilla: ({ haciaId }: { haciaId: string }) => <div data-testid="cambio" data-hacia={haciaId} />,
}));
vi.mock('@/cuantificador/ColocacionDeLaPlantilla', () => ({ ColocacionDeLaPlantilla: () => null }));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { ClasificacionDelMuro } from '@/cuantificador/ClasificacionDeMuro';

const ficha = (id: string, version: number) => ({ id, nombre: 'Muro de tabique', version, tipo: 'tabique' });

beforeEach(() => {
  m.vigente.current = { trazo_id: 't1', actual: ficha('v1', 1), vigente: ficha('v2', 2), hay_version_nueva: true };
});

describe('Versión vigente de la plantilla del muro', () => {
  it('avisa que hay una versión nueva y ofrece actualizarla o eliminar el trazo', () => {
    const eliminar = vi.fn();
    render(<ClasificacionDelMuro trazoId="t1" onCambio={vi.fn()} onError={vi.fn()} onEliminarTrazo={eliminar} />);
    const aviso = screen.getByTestId('version-nueva-de-plantilla');
    expect(aviso).toHaveTextContent('versión 1');
    expect(aviso).toHaveTextContent('la vigente es la versión 2');
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar el trazo' }));
    expect(eliminar).toHaveBeenCalledTimes(1);
  });

  it('«Actualizar a la versión vigente» abre el cambio hacia la vigente (con su aviso de qué cambia)', () => {
    render(<ClasificacionDelMuro trazoId="t1" onCambio={vi.fn()} onError={vi.fn()} onEliminarTrazo={vi.fn()} />);
    expect(screen.queryByTestId('cambio')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar a la versión vigente' }));
    expect(screen.getByTestId('cambio')).toHaveAttribute('data-hacia', 'v2');
  });

  it('con la versión vigente no ofrece nada', () => {
    m.vigente.current = { trazo_id: 't1', actual: ficha('v2', 2), vigente: ficha('v2', 2), hay_version_nueva: false };
    render(<ClasificacionDelMuro trazoId="t1" onCambio={vi.fn()} onError={vi.fn()} onEliminarTrazo={vi.fn()} />);
    expect(screen.queryByTestId('version-nueva-de-plantilla')).toBeNull();
  });
});
