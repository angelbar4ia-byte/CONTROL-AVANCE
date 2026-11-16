/**
 * Lo que la plantilla del muro coloca en el plano (Ola 4C): los castillos con su alto y nivel, el concepto que paga cada parte o por qué no
 * cuenta (falta la partida en el árbol), y los botones de colocar y retirar. Solo se pinta lo que responde el servidor.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  colocar: vi.fn(),
  retirar: vi.fn(),
  datos: { current: undefined as unknown },
}));

vi.mock('@/api/generado/artefacto-de-muros/artefacto-de-muros', () => ({
  getColocacionDelMuroApiV1TrazosTrazoIdMuroPlantillaColocacionGetQueryKey: (id: string) => ['colocacion', id],
  useColocacionDelMuroApiV1TrazosTrazoIdMuroPlantillaColocacionGet: () => ({ data: m.datos.current, isLoading: false }),
  useColocarPlantillaEnElMuroApiV1TrazosTrazoIdMuroPlantillaColocarPost: () => ({ mutateAsync: m.colocar, isPending: false }),
  useRetirarPlantillaDelMuroApiV1TrazosTrazoIdMuroPlantillaColocarDelete: () => ({ mutateAsync: m.retirar, isPending: false }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { ColocacionDeLaPlantilla } from '@/cuantificador/ColocacionDeLaPlantilla';

const concepto = (o: Record<string, unknown>) => ({
  ranura: 'acero', concepto_id: 'c1', clave: 'EST-11011', unidad: 'pza', cantidad: '2', cuenta: true, estado: 'cuenta', origen: 'contexto',
  aviso: null, partida_id: 'p1', ...o,
});
const base = (o: Record<string, unknown> = {}) => ({
  trazo_id: 't1', plantilla_id: 'pl', plantilla: 'Muro con castillos', version: 1, largo_m: '10', altura_m: '3', nivel: 1, ubicacion: null,
  avisos: [],
  elementos: [
    {
      uid: 'K-1', ref: 'K-1', nombre: 'Castillo K-1', clase: 'castillo', modo: 'ubicado', piezas: 2, alto_m: '3', z_m: '0', metros: '6',
      posiciones_m: ['0.075', '9.925'], se_coloca: true, colocados: 0, descuento_m2_por_cara: '0.9',
      conceptos: [
        concepto({}),
        concepto({ ranura: 'colado', clave: 'COL-3', unidad: 'ml', cantidad: '6', cuenta: false, estado: 'falta_partida', aviso: 'El concepto COL-3 no está en el árbol de la obra en este nivel: agrégalo; mientras tanto no cuenta.' }),
      ],
    },
  ],
  ...o,
});

beforeEach(() => {
  m.colocar.mockReset().mockResolvedValue({ colocados: 2, reemplazados: 0, descuento_m2_por_cara: '0.9' });
  m.retirar.mockReset().mockResolvedValue({ retirados: 2 });
  m.datos.current = base();
});

describe('Elementos de la plantilla en el plano', () => {
  it('muestra el contexto (largo, altura del driver, nivel) y el concepto que paga cada parte', () => {
    render(<ColocacionDeLaPlantilla trazoId="t1" onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByTestId('contexto-de-colocacion')).toHaveTextContent('10.00 m de largo · 3.00 m de alto · nivel 1');
    const k = screen.getByRole('region', { name: 'Elementos de la plantilla' }).querySelector('[data-elemento="K-1"]') as HTMLElement;
    expect(within(k).getByText(/2 pza × 3.00 m · colocados 0 de 2/)).toBeInTheDocument();
    expect(k.querySelector('[data-concepto="EST-11011"]')).toHaveAttribute('data-cuenta', 'si');
    const sinPartida = k.querySelector('[data-concepto="COL-3"]') as HTMLElement;
    expect(sinPartida).toHaveAttribute('data-cuenta', 'no');
    expect(sinPartida).toHaveTextContent(/no cuenta: El concepto COL-3 no está en el árbol/);
  });

  it('coloca en el plano y avisa cuántos castillos quedaron', async () => {
    const onCambio = vi.fn();
    render(<ColocacionDeLaPlantilla trazoId="t1" onCambio={onCambio} onError={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Retirar lo colocado' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Colocar los elementos de la plantilla' }));
    await waitFor(() => expect(m.colocar).toHaveBeenCalledWith({ trazoId: 't1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith('Plantilla colocada: 2 castillos en el plano.'));
  });

  it('con castillos colocados ofrece retirarlos', async () => {
    const d = base();
    d.elementos[0]!.colocados = 2;
    m.datos.current = d;
    const onCambio = vi.fn();
    render(<ColocacionDeLaPlantilla trazoId="t1" onCambio={onCambio} onError={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Retirar lo colocado' }));
    await waitFor(() => expect(m.retirar).toHaveBeenCalled());
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith('Se retiró lo que colocó la plantilla (2).'));
  });

  it('un castillo estimado se cuenta pero no se coloca: el botón no se ofrece activo', () => {
    const d = base();
    Object.assign(d.elementos[0]!, { modo: 'estimado', se_coloca: false, posiciones_m: [] });
    m.datos.current = d;
    render(<ColocacionDeLaPlantilla trazoId="t1" onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByText(/estimados \(no se colocan\)/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Colocar los elementos de la plantilla' })).toBeDisabled();
  });

  it('si el servidor rechaza, avisa con su mensaje', async () => {
    m.colocar.mockRejectedValue(new Error('La plantilla de este muro no lleva castillos ubicados'));
    const onError = vi.fn();
    render(<ColocacionDeLaPlantilla trazoId="t1" onCambio={vi.fn()} onError={onError} />);
    fireEvent.click(screen.getByRole('button', { name: 'Colocar los elementos de la plantilla' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith('La plantilla de este muro no lleva castillos ubicados'));
  });
});
