import { describe, expect, it } from 'vitest';

import { alternarEnSeleccion, trazosElegidos } from '@/cuantificador/seleccion';

describe('multiselección de trazos', () => {
  it('el primero que se elige es el principal', () => {
    expect(alternarEnSeleccion(null, new Set(), 'a')).toEqual({ principal: 'a', extras: new Set() });
  });
  it('Mayús + clic suma un trazo y otro clic lo quita', () => {
    const uno = alternarEnSeleccion('a', new Set(), 'b');
    expect(trazosElegidos(uno.principal, uno.extras)).toEqual(['a', 'b']);
    const dos = alternarEnSeleccion(uno.principal, uno.extras, 'c');
    expect(trazosElegidos(dos.principal, dos.extras)).toEqual(['a', 'b', 'c']);
    const sin = alternarEnSeleccion(dos.principal, dos.extras, 'b');
    expect(trazosElegidos(sin.principal, sin.extras)).toEqual(['a', 'c']);
  });
  it('quitar el principal pasa el relevo al siguiente', () => {
    const r = alternarEnSeleccion('a', new Set(['b', 'c']), 'a');
    expect(r.principal).toBe('b');
    expect([...r.extras]).toEqual(['c']);
  });
  it('quitar el único trazo deja la selección vacía', () => {
    const r = alternarEnSeleccion('a', new Set(), 'a');
    expect(r.principal).toBeNull();
    expect(trazosElegidos(r.principal, r.extras)).toEqual([]);
  });
});
