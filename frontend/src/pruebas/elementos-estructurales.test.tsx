/**
 * La tarjeta de los elementos estructurales de la biblioteca (Ola 3B) y sus correcciones al catálogo: solo se pinta lo que responde el
 * servidor; el cambio de modo manda lo que corresponde y el elemento queda sin mano de obra.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calcular: vi.fn(),
  proponer: vi.fn(),
  autorizar: vi.fn(),
  rechazar: vi.fn(),
  definicion: { current: undefined as unknown },
  correcciones: { current: undefined as unknown },
  biblioteca: { current: undefined as unknown },
  propuestas: { current: [] as unknown[] },
  proponerCorrecciones: vi.fn(),
  autorizarPropuesta: vi.fn(),
  rechazarPropuesta: vi.fn(),
}));

vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  getCorreccionesDeCatalogoApiV1CorreccionesDeCatalogoGetQueryKey: () => ['correcciones'],
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({ data: m.biblioteca.current }),
  useDefinicionDelElementoEstructuralApiV1BibliotecaDeElementosEstructuraLinealClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularElementoEstructuralApiV1BibliotecaDeElementosEstructuraLinealClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDeEstructuraApiV1BibliotecaDeElementosEstructuraClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerCorreccionesApiV1BibliotecaDeElementosEstructuraClavePropuestasCorreccionesPost: () => ({ mutateAsync: m.proponerCorrecciones, isPending: false }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizarPropuesta }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazarPropuesta }),
  useCorreccionesDeCatalogoApiV1CorreccionesDeCatalogoGet: () => ({ data: m.correcciones.current }),
  useProponerCorreccionApiV1CorreccionesDeCatalogoPost: () => ({ mutateAsync: m.proponer }),
  useAutorizarCorreccionApiV1CorreccionesDeCatalogoCorreccionIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarCorreccionApiV1CorreccionesDeCatalogoCorreccionIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaElementoEstructural } from '@/cuantificador/elementos/TarjetaElementoEstructural';

const DEFINICION = {
  clave: 'T-1-15x25',
  nombre: 'Trabe T-1 de 15x25 cm 4 var. del #3 est. no. 2 @25 cm.',
  tipo: 'lineal_estructural',
  se_mide_por: 'metro lineal de trazo o pieza de largo conocido',
  concepto: { clave: 'AUX-00008', descripcion: 'Trabe T-1', unidad: 'm' },
  categoria: { clave: 'trabes', nombre: 'Trabes' },
  subcategoria: { clave: 'losa', nombre: 'Trabes de losa (catálogo)' },
  seccion: { ancho_cm: 15, peralte_cm: 25, largo_cm: null },
  lados_de_cimbra: 3,
  modos: ['ml', 'pieza'],
  modo_por_defecto: 'ml',
  largo_por_defecto_m: 4,
  alto_por_defecto_m: null,
  armado: [
    { parte: 'arriba', clave: 'ACR-00001', descripcion: 'VARILLA 3/8', cantidad: 2, detalle: 'arriba' },
    { parte: 'anillos', clave: 'ACE-00005', descripcion: 'ANILLO 10X20', cantidad: 1, detalle: '@25 cm' },
  ],
  concreto: { clave: 'CON-00003', descripcion: 'CONCRETO BOMBEADO 250' },
  alambre: { clave: 'ACE-00001', descripcion: 'ALAMBRE RECOCIDO' },
  cimbra: [],
  conceptos_del_catalogo: [],
  camino_de_colado_y_cimbra: {
    estado: 'por_registrar',
    motivo: 'El catálogo paga el concreto y la cimbra de este elemento dentro de la losa por m².',
    borrador: {
      unidad: 'ml',
      toma: { concreto: true, cimbra: true },
      clave_propuesta: null,
      descripcion_sugerida: 'Colado y cimbra de Trabe T-1',
      concreto: { clave: 'CON-00003', descripcion: 'CONCRETO' },
      cimbra: [{ clave: 'MAD-00001', descripcion: 'CIMBRA', consumo: 'por_m2', cantidad: 1 }],
      ruta: 'POST /elementos-parametricos/{elemento_id}/conceptos con unidad, toma, clave_propuesta y descripcion',
    },
    mano_de_obra: { estado: 'sin_destajo_por_ml', destajo: null, nota: 'El catálogo de trabajos no trae destajo para trabes.' },
    preguntas: ['Q51', 'Q52'],
  },
  usado_en: [],
  usos_total: 1,
  pendientes: [
    { clave: 'Q51', texto: 'Sin concepto propio de colado.' },
    { clave: 'Q52', texto: 'Sin destajo por ml.' },
  ],
  correcciones_de_fabrica: [] as unknown[],
};

const CALCULO = {
  clave: 'T-1-15x25',
  nombre: DEFINICION.nombre,
  tipo: 'lineal_estructural',
  modo: 'ml',
  unidad: 'ml',
  longitud_m: 1,
  cantidad: 1,
  seccion: { ancho_cm: 15, peralte_cm: 25, largo_cm: null },
  concreto: { clave: 'CON-00003', descripcion: 'CONCRETO', m3: 0.039375, desperdicio_pct: 5 },
  acero_kg: 3.135,
  cimbra: { m2: 0.65, lados: 3, consumos: [] },
  receta_acero: null,
  parrilla: null,
  insumos: [
    { parte: 'acero', clave: 'ACR-00001', descripcion: 'VARILLA 3/8', unidad: 'pza', por_unidad: 0.3443, total: 0.3443, a_comprar: 1, kg: 1.9, ml: 4.1, detalle: '4 varillas' },
    { parte: 'concreto', clave: 'CON-00003', descripcion: 'CONCRETO', unidad: 'm³', por_unidad: 0.039375, total: 0.039375, a_comprar: null, kg: null, ml: null, detalle: '' },
  ],
  mano_de_obra: { estado: 'sin_mano_de_obra', nota: 'El elemento no calcula mano de obra.' },
  conciliacion: [
    {
      concepto: { clave: 'AUX-00008', descripcion: 'Trabe T-1', unidad: 'm', toma: ['acero'], hasta_m: null, fuente: 'CATALOGO_DE_MATERIALES:34' },
      sobre: 'por metro',
      filas: [
        { clave: 'ACR-00001', descripcion: 'VARILLA 3/8', unidad: 'pza', catalogo: 0.36, elemento: 0.3443, diferencia: -0.0157, diferencia_pct: -4.37, marca: '≈' },
        { clave: 'ACE-00005', descripcion: 'ANILLO 10X20', unidad: 'kg', catalogo: 0.8217, elemento: 0.8217, diferencia: 0, diferencia_pct: 0, marca: '=' },
        { clave: 'ACE-00029', descripcion: 'OTRO', unidad: 'kg', catalogo: 0.1, elemento: null, diferencia: null, diferencia_pct: null, marca: 'solo_catalogo' },
      ],
      mano_de_obra: [],
      resumen: { '=': 1, '≈': 1, '≠': 0, solo_catalogo: 1, solo_elemento: 0 },
      coincide: false,
      fuente_de_las_filas: [],
      avisos: [],
    },
  ],
  anclaje: { aplica: false, sugerido_diametros: 40, capturado_cm: null, cumple: null, grupos: [], mensaje: 'El anclaje es de una pieza.' },
  camino_de_colado_y_cimbra: DEFINICION.camino_de_colado_y_cimbra,
  advertencias: [],
};

const CORRECCION_DE_FABRICA = {
  concepto_clave: 'AUX-00008',
  resumen: 'Nueva versión de AUX-00008: ACE-00005 0.8217 → 0.7',
  cambios: [{ insumo: 'ACE-00005', unidad: 'kg', antes: 0.8217, despues: 0.7 }],
  motivos: ['Q56 / D7: prueba.'],
};

const CORRECCION = {
  concepto_clave: 'EST-02330',
  campo: 'unidad',
  concepto: 'Cadena intermedia de 15x70 cm',
  valor_catalogo: 'm2',
  valor_propuesto: 'm',
  valor_vigente: 'm2',
  motivo: 'Las cantidades son por metro.',
  fuente: 'CATALOGO_DE_MATRICES:191',
  preguntas: ['Q59'],
  nota: 'El elemento no se construye en esta ola.',
  estado: 'sin_proponer',
  version_vigente: null,
  pendiente_id: null,
  historial: [],
};

beforeEach(() => {
  for (const f of [m.calcular, m.proponer, m.autorizar, m.rechazar, m.proponerCorrecciones, m.autorizarPropuesta, m.rechazarPropuesta]) f.mockReset();
  m.propuestas.current = [];
  m.proponerCorrecciones.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.autorizarPropuesta.mockResolvedValue({ version: 2 });
  m.rechazarPropuesta.mockResolvedValue(undefined);
  m.calcular.mockResolvedValue(CALCULO);
  m.proponer.mockResolvedValue({ id: 'c1', estado: 'pendiente', version: null });
  m.autorizar.mockResolvedValue({ version: 1 });
  m.rechazar.mockResolvedValue(undefined);
  m.definicion.current = DEFINICION;
  m.correcciones.current = [CORRECCION];
});

describe('TarjetaElementoEstructural', () => {
  it('muestra la sección como ancho × peralte, calcula por ml y lista la conciliación con sus marcas', async () => {
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    expect(screen.getByTestId('ee-seccion')).toHaveTextContent('15 × 25 cm (ancho × peralte)');
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'T-1-15x25', data: { modo: 'ml', cantidad: 1 } }));
    expect(await screen.findByTestId('ee-concreto')).toHaveTextContent('0.0394 m³ por metro');
    expect(screen.getByTestId('ee-sin-mano-de-obra')).toBeInTheDocument();
    const conciliacion = screen.getByRole('region', { name: 'Conciliación con el catálogo' });
    const filas = within(conciliacion).getAllByRole('row');
    expect(filas.map((f) => f.getAttribute('data-marca'))).toEqual([null, '≈', '=', 'solo_catalogo']);
    expect(within(conciliacion).getByText('solo en el catálogo')).toBeInTheDocument();
    expect(within(conciliacion).getByText('-4.4 %')).toBeInTheDocument();
  });

  it('por pieza manda el largo y las zonas de anillo; vuelve a ml sin mandar el largo', async () => {
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    await screen.findByTestId('ee-concreto');
    fireEvent.change(screen.getByLabelText('Se mide por'), { target: { value: 'pieza' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'T-1-15x25', data: { modo: 'pieza', cantidad: 1, largo_m: 4 } }),
    );
    fireEvent.change(screen.getByLabelText('Largo de la pieza en metros'), { target: { value: '6' } });
    fireEvent.click(screen.getByLabelText(/Anillos con zona más cerrada/));
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({
        clave: 'T-1-15x25',
        data: { modo: 'pieza', cantidad: 1, largo_m: 6, zonas_de_anillo: [{ len_cm: 50, sep_cm: 10 }, { sep_cm: 25 }] },
      }),
    );
    fireEvent.change(screen.getByLabelText('Se mide por'), { target: { value: 'ml' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'T-1-15x25', data: { modo: 'ml', cantidad: 1 } }));
  });

  it('deja el colado y cimbra por registrar, sin clave ni destajo', async () => {
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    const camino = await screen.findByRole('region', { name: 'Colado, cimbra y destajo' });
    expect(camino).toHaveAttribute('data-camino', 'por_registrar');
    expect(within(camino).getByTestId('ee-camino-colado')).toHaveTextContent('Concepto nuevo por registrar');
    expect(within(camino).getByTestId('ee-sin-destajo')).toHaveTextContent('no trae destajo');
    expect(camino.textContent).not.toMatch(/EJ-7/);
  });

  it('la columna manda su altura y la zapata solo es pieza', async () => {
    m.definicion.current = {
      ...DEFINICION,
      clave: 'C-1',
      tipo: 'columna_de_concreto',
      modos: ['pieza'],
      modo_por_defecto: 'pieza',
      largo_por_defecto_m: null,
      alto_por_defecto_m: 4.2,
      categoria: { clave: 'columnas', nombre: 'Columnas' },
    };
    render(<TarjetaElementoEstructural clave="C-1" />);
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'C-1', data: { modo: 'pieza', cantidad: 1, alto_m: 4.2 } }));
    expect(screen.queryByLabelText('Se mide por')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Altura de la columna en metros'), { target: { value: '4.5' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'C-1', data: { modo: 'pieza', cantidad: 1, alto_m: 4.5 } }));
  });

  it('el anclaje es una sugerencia: vacío no se manda y capturado se manda y avisa si cumple', async () => {
    m.calcular.mockResolvedValue({
      ...CALCULO,
      modo: 'pieza',
      unidad: 'pza',
      anclaje: {
        aplica: true,
        sugerido_diametros: 40,
        capturado_cm: 20,
        cumple: false,
        grupos: [{ numero: 3, clave: 'ACR-00001', diametro_cm: 0.9525, sugerido_cm: 38.1, cumple: false }],
        mensaje: 'El anclaje de 20 cm por extremo NO cumple lo sugerido (40 diámetros: 38 cm en la varilla no. 3); es una sugerencia.',
      },
    });
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    await screen.findByTestId('ee-concreto');
    expect(screen.queryByLabelText('Anclaje de la varilla por extremo en centímetros')).not.toBeInTheDocument(); // por ml no aplica
    fireEvent.change(screen.getByLabelText('Se mide por'), { target: { value: 'pieza' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'T-1-15x25', data: { modo: 'pieza', cantidad: 1, largo_m: 4 } }),
    );
    fireEvent.change(screen.getByLabelText('Anclaje de la varilla por extremo en centímetros'), { target: { value: '20' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'T-1-15x25', data: { modo: 'pieza', cantidad: 1, largo_m: 4, anclaje_cm: 20 } }),
    );
    const aviso = await screen.findByTestId('ee-anclaje');
    expect(aviso).toHaveAttribute('data-cumple', 'false');
    expect(aviso).toHaveTextContent('Anclaje no cumple');
    expect(aviso).toHaveTextContent('es una sugerencia');
  });

  it('una trabe con corrección de fábrica muestra la versión propuesta junto al catálogo vigente y deja proponerla', async () => {
    m.definicion.current = { ...DEFINICION, correcciones_de_fabrica: [CORRECCION_DE_FABRICA] };
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    const conciliacion = await screen.findByRole('region', { name: 'Conciliación con el catálogo' });
    expect(within(conciliacion).getByText('Versión propuesta')).toBeInTheDocument();
    expect(within(conciliacion).getByText('0.7000')).toBeInTheDocument();
    expect(within(conciliacion).getByText('(sin proponer)')).toBeInTheDocument();
    const region = screen.getByRole('region', { name: 'Versiones propuestas' });
    expect(within(region).getByText(/Sin proponer/)).toBeInTheDocument();
    fireEvent.click(within(region).getByRole('button', { name: 'Proponer las correcciones del catálogo' }));
    await waitFor(() => expect(m.proponerCorrecciones).toHaveBeenCalledWith({ clave: 'T-1-15x25' }));
    expect(within(region).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
  });

  it('una versión propuesta que cambia el anillo por alambrón muestra la fila del insumo nuevo y el anillo en cero', async () => {
    m.definicion.current = {
      ...DEFINICION,
      correcciones_de_fabrica: [
        {
          concepto_clave: 'AUX-00008',
          resumen: 'Nueva versión de AUX-00008: ACE-00005 0.8217 → 0; ACE-00002 0 → 0.8217',
          cambios: [
            { insumo: 'ACE-00005', unidad: 'kg', antes: 0.8217, despues: 0 },
            { insumo: 'ACE-00002', unidad: 'kg', antes: 0, despues: 0.8217 },
          ],
          motivos: ['Q56 / D7: alambrón.'],
        },
      ],
    };
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    const conciliacion = await screen.findByRole('region', { name: 'Conciliación con el catálogo' });
    const nueva = within(conciliacion).getByText('ACE-00002').closest('tr') as HTMLElement;
    expect(nueva).toHaveAttribute('data-marca', 'solo_propuesta');
    expect(within(nueva).getByText(/0\.8217/)).toBeInTheDocument();
    const anillo = within(conciliacion).getByText('ACE-00005').closest('tr') as HTMLElement;
    expect(within(anillo).getByText('0.0000')).toBeInTheDocument();
  });

  it('Control de obra autoriza la propuesta pendiente de una trabe; Costos no puede', async () => {
    m.definicion.current = { ...DEFINICION, correcciones_de_fabrica: [CORRECCION_DE_FABRICA] };
    m.propuestas.current = [
      {
        id: 'p1', elemento_clave: 'T-1-15x25', concepto_clave: 'AUX-00008', clase: 'version_de_concepto', estado: 'pendiente', version: null,
        resumen: CORRECCION_DE_FABRICA.resumen, cambios: CORRECCION_DE_FABRICA.cambios, motivos: [], destajo_por_definir: null,
        propuso_nombre: 'Ana', propuso_rol: 'costos', propuesto_en: '2026-11-19T00:00:00Z', decidio_nombre: null, decidio_rol: null, decidido_en: null, motivo: null,
      },
    ];
    const { unmount } = render(<TarjetaElementoEstructural clave="T-1-15x25" rol="control_obra" />);
    const region = await screen.findByRole('region', { name: 'Versiones propuestas' });
    expect(within(region).queryByRole('button', { name: 'Proponer las correcciones del catálogo' })).not.toBeInTheDocument();
    fireEvent.click(within(region).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizarPropuesta).toHaveBeenCalledWith({ propuestaId: 'p1' }));
    unmount();
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    const otra = await screen.findByRole('region', { name: 'Versiones propuestas' });
    expect(within(otra).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
  });

  it('un cálculo que el servidor rechaza se muestra como error', async () => {
    m.calcular.mockRejectedValue(new Error('La cantidad debe ser mayor que cero.'));
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('La cantidad debe ser mayor que cero.');
  });
});

describe('CorreccionesDelCatalogo en la tarjeta de una trabe', () => {
  it('Costos propone la versión nueva de EST-02330 (m² → m) y no puede autorizarla', async () => {
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    const region = await screen.findByRole('region', { name: 'Correcciones propuestas al catálogo' });
    const tabla = within(region).getByRole('table', { name: 'Diferencia de EST-02330' });
    expect(within(tabla).getByText('m²')).toBeInTheDocument(); // el catálogo vigente no se edita
    fireEvent.click(within(region).getByRole('button', { name: /Proponer versión nueva \(m² → m\)/ }));
    await waitFor(() => expect(m.proponer).toHaveBeenCalledWith({ data: { concepto_clave: 'EST-02330', campo: 'unidad' } }));
    expect(within(region).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
  });

  it('Control de obra autoriza o rechaza la pendiente; Costos no ve los botones', async () => {
    m.correcciones.current = [{ ...CORRECCION, estado: 'pendiente', pendiente_id: 'c1' }];
    const { unmount } = render(<TarjetaElementoEstructural clave="T-1-15x25" rol="control_obra" />);
    const region = await screen.findByRole('region', { name: 'Correcciones propuestas al catálogo' });
    expect(within(region).getByText(/Pendiente de autorizar por Control de obra/)).toBeInTheDocument();
    fireEvent.click(within(region).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ correccionId: 'c1' }));
    fireEvent.click(within(region).getByRole('button', { name: 'Rechazar' }));
    await waitFor(() => expect(m.rechazar).toHaveBeenCalledWith({ correccionId: 'c1', data: {} }));
    unmount();
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="costos" />);
    const otra = await screen.findByRole('region', { name: 'Correcciones propuestas al catálogo' });
    expect(within(otra).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
  });

  it('un rol que no propone no ve las correcciones', async () => {
    render(<TarjetaElementoEstructural clave="T-1-15x25" rol="residente" />);
    await screen.findByTestId('ee-concreto');
    expect(screen.queryByRole('region', { name: 'Correcciones propuestas al catálogo' })).not.toBeInTheDocument();
  });
});

describe('PantallaDeElementos', () => {
  it('abre la tarjeta estructural de un elemento de la biblioteca según su tipo', async () => {
    m.biblioteca.current = [
      { clave: 'trabes', nombre: 'Trabes', prefijo: 'T', subcategorias: [{ clave: 'losa', nombre: 'Losa', prefijo: 'T', elementos: [{ clave: 'T-1-15x25', nombre: 'x', tipo: 'lineal_estructural', se_mide_por: 'ml', concepto: { clave: 'AUX-00008', descripcion: 'x', unidad: 'm' } }] }] },
    ];
    render(<PantallaDeElementos clave="T-1-15x25" rol="costos" />);
    expect(await screen.findByRole('article', { name: /T-1-15x25/ })).toBeInTheDocument();
  });

  it('sin elemento elegido pide elegir uno', () => {
    m.biblioteca.current = [];
    render(<PantallaDeElementos clave={null} />);
    expect(screen.getByText('Elige un elemento de la biblioteca')).toBeInTheDocument();
  });
});
