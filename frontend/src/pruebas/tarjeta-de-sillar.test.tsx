/**
 * La tarjeta del muro de sillar amarillo BAP-01010: solo se pinta lo que responde el servidor; la junta y el desperdicio se mandan tal cual (el
 * desperdicio vacío lo resuelve el driver de la obra), el concepto es el del catálogo (sin concepto nuevo ni precios) y Costos propone sin
 * poder autorizar.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  calcular: vi.fn(),
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
  useDefinicionDelSillarApiV1BibliotecaDeElementosSillarClaveGet: () => ({ data: m.definicion.current, isLoading: false }),
  useCalcularSillarApiV1BibliotecaDeElementosSillarClaveCalcularPost: () => ({ mutateAsync: m.calcular }),
  usePropuestasDeSillarApiV1BibliotecaDeElementosSillarClavePropuestasGet: () => ({ data: m.propuestas.current }),
  useProponerActualizacionDeApuDelSillarApiV1BibliotecaDeElementosSillarClavePropuestasActualizarApuPost: () => ({ mutateAsync: m.proponerApu }),
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));
vi.mock('@/app/sesion', () => ({ useSesion: () => ({ sesion: { rol: m.rol.current } }) }));

import { PantallaDeElementos } from '@/cuantificador/elementos/PantallaDeElementos';
import { TarjetaMuroSillar } from '@/cuantificador/elementos/TarjetaMuroSillar';

const PARAMETROS = {
  junta_cm: 2,
  junta_entre_hileras_cm: null,
  desperdicio_de_pieza_pct: 5,
  desperdicio_de_mezcla_pct: 5,
  cama_cm: null,
  tipo_de_sardinel: null,
  nivel_desde_3er_nivel: null,
};

const DEFINICION = {
  clave: 'BAP-01010',
  nombre: 'Muro de sillar amarillo 19 cm, a hilo',
  nombre_nominal: 'Muro de sillar amarillo de 19 cm',
  tipo: 'sillar',
  medida: 'm2',
  se_mide_por: 'm²',
  categoria: { clave: 'muros', nombre: 'Muros' },
  subcategoria: { clave: 'sillar', nombre: 'Muros de sillar' },
  espesor_nominal_cm: 19,
  espesor_real_cm: 19,
  aparejo: 'a hilo (soga)',
  aparejo_largo: 'A hilo',
  aparejo_texto: 'colocada a hilo.',
  planta_nota: 'Planta de la hilada.',
  pieza: { insumo: 'PET-00008', ancho_cm: 19, alto_cm: 25, largo_cm: 45 },
  mezcla: 'MEZ-07010',
  parametros_por_defecto: PARAMETROS,
  hiladas: [{ peso: 1, filas: ['hilo'] }],
  conceptos: [
    { clave: 'BAP-01010', etiqueta: 'Concepto del catálogo', descripcion: 'Muro de 19 cm', unidad: 'm2', estado: 'catalogo', clave_provisional: false, en_catalogo: true, destajo: { clave: 'MOE-02016', descripcion: 'MO MURO DE SILLAR- HILO', unidad: 'm2' }, nivel_desde: null },
  ],
  driver_de_desperdicio: 'desperdicio_mamposteria',
  piezas_por_unidad_de_partida: 8.27,
  fuente: 'x',
  avisos_de_catalogo: [],
  pendientes: [{ clave: 'S1', texto: 'La junta del sillar no viene en el catálogo.' }],
};

const CALCULO = {
  clave: 'BAP-01010',
  nombre: DEFINICION.nombre,
  medida: 'm2',
  unidad: 'm²',
  cantidad: 1,
  nivel: null,
  concepto: { clave: 'BAP-01010', descripcion: 'Muro de 19 cm', unidad: 'm2', etiqueta: 'Concepto del catálogo', estado: 'catalogo', clave_provisional: false, nivel_desde: null },
  pieza: DEFINICION.pieza,
  parametros: PARAMETROS,
  geometria: {
    espesor_real_cm: 19,
    espesor_minimo_cm: 19,
    espesor_medio_cm: 19,
    hilada_promedio_cm: 27,
    piezas_por_hilada: 2.13,
    hiladas: [{ peso: 1, espesor_cm: 19, filas: [{ orientacion: 'hilo', etiqueta: 'a hilo', visible_cm: 45, alto_cm: 25, espesor_cm: 19, piezas_netas_m2: 7.88 }] }],
  },
  piezas: { netas_por_unidad: 7.88, por_unidad: 8.2742, total: 8.2742, a_comprar: 9 },
  mezcla: { neta_por_unidad: 0.02156, por_unidad: 0.022638, total_m3: 0.022638 },
  insumos: [
    { parte: 'sillar', clave: 'PET-00008', descripcion: 'SILLAR 19X25X45 AMARILLO', unidad: 'pza', por_unidad: 8.2742, total: 8.2742, a_comprar: 9 },
    { parte: 'mezcla', clave: 'MEZ-07010', descripcion: 'MEZCLA CEMENTO-ARENA 1:4', unidad: 'm3', por_unidad: 0.022638, total: 0.022638, a_comprar: null },
  ],
  mezcla_compuesta: [{ clave: 'ADH-00005', descripcion: 'CEMENTO SACO DE 50 KG', unidad: 'bts', por_m3: 7.28, total: 0.16, linea: 'x' }],
  mano_de_obra: { estado: 'destajo_del_catalogo', destajo: DEFINICION.conceptos[0]!.destajo, cantidad: 1, nota: 'El destajo es el del catálogo.' },
  herramienta: [],
  conciliacion: [
    {
      concepto: { clave: 'BAP-01010', descripcion: 'Muro de 19 cm', unidad: 'm2' },
      sobre: 'por m² de muro',
      filas: [
        { clave: 'PET-00008', descripcion: 'SILLAR', unidad: 'pza', catalogo: 9, elemento: 8.2742, diferencia: -0.7258, diferencia_pct: -8.1, marca: '≠' },
        { clave: 'MEZ-07010', descripcion: 'MEZCLA', unidad: 'm3', catalogo: 0.0292, elemento: 0.022638, diferencia: -0.0066, diferencia_pct: -22.5, marca: '≠' },
      ],
      mano_de_obra: [{ clave: 'MOE-02016', descripcion: 'MO MURO DE SILLAR- HILO', unidad: 'm2', cantidad: 1, costo: 190 }],
      resumen: { '=': 0, '≈': 0, '≠': 2, solo_catalogo: 0, solo_elemento: 0 },
      coincide: false,
      fuente_de_las_filas: [],
      avisos: [],
    },
  ],
  avisos: ['El catálogo trae 9 pza y 0.0292 m³ por m².'],
  drivers_usados: [{ clave: 'desperdicio_mamposteria', nombre: 'Desperdicio de mampostería', unidad: '%', valor: 5, fuente: 'defecto' }],
};

const PROPUESTA = {
  id: 'p1',
  elemento_clave: 'BAP-01010',
  concepto_clave: 'BAP-01010',
  clase: 'version_de_concepto',
  estado: 'pendiente',
  version: null,
  resumen: 'Nueva versión de BAP-01010: PET-00008 9 → 8.27423',
  cambios: [{ insumo: 'PET-00008', unidad: 'pza', antes: 9, despues: 8.27423 }],
  motivos: [],
  destajo_por_definir: null,
  propuso_nombre: 'Ana',
  propuso_rol: 'costos',
  propuesto_en: '2026-11-20T00:00:00Z',
  decidio_nombre: null,
  decidio_rol: null,
  decidido_en: null,
  motivo: null,
};

beforeEach(() => {
  for (const f of [m.calcular, m.proponerApu, m.autorizar, m.rechazar]) f.mockReset();
  m.calcular.mockResolvedValue(CALCULO);
  m.proponerApu.mockResolvedValue({ creadas: ['p1'], omitidas: [] });
  m.autorizar.mockResolvedValue({ version: 2 });
  m.rol.current = 'costos';
  m.definicion.current = DEFINICION;
  m.propuestas.current = [];
});

describe('TarjetaMuroSillar', () => {
  it('manda la junta sin desperdicio (lo resuelve el driver) y pinta piezas, mezcla, espesor y el concepto del catálogo', async () => {
    render(<TarjetaMuroSillar clave="BAP-01010" />);
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'BAP-01010', data: { cantidad: 1, junta_cm: 2 } }));
    expect(await screen.findByTestId('sillar-piezas')).toHaveTextContent('8.27 pza');
    expect(screen.getByTestId('sillar-mezcla')).toHaveTextContent('0.0226 m³');
    expect(screen.getByTestId('sillar-espesor')).toHaveTextContent('19.0 cm');
    expect(screen.getByTestId('sillar-mano-de-obra')).toHaveTextContent('MOE-02016');
    expect(screen.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'BAP-01010');
    expect(screen.getByRole('region', { name: 'Concepto que lo paga' })).toHaveTextContent('Matriz del catálogo');
    expect(screen.getByTestId('tabique-planta')).toBeInTheDocument();
    expect(screen.queryByText(/provisional/i)).not.toBeInTheDocument();
  });

  it('con una obra manda su id y muestra de dónde salió el desperdicio; teclear el desperdicio manda sobre el driver', async () => {
    render(<TarjetaMuroSillar clave="BAP-01010" obraId="obra-1" />);
    await waitFor(() => expect(m.calcular).toHaveBeenCalledWith({ clave: 'BAP-01010', data: { cantidad: 1, junta_cm: 2, obra_id: 'obra-1' } }));
    const drivers = await screen.findByRole('region', { name: 'Drivers que usa este cálculo' });
    expect(within(drivers).getByText(/desperdicio_mamposteria/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Desperdicio de mampostería'), { target: { value: '9' } });
    await waitFor(() =>
      expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'BAP-01010', data: { cantidad: 1, junta_cm: 2, desperdicio_pct: 9, obra_id: 'obra-1' } }),
    );
    fireEvent.change(screen.getByLabelText('Junta en centímetros'), { target: { value: '2.4' } });
    await waitFor(() => expect(m.calcular).toHaveBeenLastCalledWith({ clave: 'BAP-01010', data: expect.objectContaining({ junta_cm: 2.4 }) }));
  });

  it('la conciliación muestra la diferencia con el catálogo, el destajo y ningún precio', async () => {
    render(<TarjetaMuroSillar clave="BAP-01010" />);
    const bloque = (await screen.findByRole('region', { name: 'Conciliación con el catálogo' })).querySelector('[data-conciliacion="BAP-01010"]') as HTMLElement;
    expect(within(bloque).getAllByRole('row').map((f) => f.getAttribute('data-marca'))).toEqual([null, '≠', '≠']);
    expect(within(bloque).getByText('-8.1 %')).toBeInTheDocument();
    expect(bloque).toHaveTextContent('MOE-02016');
    expect(bloque.textContent).not.toMatch(/\$/);
    expect(screen.getByRole('list', { name: 'Advertencias' })).toHaveTextContent('9 pza');
  });

  it('Costos propone la actualización de BAP-01010 y no puede autorizar; no hay botón de concepto nuevo', async () => {
    m.propuestas.current = [PROPUESTA];
    render(<TarjetaMuroSillar clave="BAP-01010" />);
    await screen.findByTestId('sillar-piezas');
    const region = screen.getByRole('region', { name: 'Versiones propuestas' });
    expect(within(region).queryByRole('button', { name: 'Autorizar' })).not.toBeInTheDocument();
    expect(within(region).queryByRole('button', { name: /concepto nuevo/i })).not.toBeInTheDocument();
    fireEvent.click(within(region).getByRole('button', { name: /Confirmar cálculo/ }));
    await waitFor(() => expect(m.proponerApu).toHaveBeenCalledWith({ clave: 'BAP-01010', data: expect.objectContaining({ junta_cm: 2 }) }));
    expect(await screen.findByTestId('sillar-aviso')).toHaveTextContent('espera la autorización de Control de obra');
    expect(screen.getByRole('region', { name: 'Conciliación con el catálogo' }).querySelector('tr[data-insumo="PET-00008"]')).toHaveTextContent('8.2742');
  });

  it('Control de obra autoriza la propuesta pendiente', async () => {
    m.rol.current = 'control_obra';
    m.propuestas.current = [PROPUESTA];
    render(<TarjetaMuroSillar clave="BAP-01010" />);
    const region = await screen.findByRole('region', { name: 'Versiones propuestas' });
    fireEvent.click(within(region).getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
  });

  it('los supuestos y pendientes se listan y un cálculo rechazado por el servidor se muestra como error', async () => {
    m.calcular.mockRejectedValue(new Error('La junta va en centímetros, entre 0 y 10.'));
    render(<TarjetaMuroSillar clave="BAP-01010" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('La junta va en centímetros');
    expect(screen.getByRole('region', { name: 'Pendientes por confirmar' })).toHaveTextContent('La junta del sillar no viene en el catálogo');
  });
});

describe('PantallaDeElementos', () => {
  it('abre la tarjeta del sillar para un elemento de tipo sillar y la del tabique no se mezcla', async () => {
    m.biblioteca.current = [
      {
        clave: 'muros',
        nombre: 'Muros',
        prefijo: 'MT',
        subcategorias: [
          { clave: 'sillar', nombre: 'Muros de sillar', prefijo: 'MS', elementos: [{ clave: 'BAP-01010', nombre: 'x', tipo: 'sillar', se_mide_por: 'm²', concepto: { clave: 'BAP-01010', descripcion: 'x', unidad: 'm2' } }] },
        ],
      },
    ];
    render(<PantallaDeElementos clave="BAP-01010" rol="costos" obraId="obra-1" />);
    expect(await screen.findByRole('article', { name: /BAP-01010/ })).toHaveAttribute('data-sillar', 'BAP-01010');
  });
});
