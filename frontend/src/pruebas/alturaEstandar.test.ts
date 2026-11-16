import { describe, expect, it } from 'vitest';

import { ALTURA_ESTANDAR_DE_PARTIDA_M, alturaEstandarDe } from '@/cuantificador/alturaEstandar';
import { vanoPorDefecto } from '@/cuantificador/vanos';

describe('Altura estándar del plano (driver altura_estandar, Ola 4C)', () => {
  it('la de partida es 3.00 m, ya no 2.6', () => {
    expect(ALTURA_ESTANDAR_DE_PARTIDA_M).toBe(3);
  });

  it('toma el valor vigente del driver de la obra', () => {
    expect(alturaEstandarDe([{ clave: 'separacion', valor_vigente: '0.20' }, { clave: 'altura_estandar', valor_vigente: '2.60' }])).toBe(2.6);
    expect(alturaEstandarDe([{ clave: 'altura_estandar', valor_vigente: '3.2' }])).toBe(3.2);
  });

  it('sin driver, sin lista o con un valor que no vale cae a la de partida', () => {
    expect(alturaEstandarDe(undefined)).toBe(3);
    expect(alturaEstandarDe([])).toBe(3);
    expect(alturaEstandarDe([{ clave: 'altura_estandar', valor_vigente: '0' }])).toBe(3);
    expect(alturaEstandarDe([{ clave: 'altura_estandar', valor_vigente: 'x' }])).toBe(3);
  });

  it('el castillo se propone con la altura de la obra; los demás vanos no cambian', () => {
    expect(vanoPorDefecto('castillo').alto).toBe(3);
    expect(vanoPorDefecto('castillo', 2.6).alto).toBe(2.6);
    expect(vanoPorDefecto('puerta', 2.6).alto).toBe(2.1);
  });
});
