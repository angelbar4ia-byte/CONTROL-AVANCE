/**
 * Ensambles paramétricos: reflejo de UX y reporte de Generación
 * (`src/ensambles/reglas.ts`, `ReporteGeneracion.tsx`; skill `erp-parametrico`
 * §2, §5.7, §6, §8).
 *
 * Lo que estas pruebas protegen es la frontera: la web **muestra** lo que
 * clasificó y calculó el backend y nunca lo recompone. Por eso no hay ninguna
 * prueba de "cantidad × factor" ni de "tasa = media": si algún día aparece
 * una, es la señal de que la regla se duplicó en el front.
 *
 * Lo que sí se fija es la regla de producto del §8 (regla 11): nada sale del
 * presupuesto ni se pisa sin que el usuario lo decida, así que lo pendiente se
 * pinta como alerta —no como éxito— y con las tres cifras a la vista.
 */

import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import type { ReporteGeneracionRespuesta } from '@/api/generado/modelo';
import { ReporteGeneracion } from '@/ensambles/ReporteGeneracion';
import {
  RENGLON_VACIO,
  etiquetaEstadoRenglon,
  etiquetaOrigen,
  explicacionEstado,
  factorValido,
  peticionRenglon,
  puedeConsultarEnsambles,
  puedeEscribirEnsambles,
  renglonCompleto,
  tasaPublicada,
  tonoEstadoRenglon,
} from '@/ensambles/reglas';

describe('roles (§11.2)', () => {
  it('leer es de Control de obra y Super intendente', () => {
    expect(puedeConsultarEnsambles('control_obra')).toBe(true);
    expect(puedeConsultarEnsambles('super_intendente')).toBe(true);
    expect(puedeConsultarEnsambles('residente')).toBe(false);
    expect(puedeConsultarEnsambles('supervisor')).toBe(false);
  });

  it('crear y generar son solo de Control de obra', () => {
    expect(puedeEscribirEnsambles('control_obra')).toBe(true);
    expect(puedeEscribirEnsambles('super_intendente')).toBe(false);
    expect(puedeEscribirEnsambles('residente')).toBe(false);
  });
});

describe('estado de un renglón al generar (skill §6, §8 regla 11)', () => {
  it('solo nuevo y actualizado se pintan como éxito', () => {
    expect(tonoEstadoRenglon('nuevo')).toBe('ok');
    expect(tonoEstadoRenglon('actualizado')).toBe('ok');
  });

  it('lo que no se escribió solo se pinta como alerta, nunca como éxito', () => {
    expect(tonoEstadoRenglon('desvinculado')).toBe('danger');
    expect(tonoEstadoRenglon('conflicto')).toBe('danger');
    // «sobra» es lo menos grave: la partida sigue ahí, solo ya no es receta.
    expect(tonoEstadoRenglon('sobra')).toBe('warn');
  });

  it('cada estado pendiente explica qué pasó y que no se tocó', () => {
    for (const estado of ['desvinculado', 'conflicto', 'sobra']) {
      expect(explicacionEstado(estado)).not.toBe('');
    }
    expect(explicacionEstado('nuevo')).toBe('');
    expect(explicacionEstado('sobra')).toMatch(/nada se borra solo/i);
  });

  it('las etiquetas hablan el idioma del usuario, no el del enum', () => {
    expect(etiquetaEstadoRenglon('desvinculado')).toBe('Editado a mano');
    expect(etiquetaEstadoRenglon('conflicto')).toBe('Ya existía capturado');
    expect(etiquetaEstadoRenglon('inventado')).toBe('inventado');
  });
});

describe('origen de la cantidad (skill §2)', () => {
  it('nombra las tres procedencias', () => {
    expect(etiquetaOrigen('heredada_concepto')).toBe('Heredada del concepto');
    expect(etiquetaOrigen('heredada_destajo')).toBe('Heredada de un destajo');
    expect(etiquetaOrigen('manual')).toBe('Manual');
  });
});

describe('tasa y dispersión viajan juntas (skill §5.7, regla 9)', () => {
  it('con las dos es dato publicado', () => {
    expect(tasaPublicada('1101.000000', '6.0300')).toBe(true);
  });

  it('con una sola no se presenta como dato firme', () => {
    expect(tasaPublicada('1101.000000', null)).toBe(false);
    expect(tasaPublicada(null, '6.0300')).toBe(false);
    expect(tasaPublicada(undefined, undefined)).toBe(false);
  });
});

describe('formulario de Extracción', () => {
  it('el factor es un número mayor que cero', () => {
    expect(factorValido('2')).toBe(true);
    expect(factorValido('0.5')).toBe(true);
    expect(factorValido('0')).toBe(false);
    expect(factorValido('-1')).toBe(false);
    expect(factorValido('')).toBe(false);
    expect(factorValido('abc')).toBe(false);
  });

  it('un renglón pide clave y cantidad positiva', () => {
    expect(renglonCompleto(RENGLON_VACIO)).toBe(false);
    expect(renglonCompleto({ ...RENGLON_VACIO, clave: 'EST-MURO', cantidad: '4' })).toBe(true);
    expect(renglonCompleto({ ...RENGLON_VACIO, clave: 'EST-MURO', cantidad: '0' })).toBe(false);
    expect(renglonCompleto({ ...RENGLON_VACIO, clave: '  ', cantidad: '4' })).toBe(false);
  });

  it('manda concepto o sub-ensamble, nunca los dos', () => {
    const concepto = peticionRenglon(
      { tipo: 'concepto', clave: ' EST-MURO ', cantidad: '4', origen: 'manual' },
      1,
    );
    expect(concepto.clave_concepto).toBe('EST-MURO');
    expect(concepto.clave_sub_ensamble).toBeNull();

    const sub = peticionRenglon(
      { tipo: 'sub_ensamble', clave: 'RECAMARA-A', cantidad: '2', origen: 'manual' },
      2,
    );
    expect(sub.clave_concepto).toBeNull();
    expect(sub.clave_sub_ensamble).toBe('RECAMARA-A');
    expect(sub.orden).toBe(2);
  });
});

function reporte(parcial: Partial<ReporteGeneracionRespuesta> = {}): ReporteGeneracionRespuesta {
  return {
    prototipo_nodo_id: 'n1',
    nuevos: [],
    actualizados: [],
    pendientes: [],
    ...parcial,
  };
}

describe('ReporteGeneracion', () => {
  it('sin pendientes lo dice y no pinta ninguna tarjeta de decisión', () => {
    render(<ReporteGeneracion reporte={reporte({ nuevos: ['EST-MURO'] })} />);

    expect(screen.getByText(/no hay nada por decidir/i)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /por decidir/i })).not.toBeInTheDocument();
    expect(screen.getByText('EST-MURO')).toBeInTheDocument();
  });

  it('un renglón editado a mano muestra las tres cifras', () => {
    render(
      <ReporteGeneracion
        reporte={reporte({
          pendientes: [
            {
              clave_concepto: 'EST-MURO',
              estado: 'desvinculado',
              receta: { cantidad: '8.000000', precio_unitario: '100.0000' },
              existente: {
                actual: { cantidad: '9.000000', precio_unitario: '100.0000' },
                snapshot: { cantidad: '8.000000', precio_unitario: '100.0000' },
              },
            },
          ],
        })}
      />,
    );

    const tarjeta = screen.getByText('EST-MURO').closest('.card') as HTMLElement;
    expect(within(tarjeta).getByText('Editado a mano')).toHaveClass('badge--danger');
    // Hoy (9), al generarse (8) y lo que pide el ensamble ahora (8).
    expect(within(tarjeta).getAllByText(/× \$100\.00/)).toHaveLength(3);
    expect(within(tarjeta).getByText('9.00')).toBeInTheDocument();
    expect(within(tarjeta).getAllByText('8.00')).toHaveLength(2);
    expect(screen.getByText(/alguien editó esta partida a mano/i)).toBeInTheDocument();
  });

  it('una partida capturada que nunca se generó no finge tener historial', () => {
    render(
      <ReporteGeneracion
        reporte={reporte({
          pendientes: [
            {
              clave_concepto: 'EST-PISO',
              estado: 'conflicto',
              receta: { cantidad: '1.000000', precio_unitario: '50.0000' },
              existente: { actual: { cantidad: '10.000000', precio_unitario: '50.0000' } },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText(/capturada a mano: nunca se generó/i)).toBeInTheDocument();
  });

  it('un concepto que ya no está en la receta no inventa una cifra del ensamble', () => {
    render(
      <ReporteGeneracion
        reporte={reporte({
          pendientes: [
            {
              clave_concepto: 'EST-LOSA',
              estado: 'sobra',
              existente: {
                actual: { cantidad: '1.000000', precio_unitario: '200.0000' },
                snapshot: { cantidad: '1.000000', precio_unitario: '200.0000' },
              },
            },
          ],
        })}
      />,
    );

    const tarjeta = screen.getByText('EST-LOSA').closest('.card') as HTMLElement;
    expect(within(tarjeta).getByText('Ya no está en la receta')).toHaveClass('badge--warn');
    expect(within(tarjeta).getByText('—')).toBeInTheDocument();
    expect(screen.getByText(/nada se borra solo/i)).toBeInTheDocument();
  });

  it('cuenta lo escrito y lo por decidir por separado', () => {
    render(
      <ReporteGeneracion
        reporte={reporte({
          nuevos: ['A', 'B'],
          actualizados: ['C'],
          pendientes: [{ clave_concepto: 'D', estado: 'sobra' }],
        })}
      />,
    );

    // «Por decidir» es además el título de la tarjeta de abajo: se acota a la
    // etiqueta del KPI para no leer el texto equivocado.
    const valorDe = (etiqueta: string) => {
      const kpi = within(screen.getByTestId('reporte-generacion'))
        .getAllByText(etiqueta)
        .find((el) => el.classList.contains('kpi__label'));
      return kpi?.nextElementSibling;
    };
    expect(valorDe('Nuevos')).toHaveTextContent('2');
    expect(valorDe('Actualizados')).toHaveTextContent('1');
    expect(valorDe('Por decidir')).toHaveTextContent('1');
  });
});
