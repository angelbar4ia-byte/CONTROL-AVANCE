/**
 * La pestaña Paramétrico (Ola 4B): los drivers (global, modo, ajuste de la obra, vigente) y el enlace de ranuras con el árbol.
 * Costos y Control de obra editan; los demás roles ven en solo lectura. Solo se pinta lo que responde el servidor.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  fijarGlobal: vi.fn(),
  fijarDeObra: vi.fn(),
  quitarDeObra: vi.fn(),
  enlazar: vi.fn(),
  quitarEnlace: vi.fn(),
  autorizar: vi.fn(),
  rechazar: vi.fn(),
  bitacora: { current: [] as unknown[] },
  drivers: { current: [] as unknown[] },
  enlaces: { current: undefined as unknown },
}));

vi.mock('@/api/generado/parametrico/parametrico', () => ({
  getDriversDeObraApiV1ObrasObraIdDriversGetQueryKey: (id: string) => ['drivers', id],
  getEnlacesDeRanuraApiV1ObrasObraIdEnlacesDeRanuraGetQueryKey: (id: string) => ['enlaces', id],
  useDriversDeObraApiV1ObrasObraIdDriversGet: () => ({ data: m.drivers.current, isLoading: false }),
  useFijarDriverGlobalApiV1DriversClavePut: () => ({ mutateAsync: m.fijarGlobal }),
  useFijarDriverDeObraApiV1ObrasObraIdDriversClavePut: () => ({ mutateAsync: m.fijarDeObra }),
  useQuitarDriverDeObraApiV1ObrasObraIdDriversClaveDelete: () => ({ mutateAsync: m.quitarDeObra }),
  getPropuestasDeDriversApiV1DriversPropuestasGetQueryKey: (p: unknown) => ['propuestas', p],
  usePropuestasDeDriversApiV1DriversPropuestasGet: () => ({ data: m.bitacora.current }),
  useAutorizarPropuestaDeDriverApiV1DriversPropuestasPropuestaIdAutorizarPost: () => ({ mutateAsync: m.autorizar }),
  useRechazarPropuestaDeDriverApiV1DriversPropuestasPropuestaIdRechazarPost: () => ({ mutateAsync: m.rechazar }),
  useEnlacesDeRanuraApiV1ObrasObraIdEnlacesDeRanuraGet: () => ({ data: m.enlaces.current, isLoading: false }),
  useEnlazarRanuraApiV1ObrasObraIdEnlacesDeRanuraPut: () => ({ mutateAsync: m.enlazar, isPending: false }),
  useQuitarEnlaceApiV1ObrasObraIdEnlacesDeRanuraEnlaceIdDelete: () => ({ mutateAsync: m.quitarEnlace }),
}));
vi.mock('@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos', () => ({
  useBibliotecaDeElementosApiV1BibliotecaDeElementosGet: () => ({
    data: [{ clave: 'castillos', nombre: 'Castillos', subcategorias: [{ clave: 'muro', nombre: 'Muro', elementos: [{ clave: 'K-1', nombre: 'Castillo K-1', tipo: 'estructura_de_catalogo' }] }] }],
  }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { PantallaParametrica } from '@/cuantificador/elementos/PantallaParametrica';

const driver = (o: Record<string, unknown>) => ({
  nombre: 'Altura estándar del muro', unidad: 'm', nota: 'M-9', por_confirmar: false, valor_inicial: '3', modo_inicial: 'ajustable',
  valor_global: '3', modo: 'ajustable', valor_obra: null, valor_vigente: '3', origen: 'inicial', ajuste_ignorado: false, editado: false,
  clave: 'altura_estandar', ...o,
});

const DRIVERS = [
  driver({}),
  driver({ clave: 'escarpio_minimo', nombre: 'Escarpio del muro de cimentación de piedra', unidad: 'V:H', valor_inicial: '1.5', modo_inicial: 'fijo', valor_global: '1.5', modo: 'fijo', valor_vigente: '1.5', por_confirmar: true, inmutable: true }),
  driver({ clave: 'desperdicio_concreto', nombre: 'Desperdicio de concreto', unidad: '%', valor_inicial: '5', valor_global: '5', valor_vigente: '2.5', valor_obra: '2.5', origen: 'obra' }),
];

const NIVEL = { id: 'n1', clave: 'NIV-1', descripcion: 'Planta baja' };
const ENLACES = {
  enlaces: [
    {
      id: 'e1', ranura: 'mamposteria:tabique_rojo', capa: { nivel_id: 'n1', etapa_id: null, ubicacion: null }, concepto_id: 'c1',
      concepto_clave: 'EST-02010', concepto_descripcion: 'Muro de tabique de 14 cm', unidad: 'm2', estado: 'enlazado', cuenta: true,
      aviso: null, partida_id: 'p1', partida_nombre: 'EST-02010',
    },
    {
      id: 'e2', ranura: 'elemento:K-1:acero', capa: { nivel_id: null, etapa_id: null, ubicacion: 'barda' }, concepto_id: 'c2',
      concepto_clave: 'EST-10011', concepto_descripcion: 'Colocación de acero', unidad: 'pza', estado: 'falta_partida', cuenta: false,
      aviso: 'El concepto EST-10011 no está en el árbol de la obra en esa capa: agrégalo al árbol; mientras tanto no cuenta.',
      partida_id: null, partida_nombre: null,
    },
  ],
  ranuras_de_plantilla: [
    { ranura: 'mamposteria:tabique_rojo', nombre: 'Mampostería · Tabique rojo', grupo: 'mamposteria', sugerido_clave: 'EST-02010' },
    { ranura: 'mamposteria:sillar_amarillo', nombre: 'Mampostería · Sillar amarillo', grupo: 'mamposteria', sugerido_clave: null },
  ],
  niveles: [NIVEL],
  etapas: [],
  partidas_del_arbol: 3,
  conceptos_del_arbol: [{ clave: 'EST-02010', descripcion: 'Muro de tabique de 14 cm' }],
};

function pintar(rol: string) {
  return render(<PantallaParametrica obraId="o1" obraClave="F1" rol={rol} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.drivers.current = DRIVERS;
  m.bitacora.current = [];
  m.autorizar.mockResolvedValue({});
  m.rechazar.mockResolvedValue({});
  m.enlaces.current = ENLACES;
  m.fijarGlobal.mockResolvedValue({});
  m.fijarDeObra.mockResolvedValue({});
  m.quitarDeObra.mockResolvedValue({});
  m.enlazar.mockResolvedValue({});
  m.quitarEnlace.mockResolvedValue(undefined);
});

describe('Paramétrico · drivers', () => {
  it('muestra el valor global, el modo, el ajuste de la obra y el vigente de cada driver', () => {
    pintar('costos');
    const tabla = screen.getByRole('table', { name: 'Drivers del Paramétrico' });
    const altura = within(tabla).getByText('Altura estándar del muro').closest('tr') as HTMLElement;
    expect(within(altura).getByLabelText('Valor global de Altura estándar del muro')).toHaveValue('3');
    expect(altura.querySelector('[data-vigente]')?.textContent).toBe('3');
    expect(within(altura).getByText('de partida')).toBeInTheDocument();
    const concreto = within(tabla).getByText('Desperdicio de concreto').closest('tr') as HTMLElement;
    expect(within(concreto).getByLabelText('Valor de la obra para Desperdicio de concreto')).toHaveValue('2.5');
    expect(concreto.querySelector('[data-vigente]')?.textContent).toBe('2.5');
    expect(within(concreto).getByText('obra')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Obra F1' })).toBeInTheDocument();
  });

  it('un driver fijo no se ajusta por obra y lo por confirmar se marca', () => {
    pintar('control_obra');
    const fijo = screen.getByText('Escarpio del muro de cimentación de piedra').closest('tr') as HTMLElement;
    expect(within(fijo).getByLabelText('Valor de la obra para Escarpio del muro de cimentación de piedra')).toBeDisabled();
    expect(within(fijo).getByLabelText('Modo de Escarpio del muro de cimentación de piedra')).toHaveValue('fijo');
    expect(within(fijo).getByText('por confirmar')).toBeInTheDocument();
  });

  it('F4: el escarpio y la corona siguen fijos: ni valor ni modo se pueden cambiar, ni para Control de obra', () => {
    pintar('control_obra');
    const fijo = screen.getByText('Escarpio del muro de cimentación de piedra').closest('tr') as HTMLElement;
    expect(within(fijo).getByText('fijo: no se cambia')).toBeInTheDocument();
    expect(within(fijo).getByLabelText('Valor global de Escarpio del muro de cimentación de piedra')).toBeDisabled();
    expect(within(fijo).getByLabelText('Modo de Escarpio del muro de cimentación de piedra')).toBeDisabled();
    const normal = screen.getByText('Desperdicio de concreto').closest('tr') as HTMLElement;
    expect(within(normal).queryByText('fijo: no se cambia')).not.toBeInTheDocument();
  });

  it('F3: lo que propone Costos queda pendiente y se dice; Control de obra autoriza y Costos no ve el botón', async () => {
    const propuesta = {
      id: 'p1', clave: 'altura_estandar', alcance: 'global', obra_id: null, accion: 'fijar', valor: '2.8', modo: null, valor_anterior: '3',
      modo_anterior: null, estado: 'pendiente', propuso_id: 'u1', propuso_nombre: 'Costos', propuso_rol: 'costos', propuesto_en: '2026-11-19T10:00:00Z',
      decidio_id: null, decidio_nombre: null, decidio_rol: null, decidido_en: null, motivo: null,
    };
    m.drivers.current = [driver({ propuestas_pendientes: [propuesta] }), ...DRIVERS.slice(1)];
    m.fijarGlobal.mockResolvedValue({ propuesta });
    const { unmount } = pintar('costos');
    const fila = screen.getByText('Altura estándar del muro').closest('tr') as HTMLElement;
    expect(within(fila).getByText(/valor 2\.8 \(antes 3\)/)).toBeInTheDocument();
    expect(within(fila).queryByRole('button', { name: /Autorizar el cambio/ })).not.toBeInTheDocument();
    const global = screen.getByLabelText('Valor global de Altura estándar del muro');
    fireEvent.change(global, { target: { value: '2.9' } });
    fireEvent.blur(global);
    expect(await screen.findByText(/queda pendiente hasta que Control de obra lo autorice/)).toBeInTheDocument();
    unmount();
    pintar('control_obra');
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar el cambio de Altura estándar del muro' }));
    await waitFor(() => expect(m.autorizar).toHaveBeenCalledWith({ propuestaId: 'p1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Rechazar el cambio de Altura estándar del muro' }));
    await waitFor(() => expect(m.rechazar).toHaveBeenCalledWith({ propuestaId: 'p1', data: {} }));
  });

  it('F3: la bitácora dice quién propuso, quién decidió y cuándo', () => {
    m.bitacora.current = [
      {
        id: 'p9', clave: 'desperdicio_concreto', alcance: 'global', obra_id: null, accion: 'fijar', valor: '8', modo: null, valor_anterior: '5',
        modo_anterior: null, estado: 'autorizada', propuso_id: 'u1', propuso_nombre: 'Costos', propuso_rol: 'costos', propuesto_en: '2026-11-19T10:00:00Z',
        decidio_id: 'u2', decidio_nombre: 'Control', decidio_rol: 'control_obra', decidido_en: '2026-11-19T11:00:00Z', motivo: null,
      },
    ];
    pintar('residente');
    const tabla = screen.getByRole('table', { name: 'Bitácora de cambios de drivers', hidden: true });
    const fila = tabla.querySelector('[data-bitacora-propuesta="p9"]') as HTMLElement;
    expect(fila.textContent).toContain('desperdicio_concreto');
    expect(fila.textContent).toContain('autorizada');
    expect(fila.textContent).toContain('Costos');
    expect(fila.textContent).toContain('Control');
  });

  it('Costos cambia el global, el modo y el ajuste de la obra, y lo manda tal cual (con punto decimal)', async () => {
    pintar('costos');
    const global = screen.getByLabelText('Valor global de Altura estándar del muro');
    fireEvent.change(global, { target: { value: '2,8' } });
    fireEvent.blur(global);
    await waitFor(() => expect(m.fijarGlobal).toHaveBeenCalledWith({ clave: 'altura_estandar', data: { valor: '2.8' } }));

    fireEvent.change(screen.getByLabelText('Modo de Altura estándar del muro'), { target: { value: 'fijo' } });
    await waitFor(() => expect(m.fijarGlobal).toHaveBeenCalledWith({ clave: 'altura_estandar', data: { modo: 'fijo' } }));

    const obra = screen.getByLabelText('Valor de la obra para Altura estándar del muro');
    fireEvent.change(obra, { target: { value: '2.6' } });
    fireEvent.blur(obra);
    await waitFor(() => expect(m.fijarDeObra).toHaveBeenCalledWith({ obraId: 'o1', clave: 'altura_estandar', data: { valor: '2.6' } }));
  });

  it('vaciar el campo de la obra quita el ajuste: vuelve al global', async () => {
    pintar('control_obra');
    const obra = screen.getByLabelText('Valor de la obra para Desperdicio de concreto');
    fireEvent.change(obra, { target: { value: '' } });
    fireEvent.blur(obra);
    await waitFor(() => expect(m.quitarDeObra).toHaveBeenCalledWith({ obraId: 'o1', clave: 'desperdicio_concreto' }));
  });

  it('un valor sin cambiar no se manda, y el global vacío no se manda', () => {
    pintar('costos');
    const global = screen.getByLabelText('Valor global de Altura estándar del muro');
    fireEvent.focus(global);
    fireEvent.blur(global);
    fireEvent.change(global, { target: { value: '' } });
    fireEvent.blur(global);
    expect(m.fijarGlobal).not.toHaveBeenCalled();
  });

  it('el error del servidor se muestra', async () => {
    m.fijarGlobal.mockRejectedValue(new Error('«Altura estándar del muro» debe ser mayor que 0 m.'));
    pintar('costos');
    const global = screen.getByLabelText('Valor global de Altura estándar del muro');
    fireEvent.change(global, { target: { value: '0' } });
    fireEvent.blur(global);
    expect(await screen.findByRole('alert')).toHaveTextContent('debe ser mayor que 0 m');
  });

  it('los demás roles ven la tabla en solo lectura', () => {
    pintar('residente');
    expect(screen.getByLabelText('Valor global de Altura estándar del muro')).toBeDisabled();
    expect(screen.getByLabelText('Modo de Altura estándar del muro')).toBeDisabled();
    expect(screen.getByLabelText('Valor de la obra para Altura estándar del muro')).toBeDisabled();
    expect(screen.getByText(/Solo Costos y Control de obra editan los drivers/)).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Enlazar una ranura' })).not.toBeInTheDocument();
  });

  it('avisa que un ajuste de obra de un driver fijo no vale', () => {
    m.drivers.current = [driver({ modo: 'fijo', valor_obra: '2.6', ajuste_ignorado: true, origen: 'global' })];
    pintar('costos');
    expect(screen.getByText('El driver es fijo: el ajuste de la obra no vale.')).toBeInTheDocument();
  });
});

describe('Paramétrico · enlace de ranuras', () => {
  it('la ranura sin partida en el árbol avisa y no cuenta; la enlazada cuenta', () => {
    pintar('costos');
    const tabla = screen.getByRole('table', { name: 'Enlaces de ranura de la obra' });
    const ok = tabla.querySelector('[data-enlace="mamposteria:tabique_rojo"]') as HTMLElement;
    expect(ok.getAttribute('data-estado')).toBe('enlazado');
    expect(within(ok).getByText('enlazado · EST-02010')).toBeInTheDocument();
    expect(within(ok).getByText('Planta baja')).toBeInTheDocument();
    const falta = tabla.querySelector('[data-enlace="elemento:K-1:acero"]') as HTMLElement;
    expect(falta.getAttribute('data-estado')).toBe('falta_partida');
    expect(within(falta).getByText('falta la partida · no cuenta')).toBeInTheDocument();
    expect(within(falta).getByText(/no está en el árbol de la obra/)).toBeInTheDocument();
    expect(within(falta).getByText('Barda')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 enlace no cuenta');
  });

  it('enlaza una ranura de plantilla con la capa elegida y puede usar el concepto propuesto', async () => {
    pintar('costos');
    const form = screen.getByRole('group', { name: 'Enlazar una ranura' });
    fireEvent.change(within(form).getByLabelText('Ranura'), { target: { value: 'mamposteria:tabique_rojo' } });
    expect(within(form).getByRole('button', { name: 'Enlazar' })).toBeDisabled(); // sin concepto no se enlaza
    fireEvent.click(within(form).getByRole('button', { name: /Usar EST-02010/ }));
    fireEvent.change(within(form).getByLabelText('Nivel'), { target: { value: 'n1' } });
    fireEvent.change(within(form).getByLabelText('Ubicación'), { target: { value: 'pretil' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Enlazar' }));
    await waitFor(() =>
      expect(m.enlazar).toHaveBeenCalledWith({
        obraId: 'o1',
        data: { ranura: 'mamposteria:tabique_rojo', concepto_clave: 'EST-02010', nivel_id: 'n1', etapa_id: null, ubicacion: 'pretil' },
      }),
    );
  });

  it('enlaza la parte de un elemento de la biblioteca', async () => {
    pintar('control_obra');
    const form = screen.getByRole('group', { name: 'Enlazar una ranura' });
    fireEvent.change(within(form).getByLabelText('Qué se enlaza'), { target: { value: 'elemento' } });
    fireEvent.change(within(form).getByLabelText('Elemento'), { target: { value: 'K-1' } });
    fireEvent.change(within(form).getByLabelText('Parte'), { target: { value: 'colado' } });
    fireEvent.change(within(form).getByLabelText('Concepto (clave del catálogo)'), { target: { value: 'est-02110' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Enlazar' }));
    await waitFor(() =>
      expect(m.enlazar).toHaveBeenCalledWith({
        obraId: 'o1',
        data: { ranura: 'elemento:K-1:colado', concepto_clave: 'EST-02110', nivel_id: null, etapa_id: null, ubicacion: null },
      }),
    );
  });

  it('quita un enlace; un residente no ve el botón', async () => {
    const { unmount } = pintar('costos');
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el enlace de elemento:K-1:acero' }));
    await waitFor(() => expect(m.quitarEnlace).toHaveBeenCalledWith({ obraId: 'o1', enlaceId: 'e2' }));
    unmount();
    pintar('residente');
    expect(screen.queryByRole('button', { name: /Quitar el enlace/ })).not.toBeInTheDocument();
  });

  it('el concepto que no existe se dice tal cual lo responde el servidor', async () => {
    m.enlazar.mockRejectedValue(new Error('El concepto «EJ-101» no existe en el catálogo: no se inventa uno aquí.'));
    pintar('costos');
    const form = screen.getByRole('group', { name: 'Enlazar una ranura' });
    fireEvent.change(within(form).getByLabelText('Ranura'), { target: { value: 'mamposteria:sillar_amarillo' } });
    fireEvent.change(within(form).getByLabelText('Concepto (clave del catálogo)'), { target: { value: 'ej-101' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Enlazar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no se inventa uno aquí');
  });

  it('sin obra elegida no pinta tablas', () => {
    render(<PantallaParametrica obraId="" rol="costos" />);
    expect(screen.getByText('Elige una obra')).toBeInTheDocument();
  });
});
