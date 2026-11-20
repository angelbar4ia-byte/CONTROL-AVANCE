/**
 * La capa «espacio» en pantalla (0143): el panel de espacios de la obra y el detalle del trazo (un polígono de losa se asigna a un espacio; un muro se
 * asigna o se comparte entre dos con su reparto). Solo se pinta lo que responde el servidor; Control de obra escribe, los demás leen.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  espacios: { current: [] as unknown[] },
  asignacion: { current: undefined as unknown },
  crear: vi.fn(),
  borrar: vi.fn(),
  asignar: vi.fn(),
}));

vi.mock('@/api/generado/espacios/espacios', () => ({
  useEspaciosDeLaObraApiV1ObrasObraIdEspaciosGet: () => ({ data: m.espacios.current }),
  useEspacioDelTrazoApiV1TrazosTrazoIdEspacioGet: () => ({ data: m.asignacion.current }),
  useCrearEspacioApiV1ObrasObraIdEspaciosPost: () => ({ mutateAsync: m.crear, isPending: false }),
  useBorrarEspacioApiV1EspaciosEspacioIdDelete: () => ({ mutateAsync: m.borrar, isPending: false }),
  useAsignarEspacioAlTrazoApiV1TrazosTrazoIdEspacioPut: () => ({ mutateAsync: m.asignar, isPending: false }),
}));
vi.mock('@/app/queryClient', () => ({ queryClient: { invalidateQueries: vi.fn() } }));

import { EspacioDelTrazo, PanelDeEspacios } from '@/cuantificador/EspaciosDeLaObra';

const ESPACIO = (id: string, nombre: string, extra: Record<string, unknown> = {}) => ({
  id, obra_id: 'o1', nombre, tipo: 'recamara', nivel_id: null, area_m2: null, orden: 0, muros: 0, losas: 0, elementos: 0, nodos: [], ...extra,
});
const ASIGNACION = (extra: Record<string, unknown> = {}) => ({
  trazo_id: 't1', espacio_id: null, espacio_comparte_id: null, reparto_pct: null, reparto: [], ...extra,
});

beforeEach(() => {
  for (const f of [m.crear, m.borrar, m.asignar]) f.mockReset();
  m.crear.mockResolvedValue({});
  m.borrar.mockResolvedValue(undefined);
  m.asignar.mockResolvedValue({});
  m.espacios.current = [ESPACIO('r', 'Recámara 1', { muros: 2, losas: 1 }), ESPACIO('b', 'Baño', { tipo: 'bano', elementos: 3 })];
  m.asignacion.current = ASIGNACION();
});

describe('PanelDeEspacios', () => {
  it('lista los espacios con lo asignado a cada uno', () => {
    render(<PanelDeEspacios obraId="o1" puedeEditar onCambio={vi.fn()} onError={vi.fn()} />);
    const r = screen.getAllByTestId('espacio')[0]!;
    expect(r).toHaveTextContent('Recámara 1');
    expect(r).toHaveTextContent('2 muros · 1 losa · 0 elementos');
    expect(screen.getAllByTestId('espacio')[1]).toHaveTextContent('Baño');
    expect(screen.getAllByTestId('espacio')[1]).toHaveTextContent('3 elementos');
  });

  it('Control de obra crea y borra espacios', async () => {
    const onCambio = vi.fn();
    render(<PanelDeEspacios obraId="o1" puedeEditar onCambio={onCambio} onError={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Nombre del espacio'), { target: { value: '  Cochera ' } });
    fireEvent.change(screen.getByLabelText('Tipo de espacio'), { target: { value: 'cochera' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar espacio' }));
    await waitFor(() => expect(m.crear).toHaveBeenCalledWith({ obraId: 'o1', data: { nombre: 'Cochera', tipo: 'cochera' } }));
    expect(onCambio).toHaveBeenCalledWith('Espacio «Cochera» creado.');
    fireEvent.click(screen.getByRole('button', { name: 'Borrar el espacio Baño' }));
    await waitFor(() => expect(m.borrar).toHaveBeenCalledWith({ espacioId: 'b' }));
  });

  it('un nombre vacío no se manda y el error del servidor se avisa', async () => {
    const onError = vi.fn();
    render(<PanelDeEspacios obraId="o1" puedeEditar onCambio={vi.fn()} onError={onError} />);
    fireEvent.click(screen.getByRole('button', { name: 'Agregar espacio' }));
    expect(onError).toHaveBeenCalledWith('Captura el nombre del espacio.');
    expect(m.crear).not.toHaveBeenCalled();
    m.crear.mockRejectedValue(new Error('Ya hay un espacio llamado «Cocina» en esta obra.'));
    fireEvent.change(screen.getByLabelText('Nombre del espacio'), { target: { value: 'Cocina' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar espacio' }));
    await waitFor(() => expect(onError).toHaveBeenLastCalledWith('Ya hay un espacio llamado «Cocina» en esta obra.'));
  });

  it('los demás roles leen: no hay formulario ni botones de borrar', () => {
    render(<PanelDeEspacios obraId="o1" puedeEditar={false} onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByRole('group', { name: 'Nuevo espacio' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Borrar el espacio/ })).not.toBeInTheDocument();
    expect(screen.getByTestId('espacios-de-la-obra')).toHaveTextContent('Solo Control de obra los edita.');
  });

  it('una obra sin espacios lo dice', () => {
    m.espacios.current = [];
    render(<PanelDeEspacios obraId="o1" puedeEditar onCambio={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByText('Esta obra no tiene espacios.')).toBeInTheDocument();
  });
});

describe('EspacioDelTrazo', () => {
  const pintar = (esMuro: boolean, puedeEditar = true) => {
    const onCambio = vi.fn();
    const onError = vi.fn();
    render(<EspacioDelTrazo obraId="o1" trazoId="t1" esMuro={esMuro} puedeEditar={puedeEditar} onCambio={onCambio} onError={onError} />);
    return { onCambio, onError };
  };

  it('un trazo sin espacio, en una obra sin espacios, no muestra nada', () => {
    m.espacios.current = [];
    const { container } = render(<EspacioDelTrazo obraId="o1" trazoId="t1" esMuro puedeEditar onCambio={vi.fn()} onError={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('asigna un muro a un espacio y dice que cuenta como siempre mientras no tiene uno', async () => {
    pintar(true);
    expect(screen.getByTestId('reparto-del-trazo')).toHaveTextContent('Sin espacio: cuenta como siempre.');
    fireEvent.change(screen.getByLabelText('Espacio del trazo'), { target: { value: 'r' } });
    await waitFor(() => expect(m.asignar).toHaveBeenCalledWith({ trazoId: 't1', data: { espacio_id: 'r', espacio_comparte_id: null, reparto_pct: null } }));
  });

  it('un muro compartido se lee con su reparto y se guarda el porcentaje del principal', async () => {
    m.asignacion.current = ASIGNACION({
      espacio_id: 'r', espacio_comparte_id: 'b', reparto_pct: '40.00',
      reparto: [{ espacio_id: 'r', fraccion: '0.4' }, { espacio_id: 'b', fraccion: '0.6' }],
    });
    const { onError } = pintar(true);
    expect(screen.getByTestId('reparto-del-trazo')).toHaveTextContent('Cuenta en: Recámara 1 40 % · Baño 60 %.');
    expect(screen.getByLabelText('Muro compartido con')).toHaveValue('b');
    fireEvent.change(screen.getByLabelText('Reparto del espacio principal en por ciento'), { target: { value: '70' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar reparto' }));
    await waitFor(() => expect(m.asignar).toHaveBeenCalledWith({ trazoId: 't1', data: { espacio_id: 'r', espacio_comparte_id: 'b', reparto_pct: '70' } }));
    // Un reparto que no vale no se manda.
    m.asignar.mockClear();
    fireEvent.change(screen.getByLabelText('Reparto del espacio principal en por ciento'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar reparto' }));
    expect(onError).toHaveBeenCalledWith('El reparto del espacio principal va de más de 0 a menos de 100 %.');
    expect(m.asignar).not.toHaveBeenCalled();
    // Vacío = mitad y mitad.
    fireEvent.change(screen.getByLabelText('Reparto del espacio principal en por ciento'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar reparto' }));
    await waitFor(() => expect(m.asignar).toHaveBeenCalledWith({ trazoId: 't1', data: { espacio_id: 'r', espacio_comparte_id: 'b', reparto_pct: null } }));
  });

  it('compartir ofrece solo los otros espacios y el muro pasa a mitad y mitad', async () => {
    m.asignacion.current = ASIGNACION({ espacio_id: 'r', reparto: [{ espacio_id: 'r', fraccion: '1' }] });
    pintar(true);
    const compartido = screen.getByLabelText('Muro compartido con');
    expect(within(compartido).getAllByRole('option').map((o) => o.textContent)).toEqual(['No se comparte', 'Baño']);
    fireEvent.change(compartido, { target: { value: 'b' } });
    await waitFor(() => expect(m.asignar).toHaveBeenCalledWith({ trazoId: 't1', data: { espacio_id: 'r', espacio_comparte_id: 'b', reparto_pct: null } }));
  });

  it('un polígono de losa se asigna a un espacio pero no se comparte', () => {
    m.asignacion.current = ASIGNACION({ espacio_id: 'r', reparto: [{ espacio_id: 'r', fraccion: '1' }] });
    pintar(false);
    expect(screen.getByText('Espacio de la losa')).toBeInTheDocument();
    expect(screen.queryByLabelText('Muro compartido con')).not.toBeInTheDocument();
  });

  it('quitar el espacio deja el trazo sin espacio', async () => {
    m.asignacion.current = ASIGNACION({ espacio_id: 'r', reparto: [{ espacio_id: 'r', fraccion: '1' }] });
    pintar(true);
    fireEvent.change(screen.getByLabelText('Espacio del trazo'), { target: { value: '' } });
    await waitFor(() => expect(m.asignar).toHaveBeenCalledWith({ trazoId: 't1', data: { espacio_id: null, espacio_comparte_id: null, reparto_pct: null } }));
  });

  it('los demás roles leen: los selectores van deshabilitados', () => {
    m.asignacion.current = ASIGNACION({ espacio_id: 'r', espacio_comparte_id: 'b', reparto: [{ espacio_id: 'r', fraccion: '0.5' }, { espacio_id: 'b', fraccion: '0.5' }] });
    pintar(true, false);
    expect(screen.getByLabelText('Espacio del trazo')).toBeDisabled();
    expect(screen.getByLabelText('Muro compartido con')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Guardar reparto' })).not.toBeInTheDocument();
  });

  it('el error del servidor se avisa', async () => {
    m.asignar.mockRejectedValue(new Error('El espacio no existe en la obra de este trazo.'));
    const { onError } = pintar(true);
    fireEvent.change(screen.getByLabelText('Espacio del trazo'), { target: { value: 'r' } });
    await waitFor(() => expect(onError).toHaveBeenCalledWith('El espacio no existe en la obra de este trazo.'));
  });
});
