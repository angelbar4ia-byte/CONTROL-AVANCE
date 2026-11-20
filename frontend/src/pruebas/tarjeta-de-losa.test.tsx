/**
 * La tarjeta de la losa (fase 2 de las zonas de losa): solo se pinta lo que responde el servidor; manda el espesor, el uso, las áreas y los
 * elementos con su pago; los conceptos nuevos salen como propuestos con clave provisional (sin precios) y Costos propone sin poder autorizar.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calcular: vi.fn(),
  proponer: vi.fn(),
  autorizar: vi.fn(),
  rechazar: vi.fn(),
  definicion: { current: undefined as unknown },
  propuestas: { current: [] as unknown[] },
  biblioteca: { current: undefined as unknown },
}));

vi.mock('@/api/generado/losas/losas', () => ({
  useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularLaLosaApiV1BibliotecaDeElementosLosaClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDeLaLosaApiV1BibliotecaDeElementosLosaClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerConceptoDeLaLosaApiV1BibliotecaDeElementosLosaClavePropuestasConceptoPost: () => ({ mutateAsync: m.proponer, isPending: false }),
}));
vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({ data: m.biblioteca.current }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaLosa } from '@/cuantificador/elementos/TarjetaLosa';

const FICHA = {
  clave: 'LOSA-MACIZA',
  nombre: 'Losa maciza',
  tipo: 'maciza',
  se_mide_por: 'm² de losa de una zona del plano',
  categoria: { clave: 'losas', nombre: 'Losas' },
  subcategoria: { clave: 'maciza', nombre: 'Losas macizas' },
  concepto: { clave: 'EJ-800', descripcion: 'Losa maciza de concreto armado por m²', unidad: 'm²', estado: 'propuesto', provisional: true },
  usos: ['entrepiso', 'azotea'],
  concreto_por_uso: [
    { uso: 'entrepiso', clave: 'CON-00003', descripcion: 'CONCRETO BOMBEADO 250 (LOSAS ENTREPISO)' },
    { uso: 'azotea', clave: 'CON-00004', descripcion: 'CONCRETO BOMBEADO 250 (LOSAS AZOTEA Y ROOF)' },
  ],
  cimbra: { clave: 'MAD-00001', descripcion: 'CIMBRA 3 MTS', por_m2_de_losa: 1 },
  espesor_por_defecto_m: 0.12,
  capa_de_compresion_cm: null,
  parrilla: { clave: 'AUX-06010', descripcion: 'Acero para losa varilla del no. 3 @20 cm.', unidad: 'm²', cantidad: null, insumos: [] },
  elementos_permitidos: [
    { clave: 'T-1-15x25', tiene_concepto_de_colado: true },
    { clave: 'N-1-12x25', tiene_concepto_de_colado: true },
  ],
  destajos_candidatos: [{ clave: 'MOE-02213', descripcion: 'MO ARMADO DE LOSA MACIZA', unidad: 'm²' }],
  pagos: ['en_la_losa', 'propio'],
  pendientes: [{ clave: 'Q49', texto: 'Matriz dentro de matriz: valor conservador.' }],
};

const CALCULO = {
  clave: 'LOSA-MACIZA',
  nombre: 'Losa maciza',
  tipo: 'maciza',
  uso: 'entrepiso',
  espesor_m: 0.12,
  capa_de_compresion_cm: null,
  area_m2: 100,
  losas: [{ id: '1', area_m2: 100, espesor_m: 0.12, subzona: false, concreto_m3: 12 }],
  concreto: { clave: 'CON-00003', descripcion: 'CONCRETO BOMBEADO 250', geometrico_m3: 12, con_desperdicio_m3: 12.6, desperdicio_pct: 5 },
  cimbra: { clave: 'MAD-00001', descripcion: 'CIMBRA 3 MTS', m2: 100 },
  parrilla: { clave: 'AUX-06010', descripcion: 'Acero', unidad: 'm²', cantidad: 100, insumos: [{ clave: 'ACR-00001', descripcion: 'VARILLA 3/8', unidad: 'pza', por_m2: 0.9, total: 90, fuente: 'x' }] },
  elementos: [],
  totales: {
    area_m2: 100, longitud_de_elementos_ml: 0, concreto_m3: 12.6, concreto_de_la_losa_m3: 12.6, concreto_de_los_elementos_m3: 0, concreto_pagado_por_la_losa_m3: 12.6,
    concreto_pagado_por_elementos_m3: 0, cimbra_m2: 100, cimbra_pagada_por_la_losa_m2: 100, cimbra_pagada_por_elementos_m2: 0, acero_de_elementos_kg: 0, solape_con_la_losa_m3: 0,
  },
  insumos: [
    { parte: 'concreto', clave: 'CON-00003', descripcion: 'CONCRETO', unidad: 'm³', cantidad: 12.6, origen: 'zona', paga: 'losa' },
    { parte: 'cimbra', clave: 'MAD-00001', descripcion: 'CIMBRA 3 MTS', unidad: 'm²', cantidad: 100, origen: 'zona', paga: 'losa' },
  ],
  conceptos: [
    {
      parte: 'losa', elemento_clave: 'LOSA-MACIZA', ref: null, toma: ['concreto', 'cimbra', 'acero'], cantidad: 100, unidad: 'm²', nota: 'x', propuesta: null,
      concepto: { clave: 'EJ-800', descripcion: 'Losa maciza de concreto armado por m²', unidad: 'm²', estado: 'propuesto', provisional: true },
    },
  ],
  mano_de_obra: { estado: 'sin_mano_de_obra', nota: 'El elemento no calcula mano de obra ni elige un destajo de losa. Sin precios.', destajos_candidatos: [] },
  advertencias: ['La sección de las trabes se mide completa.'],
  pendientes: [],
  drivers_usados: [{ clave: 'desperdicio_concreto', nombre: 'Desperdicio de concreto', unidad: '%', valor: 5, fuente: 'defecto' }],
};

const PROPUESTA = {
  id: 'p1', elemento_clave: 'LOSA-MACIZA', concepto_clave: 'EJ-800', clase: 'concepto_nuevo', estado: 'pendiente', version: null, resumen: 'Concepto nuevo EJ-800',
  cambios: [], motivos: [], destajo_por_definir: null, propuso_nombre: 'Ana', propuso_rol: 'costos', propuesto_en: '2026-11-20T00:00:00Z',
  decidio_nombre: null, decidio_rol: null, decidido_en: null, motivo: null,
};

beforeEach(() => {
  for (const f of [m.calcular, m.proponer, m.autorizar, m.rechazar]) f.mockReset();
  m.calcular.mockResolvedValue(CALCULO);
  m.proponer.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.autorizar.mockResolvedValue({ version: 1 });
  m.rechazar.mockResolvedValue(undefined);
  m.definicion.current = FICHA;
  m.propuestas.current = [];
  m.biblioteca.current = [
    {
      clave: 'losas', nombre: 'Losas', prefijo: 'L',
      subcategorias: [{ clave: 'maciza', nombre: 'Losas macizas', prefijo: 'L', elementos: [{ clave: 'LOSA-MACIZA', nombre: 'Losa maciza', tipo: 'losa_de_concreto', se_mide_por: 'm²', concepto: FICHA.concepto }] }],
    },
  ];
});

describe('TarjetaLosa', () => {
  it('calcula con el espesor, el uso y las áreas, y pinta lo que responde el servidor', async () => {
    render(<TarjetaLosa clave="LOSA-MACIZA" rol="costos" />);
    await waitFor(() =>
      expect(m.calcular).toHaveBeenCalledWith({
        clave: 'LOSA-MACIZA',
        data: { espesor_m: 0.12, uso: 'entrepiso', losas: [{ area_m2: 100 }], elementos: [] },
      }),
    );
    expect(await screen.findByTestId('losa-area')).toHaveTextContent('Área 100.00 m² en 1 polígono');
    expect(screen.getByTestId('losa-concreto')).toHaveTextContent('12.600 m³');
    expect(screen.getByTestId('losa-cimbra')).toHaveTextContent('100.00 m²');
    expect(screen.getByTestId('losa-parrilla')).toHaveTextContent('AUX-06010');
    expect(screen.getByTestId('losa-sin-mano-de-obra')).toHaveTextContent('Sin precios');
    const conceptos = screen.getByRole('region', { name: 'Conceptos de la matriz' });
    const fila = conceptos.querySelector('[data-concepto="EJ-800"]') as HTMLElement;
    expect(fila).toHaveAttribute('data-estado', 'propuesto');
    expect(fila).toHaveTextContent('propuesto · clave provisional');
    expect(screen.getByRole('region', { name: 'Drivers que usa este cálculo' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Pendientes por confirmar' })).toHaveTextContent('Q49');
  });

  it('manda los elementos con su modo, su largo y su pago; el pago propio y el cambio de uso viajan al servidor', async () => {
    render(<TarjetaLosa clave="LOSA-MACIZA" rol="costos" obraId="obra-1" />);
    await screen.findByTestId('losa-area');
    fireEvent.click(screen.getByRole('button', { name: 'Agregar un elemento' }));
    fireEvent.change(screen.getByLabelText('Se mide por del elemento 1'), { target: { value: 'pieza' } });
    fireEvent.change(screen.getByLabelText('Largo de la pieza del elemento 1'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Cantidad del elemento 1'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Pago del elemento 1'), { target: { value: 'propio' } });
    fireEvent.change(screen.getByLabelText('Uso de la losa'), { target: { value: 'azotea' } });
    fireEvent.change(screen.getByLabelText('Áreas de los polígonos de losa en metros cuadrados'), { target: { value: '40, 12.5' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({
        clave: 'LOSA-MACIZA',
        data: {
          espesor_m: 0.12, uso: 'azotea', obra_id: 'obra-1', losas: [{ area_m2: 40 }, { area_m2: 12.5 }],
          elementos: [{ clave: 'T-1-15x25', modo: 'pieza', cantidad: 3, largo_m: 6, pago: 'propio' }],
        },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el elemento 1' }));
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'LOSA-MACIZA', data: expect.objectContaining({ elementos: [] }) }));
  });

  it('un dato que no vale no se manda y un error del servidor se muestra', async () => {
    render(<TarjetaLosa clave="LOSA-MACIZA" rol="costos" />);
    await screen.findByTestId('losa-area');
    const llamadas = m.calcular.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Áreas de los polígonos de losa en metros cuadrados'), { target: { value: 'abc' } });
    await new Promise((r) => setTimeout(r, 350));
    expect(m.calcular.mock.calls.length).toBe(llamadas);
    m.calcular.mockRejectedValue(new Error('El espesor de la losa no vale.'));
    fireEvent.change(screen.getByLabelText('Áreas de los polígonos de losa en metros cuadrados'), { target: { value: '10' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('El espesor de la losa no vale.');
  });

  it('Costos propone el concepto de la losa y no autoriza; Control de obra autoriza la pendiente', async () => {
    const { unmount } = render(<TarjetaLosa clave="LOSA-MACIZA" rol="costos" />);
    const bloque = await screen.findByRole('region', { name: 'Concepto nuevo de la losa' });
    expect(bloque.querySelector('[data-concepto-propuesto="EJ-800"]')).toHaveAttribute('data-estado-propuesta', 'sin_proponer');
    fireEvent.click(within(bloque).getByRole('button', { name: 'Proponer el concepto de la losa' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ clave: 'LOSA-MACIZA' }));
    unmount();
    m.propuestas.current = [PROPUESTA];
    const costos = render(<TarjetaLosa clave="LOSA-MACIZA" rol="costos" />);
    const b1 = await screen.findByRole('region', { name: 'Concepto nuevo de la losa' });
    expect(within(b1).getByText('Pendiente')).toBeInTheDocument();
    expect(within(b1).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    costos.unmount();
    render(<TarjetaLosa clave="LOSA-MACIZA" rol="control_obra" />);
    const b2 = await screen.findByRole('region', { name: 'Concepto nuevo de la losa' });
    fireEvent.click(within(b2).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
  });

  it('la nervada pide la capa de compresión y la manda', async () => {
    m.definicion.current = { ...FICHA, clave: 'LOSA-NERVADA', nombre: 'Losa nervada', tipo: 'nervada', espesor_por_defecto_m: 0.2, capa_de_compresion_cm: 5, parrilla: null };
    render(<TarjetaLosa clave="LOSA-NERVADA" rol="costos" />);
    await waitFor(() =>
      expect(m.calcular).toHaveBeenCalledWith({
        clave: 'LOSA-NERVADA',
        data: { espesor_m: 0.2, uso: 'entrepiso', capa_de_compresion_cm: 5, losas: [{ area_m2: 100 }], elementos: [] },
      }),
    );
    fireEvent.change(screen.getByLabelText('Capa de compresión en centímetros'), { target: { value: '6' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'LOSA-NERVADA', data: expect.objectContaining({ capa_de_compresion_cm: 6 }) }));
  });

  it('la pantalla de elementos muestra la tarjeta de la losa para una clave de losa', async () => {
    render(<PantallaDeElementos clave="LOSA-MACIZA" rol="costos" />);
    expect(await screen.findByRole('article', { name: /LOSA-MACIZA/ })).toBeInTheDocument();
  });
});
