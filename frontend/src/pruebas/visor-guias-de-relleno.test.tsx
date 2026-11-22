/**
 * El visor pinta las guías del relleno dinámico de azotea: la línea de pendiente con su flecha hacia la bajada, los hilos de nivel punteados con su espesor y las
 * bajadas como puntos con su rótulo. Solo pinta lo que le dan (las genera el servidor).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Visor, type BajadaDeRellenoVisible, type GuiaDeRellenoVisible } from '@/cuantificador/Visor';

const GUIAS: readonly GuiaDeRellenoVisible[] = [
  { id: 'g1', tipo: 'pendiente', origen: 'generada', puntos: [[8, 0], [0, 0]] },
  { id: 'g2', tipo: 'pendiente', origen: 'trazada', puntos: [[0, -4], [8, -4]] },
  { id: 'g3', tipo: 'hilo', origen: 'generada', puntos: [[1, 0], [1, -2], [1, -4]], espesorM: 0.07 },
];
const BAJADAS: readonly BajadaDeRellenoVisible[] = [{ id: 'b1', punto: [0, 0], rotulo: 'BAP-1' }];

function pintar(guias: readonly GuiaDeRellenoVisible[], bajadas: readonly BajadaDeRellenoVisible[]) {
  return render(
    <Visor
      fondoUrl={null} trazos={[]} notas={[]} seleccion={null} herramienta="seleccionar" borrador={[]} onPunto={vi.fn()} onSeleccionar={vi.fn()}
      claveDePlano="plano-1" guiasDeRelleno={guias} bajadasDeRelleno={bajadas}
    />,
  );
}

describe('Visor · guías del relleno dinámico', () => {
  it('pinta la línea de pendiente (trazada o generada), los hilos de nivel punteados con su espesor y las bajadas', () => {
    pintar(GUIAS, BAJADAS);
    const lineas = screen.getAllByTestId('linea-de-pendiente');
    expect(lineas.map((l) => l.getAttribute('data-origen'))).toEqual(['generada', 'trazada']);
    expect(lineas[1]!.querySelector('polyline')).toHaveClass('is-trazada');
    expect(lineas[0]!.querySelector('path')).toBeTruthy(); // la flecha hacia la bajada
    const hilo = screen.getByTestId('hilo-de-nivel');
    expect(hilo).toHaveAttribute('data-espesor-cm', '7.0');
    expect(hilo.querySelector('polyline')).toHaveClass('visor__hilo-de-nivel');
    expect(hilo).toHaveTextContent('7.0 cm');
    expect(screen.getByTestId('bajada-de-relleno')).toHaveAttribute('data-bajada-id', 'b1');
    expect(screen.getByTestId('bajada-de-relleno')).toHaveTextContent('BAP-1');
  });

  it('sin guías ni bajadas no pinta nada', () => {
    pintar([], []);
    expect(screen.queryByTestId('guias-de-relleno')).not.toBeInTheDocument();
  });
});
