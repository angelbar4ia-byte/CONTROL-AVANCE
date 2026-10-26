/**
 * Reflejo de UX de las desviaciones (cerebro MODELO.md §5g): etiquetas del
 * vocabulario controlado y el porcentaje «sin causa», que es un estado válido y
 * se muestra sin penalizarlo.
 */

import { describe, expect, it } from 'vitest';

import { etiquetaCausa, etiquetaFactor, resumenDeCausas } from '@/desviaciones/reglas';
import { navegacionDe, rutaPermitida, type Rol } from '@/shell/navegacion';

describe('etiquetas', () => {
  it('traduce el vocabulario controlado y humaniza lo que no conoce', () => {
    expect(etiquetaCausa('retrabajo')).toBe('Retrabajo');
    expect(etiquetaCausa('merma_por_dano_clima_o_robo')).toBe('Merma por daño, clima o robo');
    expect(etiquetaCausa('causa_nueva_del_backend')).toBe('Causa nueva del backend');
  });

  it('los dos factores nunca se mezclan', () => {
    expect(etiquetaFactor('precio')).toBe('Precio');
    expect(etiquetaFactor('consumo')).toBe('Consumo');
  });
});

describe('resumenDeCausas', () => {
  it('cuenta las que están sin causa y su porcentaje', () => {
    const r = resumenDeCausas([{ causa: null }, { causa: 'retrabajo' }, { causa: null }, { causa: 'mercado' }]);
    expect(r).toEqual({ total: 4, sinCausa: 2, pctSinCausa: 50 });
  });

  it('sin desviaciones no divide entre cero', () => {
    expect(resumenDeCausas([])).toEqual({ total: 0, sinCausa: 0, pctSinCausa: 0 });
  });
});

describe('navegación', () => {
  it('los cuatro roles ven las desviaciones de las obras de su alcance', () => {
    const roles: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];
    for (const rol of roles) {
      expect(rutaPermitida(rol, '/desviaciones')).toBe(true);
      expect(navegacionDe(rol).flatMap((s) => s.items.map((i) => i.a))).toContain('/desviaciones');
    }
  });
});
