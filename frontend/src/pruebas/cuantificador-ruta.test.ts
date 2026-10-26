import { describe, expect, it } from 'vitest';

import { rutaDelModulo } from '@/cuantificador/ruta';

describe('«Abrir en el módulo» (D-532)', () => {
  it('lleva la obra, el plano y la actividad', () => {
    const ruta = rutaDelModulo({ obraId: 'o1', planoId: 'p1', actividadId: 'a1' });
    const [camino, busqueda] = ruta.split('?');
    expect(camino).toBe('/cuantificador');
    const params = new URLSearchParams(busqueda);
    expect(params.get('obra')).toBe('o1');
    expect(params.get('plano')).toBe('p1');
    expect(params.get('actividad')).toBe('a1');
  });

  it('sin plano ni actividad solo lleva la obra', () => {
    expect(rutaDelModulo({ obraId: 'o1' })).toBe('/cuantificador?obra=o1');
  });

  it('escapa lo que no es seguro en una URL', () => {
    const ruta = rutaDelModulo({ obraId: 'a&b=c' });
    expect(new URLSearchParams(ruta.split('?')[1]).get('obra')).toBe('a&b=c');
  });
});
