/**
 * La tarjeta de los castillos, aparentes y columnas forjadas (Ola 3, lane 3A). No calcula nada: se pinta lo que responde el
 * servidor. Costos propone y solo Control de obra autoriza; lo que el catálogo trae mal se muestra como versión propuesta.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  rol: { current: 'control_obra' as string },
  definicion: { current: undefined as unknown },
  calculo: { current: undefined as unknown },
  conciliacion: { current: undefined as unknown },
  propuestas: { current: [] as unknown[] },
  calcular: vi.fn(),
  proponer: vi.fn(),
  porAltura: vi.fn(),
  autorizar: vi.fn(),
  rechazar: vi.fn(),
}));

vi.mock('@/app/sesion', () => ({ useSesion: () => ({ sesion: { rol: m.rol.current } }) }));
vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useDefinicionDeEstructuraApiV1BibliotecaDeElementosEstructuraClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularEstructuraApiV1BibliotecaDeElementosEstructuraClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  useConciliacionDeEstructuraApiV1BibliotecaDeElementosEstructuraClaveConciliacionGet: () => ({
    data: m.conciliacion.current,
    isLoading: false,
    isError: false,
  }),
  usePropuestasDeEstructuraApiV1BibliotecaDeElementosEstructuraClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerCorreccionesApiV1BibliotecaDeElementosEstructuraClavePropuestasCorreccionesPost: () => ({ mutateAsync: m.proponer, isPending: false }),
  useProponerConceptoPorAlturaApiV1BibliotecaDeElementosEstructuraClavePropuestasConceptoPorAlturaPost: () => ({
    mutateAsync: m.porAltura,
    isPending: false,
  }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));

import { TarjetaEstructura } from '@/cuantificador/elementos/TarjetaEstructura';

const DEFINICION_K7 = {
  clave: 'EST-02170',
  alias: 'K-7',
  nombre: 'Castillo K-7 de 15 × 20 con armex 10×15',
  tipo: 'castillo',
  categoria: { clave: 'castillos', nombre: 'Castillos' },
  subcategoria: { clave: 'muro', nombre: 'Castillos de muro' },
  seccion: { ancho_cm: 15, largo_cm: 20, peralte_cm: null },
  posicion: null,
  alto_fijo_m: null,
  alto_por_defecto_m: 3,
  armado: { tipo: 'armex', armex: 'ACE-00020', varillas: [], anillo: null, alambre_kg_ml: 0.0165 },
  conceptos: [],
  pendientes: ['El catálogo no trae escalón de acero para alturas mayores a la del último: el elemento repite el último y avisa (Q80).'],
  fuente: 'EST-02170 y EST-10070, 10071, 10072',
};

const CALCULO_K7 = {
  clave: 'EST-02170',
  alias: 'K-7',
  nombre: DEFINICION_K7.nombre,
  tipo: 'castillo',
  categoria: 'castillos',
  subcategoria: 'muro',
  posicion: null,
  seccion: DEFINICION_K7.seccion,
  alto_m: 3,
  alto_fijo: false,
  unidad_de_calculo: 'pza',
  lados_cimbra: 2,
  armado: DEFINICION_K7.armado,
  acero: {
    forma: 'castillo',
    unidad: 'pza',
    longitud_m: 3,
    cantidad: 1,
    armex: { clave: 'ACE-00020', largo_pieza_m: 6, ml: 4, piezas_comerciales: 0.6667, kg: null, traslape_m: 0.15, puntas_m: 0.5, corte: { piezas: 1, modulo_m: 4, total_m: 4, alto_que_cubre_m: 3.5, necesario_m: 3.5, traslape_m: 0.15, puntas_m: 0.5, sobrante_m: 0, excede_maximo: false, cubre_completo: true } },
    varillas: [],
    anillos: null,
    alambre: { kg: 0.0495, kg_por_ml: 0.0165 },
    cimbra: { m2: 1.2, lados: 2, consumos: [] },
    acero_kg: 0,
    acero_kg_completo: false,
    desperdicio: { sobrante_de_corte_m: 0, traslape_m: 0, puntas_m: 0.5, desperdicio_acero_pct: 0 },
    totales: [],
    drivers: {},
    advertencias: [],
  },
  colado: { concreto_m3_ml: 0.0315, consumos: [] },
  forro: null,
  conceptos: [
    { ranura: 'acero', unidad: 'pza', clave: 'EST-10070', hasta_m: 4, escalones: [{ clave: 'EST-10072', hasta_m: 2 }, { clave: 'EST-10070', hasta_m: 4 }, { clave: 'EST-10071', hasta_m: 6 }], nuevo: false, rebasa: false, insumos: { 'ACE-00020': 0.6667 } },
    { ranura: 'colado', unidad: 'm', clave: 'EST-02170', hasta_m: null, escalones: [], nuevo: false, rebasa: false, insumos: { 'MEZ-01020': 0.0315 } },
  ],
  concepto_nuevo_por_altura: null,
  solo_en_catalogo: [{ clave: 'MEZ-07010', motivo: 'Mortero 1:4: el catálogo no dice para qué es (Q82).' }],
  pendientes: DEFINICION_K7.pendientes,
  advertencias: [],
  fuente: DEFINICION_K7.fuente,
};

const CONCILIACION = {
  elemento_clave: 'EST-02170',
  umbral_igual_pct: 3,
  umbral_aproximado_pct: 8,
  conceptos: [
    {
      concepto_clave: 'EST-10071',
      ranura: 'acero',
      unidad: 'pza',
      alto_m: 3,
      hasta_m: 6,
      nuevo: false,
      sin_catalogo: false,
      en_catalogo: true,
      propuestas: [{ id: 'p1', estado: 'pendiente', version: null, resumen: 'Nueva versión de EST-10071', clase: 'version_de_concepto' }],
      filas: [
        { clave: 'ACE-00020', descripcion: 'Armex 10x15', unidad: 'pza', catalogo: 0.833333, elemento: 1.3333, diferencia: 0.5, diferencia_pct: 60, marca: '≠', motivo: null, propuesta: { valor: 1.3333, estado: 'pendiente', propuesta_id: 'p1', marca: '≠', diferencia_pct: 0 } },
        { clave: 'MEZ-07010', descripcion: 'MEZCLA CEMENTO-ARENA 1:4', unidad: 'm3', catalogo: 0.0021, elemento: null, diferencia: null, diferencia_pct: null, marca: 'solo_catalogo', motivo: 'Mortero 1:4: el catálogo no dice para qué es (Q82).', propuesta: null },
      ],
      mano_de_obra: [{ clave: 'MOE-02027', descripcion: 'MO CASTILLOS K7', unidad: 'm', cantidad: 1, costo: 140 }],
      resumen: {},
      coincide: false,
    },
  ],
};

const PROPUESTA = {
  id: 'p1', elemento_clave: 'EST-02170', concepto_clave: 'EST-10071', clase: 'version_de_concepto', estado: 'pendiente', version: null,
  resumen: 'Nueva versión de EST-10071: ACE-00020 0.833333 → 1.333333', cambios: [{ insumo: 'ACE-00020', unidad: 'pza', antes: 0.833333, despues: 1.333333 }],
  motivos: ['Q79'], destajo_por_definir: null, propuso_nombre: 'Ana de Costos', propuso_rol: 'costos', propuesto_en: '2026-11-15T10:00:00Z',
  decidio_nombre: null, decidio_rol: null, decidido_en: null, motivo: null,
};

beforeEach(() => {
  for (const f of [m.calcular, m.proponer, m.porAltura, m.autorizar, m.rechazar]) f.mockReset();
  m.rol.current = 'control_obra';
  m.definicion.current = DEFINICION_K7;
  m.calculo.current = CALCULO_K7;
  m.conciliacion.current = CONCILIACION;
  m.propuestas.current = [PROPUESTA];
  m.calcular.mockImplementation(() => Promise.resolve(m.calculo.current));
});

describe('TarjetaEstructura', () => {
  it('con una obra manda su obra_id y, con el alto sin tocar, el alto sale del driver de la obra', async () => {
    m.calculo.current = { ...CALCULO_K7, alto_m: 3.5, drivers_usados: [{ clave: 'altura_estandar', nombre: 'Altura estándar del muro', unidad: 'm', valor: 3.5, fuente: 'obra' }] };
    render(<TarjetaEstructura clave="EST-02170" obraId="obra-1" />);
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'EST-02170', data: { obra_id: 'obra-1' } }));
    const fila = await screen.findByText('Altura estándar del muro');
    expect(fila.closest('[data-driver-usado]')).toHaveAttribute('data-fuente', 'obra');
    await waitFor(() => expect(screen.getByLabelText(/Alto/)).toHaveValue('3.50'));
  });

  it('pinta la ficha, el cálculo del servidor con su escalón y lo que solo trae el catálogo', async () => {
    render(<TarjetaEstructura clave="EST-02170" />);
    expect(screen.getByRole('article', { name: /EST-02170/ })).toHaveTextContent('K-7');
    expect(screen.getByTestId('estructura-seccion')).toHaveTextContent('15 × 20 (ancho del muro × largo)');
    expect(screen.getByTestId('estructura-armado')).toHaveTextContent('Armex ACE-00020');
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'EST-02170', data: {} }));  // el alto sin tocar no se manda: lo da la altura estándar de la obra o el alto fijo
    const concepto = await screen.findByText('EST-10070');
    expect(concepto.closest('[data-concepto]')).toHaveTextContent('hasta 4.00 m');
    expect(screen.getByTestId('estructura-cimbra')).toHaveTextContent('2 lados');
    expect(screen.getByRole('list', { name: 'Solo en el catálogo' })).toHaveTextContent('MEZ-07010');
    expect(screen.getByText('Q80', { exact: false })).toBeInTheDocument();
  });

  it('manda el alto que se teclea y no calcula por su cuenta', async () => {
    render(<TarjetaEstructura clave="EST-02170" />);
    await screen.findByText('EST-10070');
    fireEvent.change(screen.getByLabelText('Alto en metros'), { target: { value: '5.5' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'EST-02170', data: { alto_m: 5.5 } }));
  });

  it('la conciliación pone el catálogo vigente junto a la versión propuesta y al elemento', () => {
    render(<TarjetaEstructura clave="EST-02170" />);
    const fila = document.querySelector('[data-conciliacion="EST-10071"] [data-insumo="ACE-00020"]') as HTMLElement;
    expect(within(fila).getByText('0.8333')).toBeInTheDocument();
    expect(fila).toHaveTextContent('1.3333 (pendiente)');
    expect(fila).toHaveTextContent('1.3333');
    expect(fila).toHaveTextContent('≠');
    const sola = document.querySelector('[data-conciliacion="EST-10071"] [data-insumo="MEZ-07010"]') as HTMLElement;
    expect(sola).toHaveTextContent('solo en el catálogo');
    expect(screen.getByText(/MOE-02027/)).toBeInTheDocument();
  });

  it('Control de obra autoriza y rechaza la propuesta; Costos solo la ve', async () => {
    m.autorizar.mockResolvedValue({ version: 2 });
    const { unmount } = render(<TarjetaEstructura clave="EST-02170" />);
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
    expect(await screen.findByTestId('estructura-aviso')).toHaveTextContent('versión 2');
    expect(screen.getByRole('button', { name: 'Rechazar' })).toBeInTheDocument();
    unmount();

    m.rol.current = 'costos';
    render(<TarjetaEstructura clave="EST-02170" />);
    expect(screen.queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Proponer las correcciones del catálogo' })).toBeInTheDocument();
  });

  it('el residente no propone ni autoriza', () => {
    m.rol.current = 'residente';
    render(<TarjetaEstructura clave="EST-02170" />);
    expect(screen.queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Proponer las correcciones del catálogo' })).not.toBeInTheDocument();
  });

  it('proponer las correcciones avisa cuántas quedaron propuestas', async () => {
    m.rol.current = 'costos';
    m.proponer.mockResolvedValue({ creadas: ['a', 'b'], omitidas: [] });
    render(<TarjetaEstructura clave="EST-02170" />);
    fireEvent.click(screen.getByRole('button', { name: 'Proponer las correcciones del catálogo' }));
    expect(await screen.findByTestId('estructura-aviso')).toHaveTextContent('2 correcciones propuestas');
  });

  it('una forjada con otra altura ofrece proponer el concepto nuevo y no inventa precio', async () => {
    m.rol.current = 'costos';
    m.definicion.current = { ...DEFINICION_K7, clave: 'EST-07010', alias: 'CM-1', alto_fijo_m: 4.2, alto_por_defecto_m: 4.2 };
    m.calculo.current = {
      ...CALCULO_K7,
      clave: 'EST-07010',
      alto_m: 3.8,
      alto_fijo: true,
      lados_cimbra: 1,
      forro: { caras: [], pza_netas: 144.4, tabique_pza: 161.7, mezcla_neta_m3: 0.1, mezcla_m3: 0.1055, cimbra_m2: 1.386, lados_cimbra: 1 },
      concepto_nuevo_por_altura: { clave_propuesta: 'EST-07010-H380', descripcion: 'x', unidad: 'pza', alto_m: 3.8 },
    };
    m.porAltura.mockResolvedValue({ id: 'n1' });
    render(<TarjetaEstructura clave="EST-07010" />);
    const bloque = await screen.findByTestId('estructura-concepto-nuevo');
    expect(bloque).toHaveTextContent('EST-07010-H380');
    expect(bloque).toHaveTextContent('sin precio ni destajo');
    expect(screen.getByTestId('estructura-tabique')).toHaveTextContent('161.7 pza de tabique');
    fireEvent.click(within(bloque).getByRole('button', { name: 'Proponer el concepto nuevo' }));
    await waitFor(() => expect(m.porAltura).toHaveBeenCalledWith({ clave: 'EST-07010', data: { alto_m: 3.8 } }));
  });
});
