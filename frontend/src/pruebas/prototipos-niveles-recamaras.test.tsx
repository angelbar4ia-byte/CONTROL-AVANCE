/**
 * Niveles (= plantas) y recámaras de un prototipo, editables en la tabla.
 * Solo quien configura la estructura ve los controles; los demás ven el dato.
 */

import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { CeldasNivelesYRecamaras } from '@/proyectos/NivelesYRecamaras';


const PROTOTIPO = { id: 'p-1', clave: 'CAS-00001', niveles: null, recamaras: 2 };

function pintar(editable: boolean) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <table>
        <tbody>
          <tr>
            <CeldasNivelesYRecamaras prototipo={PROTOTIPO} editable={editable} />
          </tr>
        </tbody>
      </table>
    </QueryClientProvider>,
  );
}

describe('niveles y recámaras del prototipo', () => {
  it('sin permiso solo muestra el dato', () => {
    pintar(false);
    expect(screen.queryByLabelText('Niveles de CAS-00001')).toBeNull();
    expect(screen.getByText('—')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('con permiso ofrece 1 o 2 niveles y recámaras', () => {
    pintar(true);
    const niveles = screen.getByLabelText('Niveles de CAS-00001') as HTMLSelectElement;
    expect(Array.from(niveles.options).map((o) => o.value)).toEqual(['', '1', '2']);
    expect((screen.getByLabelText('Recámaras de CAS-00001') as HTMLInputElement).value).toBe('2');
  });

  it('una recámara negativa no se envía', () => {
    pintar(true);
    const entrada = screen.getByLabelText('Recámaras de CAS-00001');
    fireEvent.change(entrada, { target: { value: '-1' } });
    fireEvent.blur(entrada);
    expect(screen.getByRole('alert').textContent).toMatch(/entero, cero o más/);
  });
});
