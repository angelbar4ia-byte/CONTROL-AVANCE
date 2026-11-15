/**
 * Costos propone, Control de obra autoriza (plan de elementos de muro, fase I): el estado y las versiones del elemento, el concepto
 * nuevo pendiente y «Confirmar cálculo → actualizar APU» con su conciliación. Solo se pinta lo que responde el servidor.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  autorizarElemento: vi.fn(),
  autorizarRevision: vi.fn(),
  rechazarRevision: vi.fn(),
  autorizarConcepto: vi.fn(),
  confirmar: vi.fn(),
  autorizacion: { current: undefined as unknown },
  plan: { current: undefined as unknown },
  conciliacion: { current: undefined as unknown },
  conceptos: { current: undefined as unknown },
}));

vi.mock('@/api/generado/elementos-parametricos/elementos-parametricos', () => ({
  getAutorizacionDelElementoApiV1ElementosParametricosElementoIdAutorizacionGetQueryKey: (id: string) => ['autorizacion', id],
  getListarElementosParametricosApiV1ElementosParametricosGetQueryKey: () => ['elementos'],
  getConceptosPorContextoApiV1ElementosParametricosElementoIdConceptosPorContextoGetQueryKey: (id: string) => ['conceptos', id],
  getConciliacionDelConceptoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdConciliacionGetQueryKey: (e: string, f: string) => ['conciliacion', e, f],
  getPlanDeApuApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdApuGetQueryKey: (e: string, f: string) => ['plan', e, f],
  useAutorizacionDelElementoApiV1ElementosParametricosElementoIdAutorizacionGet: () => ({ data: m.autorizacion.current }),
  useAutorizarElementoApiV1ElementosParametricosElementoIdAutorizarPost: () => ({ mutateAsync: m.autorizarElemento, isPending: false }),
  useAutorizarRevisionApiV1RevisionesDeElementosRevisionIdAutorizarPost: () => ({ mutateAsync: m.autorizarRevision, isPending: false }),
  useRechazarRevisionApiV1RevisionesDeElementosRevisionIdRechazarPost: () => ({ mutateAsync: m.rechazarRevision, isPending: false }),
  useAutorizarConceptoDelElementoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdAutorizarPost: () => ({
    mutateAsync: m.autorizarConcepto,
    isPending: false,
  }),
  useConfirmarCalculoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdApuConfirmarPost: () => ({ mutateAsync: m.confirmar, isPending: false }),
  usePlanDeApuApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdApuGet: () => ({ data: m.plan.current }),
  useConciliacionDelConceptoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdConciliacionGet: () => ({ data: m.conciliacion.current }),
  useConceptosPorContextoApiV1ElementosParametricosElementoIdConceptosPorContextoGet: () => ({
    data: m.conceptos.current,
    isSuccess: true,
  }),
}));

import { ApuDelConcepto } from '@/cuantificador/ApuDelConcepto';
import { AutorizacionDelElemento } from '@/cuantificador/AutorizacionDelElemento';
import { ConceptosPorContexto } from '@/cuantificador/ConceptosPorContexto';

const version = (o: Record<string, unknown>) => ({
  id: 'v', clase: 'elemento', estado: 'autorizada', version: 1, fila_id: null, concepto_clave: null, resumen: 'Alta', propuso_id: null,
  propuso_nombre: null, propuso_rol: null, propuesto_en: '2026-11-01T10:00:00Z', decidio_id: null, decidio_nombre: null, decidio_rol: null,
  decidido_en: '2026-11-01T10:00:00Z', motivo: null, ...o,
});

beforeEach(() => {
  for (const f of [m.autorizarElemento, m.autorizarRevision, m.rechazarRevision, m.autorizarConcepto, m.confirmar]) f.mockReset();
});

describe('AutorizacionDelElemento', () => {
  const pendiente = {
    elemento_id: 'e1',
    estado: 'pendiente',
    version: null,
    versiones: [
      version({ id: 'r1', clase: 'apu', estado: 'pendiente', version: null, fila_id: 'f1', concepto_clave: 'EST-02110', resumen: 'APU de EST-02110: MEZ-01020 0.023625 → 0.0225', propuso_nombre: 'Ana de Costos', propuso_rol: 'costos', decidido_en: null }),
    ],
  };

  it('Costos ve el elemento provisional y espera: no hay botones de autorizar', () => {
    m.autorizacion.current = pendiente;
    render(<AutorizacionDelElemento elementoId="e1" clave="K-1" puedeAutorizar={false} onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByText(/Nuevo, pendiente de autorizar: se usa como provisional/)).toBeTruthy();
    expect(screen.getByText('sin versión')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Autorizar/ })).toBeNull();
    expect(screen.getAllByText(/Espera la autorización de Control de obra/).length).toBeGreaterThan(0);
  });

  it('Control de obra autoriza el elemento nuevo y la propuesta, y rechaza con motivo', async () => {
    m.autorizacion.current = pendiente;
    m.autorizarElemento.mockResolvedValue({ version: 1 });
    m.autorizarRevision.mockResolvedValue({ version: 2 });
    m.rechazarRevision.mockResolvedValue(undefined);
    const onCambio = vi.fn();
    vi.spyOn(window, 'prompt').mockReturnValue('No es el armado acordado');
    render(<AutorizacionDelElemento elementoId="e1" clave="K-1" puedeAutorizar onCambio={onCambio} onError={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar y crear v1' }));
    await waitFor(() => expect(m.autorizarElemento).toHaveBeenCalledWith({ elementoId: 'e1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith('K-1 autorizado: versión 1.'));
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar' }));
    await waitFor(() => expect(m.autorizarRevision).toHaveBeenCalledWith({ revisionId: 'r1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Rechazar' }));
    await waitFor(() => expect(m.rechazarRevision).toHaveBeenCalledWith({ revisionId: 'r1', data: { motivo: 'No es el armado acordado' } }));
  });

  it('el historial dice quién propuso, quién autorizó y cuándo', () => {
    m.autorizacion.current = {
      elemento_id: 'e1',
      estado: 'autorizado',
      version: 2,
      versiones: [
        version({ id: 'a', version: 2, resumen: 'Nombre: K-1 → K-1 reforzado', propuso_nombre: 'Ana de Costos', decidio_nombre: 'Beto de Control' }),
        version({ id: 'b', version: 1, resumen: 'Alta del elemento K-1' }),
      ],
    };
    render(<AutorizacionDelElemento elementoId="e1" clave="K-1" puedeAutorizar={false} onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByText('v2', { selector: '[data-version-del-elemento]' })).toBeTruthy();
    const fila = screen.getByText('Nombre: K-1 → K-1 reforzado').closest('tr');
    expect(fila?.textContent).toContain('Ana de Costos');
    expect(fila?.textContent).toContain('Beto de Control');
    expect(fila?.textContent).toContain('v2');
  });
});

describe('ConceptosPorContexto', () => {
  const concepto = (o: Record<string, unknown>) => ({
    id: 'f1', concepto_id: null, clave: 'EJ-420', descripcion: 'Castillo de entrepiso', descripcion_catalogo: null, nuevo: true, estado: 'propuesto',
    unidad: 'ml', ranura: 'colado', toma: {}, nivel_min: null, nivel_max: null, ubicacion: null, contexto: 'Todo contexto', alto_hasta_m: null,
    elegido: null, version: null, con_propuesta: false, ...o,
  });

  it('un concepto nuevo no cuenta hasta autorizarse y solo Control de obra lo autoriza', async () => {
    m.conceptos.current = { conceptos: [concepto({})], avisos: [] };
    m.autorizarConcepto.mockResolvedValue({ version: 1 });
    const onCambio = vi.fn();
    const { rerender } = render(<ConceptosPorContexto elementoId="e1" clave="K-1" onCambio={onCambio} />);
    expect(screen.getByText(/No cuenta en el presupuesto hasta autorizarse/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Autorizar concepto' })).toBeNull();
    rerender(<ConceptosPorContexto elementoId="e1" clave="K-1" puedeAutorizar onCambio={onCambio} />);
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar concepto' }));
    await waitFor(() => expect(m.autorizarConcepto).toHaveBeenCalledWith({ elementoId: 'e1', filaId: 'f1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(expect.stringContaining('autorizado sin precio: versión 1')));
  });

  it('un concepto autorizado muestra su versión y la propuesta de APU pendiente', () => {
    m.conceptos.current = { conceptos: [concepto({ estado: 'autorizado', nuevo: false, concepto_id: 'c1', clave: 'EST-02110', version: 2, con_propuesta: true })], avisos: [] };
    render(<ConceptosPorContexto elementoId="e1" clave="K-1" puedeAutorizar />);
    expect(screen.getByText('v2')).toBeTruthy();
    expect(screen.getByText('APU: propuesta pendiente')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Autorizar concepto' })).toBeNull();
  });
});

describe('ApuDelConcepto', () => {
  const plan = (o: Record<string, unknown>) => ({
    fila_id: 'f1', concepto_clave: 'EST-02110', concepto_descripcion: 'x', unidad: 'ml', sin_catalogo: false, manda: 'apu', avisos: [], hay_cambios: true,
    pu_vigente: 100, pu_con_el_calculo: 96.5, propuesta_pendiente: null,
    filas: [
      { clave: 'MEZ-01020', descripcion: 'CONCRETO', unidad: 'm3', apu: 0.023625, calculo: 0.0225, diferencia_pct: -4.76, marca: '≈', accion: 'actualizar', motivo: '' },
      { clave: 'MAD-00004', descripcion: 'TABLAS', unidad: 'pza', apu: 0.01, calculo: null, diferencia_pct: null, marca: 'solo_catalogo', accion: 'solo_apu', motivo: 'Manda el APU' },
    ],
    ...o,
  });
  const propiedades = { elementoId: 'e1', filaId: 'f1', concepto: 'EST-02110', onCambio: vi.fn(), onError: vi.fn() };

  it('pone el APU contra el cálculo y el precio unitario, y propone si no es Control de obra', async () => {
    m.plan.current = plan({});
    m.conciliacion.current = undefined;
    m.confirmar.mockResolvedValue({ aplicado: false, revision_id: 'r', version: null, resumen: '', pu_antes: 100, pu_despues: 96.5 });
    const onCambio = vi.fn();
    render(<ApuDelConcepto {...propiedades} puedeAutorizar={false} onCambio={onCambio} />);
    expect(screen.getByText('Se actualiza')).toBeTruthy();
    expect(screen.getByText('Solo el APU: manda el APU')).toBeTruthy();
    expect(screen.getByText(/Precio unitario: \$100\.00 → \$96\.50/)).toBeTruthy();
    expect(screen.getByText(/Propone una versión nueva del APU/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cálculo → actualizar APU' }));
    await waitFor(() => expect(m.confirmar).toHaveBeenCalledWith({ elementoId: 'e1', filaId: 'f1' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(expect.stringContaining('quedó propuesta; rige el APU vigente')));
  });

  it('Control de obra lo aplica y se avisa la versión; sin cambios o con propuesta pendiente el botón no se pulsa', async () => {
    m.plan.current = plan({});
    m.confirmar.mockResolvedValue({ aplicado: true, revision_id: 'r', version: 3, resumen: '', pu_antes: 100, pu_despues: 96.5 });
    const onCambio = vi.fn();
    const { rerender } = render(<ApuDelConcepto {...propiedades} puedeAutorizar onCambio={onCambio} />);
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cálculo → actualizar APU' }));
    await waitFor(() => expect(onCambio).toHaveBeenCalledWith('EST-02110: APU actualizado, versión 3.'));
    m.plan.current = plan({ hay_cambios: false });
    rerender(<ApuDelConcepto {...propiedades} puedeAutorizar onCambio={onCambio} />);
    expect((screen.getByRole('button', { name: 'Confirmar cálculo → actualizar APU' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('El cálculo ya coincide con el APU.')).toBeTruthy();
    m.plan.current = plan({ propuesta_pendiente: 'r1' });
    rerender(<ApuDelConcepto {...propiedades} puedeAutorizar onCambio={onCambio} />);
    expect((screen.getByRole('button', { name: 'Confirmar cálculo → actualizar APU' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Propuesta pendiente de autorización: rige el APU vigente/)).toBeTruthy();
  });

  it('un concepto nuevo no tiene APU y la conciliación va en las dos direcciones sin inventar precios', () => {
    m.plan.current = plan({ sin_catalogo: true });
    const { unmount } = render(<ApuDelConcepto {...propiedades} puedeAutorizar />);
    expect(screen.getByText(/Concepto nuevo: aún no tiene APU en el catálogo/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Confirmar cálculo → actualizar APU' })).toBeNull();
    unmount();
    m.plan.current = plan({});
    m.conciliacion.current = {
      fila_id: 'f1', concepto_clave: 'EST-02110', unidad: 'ml', sin_catalogo: false, cantidad: 100, manda: 'apu', tolerancia_pct: 3, importe_apu: 4000, importe_salida: 3800,
      sin_precio: true, resumen: {}, avisos: [],
      filas: [
        { clave: 'MEZ-01020', descripcion: 'CONCRETO', unidad: 'm3', estimado: 2.3625, salida: 2.25, diferencia_cantidad: -0.1125, diferencia_pct: -4.76, costo: 1500, importe_apu: 3543.75, importe_salida: 3375, diferencia_importe: -168.75, marca: '≈', sentido: 'difieren', avisa: true },
        { clave: 'XXX-1', descripcion: 'SIN PRECIO', unidad: 'kg', estimado: null, salida: 2, diferencia_cantidad: null, diferencia_pct: null, costo: null, importe_apu: null, importe_salida: null, diferencia_importe: null, marca: 'solo_elemento', sentido: 'salida_sin_estimado', avisa: false },
      ],
    };
    render(<ApuDelConcepto {...propiedades} puedeAutorizar />);
    const mez = screen.getByText('MEZ-01020', { selector: '[data-conciliado] td' }).closest('tr');
    expect(mez?.getAttribute('data-sentido')).toBe('difieren');
    expect(mez?.textContent).toContain('Difieren');
    const sin = screen.getByText('XXX-1', { selector: '[data-conciliado] td' }).closest('tr');
    expect(sin?.textContent).toContain('Salida sin estimado');
    expect(screen.getByText(/su importe queda vacío \(no se inventa\)/)).toBeTruthy();
  });
});
