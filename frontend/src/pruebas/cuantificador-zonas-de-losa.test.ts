import { describe, expect, it } from 'vitest';

import { etiquetasDeZonas, textoDeCota, textoDeMetros } from '@/cuantificador/zonasDeLosa';

describe('zonas de losa: textos', () => {
  it('escribe las cotas con su signo', () => {
    expect(textoDeCota('3')).toMatch(/^\+3[.,]00 m$/);
    expect(textoDeCota('-0.3')).toMatch(/^−0[.,]30 m$/);
    expect(textoDeMetros('4.2')).toMatch(/^4[.,]20 m$/);
  });

  it('etiqueta cada losa con su zona y cada punto de nivel con su rótulo', () => {
    const zonas = [{ id: 'z', nombre: 'Entrepiso 3.00', altura_libre_m: '3.000', espesor_m: '0.120' }];
    const e = etiquetasDeZonas(
      [
        { geometry: { type: 'Polygon', coordinates: [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]] }, properties: { losa_zona_id: 'z', losa_espesor_m: '0.150' } },
        { geometry: { type: 'Point', coordinates: [9, 9] }, properties: { nivel_exterior_m: '-0.300', rotulo: 'Banqueta' } },
        { geometry: { type: 'Point', coordinates: [1, 1] }, properties: {} },
      ],
      zonas,
    );
    expect(e).toHaveLength(2);
    expect(e[0]?.titulo).toBe('Losa · Entrepiso 3.00');
    expect(e[0]?.texto).toContain('(subzona)');
    expect(e[1]?.titulo).toBe('Nivel exterior · Banqueta');
    expect(e[1]?.texto).toMatch(/^−0[.,]30 m$/);
  });
});
