/**
 * La tarjeta del bastón (Ola 4, 4D): solo se pinta lo que responde el servidor; los parámetros se mandan tal cual, el corte ajustado
 * y el exacto salen lado a lado, el escalón que falta se avisa y Costos propone sin poder autorizar.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calcular: vi.fn(),
  proponerNuevo: vi.fn(),
  proponerApu: vi.fn(),
  autorizar: vi.fn(),
  rechazar: vi.fn(),
  rol: { current: 'costos' as string },
  definicion: { current: undefined as unknown },
  propuestas: { current: [] as unknown[] },
  biblioteca: { current: undefined as unknown },
}));

vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({ data: m.biblioteca.current }),
  useDefinicionDelBastonApiV1BibliotecaDeElementosBastonClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularElBastonApiV1BibliotecaDeElementosBastonClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDelBastonApiV1BibliotecaDeElementosBastonClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerConceptoNuevoApiV1BibliotecaDeElementosBastonClavePropuestasConceptoNuevoPost: () => ({ mutateAsync: m.proponerNuevo }),
  useProponerActualizacionDeApuApiV1BibliotecaDeElementosBastonClavePropuestasActualizarApuPost: () => ({ mutateAsync: m.proponerApu }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));
vi.mock('@/app/sesion', () => ({ useSesion: () => ({ sesion: { rol: m.rol.current } }) }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaBaston } from '@/cuantificador/elementos/TarjetaBaston';

const DEFINICION = {
  clave: 'BA-1',
  nombre: 'Bastón de varilla',
  tipo: 'baston',
  se_mide_por: 'metro lineal de trazo',
  categoria: { clave: 'aceros', nombre: 'Acero de refuerzo' },
  subcategoria: { clave: 'bastones', nombre: 'Bastones' },
  parametros_por_defecto: { varilla_numero: 3, sep_cm: 25, largo_cm: 120, puntas_cm: 0, traslape_diametros: 40, trazo_m: 1 },
  varillas: [
    { numero: 3, clave: 'ACR-00001', nombre: '3/8', peso_kg_m: 0.56 },
    { numero: 4, clave: 'ACR-00002', nombre: '1/2', peso_kg_m: 0.994 },
  ],
  modulos_de_corte_m: [1, 1.5, 2, 3, 4, 6],
  escalones: [],
  fuente: 'x',
  pendientes: [
    { clave: 'Q28', texto: 'Corte exacto o ajustado.' },
    { clave: 'Q27', texto: 'Escalones más largos.' },
  ],
};

const CALCULO = {
  clave: 'BA-1',
  nombre: 'Bastón de varilla de 3/8" a cada 25 cm',
  unidad: 'ml de trazo',
  trazo_m: 10,
  varilla: { clave: 'ACR-00001', numero: 3, nombre: '3/8', peso_kg_m: 0.56, largo_m: 12 },
  parametros: { sep_cm: 25, largo_cm: 120, puntas_cm: 0, traslape_diametros: 40 },
  bastones_por_metro: 4,
  ajustado: {
    corte: { piezas_por_baston: 1, modulo_m: 1.5, material_por_baston_m: 1.5, traslape_m: 0, puntas_m: 0, necesario_m: 1.2, sobrante_por_baston_m: 0.3, piezas_por_varilla: 8, excede_maximo: false },
    bastones: 41,
    varillas: 6,
    material_m: 61.5,
    kg: 34.44,
    sobra_m: 10.5,
  },
  exacto: { bastones: 41, varillas: 5, material_m: 49.2, kg: 27.55, sobra_m: 10.8 },
  varillas_por_metro: 0.5,
  pago: { modo: 'pieza', unidad: 'pza', cantidad: 41, texto: 'Pago por pieza' },
  concepto: { clave: 'AUX-02010', descripcion: 'Bastones var 3/8" de 1.20 @25 cm', unidad: 'ml', estado: 'catalogo', clave_provisional: false, escalon: 'exacto', largo_m: 1.2, sep_cm: 25 },
  escalon: 'exacto',
  conciliacion: [
    {
      concepto: { clave: 'AUX-02010', descripcion: 'Bastones var 3/8" de 1.20 @25 cm', unidad: 'ml' },
      sobre: 'por metro de trazo',
      filas: [
        { clave: 'ACR-00001', descripcion: 'VARILLA 3/8', unidad: 'pza', catalogo: 0.432, elemento: 0.5, diferencia: 0.157, diferencia_pct: 15.7, marca: '≠' },
        { clave: 'ACE-00001', descripcion: 'ALAMBRE RECOCIDO', unidad: 'kg', catalogo: 0.164724, elemento: null, diferencia: null, diferencia_pct: null, marca: 'solo_catalogo' },
      ],
      mano_de_obra: [],
      resumen: { '=': 0, '≈': 0, '≠': 1, solo_catalogo: 1, solo_elemento: 0 },
      coincide: false,
      fuente_de_las_filas: [],
      avisos: ['El bastón no calcula el alambre recocido de amarre.'],
    },
  ],
  avisos: ['Con el corte ajustado a módulos salen 6 varillas.'],
};

const SIN_ESCALON = {
  ...CALCULO,
  concepto: { ...CALCULO.concepto, clave: 'AUX-B3-135-30', estado: 'propuesto', clave_provisional: true, escalon: 'sin_escalon' },
  escalon: 'sin_escalon',
  conciliacion: [],
};

const PROPUESTA = {
  id: 'p1',
  elemento_clave: 'BA-1',
  concepto_clave: 'AUX-02010',
  clase: 'version_de_concepto',
  estado: 'pendiente',
  version: null,
  resumen: 'Nueva versión de AUX-02010: ACR-00001 0.432 → 0.5',
  cambios: [{ insumo: 'ACR-00001', unidad: 'pza', antes: 0.432, despues: 0.5 }],
  motivos: [],
  destajo_por_definir: null,
  propuso_nombre: 'Ana',
  propuso_rol: 'costos',
  propuesto_en: '2026-11-16T00:00:00Z',
  decidio_nombre: null,
  decidio_rol: null,
  decidido_en: null,
  motivo: null,
};

const PETICION = { trazo_m: 1, varilla_numero: 3, sep_cm: 25, largo_cm: 120, puntas_cm: 0, traslape_diametros: 40 };

beforeEach(() => {
  for (const f of [m.calcular, m.proponerNuevo, m.proponerApu, m.autorizar, m.rechazar]) f.mockReset();
  m.calcular.mockResolvedValue(CALCULO);
  m.proponerNuevo.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.proponerApu.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.autorizar.mockResolvedValue({ version: 2 });
  m.rol.current = 'costos';
  m.definicion.current = DEFINICION;
  m.propuestas.current = [];
});

describe('TarjetaBaston', () => {
  it('manda los parámetros al servidor y pinta bastones, corte, varillas, kg y el concepto del escalón', async () => {
    render(<TarjetaBaston clave="BA-1" />);
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'BA-1', data: PETICION }));
    expect(await screen.findByTestId('baston-piezas')).toHaveTextContent('41 bastones');
    expect(screen.getByTestId('baston-corte')).toHaveTextContent('1 × 1.5 m · 8 por varilla');
    expect(screen.getByTestId('baston-varillas')).toHaveTextContent('6 varillas');
    expect(screen.getByTestId('baston-kg')).toHaveTextContent('34.44 kg');
    expect(screen.getByTestId('baston-varilla')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'AUX-02010');
    expect(screen.getByTestId('baston-escalon')).toHaveTextContent('Escalón exacto del catálogo');
    fireEvent.change(screen.getByLabelText('Largo del bastón en centímetros'), { target: { value: '135' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'BA-1', data: { ...PETICION, largo_cm: 135 } }));
  });

  it('muestra el corte ajustado y el exacto lado a lado', async () => {
    render(<TarjetaBaston clave="BA-1" />);
    const tabla = await screen.findByTestId('baston-comparacion');
    expect(within(tabla).getByText('Ajustado a módulos').closest('tr')).toHaveTextContent('6');
    expect(tabla.querySelector('tr[data-corte="exacto"]')).toHaveTextContent('27.55');
  });

  it('la conciliación marca ≠ y solo en el catálogo, sin precios', async () => {
    render(<TarjetaBaston clave="BA-1" />);
    const bloque = (await screen.findByRole('region', { name: 'Conciliación con el catálogo' })).querySelector('[data-conciliacion="AUX-02010"]') as HTMLElement;
    expect(within(bloque).getAllByRole('row').map((f) => f.getAttribute('data-marca'))).toEqual([null, '≠', 'solo_catalogo']);
    expect(within(bloque).getByText('+15.7 %')).toBeInTheDocument();
    expect(bloque.textContent).not.toMatch(/\$/);
  });

  it('sin escalón avisa y Costos propone el concepto nuevo con los parámetros', async () => {
    m.calcular.mockResolvedValue(SIN_ESCALON);
    render(<TarjetaBaston clave="BA-1" />);
    expect(await screen.findByTestId('baston-concepto')).toHaveTextContent('AUX-B3-135-30 · provisional');
    expect(screen.getByTestId('baston-sin-escalon')).toHaveTextContent('Falta el escalón en el catálogo');
    expect(screen.getByTestId('baston-sin-catalogo')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Proponer el concepto nuevo' }));
    await waitFor(() => expect(m.proponerNuevo).toHaveBeenCalledWith({ clave: 'BA-1', data: PETICION }));
    expect(await screen.findByTestId('baston-aviso')).toHaveTextContent('propuesto como concepto nuevo');
  });

  it('Costos propone la actualización del APU y la versión propuesta aparece en la conciliación', async () => {
    m.propuestas.current = [PROPUESTA];
    render(<TarjetaBaston clave="BA-1" />);
    await screen.findByTestId('baston-piezas');
    fireEvent.click(within(screen.getByRole('region', { name: 'Versiones propuestas' })).getByRole('button', { name: /Confirmar cálculo/ }));
    await waitFor(() => expect(m.proponerApu).toHaveBeenCalledWith({ clave: 'BA-1', data: PETICION }));
    expect(screen.getByRole('region', { name: 'Conciliación con el catálogo' }).querySelector('tr[data-insumo="ACR-00001"]')).toHaveTextContent('0.5000');
  });

  it('Control de obra autoriza la propuesta pendiente', async () => {
    m.rol.current = 'control_obra';
    m.propuestas.current = [PROPUESTA];
    render(<TarjetaBaston clave="BA-1" />);
    const region = await screen.findByRole('region', { name: 'Versiones propuestas' });
    fireEvent.click(within(region).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
  });

  it('trae las preguntas pendientes y un cálculo rechazado se muestra como error', async () => {
    m.calcular.mockRejectedValue(new Error('El largo del bastón va de 10 a 3000 cm.'));
    render(<TarjetaBaston clave="BA-1" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('El largo del bastón');
    expect(screen.getByTestId('baston-pendientes').querySelector('[data-pendiente="Q28"]')).toBeInTheDocument();
  });
});

describe('PantallaDeElementos', () => {
  it('abre la tarjeta del bastón de un elemento de la biblioteca según su tipo', async () => {
    m.biblioteca.current = [
      {
        clave: 'aceros',
        nombre: 'Acero de refuerzo',
        prefijo: 'BA',
        subcategorias: [{ clave: 'bastones', nombre: 'Bastones', prefijo: 'BA', elementos: [{ clave: 'BA-1', nombre: 'x', tipo: 'baston', se_mide_por: 'ml', concepto: { clave: 'AUX-02xxx', descripcion: 'x', unidad: 'ml' } }] }],
      },
    ];
    render(<PantallaDeElementos clave="BA-1" rol="costos" />);
    expect(await screen.findByRole('article', { name: /BA-1/ })).toBeInTheDocument();
  });
});
