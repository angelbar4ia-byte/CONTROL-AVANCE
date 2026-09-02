/**
 * Que la matriz de cuadrillas por frente pinte lo que dice pintar (§8.3).
 *
 * Complementa `planeacion.test.ts`, que fija las reglas sin render. Aquí se
 * comprueba lo que un typecheck no ve, y que son las decisiones que la tabla
 * tiene que respetar para que se pueda contratar mirándola:
 *
 *  1. **Las cuadrillas no se redondean.** 2.3 significa que dos aprietan y tres
 *     sobran; pintar «2» prometería una meta que no se cumple y «3», gente de
 *     más. Es la misma decisión que el dominio toma, y aquí se puede perder.
 *  2. **El renglón sin frente no ofrece botón**, y dice a dónde ir. Ofrecerlo
 *     guardaría contra un `frente_id` vacío.
 *  3. **Quien no planifica no ve la columna de contratar** (§4). No basta con
 *     que el `PUT` le dé 403: vería un botón que siempre falla.
 *
 * Componente de presentación: recibe todo por props, así que no hace falta
 * simular la red — ninguna prueba de este repo lo hace.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { FrenteDeObraRespuesta } from '@/api/generado/modelo';
import { TablaFrentes, type PeriodoDePlaneacion } from '@/planeacion/TablaFrentes';

const PERIODOS: readonly PeriodoDePlaneacion[] = [
  {
    clave: '2026-S20',
    desde: '2026-05-11',
    hasta: '2026-05-18',
    etiqueta: 'S20',
    dias_habiles: 5,
  },
  {
    clave: '2026-S21',
    desde: '2026-05-18',
    hasta: '2026-05-25',
    etiqueta: 'S21',
    dias_habiles: 5,
  },
];

function frente(sobre: Partial<FrenteDeObraRespuesta> = {}): FrenteDeObraRespuesta {
  return {
    frente_id: '22222222-2222-2222-2222-222222222222',
    frente_clave: 'EST',
    frente_nombre: 'Estructura',
    jornadas: [11.5, 40],
    cuadrillas: [2.3, 8],
    total_jornadas: 51.5,
    pico_cuadrillas: 8,
    contratista_id: null,
    contratista_nombre: null,
    cuadrillas_plan: null,
    notas: null,
    ...sobre,
  } as FrenteDeObraRespuesta;
}

function pintar(
  frentes: readonly FrenteDeObraRespuesta[],
  opciones: { puedeAsignar?: boolean; onAsignar?: () => void } = {},
) {
  const onAsignar = opciones.onAsignar ?? vi.fn();
  render(
    <TablaFrentes
      periodos={PERIODOS}
      frentes={frentes}
      puedeAsignar={opciones.puedeAsignar ?? true}
      onAsignar={onAsignar}
    />,
  );
  return { onAsignar };
}

describe('la cifra con la que se contrata', () => {
  it('escribe las cuadrillas sin redondear', () => {
    // 2.3 dice que dos aprietan y tres sobran. El dominio decidió no redondear;
    // la tabla es el otro sitio donde esa decisión se puede perder.
    pintar([frente()]);
    expect(screen.getByText('2.30')).toBeInTheDocument();
  });

  it('enseña de dónde salió cada celda', () => {
    // Un 2.3 en una semana corta y un 2.3 en una completa se leen igual y no
    // son lo mismo: el título trae las jornadas y los días hábiles.
    pintar([frente()]);
    const celda = screen.getByTitle(/11\.50 jornada\(s\) ÷ 5 día\(s\) hábil\(es\)/);
    expect(celda).toBeInTheDocument();
  });

  it('un periodo sin carga no se deja en blanco', () => {
    // Blanco diría "no se sabe", que es otra afirmación. El punto dice "aquí no
    // se ocupa nadie".
    pintar([frente({ cuadrillas: [0, 8], jornadas: [0, 40] })]);
    expect(screen.getAllByText('·').length).toBeGreaterThan(0);
  });
});

describe('el renglón que agrupa lo que no tiene frente', () => {
  const SIN_FRENTE = frente({
    frente_id: '',
    frente_clave: '—',
    frente_nombre: 'Sin frente asignado',
  });

  it('no ofrece asignar contratista', () => {
    pintar([SIN_FRENTE]);
    expect(screen.queryByRole('button', { name: /asignar|cambiar/i })).toBeNull();
  });

  it('dice a dónde ir a resolverlo', () => {
    // Sin esto el renglón parece un error de datos en vez de captura pendiente.
    pintar([SIN_FRENTE]);
    expect(screen.getByText(/Frentes de obra/)).toBeInTheDocument();
  });

  it('sigue apareciendo con su carga: es trabajo real', () => {
    pintar([SIN_FRENTE]);
    expect(screen.getByText('Sin frente asignado')).toBeInTheDocument();
    expect(screen.getByText('51.50')).toBeInTheDocument();
  });
});

describe('la cobertura', () => {
  it('un frente sin decidir no se pinta como falta', () => {
    pintar([frente()]);
    expect(screen.getByText('Sin decidir')).toBeInTheDocument();
  });

  it('un frente con menos gente de la que pide dice cuántas faltan', () => {
    pintar([frente({ cuadrillas_plan: 5 })]);
    expect(screen.getByText('Faltan 3')).toBeInTheDocument();
  });

  it('un frente con la gente suficiente lo dice', () => {
    pintar([frente({ cuadrillas_plan: 8 })]);
    expect(screen.getByText('Alcanza')).toBeInTheDocument();
  });
});

describe('quién ve la columna de contratar', () => {
  it('quien planifica ve el botón', () => {
    pintar([frente()]);
    expect(screen.getByRole('button', { name: 'Asignar' })).toBeInTheDocument();
  });

  it('el botón dice «Cambiar» cuando ya hay contratista', () => {
    pintar([
      frente({
        contratista_id: '33333333-3333-3333-3333-333333333333',
        contratista_nombre: 'Constructora del Norte',
      }),
    ]);
    expect(screen.getByRole('button', { name: 'Cambiar' })).toBeInTheDocument();
    expect(screen.getByText('Constructora del Norte')).toBeInTheDocument();
  });

  it('quien no planifica no ve el botón', () => {
    // Que el PUT le diera 403 no basta: vería un botón que siempre falla.
    pintar([frente()], { puedeAsignar: false });
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('al pulsarlo entrega el frente completo, no solo su id', () => {
    // El diálogo necesita el pico para proponer un punto de partida.
    const onAsignar = vi.fn();
    pintar([frente()], { onAsignar });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar' }));
    expect(onAsignar).toHaveBeenCalledWith(
      expect.objectContaining({ frente_clave: 'EST', pico_cuadrillas: 8 }),
    );
  });
});

describe('el orden de la tabla', () => {
  it('respeta el que trae el backend: primero quien pide más gente', () => {
    // El dominio ordena por pico descendente porque la pregunta es a quién hay
    // que conseguirle más gente. Reordenar aquí rompería esa respuesta.
    pintar([
      frente({ frente_clave: 'ALB', pico_cuadrillas: 113.93 }),
      frente({ frente_clave: 'EST', pico_cuadrillas: 44.23 }),
    ]);
    const filas = screen.getAllByRole('row').slice(1);
    expect(within(filas[0]!).getByText('ALB')).toBeInTheDocument();
    expect(within(filas[1]!).getByText('EST')).toBeInTheDocument();
  });
});
