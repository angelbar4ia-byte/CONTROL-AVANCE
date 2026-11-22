/**
 * La tarjeta del relleno (Fase 3 de las zonas de losa): solo se pinta lo que responde el servidor; manda el espesor, la pendiente, el recorrido, los polígonos
 * y, según el elemento, el abundamiento o el mortero; el relleno de azotea se liga a un concepto del catálogo y el compactado sale como propuesto con clave
 * provisional (sin precios): Costos propone sin poder autorizar.
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

vi.mock('@/api/generado/rellenos/rellenos', () => ({
  useDefinicionDelRellenoApiV1BibliotecaDeElementosRellenoClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularElRellenoApiV1BibliotecaDeElementosRellenoClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDelRellenoApiV1BibliotecaDeElementosRellenoClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerConceptoDelRellenoApiV1BibliotecaDeElementosRellenoClavePropuestasConceptoPost: () => ({ mutateAsync: m.proponer, isPending: false }),
}));
vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({ data: m.biblioteca.current }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaRelleno } from '@/cuantificador/elementos/TarjetaRelleno';

const PENDIENTES = [{ clave: 'R1', texto: 'El material del usuario no define cómo se mide el relleno.' }];
const DEFECTOS_AZOTEA = { espesor_m: 0.09, pendiente_pct: 0, recorrido_m: 0, compensar_espesores: true, abundamiento_pct: 0, mortero_m3_por_m2: 0.0735, pendiente_zona_pct: 2, espesor_bajada_m: 0.05, mortero_espesor_m: 0.05, factor_abundamiento: 1 };
const AZOTEA = {
  clave: 'REL-AZOTEA', nombre: 'Relleno de azotea', tipo: 'azotea', se_mide_por: 'm² de relleno de una zona del plano',
  categoria: { clave: 'rellenos', nombre: 'Rellenos' }, subcategoria: { clave: 'azotea', nombre: 'Rellenos de azotea' },
  concepto: { clave: 'ALB-03014', descripcion: 'Relleno en azotea mezcla antihumedad-arena-arenilla 2:4:10', unidad: 'm²', estado: 'catalogo', provisional: false },
  parametros_por_defecto: DEFECTOS_AZOTEA,
  tezontle: { clave: 'PET-00069', descripcion: 'TEZONTLE ROJO 7 MTS', unidad: 'SERV', m3_por_viaje: 7, por_m2: 0.012857, fuente: 'ANALISIS_DE_BASICOS_CONCEPTOS:255' },
  mortero: { clave: 'CON-00020', descripcion: 'Mortero fc 50', unidad: 'm³', por_m2: 0.0735, fuente: 'ANALISIS_DE_BASICOS_CONCEPTOS:256' },
  destajos_candidatos: [{ clave: 'MOA-05012', descripcion: 'MO ELEVACION TEZONTLE Y RELLENO FLUIDO', unidad: 'm²' }],
  pendientes: PENDIENTES,
};
const COMPACTADO = {
  ...AZOTEA, clave: 'REL-COMPACTADO', nombre: 'Relleno compactado', tipo: 'compactado', se_mide_por: 'm³ de relleno de una zona del plano',
  subcategoria: { clave: 'compactado', nombre: 'Rellenos compactados' },
  concepto: { clave: 'EJ-810', descripcion: 'Relleno compactado por m³', unidad: 'm³', estado: 'propuesto', provisional: true },
  parametros_por_defecto: { ...DEFECTOS_AZOTEA, espesor_m: 0.1, mortero_m3_por_m2: 0 }, tezontle: null, mortero: null, destajos_candidatos: [],
};

const CALCULO = {
  clave: 'REL-AZOTEA', nombre: 'Relleno de azotea', tipo: 'azotea', parametros: DEFECTOS_AZOTEA, espesor_de_la_zona_m: 0.12, espesor_maximo_de_la_zona_m: 0.12,
  area_m2: 100, volumen_m3: 9, volumen_suelto_m3: null, espesor_medio_m: 0.09, extra_de_pendiente_m: 0,
  poligonos: [{ id: '1', area_m2: 100, espesor_de_losa_m: 0.12, subzona: false, compensacion_m: 0, espesor_m: 0.09, volumen_m3: 9, espacio_id: null }],
  insumos: [
    { parte: 'tezontle', clave: 'PET-00069', descripcion: 'TEZONTLE ROJO 7 MTS', unidad: 'SERV', cantidad: 1.2857, origen: 'zona', nota: '9.000 m³ de relleno entre 7 m³ por viaje' },
    { parte: 'mortero', clave: 'CON-00020', descripcion: 'Mortero fc 50', unidad: 'm3', cantidad: 7.35, origen: 'catalogo', nota: 'Por m² de la composición del catálogo (editable)' },
  ],
  conceptos: [
    {
      parte: 'relleno', elemento_clave: 'REL-AZOTEA', ref: null, toma: ['tezontle', 'mortero'], cantidad: 100, unidad: 'm²', nota: 'Concepto existente.', propuesta: null,
      concepto: AZOTEA.concepto,
    },
  ],
  por_espacio: [],
  mano_de_obra: { estado: 'sin_mano_de_obra', nota: 'Sin mano de obra con importe ni precios.', destajos_candidatos: [] },
  advertencias: [], pendientes: PENDIENTES,
};

const PROPUESTA = {
  id: 'p1', elemento_clave: 'REL-COMPACTADO', concepto_clave: 'EJ-810', clase: 'concepto_nuevo', estado: 'pendiente', version: null, resumen: 'Concepto nuevo EJ-810',
  motivos: [], cambios: [], propuso_rol: 'costos', propuso_nombre: 'Costos', propuesto_en: '2026-11-20T00:00:00Z', destajo_por_definir: null,
};

beforeEach(() => {
  for (const f of [m.calcular, m.proponer, m.autorizar, m.rechazar]) f.mockReset();
  m.calcular.mockResolvedValue(CALCULO);
  m.proponer.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.autorizar.mockResolvedValue({ version: 1 });
  m.rechazar.mockResolvedValue(undefined);
  m.definicion.current = AZOTEA;
  m.propuestas.current = [];
  m.biblioteca.current = [
    {
      clave: 'rellenos', nombre: 'Rellenos', prefijo: 'REL',
      subcategorias: [{ clave: 'azotea', nombre: 'Rellenos de azotea', prefijo: 'REL', elementos: [{ clave: 'REL-AZOTEA', nombre: 'Relleno de azotea', tipo: 'relleno', se_mide_por: 'm²', concepto: AZOTEA.concepto }] }],
    },
  ];
});

describe('TarjetaRelleno', () => {
  it('calcula con el espesor de la zona y los polígonos, y pinta lo que responde el servidor; la azotea usa un concepto del catálogo', async () => {
    render(<TarjetaRelleno clave="REL-AZOTEA" rol="costos" />);
    await waitFor(() =>
      expect(m.calcular).toHaveBeenCalledWith({
        clave: 'REL-AZOTEA',
        data: { espesor_de_la_zona_m: 0.12, poligonos: [{ area_m2: 100 }], compensar_espesores: true },
      }),
    );
    expect(await screen.findByTestId('relleno-area')).toHaveTextContent('Área 100.00 m² en 1 polígono');
    expect(screen.getByTestId('relleno-volumen')).toHaveTextContent('9.000 m³');
    expect(screen.getByTestId('relleno-volumen')).toHaveTextContent('9.0 cm');
    const conceptos = screen.getByRole('region', { name: 'Concepto del relleno' });
    const fila = conceptos.querySelector('[data-concepto="ALB-03014"]') as HTMLElement;
    expect(fila).toHaveAttribute('data-estado', 'catalogo');
    expect(fila).toHaveTextContent('del catálogo');
    const insumos = screen.getByRole('region', { name: 'Insumos del relleno' });
    expect(insumos.querySelector('[data-insumo="PET-00069"]')).toHaveTextContent('1.2857');
    expect(screen.getByTestId('relleno-sin-mano-de-obra')).toHaveTextContent('Sin mano de obra con importe');
    // La azotea no propone nada: lo que toma del catálogo se muestra sin botón de proponer.
    const toma = screen.getByRole('region', { name: 'Qué toma del catálogo' });
    expect(toma).toHaveTextContent('ya existe en el catálogo');
    expect(within(toma).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Pendientes por confirmar' })).toHaveTextContent('R1');
  });

  it('manda los parámetros que se teclean, la compensación y los polígonos con su espesor propio; lo vacío vale el de omisión', async () => {
    render(<TarjetaRelleno clave="REL-AZOTEA" rol="costos" />);
    await screen.findByTestId('relleno-area');
    fireEvent.change(screen.getByLabelText('Espesor mínimo del relleno en metros'), { target: { value: '0.1' } });
    fireEvent.change(screen.getByLabelText('Pendiente del relleno en por ciento'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Recorrido de la pendiente en metros'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Mortero en metros cúbicos por metro cuadrado'), { target: { value: '0.05' } });
    fireEvent.click(screen.getByLabelText('Compensar espesores de losa'));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar un polígono' }));
    fireEvent.change(screen.getByLabelText('Área del polígono 2 en metros cuadrados'), { target: { value: '8' } });
    fireEvent.change(screen.getByLabelText('Espesor propio de la losa del polígono 2 en metros'), { target: { value: '0.2' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({
        clave: 'REL-AZOTEA',
        data: {
          espesor_de_la_zona_m: 0.12, poligonos: [{ area_m2: 100 }, { area_m2: 8, espesor_de_losa_m: 0.2 }], compensar_espesores: false,
          espesor_m: 0.1, pendiente_pct: 2, recorrido_m: 5, mortero_m3_por_m2: 0.05,
        },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el polígono 2' }));
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'REL-AZOTEA', data: expect.objectContaining({ poligonos: [{ area_m2: 100 }] }) }));
  });

  it('un dato que no vale no se manda y un error del servidor se muestra', async () => {
    render(<TarjetaRelleno clave="REL-AZOTEA" rol="costos" />);
    await screen.findByTestId('relleno-area');
    const llamadas = m.calcular.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Área del polígono 1 en metros cuadrados'), { target: { value: 'abc' } });
    fireEvent.change(screen.getByLabelText('Pendiente del relleno en por ciento'), { target: { value: '-3' } });
    await new Promise((r) => setTimeout(r, 350));
    expect(m.calcular.mock.calls.length).toBe(llamadas);
    m.calcular.mockRejectedValue(new Error('El espesor no vale.'));
    fireEvent.change(screen.getByLabelText('Área del polígono 1 en metros cuadrados'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Pendiente del relleno en por ciento'), { target: { value: '' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('El espesor no vale.');
  });

  it('el compactado pide el factor de abundamiento (no el mortero), muestra el volumen suelto y su concepto es propuesto con clave provisional', async () => {
    m.definicion.current = COMPACTADO;
    m.calcular.mockResolvedValue({
      ...CALCULO, clave: 'REL-COMPACTADO', tipo: 'compactado', volumen_m3: 5, volumen_suelto_m3: 6.25, insumos: [],
      conceptos: [{ ...CALCULO.conceptos[0], elemento_clave: 'REL-COMPACTADO', toma: ['volumen'], cantidad: 5, unidad: 'm³', concepto: COMPACTADO.concepto }],
    });
    render(<TarjetaRelleno clave="REL-COMPACTADO" rol="costos" />);
    expect(screen.queryByLabelText('Mortero en metros cúbicos por metro cuadrado')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Factor de abundamiento'), { target: { value: '1.25' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'REL-COMPACTADO', data: expect.objectContaining({ factor_abundamiento: 1.25 }) }));
    expect(await screen.findByTestId('relleno-suelto')).toHaveTextContent('6.250 m³');
    const fila = screen.getByRole('region', { name: 'Concepto del relleno' }).querySelector('[data-concepto="EJ-810"]') as HTMLElement;
    expect(fila).toHaveAttribute('data-estado', 'propuesto');
    expect(fila).toHaveTextContent('propuesto · clave provisional');
    expect(screen.queryByRole('region', { name: 'Insumos del relleno' })).not.toBeInTheDocument();
  });

  it('Costos propone el concepto del compactado y no autoriza; Control de obra autoriza la pendiente', async () => {
    m.definicion.current = COMPACTADO;
    const { unmount } = render(<TarjetaRelleno clave="REL-COMPACTADO" rol="costos" />);
    const bloque = await screen.findByRole('region', { name: 'Concepto nuevo del relleno' });
    expect(bloque.querySelector('[data-concepto-propuesto="EJ-810"]')).toHaveAttribute('data-estado-propuesta', 'sin_proponer');
    fireEvent.click(within(bloque).getByRole('button', { name: 'Proponer el concepto del relleno' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ clave: 'REL-COMPACTADO' }));
    unmount();
    m.propuestas.current = [PROPUESTA];
    const costos = render(<TarjetaRelleno clave="REL-COMPACTADO" rol="costos" />);
    const b1 = await screen.findByRole('region', { name: 'Concepto nuevo del relleno' });
    expect(within(b1).getByText('Pendiente')).toBeInTheDocument();
    expect(within(b1).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    costos.unmount();
    render(<TarjetaRelleno clave="REL-COMPACTADO" rol="control_obra" />);
    const b2 = await screen.findByRole('region', { name: 'Concepto nuevo del relleno' });
    fireEvent.click(within(b2).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
  });

  it('la pantalla de elementos muestra la tarjeta del relleno para una clave de relleno', async () => {
    render(<PantallaDeElementos clave="REL-AZOTEA" rol="costos" />);
    expect(await screen.findByRole('article', { name: /REL-AZOTEA/ })).toBeInTheDocument();
  });
});
