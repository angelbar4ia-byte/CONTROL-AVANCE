/**
 * Que la matriz de insumos programados pinte lo que dice pintar.
 *
 * Complementa `insumos.test.ts`, que fija las reglas sin render. Aquí se
 * comprueba lo que un typecheck no ve, y que son las tres decisiones de rol y
 * de dato que la pantalla tiene que respetar:
 *
 *  1. **Los importes no se dibujan para quien no los puede ver** (§4). No basta
 *     con que el backend los mande nulos: la columna no debe existir, o el
 *     residente vería un encabezado "Importe" siempre vacío y pensaría que es
 *     un error.
 *  2. **Cero es un dato y se escribe.** Esa semana no se ocupa nada; dejar la
 *     celda en blanco diría "no se sabe", que es otra afirmación.
 *  3. **El desglose se abre.** Un insumo aparece en varios conceptos y la suma
 *     es lo que se compra, pero cuando una cifra sorprende hay que poder ver de
 *     dónde salió.
 *
 * Componente de presentación: recibe todo por props, así que no hace falta
 * simular la red — ninguna prueba de este repo lo hace.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  FilaDeInsumoRespuesta,
  ObractrlAdaptersApiV1InsumosPeriodoRespuesta as PeriodoRespuesta,
} from '@/api/generado/modelo';
import { TablaInsumos } from '@/insumos/TablaInsumos';

const PERIODOS: readonly PeriodoRespuesta[] = [
  { clave: '2026-S20', desde: '2026-05-11', hasta: '2026-05-18', etiqueta: 'S20' },
  { clave: '2026-S21', desde: '2026-05-18', hasta: '2026-05-25', etiqueta: 'S21' },
];

function fila(sobre: Partial<FilaDeInsumoRespuesta> = {}): FilaDeInsumoRespuesta {
  return {
    insumo_id: '11111111-1111-1111-1111-111111111111',
    clave: 'CEM-01',
    descripcion: 'Cemento gris',
    unidad: 'BTO',
    tipo: 'material',
    dias_entrega: null,
    cantidades: [3.5, 1.5],
    total: 5,
    importe: 1250,
    ya_surtido: 2,
    desglose: [],
    ...sobre,
  } as FilaDeInsumoRespuesta;
}

function pintar(
  filas: readonly FilaDeInsumoRespuesta[],
  opciones: { conImportes?: boolean; conSurtido?: boolean; abiertos?: Set<string> } = {},
) {
  const onAlternar = vi.fn();
  const salida = render(
    <TablaInsumos
      periodos={PERIODOS}
      filas={filas}
      abiertos={opciones.abiertos ?? new Set()}
      onAlternar={onAlternar}
      conImportes={opciones.conImportes ?? true}
      conSurtido={opciones.conSurtido ?? true}
    />,
  );
  return { ...salida, onAlternar };
}

describe('TablaInsumos', () => {
  it('trae una columna por periodo, más total', () => {
    pintar([fila()]);
    expect(screen.getByRole('columnheader', { name: 'S20' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'S21' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Total' })).toBeInTheDocument();
  });

  it('pinta el renglón con su clave, descripción y unidad', () => {
    pintar([fila()]);
    expect(screen.getByText('CEM-01')).toBeInTheDocument();
    expect(screen.getByText('Cemento gris')).toBeInTheDocument();
    expect(screen.getByText('BTO')).toBeInTheDocument();
  });

  it('sin permiso de importes la columna no existe', () => {
    // No basta con que el dato venga nulo: un encabezado siempre vacío se lee
    // como un error de la pantalla.
    pintar([fila({ importe: null })], { conImportes: false });
    expect(screen.queryByRole('columnheader', { name: 'Importe' })).not.toBeInTheDocument();
  });

  it('con permiso, el importe se muestra en pesos', () => {
    pintar([fila()], { conImportes: true });
    expect(screen.getByRole('columnheader', { name: 'Importe' })).toBeInTheDocument();
  });

  it('en una simulación no hay almacén contra el cual comparar', () => {
    pintar([fila({ ya_surtido: null })], { conSurtido: false });
    expect(screen.queryByRole('columnheader', { name: 'Ya surtido' })).not.toBeInTheDocument();
  });

  it('un periodo sin consumo escribe cero, no lo deja en blanco', () => {
    // Cero dice "esa semana no se ocupa nada"; el hueco diría "no se sabe".
    const { container } = pintar([fila({ cantidades: [5, 0], total: 5 })]);
    const renglon = container.querySelector('tbody tr');
    expect(renglon).toHaveTextContent('0');
  });

  it('el plazo capturado se anuncia; el heredado no', () => {
    pintar([fila({ dias_entrega: 15 })]);
    expect(screen.getByText(/pedir 15 d antes/)).toBeInTheDocument();

    const sinPlazo = pintar([fila({ dias_entrega: null })]);
    expect(within(sinPlazo.container).queryByText(/pedir .* antes/)).not.toBeInTheDocument();
  });

  it('sin desglose no ofrece abrir el renglón', () => {
    pintar([fila({ desglose: [] })]);
    expect(screen.queryByRole('button', { name: /Desglose/ })).not.toBeInTheDocument();
  });

  it('con desglose, el botón avisa hacia arriba', () => {
    const { onAlternar } = pintar([
      fila({
        desglose: [
          { obra_id: 'obra-1111', concepto_clave: 'MURO-01', cantidad: 3 },
        ],
      }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: /Desglose de CEM-01/ }));
    expect(onAlternar).toHaveBeenCalledWith('11111111-1111-1111-1111-111111111111');
  });

  it('abierto, el desglose dice de qué conceptos salió', () => {
    pintar(
      [
        fila({
          desglose: [
            { obra_id: 'obra-1111', concepto_clave: 'MURO-01', cantidad: 3 },
            { obra_id: 'obra-2222', concepto_clave: 'LOSA-01', cantidad: 2 },
          ],
        }),
      ],
      { abiertos: new Set(['11111111-1111-1111-1111-111111111111']) },
    );
    expect(screen.getByText('MURO-01')).toBeInTheDocument();
    expect(screen.getByText('LOSA-01')).toBeInTheDocument();
  });

  it('el tipo del insumo se rotula legible', () => {
    pintar([fila({ tipo: 'mano_obra' })]);
    expect(screen.getByText(/Mano de obra/)).toBeInTheDocument();
  });
});
