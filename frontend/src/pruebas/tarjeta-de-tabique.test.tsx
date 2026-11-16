/**
 * La tarjeta de los muros de tabique, aparejos y piso de petatillo (Ola 3, 3C): solo se pinta lo que responde el servidor; el nivel y
 * los parámetros se mandan tal cual, las claves nuevas salen «provisionales» y Costos propone sin poder autorizar.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calcular: vi.fn(),
  proponerNuevo: vi.fn(),
  proponerApu: vi.fn(),
  proponerCorrecciones: vi.fn(),
  autorizar: vi.fn(),
  rechazar: vi.fn(),
  rol: { current: 'costos' as string },
  definicion: { current: undefined as unknown },
  propuestas: { current: [] as unknown[] },
  tabla: { current: [] as unknown[] },
  biblioteca: { current: undefined as unknown },
}));

vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({ data: m.biblioteca.current }),
  useDefinicionDelTabiqueApiV1BibliotecaDeElementosTabiqueClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularTabiqueApiV1BibliotecaDeElementosTabiqueClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDeTabiqueApiV1BibliotecaDeElementosTabiqueClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useTablaDeRevisionDeTabiqueApiV1BibliotecaDeElementosTabiqueTablaDeRevisionGet: () => ({ data: m.tabla.current }),
  useProponerConceptoNuevoApiV1BibliotecaDeElementosTabiqueClavePropuestasConceptoNuevoPost: () => ({ mutateAsync: m.proponerNuevo }),
  useProponerActualizacionDeApuApiV1BibliotecaDeElementosTabiqueClavePropuestasActualizarApuPost: () => ({ mutateAsync: m.proponerApu }),
  useProponerCorreccionesDeTabiqueApiV1BibliotecaDeElementosTabiqueClavePropuestasCorreccionesPost: () => ({ mutateAsync: m.proponerCorrecciones }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));
vi.mock('@/app/sesion', () => ({ useSesion: () => ({ sesion: { rol: m.rol.current } }) }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaMuroTabique } from '@/cuantificador/elementos/TarjetaMuroTabique';

const PARAMETROS = {
  junta_cm: 2,
  junta_entre_hileras_cm: null,
  desperdicio_de_pieza_pct: 12,
  desperdicio_de_mezcla_pct: 5,
  cama_cm: null,
  tipo_de_sardinel: null,
  nivel_desde_3er_nivel: 3,
};

const DEFINICION = {
  clave: 'EST-02010',
  nombre: 'Muro de tabique 14 cm, a hilo',
  nombre_nominal: 'Muro de 14 cm a hilo (soga)',
  tipo: 'tabique',
  medida: 'm2',
  se_mide_por: 'm²',
  categoria: { clave: 'muros', nombre: 'Muros' },
  subcategoria: { clave: 'tabique', nombre: 'Muros de tabique' },
  espesor_nominal_cm: 14,
  espesor_real_cm: 14,
  aparejo: 'a soga (al hilo)',
  aparejo_largo: 'A soga',
  aparejo_texto: 'colocada a soga.',
  planta_nota: 'Planta de dos hiladas.',
  pieza: { insumo: 'PET-00001', ancho_cm: 14, alto_cm: 6, largo_cm: 26 },
  mezcla: 'MEZ-07010',
  parametros_por_defecto: PARAMETROS,
  tipos_de_sardinel: [],
  hiladas: [{ peso: 1, filas: ['soga'] }],
  conceptos: [
    { clave: 'EST-02010', etiqueta: 'Niveles 1 y 2', descripcion: 'Muro de 14 cm', unidad: 'm2', estado: 'catalogo', clave_provisional: false, en_catalogo: true, destajo: { clave: 'MOE-02010', descripcion: 'MO', unidad: 'm2' }, nivel_desde: null },
    { clave: 'EST-02011', etiqueta: 'Nivel 3 en adelante', descripcion: 'Muro de 14 cm 3er nivel', unidad: 'm2', estado: 'catalogo', clave_provisional: false, en_catalogo: true, destajo: { clave: 'MOE-02012', descripcion: 'MO', unidad: 'm2' }, nivel_desde: 3 },
  ],
  fuente: 'x',
  avisos_de_catalogo: [],
  pendientes: [{ clave: 'Q99', texto: 'Las claves nuevas son provisionales.' }],
};

const CALCULO = {
  clave: 'EST-02010',
  nombre: DEFINICION.nombre,
  medida: 'm2',
  unidad: 'm²',
  cantidad: 1,
  nivel: 1,
  concepto: { clave: 'EST-02010', descripcion: 'Muro de 14 cm', unidad: 'm2', etiqueta: 'Niveles 1 y 2', estado: 'catalogo', clave_provisional: false, nivel_desde: null },
  pieza: { insumo: 'PET-00001', ancho_cm: 14, alto_cm: 6, largo_cm: 26 },
  parametros: PARAMETROS,
  geometria: {
    espesor_real_cm: 14,
    espesor_minimo_cm: 14,
    espesor_medio_cm: 14,
    hilada_promedio_cm: 8,
    piezas_por_hilada: 3.57,
    hiladas: [{ peso: 1, espesor_cm: 14, filas: [{ orientacion: 'soga', etiqueta: 'a soga', visible_cm: 26, alto_cm: 6, espesor_cm: 14, piezas_netas_m2: 44.64 }] }],
  },
  piezas: { netas_por_unidad: 44.64, por_unidad: 50, total: 50, a_comprar: 50 },
  mezcla: { neta_por_unidad: 0.0425, por_unidad: 0.044625, total_m3: 0.044625 },
  insumos: [
    { parte: 'tabique', clave: 'PET-00001', descripcion: 'TABIQUE', unidad: 'pza', por_unidad: 50, total: 50, a_comprar: 50 },
    { parte: 'mezcla', clave: 'MEZ-07010', descripcion: 'MEZCLA CEMENTO-ARENA 1:4', unidad: 'm3', por_unidad: 0.044625, total: 0.044625, a_comprar: null },
  ],
  mezcla_compuesta: [{ clave: 'ADH-00005', descripcion: 'CEMENTO SACO DE 50 KG', unidad: 'bts', por_m3: 7.28, total: 0.32, linea: 'x' }],
  mano_de_obra: { estado: 'destajo_del_catalogo', destajo: { clave: 'MOE-02010', descripcion: 'MO', unidad: 'm2' }, cantidad: 1, nota: 'El destajo es el del catálogo.' },
  herramienta: [],
  conciliacion: [
    {
      concepto: { clave: 'EST-02010', descripcion: 'Muro de 14 cm', unidad: 'm2' },
      sobre: 'por m² de muro',
      filas: [
        { clave: 'PET-00001', descripcion: 'TABIQUE', unidad: 'pza', catalogo: 86, elemento: 75, diferencia: -11, diferencia_pct: -12.8, marca: '≠' },
        { clave: 'MEZ-07010', descripcion: 'MEZCLA', unidad: 'm3', catalogo: 0.0447, elemento: 0.0446, diferencia: 0, diferencia_pct: -0.2, marca: '=' },
      ],
      mano_de_obra: [{ clave: 'MOE-02010', descripcion: 'MO', unidad: 'm2', cantidad: 1, costo: 150 }],
      resumen: { '=': 1, '≈': 0, '≠': 1, solo_catalogo: 0, solo_elemento: 0 },
      coincide: false,
      fuente_de_las_filas: [],
      avisos: ['Aviso de mortero 1:5 contra 1:4.'],
    },
  ],
  avisos: [],
};

const NUEVO = {
  ...DEFINICION,
  clave: 'EST-02030',
  nombre: 'Muro de tabique a tizón (28 cm nominal)',
  espesor_real_cm: 26,
  conceptos: [{ ...DEFINICION.conceptos[0]!, clave: 'EST-02030', etiqueta: 'Concepto nuevo propuesto (clave provisional)', estado: 'propuesto', clave_provisional: true, en_catalogo: false, destajo: null }],
  parametros_por_defecto: { ...PARAMETROS, nivel_desde_3er_nivel: null },
};

const PROPUESTA = {
  id: 'p1',
  elemento_clave: 'EST-02010',
  concepto_clave: 'EST-02010',
  clase: 'version_de_concepto',
  estado: 'pendiente',
  version: null,
  resumen: 'Nueva versión de EST-02010: PET-00001 86 → 75',
  cambios: [{ insumo: 'PET-00001', unidad: 'pza', antes: 86, despues: 75 }],
  motivos: [],
  destajo_por_definir: null,
  propuso_nombre: 'Ana',
  propuso_rol: 'costos',
  propuesto_en: '2026-11-15T00:00:00Z',
  decidio_nombre: null,
  decidio_rol: null,
  decidido_en: null,
  motivo: null,
};

beforeEach(() => {
  for (const f of [m.calcular, m.proponerNuevo, m.proponerApu, m.proponerCorrecciones, m.autorizar, m.rechazar]) f.mockReset();
  m.calcular.mockResolvedValue(CALCULO);
  m.proponerNuevo.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.proponerApu.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.autorizar.mockResolvedValue({ version: 2 });
  m.proponerCorrecciones.mockResolvedValue({ creadas: ['p9'], omitidas: [] });
  m.rol.current = 'costos';
  m.definicion.current = DEFINICION;
  m.propuestas.current = [];
  m.tabla.current = [
    { clave: 'EST-02005', provisional: true, estado: 'propuesto', nombre_nominal: 'Muro capuchino de 7 cm', nombre: 'x', espesor_real_cm: 6, aparejo: 'capuchino', unidad: 'm²', piezas_por_unidad: 25, mezcla_m3_por_unidad: 0.0118, contraste: 'Sin concepto en el catálogo' },
  ];
});

describe('TarjetaMuroTabique', () => {
  it('manda el nivel y los parámetros al servidor y pinta piezas, mezcla, espesor y el concepto elegido', async () => {
    render(<TarjetaMuroTabique clave="EST-02010" />);
    await waitFor(() =>
      expect(m.calcular).toHaveBeenCalledWith({
        clave: 'EST-02010',
        data: { cantidad: 1, junta_cm: 2, desperdicio_de_pieza_pct: 12, desperdicio_de_mezcla_pct: 5, nivel: 1 },
      }),
    );
    expect(await screen.findByTestId('tabique-piezas')).toHaveTextContent('50.0 pza');
    expect(screen.getByTestId('tabique-mezcla')).toHaveTextContent('0.0446 m³');
    expect(screen.getByTestId('tabique-espesor')).toHaveTextContent('14.0 cm');
    expect(screen.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'EST-02010');
    expect(screen.getByTestId('tabique-planta')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Nivel del plano'), { target: { value: '3' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'EST-02010', data: expect.objectContaining({ nivel: 3 }) }));
  });

  it('la conciliación marca = y ≠, lista el aviso de catálogo y no inventa precios', async () => {
    render(<TarjetaMuroTabique clave="EST-02010" />);
    const bloque = (await screen.findByRole('region', { name: 'Conciliación con el catálogo' })).querySelector('[data-conciliacion="EST-02010"]') as HTMLElement;
    expect(within(bloque).getAllByRole('row').map((f) => f.getAttribute('data-marca'))).toEqual([null, '≠', '=']);
    expect(within(bloque).getByText('-12.8 %')).toBeInTheDocument();
    expect(within(bloque).getByTestId('tabique-aviso-catalogo')).toHaveTextContent('1:5 contra 1:4');
    expect(bloque.textContent).not.toMatch(/\$/);
  });

  it('la herramienta y equipo está vacía; la sugerencia de andamio agrega un renglón sin precio', async () => {
    render(<TarjetaMuroTabique clave="EST-02010" />);
    const seccion = await screen.findByTestId('tabique-herramienta');
    expect(seccion).toHaveTextContent('Sin herramienta ni equipo');
    fireEvent.click(within(seccion).getByRole('button', { name: 'Sugerencia: andamio' }));
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({
        clave: 'EST-02010',
        data: expect.objectContaining({ herramienta: [{ descripcion: 'ANDAMIO (renta por jornada)', unidad: 'jornal', por_unidad: 0 }] }),
      }),
    );
    expect(within(seccion).getByText(/sin precio/)).toBeInTheDocument();
  });

  it('Costos propone la actualización del APU y no puede autorizar; Control de obra autoriza', async () => {
    m.propuestas.current = [PROPUESTA];
    render(<TarjetaMuroTabique clave="EST-02010" />);
    await screen.findByTestId('tabique-piezas');
    const region = screen.getByRole('region', { name: 'Versiones propuestas' });
    expect(within(region).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    fireEvent.click(within(region).getByRole('button', { name: /Confirmar cálculo/ }));
    await waitFor(() => expect(m.proponerApu).toHaveBeenCalledWith({ clave: 'EST-02010', data: expect.objectContaining({ junta_cm: 2 }) }));
    // La versión propuesta aparece en su fila de la conciliación.
    expect(screen.getByRole('region', { name: 'Conciliación con el catálogo' }).querySelector('tr[data-insumo="PET-00001"]')).toHaveTextContent('75.0000');
  });

  it('Control de obra autoriza la propuesta pendiente', async () => {
    m.rol.current = 'control_obra';
    m.propuestas.current = [PROPUESTA];
    render(<TarjetaMuroTabique clave="EST-02010" />);
    const region = await screen.findByRole('region', { name: 'Versiones propuestas' });
    fireEvent.click(within(region).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
  });

  it('un aparejo nuevo sale provisional, sin conciliación, y se propone como concepto nuevo', async () => {
    m.definicion.current = NUEVO;
    m.calcular.mockResolvedValue({
      ...CALCULO,
      clave: 'EST-02030',
      concepto: { ...CALCULO.concepto, clave: 'EST-02030', estado: 'propuesto', clave_provisional: true },
      conciliacion: [],
      mano_de_obra: { estado: 'sin_destajo', destajo: null, cantidad: 1, nota: 'Concepto nuevo sin destajo.' },
    });
    render(<TarjetaMuroTabique clave="EST-02030" />);
    expect(await screen.findByTestId('tabique-concepto')).toHaveTextContent('EST-02030 · provisional');
    expect(await screen.findByTestId('tabique-sin-catalogo')).toBeInTheDocument();
    expect(screen.getByTestId('tabique-mano-de-obra')).toHaveTextContent('Sin mano de obra');
    expect(screen.queryByLabelText('Nivel del plano')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Proponer el concepto nuevo' }));
    await waitFor(() => expect(m.proponerNuevo).toHaveBeenCalledWith({ clave: 'EST-02030' }));
    expect(await screen.findByTestId('tabique-aviso')).toHaveTextContent('propuesto como concepto nuevo');
  });

  it('el petatillo manda la cama y el sardinel su tipo', async () => {
    m.definicion.current = { ...DEFINICION, clave: 'ACA-02090', parametros_por_defecto: { ...PARAMETROS, cama_cm: 0, nivel_desde_3er_nivel: null } };
    const { unmount } = render(<TarjetaMuroTabique clave="ACA-02090" />);
    fireEvent.change(await screen.findByLabelText('Cama de mortero en centímetros'), { target: { value: '2' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'ACA-02090', data: expect.objectContaining({ cama_cm: 2 }) }));
    unmount();
    m.definicion.current = {
      ...DEFINICION,
      clave: 'EST-02050',
      medida: 'ml',
      tipos_de_sardinel: [{ clave: 'parado', descripcion: 'Parado' }],
      parametros_por_defecto: { ...PARAMETROS, tipo_de_sardinel: 'parado', nivel_desde_3er_nivel: null },
    };
    render(<TarjetaMuroTabique clave="EST-02050" />);
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'EST-02050', data: expect.objectContaining({ tipo_de_sardinel: 'parado' }) }));
  });

  it('trae la tabla de revisión de claves con la marca provisional', async () => {
    render(<TarjetaMuroTabique clave="EST-02010" />);
    const tabla = await screen.findByTestId('tabique-revision');
    expect(within(tabla).getByText('Muro capuchino de 7 cm')).toBeInTheDocument();
    expect(within(tabla).getByText('provisional')).toBeInTheDocument();
  });

  it('un cálculo que el servidor rechaza se muestra como error', async () => {
    m.calcular.mockRejectedValue(new Error('La junta va en centímetros, entre 0 y 10.'));
    render(<TarjetaMuroTabique clave="EST-02010" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('La junta va en centímetros');
  });
});

describe('Correcciones de fábrica', () => {
  it('EST-02020 y AUX-04010 proponen su corrección; EST-02010 no tiene botón', async () => {
    m.definicion.current = { ...DEFINICION, clave: 'AUX-04010' };
    render(<TarjetaMuroTabique clave="AUX-04010" />);
    await screen.findByTestId('tabique-piezas');
    fireEvent.click(screen.getByRole('button', { name: 'Proponer la corrección del catálogo' }));
    await waitFor(() => expect(m.proponerCorrecciones).toHaveBeenCalledWith({ clave: 'AUX-04010' }));
  });

  it('el aviso del mortero sigue visible con la propuesta pendiente y se quita al autorizarse el texto', async () => {
    m.propuestas.current = [{ ...PROPUESTA, concepto_clave: 'AUX-04010', cambios: [] }];
    const { unmount } = render(<TarjetaMuroTabique clave="EST-02010" />);
    expect(await screen.findByTestId('tabique-aviso-catalogo')).toHaveTextContent('1:5');
    expect(screen.getByTestId('tabique-texto-pendiente')).toBeInTheDocument();
    unmount();
    m.propuestas.current = [{ ...PROPUESTA, concepto_clave: 'AUX-04010', cambios: [], estado: 'autorizada', version: 2 }];
    render(<TarjetaMuroTabique clave="EST-02010" />);
    await screen.findByTestId('tabique-piezas');
    expect(screen.queryByTestId('tabique-aviso-catalogo')).not.toBeInTheDocument();
  });
});

describe('PantallaDeElementos', () => {
  it('abre la tarjeta de tabique de un elemento de la biblioteca según su tipo', async () => {
    m.biblioteca.current = [
      {
        clave: 'muros',
        nombre: 'Muros',
        prefijo: 'MT',
        subcategorias: [{ clave: 'tabique', nombre: 'Muros de tabique', prefijo: 'MT', elementos: [{ clave: 'EST-02010', nombre: 'x', tipo: 'tabique', se_mide_por: 'm²', concepto: { clave: 'EST-02010', descripcion: 'x', unidad: 'm2' } }] }],
      },
    ];
    render(<PantallaDeElementos clave="EST-02010" rol="costos" />);
    expect(await screen.findByRole('article', { name: /EST-02010/ })).toBeInTheDocument();
  });
});
