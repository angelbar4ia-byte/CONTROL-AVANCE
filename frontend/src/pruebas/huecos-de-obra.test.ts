/**
 * Los huecos de una obra real — `src/extras/reglas.ts` y
 * `src/revisiones/reglas.ts` (§11.2, §7.8).
 *
 * Dos pantallas que existen porque la obra se mueve: el trabajo que no estaba
 * en el prototipo y la evidencia de que lo hecho está bien hecho.
 */

import { describe, expect, it } from 'vitest';

import { ModoPago } from '@/api/generado/modelo';
import {
  campoDePrecio,
  etiquetaModoPago,
  extraCompleto,
  type FormularioExtra,
} from '@/extras/reglas';
import {
  CALIDAD_MAXIMA,
  CALIDAD_MINIMA,
  etiquetaCalidad,
  puedeRegistrarRevision,
  tonoCalidad,
} from '@/revisiones/reglas';

function formulario(parcial: Partial<FormularioExtra> = {}): FormularioExtra {
  return {
    descripcion: 'Demoler muro',
    ordenCambio: 'OC-2026-014',
    cantBase: '12.5',
    modoPago: ModoPago.destajo,
    precio: '350',
    duracionDias: '1',
    ...parcial,
  };
}

describe('extra-catálogo: qué precio pide cada modo (§7.3)', () => {
  it('el destajo pide precio de destajo', () => {
    expect(campoDePrecio(ModoPago.destajo)).toBe('precio_destajo');
  });

  it('los otros dos piden el unitario', () => {
    // Se manda el del modo elegido y **solo** ese: pedir los dos obligaría a
    // inventar un número para el que no aplica.
    expect(campoDePrecio(ModoPago.concepto)).toBe('precio_unitario');
    expect(campoDePrecio(ModoPago.subcontrato)).toBe('precio_unitario');
  });

  it('los tres modos tienen etiqueta legible', () => {
    for (const modo of Object.values(ModoPago)) {
      expect(etiquetaModoPago(modo)).not.toBe(modo);
    }
  });

  it('un modo desconocido se muestra tal cual', () => {
    expect(etiquetaModoPago('inventado')).toBe('inventado');
  });
});

describe('extra-catálogo: cuándo se puede enviar', () => {
  it('un formulario completo, sí', () => {
    expect(extraCompleto(formulario())).toBe(true);
  });

  it('sin orden de cambio, no: es lo que autoriza el trabajo', () => {
    expect(extraCompleto(formulario({ ordenCambio: '  ' }))).toBe(false);
  });

  it('sin descripción, no: no se podría revisar ni estimar', () => {
    expect(extraCompleto(formulario({ descripcion: '' }))).toBe(false);
  });

  it('sin precio, no: lo que no se estima no se cobra (§11.3 E)', () => {
    expect(extraCompleto(formulario({ precio: '0' }))).toBe(false);
    expect(extraCompleto(formulario({ precio: '' }))).toBe(false);
  });

  it('con cantidad cero o negativa, no', () => {
    expect(extraCompleto(formulario({ cantBase: '0' }))).toBe(false);
    expect(extraCompleto(formulario({ cantBase: '-3' }))).toBe(false);
  });

  it('un número mal escrito no pasa como válido', () => {
    expect(extraCompleto(formulario({ cantBase: 'doce' }))).toBe(false);
  });
});

describe('revisión física: escala de calidad (§7.8)', () => {
  it('la escala es la del dominio', () => {
    expect(CALIDAD_MINIMA).toBe(1);
    expect(CALIDAD_MAXIMA).toBe(5);
  });

  it('cada número tiene su significado', () => {
    // Un «3» sin etiqueta obliga a cada quien a inventarse la escala, y dos
    // personas calificando distinto hacen que el promedio no signifique nada.
    for (let valor = CALIDAD_MINIMA; valor <= CALIDAD_MAXIMA; valor += 1) {
      expect(etiquetaCalidad(valor)).not.toBe(String(valor));
    }
  });

  it('lo malo y lo bueno no se ven igual', () => {
    expect(tonoCalidad(1)).toBe('danger');
    expect(tonoCalidad(2)).toBe('danger');
    expect(tonoCalidad(3)).toBe('warn');
    expect(tonoCalidad(5)).toBe('ok');
  });
});

describe('revisión física: quién registra (§11.2)', () => {
  it('Control de obra', () => {
    expect(puedeRegistrarRevision('control_obra')).toBe(true);
  });

  it('los demás la ven pero no la registran', () => {
    expect(puedeRegistrarRevision('residente')).toBe(false);
    expect(puedeRegistrarRevision('supervisor')).toBe(false);
    expect(puedeRegistrarRevision('super_intendente')).toBe(false);
  });
});
