/**
 * La tarjeta de la escalera (Fase 4a): solo se pinta lo que responde el servidor; mandan las cotas, los peldaños, la huella o el recorrido, el ancho, el espesor, las
 * rampas y el descanso. El escalón se liga a un concepto del catálogo y el descanso sale como propuesto con clave provisional (sin precios): Costos propone sin
 * poder autorizar.
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

vi.mock('@/api/generado/escaleras/escaleras', () => ({
  useDefinicionDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularLaEscaleraApiV1BibliotecaDeElementosEscaleraClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerConceptoDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClavePropuestasConceptoPost: () => ({ mutateAsync: m.proponer, isPending: false }),
}));
vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({ data: m.biblioteca.current }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaEscalera } from '@/cuantificador/elementos/TarjetaEscalera';

const PARAMETROS = { peldanos: null, contrahuella_max_m: 0.18, huella_m: 0.25, ancho_m: 1.2, espesor_m: 0.12, rampas: 1, largo_descanso_m: null };
const ESCALON = { clave: 'EST-01510', descripcion: 'Escalera forjada de una rampa de concreto armado', unidad: 'pza', estado: 'catalogo', provisional: false };
const DESCANSO = { clave: 'EJ-820', descripcion: 'Descanso de escalera forjada', unidad: 'm²', estado: 'propuesto', provisional: true };
const FICHA = {
  clave: 'ESC-FORJADA', nombre: 'Escalera forjada', se_mide_por: 'escalones de 1.20 m según el desnivel', categoria: { clave: 'escaleras', nombre: 'Escaleras' },
  subcategoria: { clave: 'forjadas', nombre: 'Escaleras forjadas' }, concepto: ESCALON, concepto_del_descanso: DESCANSO, largo_base_del_escalon_m: 1.2,
  parametros_por_defecto: PARAMETROS,
  composicion_del_escalon: [{ clave: 'CON-00004', descripcion: 'CONCRETO', unidad: 'm³', por_escalon: 0.060583, fuente: 'x:800' }],
  parrilla_por_m2: [{ clave: 'ACR-00001', descripcion: 'VARILLA 3/8', unidad: 'pza', por_m2: 0.9, fuente: 'y:139' }],
  destajos_candidatos: [{ clave: 'MOE-02311', descripcion: 'MO ARMADO Y COLADO ESCALERA', unidad: 'pza' }],
  pendientes: [{ clave: 'E1', texto: 'EST-01510 se cobra por pza: se toma el escalón de 1.20 m.' }],
};
const GEOMETRIA = {
  peldanos: 18, origen_de_peldanos: 'desnivel', contrahuella_m: 0.1733, huella_m: 0.25, origen_de_huella: 'tecleada', longitud_inclinada_m: 0.304, recorrido_horizontal_m: 4.25,
  rampas: [{ numero: 1, peldanos: 18, recorrido_m: 4.25, altura_m: 3.12 }], descansos: 0, largo_del_descanso_m: 1.2, area_de_descanso_m2: 0, superficie_de_rampa_m2: 6.57,
  volumen_de_rampa_m3: 0.788, volumen_de_descanso_m3: 0, escalones_de_catalogo: 18,
};
const CALCULO = {
  clave: 'ESC-FORJADA', nombre: 'Escalera forjada', parametros: PARAMETROS, cotas: { arranque_m: 0, llegada_m: 3.12, desnivel_m: 3.12 }, geometria: GEOMETRIA,
  insumos: [{ parte: 'rampa', clave: 'CON-00004', descripcion: 'CONCRETO', unidad: 'm³', cantidad: 0.788, origen: 'geometria', nota: '6.570 m² × 12 cm' }],
  conceptos: [{ parte: 'escalon', elemento_clave: 'ESC-FORJADA', ref: null, concepto: ESCALON, toma: ['peldaños', 'ancho'], cantidad: 18, unidad: 'pza', nota: 'EST-01510 por escalón.', propuesta: null }],
  por_espacio: [], mano_de_obra: { estado: 'sin_mano_de_obra', nota: 'Sin mano de obra con importe ni precios.', destajos_candidatos: [] }, advertencias: [], pendientes: [],
};
const PROPUESTA = {
  id: 'p1', elemento_clave: 'ESC-FORJADA', concepto_clave: 'EJ-820', clase: 'concepto_nuevo', estado: 'pendiente', version: null, resumen: 'Concepto nuevo EJ-820', motivos: [], cambios: [],
  propuso_rol: 'costos', propuso_nombre: 'Costos', propuesto_en: '2026-11-21T00:00:00Z', destajo_por_definir: null,
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
      clave: 'escaleras', nombre: 'Escaleras', prefijo: 'ESC',
      subcategorias: [{ clave: 'forjadas', nombre: 'Escaleras forjadas', prefijo: 'ESC', elementos: [{ clave: 'ESC-FORJADA', nombre: 'Escalera forjada', tipo: 'escalera', se_mide_por: 'm', concepto: ESCALON }] }],
    },
  ];
});

describe('TarjetaEscalera', () => {
  it('calcula con las cotas por omisión y pinta lo que responde el servidor; el escalón usa un concepto del catálogo', async () => {
    render(<TarjetaEscalera clave="ESC-FORJADA" rol="costos" />);
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'ESC-FORJADA', data: { cota_arranque_m: 0, cota_llegada_m: 3.12 } }));
    expect(await screen.findByTestId('escalera-desnivel')).toHaveTextContent('Desnivel 3.120 m');
    expect(screen.getByTestId('escalera-peldanos')).toHaveTextContent('18 peldaños (del desnivel) · contrahuella 17.3 cm · huella 25.0 cm');
    expect(screen.getByTestId('escalera-rampas')).toHaveTextContent('1 rampa: 18 peldaños');
    expect(screen.getByTestId('escalera-concreto')).toHaveTextContent('0.788 m³');
    const fila = screen.getByRole('region', { name: 'Conceptos de la escalera' }).querySelector('[data-concepto="EST-01510"]') as HTMLElement;
    expect(fila).toHaveAttribute('data-estado', 'catalogo');
    expect(fila).toHaveTextContent('del catálogo');
    expect(screen.getByRole('region', { name: 'Insumos de la escalera' }).querySelector('[data-insumo="CON-00004"]')).toHaveTextContent('0.7880');
    expect(screen.getByTestId('escalera-sin-mano-de-obra')).toHaveTextContent('Sin mano de obra con importe');
    expect(screen.getByRole('region', { name: 'Qué toma del catálogo' })).toHaveTextContent('ya existe en el catálogo');
    expect(screen.getByRole('region', { name: 'Pendientes por confirmar' })).toHaveTextContent('E1');
  });

  it('manda las cotas y los parámetros que se teclean; lo vacío vale el de omisión', async () => {
    render(<TarjetaEscalera clave="ESC-FORJADA" rol="costos" />);
    await screen.findByTestId('escalera-desnivel');
    fireEvent.change(screen.getByLabelText('Cota de arranque en metros'), { target: { value: '3.12' } });
    fireEvent.change(screen.getByLabelText('Cota de llegada en metros'), { target: { value: '4.20' } });
    fireEvent.change(screen.getByLabelText('Número de peldaños'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Contrahuella máxima en metros'), { target: { value: '0.17' } });
    fireEvent.change(screen.getByLabelText('Huella en metros'), { target: { value: '0.28' } });
    fireEvent.change(screen.getByLabelText('Recorrido de las rampas en metros'), { target: { value: '1.4' } });
    fireEvent.change(screen.getByLabelText('Ancho de la escalera en metros'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText('Espesor de la rampa en metros'), { target: { value: '0.15' } });
    fireEvent.change(screen.getByLabelText('Número de rampas'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Largo del descanso en metros'), { target: { value: '1.5' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({
        clave: 'ESC-FORJADA',
        data: {
          cota_arranque_m: 3.12, cota_llegada_m: 4.2, peldanos: 6, contrahuella_max_m: 0.17, huella_m: 0.28, recorrido_m: 1.4, ancho_m: 1.5, espesor_m: 0.15, rampas: 2,
          largo_descanso_m: 1.5,
        },
      }),
    );
  });

  it('un dato que no vale no se manda y un error del servidor se muestra', async () => {
    render(<TarjetaEscalera clave="ESC-FORJADA" rol="costos" />);
    await screen.findByTestId('escalera-desnivel');
    const llamadas = m.calcular.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Cota de llegada en metros'), { target: { value: 'arriba' } });
    fireEvent.change(screen.getByLabelText('Ancho de la escalera en metros'), { target: { value: '-3' } });
    await new Promise((r) => setTimeout(r, 350));
    expect(m.calcular.mock.calls.length).toBe(llamadas);
    m.calcular.mockRejectedValue(new Error('La cota de llegada debe estar por encima de la de arranque: la escalera sube.'));
    fireEvent.change(screen.getByLabelText('Cota de llegada en metros'), { target: { value: '-1' } });
    fireEvent.change(screen.getByLabelText('Ancho de la escalera en metros'), { target: { value: '' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('la escalera sube');
  });

  it('con dos rampas muestra el descanso y su concepto propuesto con clave provisional', async () => {
    m.calcular.mockResolvedValue({
      ...CALCULO,
      geometria: { ...GEOMETRIA, descansos: 1, area_de_descanso_m2: 1.44, volumen_de_descanso_m3: 0.173, rampas: [{ numero: 1, peldanos: 9, recorrido_m: 2, altura_m: 1.56 }, { numero: 2, peldanos: 9, recorrido_m: 2, altura_m: 1.56 }] },
      insumos: [...CALCULO.insumos, { parte: 'descanso', clave: 'MAD-00001', descripcion: 'CIMBRA 3 MTS', unidad: 'm²', cantidad: 1.44, origen: 'catalogo', nota: '1 m² por m²' }],
      conceptos: [...CALCULO.conceptos, { parte: 'descanso', elemento_clave: 'ESC-FORJADA', ref: null, concepto: DESCANSO, toma: ['área'], cantidad: 1.44, unidad: 'm²', nota: 'Por m².', propuesta: null }],
    });
    render(<TarjetaEscalera clave="ESC-FORJADA" rol="costos" />);
    fireEvent.change(screen.getByLabelText('Número de rampas'), { target: { value: '2' } });
    expect(await screen.findByText(/1 descanso de 1.44 m²/)).toBeInTheDocument();
    const fila = screen.getByRole('region', { name: 'Conceptos de la escalera' }).querySelector('[data-concepto="EJ-820"]') as HTMLElement;
    expect(fila).toHaveAttribute('data-estado', 'propuesto');
    expect(fila).toHaveTextContent('propuesto · clave provisional');
    expect(screen.getByRole('region', { name: 'Insumos de la escalera' }).querySelector('[data-parte="descanso"][data-insumo="MAD-00001"]')).toBeInTheDocument();
  });

  it('Costos propone el concepto del descanso y no autoriza; Control de obra autoriza la pendiente', async () => {
    const { unmount } = render(<TarjetaEscalera clave="ESC-FORJADA" rol="costos" />);
    const bloque = await screen.findByRole('region', { name: 'Concepto nuevo del descanso' });
    expect(bloque.querySelector('[data-concepto-propuesto="EJ-820"]')).toHaveAttribute('data-estado-propuesta', 'sin_proponer');
    fireEvent.click(within(bloque).getByRole('button', { name: 'Proponer el concepto del descanso' }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ clave: 'ESC-FORJADA' }));
    unmount();
    m.propuestas.current = [PROPUESTA];
    const costos = render(<TarjetaEscalera clave="ESC-FORJADA" rol="costos" />);
    const b1 = await screen.findByRole('region', { name: 'Concepto nuevo del descanso' });
    expect(within(b1).getByText('Pendiente')).toBeInTheDocument();
    expect(within(b1).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    costos.unmount();
    render(<TarjetaEscalera clave="ESC-FORJADA" rol="control_obra" />);
    const b2 = await screen.findByRole('region', { name: 'Concepto nuevo del descanso' });
    fireEvent.click(within(b2).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
  });

  it('la pantalla de elementos muestra la tarjeta de la escalera para una clave de escalera', async () => {
    render(<PantallaDeElementos clave="ESC-FORJADA" rol="costos" />);
    expect(await screen.findByRole('article', { name: /ESC-FORJADA/ })).toBeInTheDocument();
  });
});
