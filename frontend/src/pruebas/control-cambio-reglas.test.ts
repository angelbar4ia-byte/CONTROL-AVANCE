/**
 * Quién resuelve un control de cambio, y qué dice cada estatus (§4, §11.3).
 *
 * Lo que fijan:
 *
 *  1. **Ni el residente ni el supervisor resuelven.** Autorizar lo que uno
 *     mismo pidió convierte el control en un trámite — misma separación que el
 *     cierre de actividad.
 *  2. **Los tres estatus tienen tono propio**, para que la bandeja se lea de un
 *     vistazo sin abrir cada fila.
 */

import { describe, expect, it } from 'vitest';

import { etiquetaTipoCambio, puedeResolver, tonoEstatusCambio } from '@/control-cambio/reglas';

describe('quién resuelve', () => {
  it('Control de obra y el Super intendente', () => {
    expect(puedeResolver('control_obra')).toBe(true);
    expect(puedeResolver('super_intendente')).toBe(true);
  });

  it('el residente no, ni sobre lo que él mismo pidió', () => {
    expect(puedeResolver('residente')).toBe(false);
  });

  it('el supervisor tampoco: no es su rol en este flujo', () => {
    expect(puedeResolver('supervisor')).toBe(false);
  });
});

describe('el tono de cada estatus', () => {
  it('solicitado se ve como pendiente', () => {
    expect(tonoEstatusCambio('solicitado')).toBe('warn');
  });

  it('autorizado se ve resuelto en positivo', () => {
    expect(tonoEstatusCambio('autorizado')).toBe('ok');
  });

  it('rechazado se ve resuelto en negativo', () => {
    expect(tonoEstatusCambio('rechazado')).toBe('danger');
  });

  it('un estatus desconocido no rompe: cae a neutro', () => {
    expect(tonoEstatusCambio('lo-que-sea')).toBe('outline');
  });
});

describe('la etiqueta del tipo', () => {
  it('traduce los cuatro tipos del dominio', () => {
    expect(etiquetaTipoCambio('extra_catalogo')).toBe('Más cantidad');
    expect(etiquetaTipoCambio('fuera_catalogo')).toBe('Fuera de catálogo');
    expect(etiquetaTipoCambio('sustitucion')).toBe('Sustitución');
    expect(etiquetaTipoCambio('alta_catalogo')).toBe('Alta de catálogo');
  });
});
