/**
 * Reflejo de UX del control de materiales — `src/materiales/reglas.ts` y
 * `src/materiales/formulario.ts` (§3.6, §7.7, §10.5, §11.2).
 *
 * Lo que estas pruebas protegen es la frontera: la web **muestra** la
 * valuación y el IVA que calculó el backend (§10.5) y nunca los recalcula.
 * Por eso no hay ninguna prueba de "importe = cantidad × costo": si algún día
 * aparece una, es la señal de que la regla se duplicó en el front.
 */

import { describe, expect, it } from 'vitest';

import {
  UMBRAL_DESVIACION_PCT,
  etiquetaOrigenValuacion,
  etiquetaSigno,
  fueraDeUmbral,
  origenValuacion,
  puedeRegistrarSalida,
  puedeVerConsumo,
  puedeVerSalidas,
  signoCoincide,
  tonoDesviacion,
} from '@/materiales/reglas';
import {
  formularioSalidaVacio,
  hoyISO,
  peticionDeSalida,
  salidaCompleta,
} from '@/materiales/formulario';

describe('tonoDesviacion (§3.6: umbral ±5%)', () => {
  it('el umbral por defecto del spec es 5%', () => {
    expect(UMBRAL_DESVIACION_PCT).toBe(5);
  });

  it('dentro de ±5% marca ok', () => {
    expect(tonoDesviacion('0')).toBe('ok');
    expect(tonoDesviacion('4.99')).toBe('ok');
    expect(tonoDesviacion('-5')).toBe('ok');
  });

  it('fuera de ±5% marca alerta, en cualquiera de los dos sentidos', () => {
    expect(tonoDesviacion('5.01')).toBe('danger');
    expect(tonoDesviacion('-12.4')).toBe('danger');
  });

  it('sin teórico contra qué comparar (null) queda neutro, no en alerta', () => {
    expect(tonoDesviacion(null)).toBe('outline');
    expect(tonoDesviacion('')).toBe('outline');
    expect(fueraDeUmbral(null)).toBe(false);
  });
});

describe('origenValuacion (§10.5: las tres reglas de valuación)', () => {
  it('con teórico y real es un cruce → costo último', () => {
    expect(origenValuacion('10', '9')).toBe('cruce');
    expect(etiquetaOrigenValuacion('cruce')).toContain('último');
  });

  it('esperado sin salida usa el precio base del catálogo', () => {
    expect(origenValuacion('10', '0')).toBe('solo_explosion');
    expect(etiquetaOrigenValuacion('solo_explosion')).toContain('base');
  });

  it('consumido sin estar en la explosión usa costo último', () => {
    expect(origenValuacion('0', '4')).toBe('solo_almacen');
    expect(etiquetaOrigenValuacion('solo_almacen')).toContain('último');
  });
});

describe('permisos reflejados de §11.2 "Materiales"', () => {
  it('solo Control de obra registra salidas (POST /obras/{id}/salidas — C)', () => {
    expect(puedeRegistrarSalida('control_obra')).toBe(true);
    expect(puedeRegistrarSalida('residente')).toBe(false);
    expect(puedeRegistrarSalida('supervisor')).toBe(false);
    expect(puedeRegistrarSalida('super_intendente')).toBe(false);
  });

  it('la bandeja de salidas es (C, SI)', () => {
    expect(puedeVerSalidas('control_obra')).toBe(true);
    expect(puedeVerSalidas('super_intendente')).toBe(true);
    expect(puedeVerSalidas('residente')).toBe(false);
  });

  it('el consumo es (R lectura, C, SI); el Supervisor no lo trae en su sidebar', () => {
    expect(puedeVerConsumo('residente')).toBe(true);
    expect(puedeVerConsumo('control_obra')).toBe(true);
    expect(puedeVerConsumo('super_intendente')).toBe(true);
    expect(puedeVerConsumo('supervisor')).toBe(false);
  });
});

describe('signoCoincide (§10.5: el signo viene con la cantidad)', () => {
  it('una salida (motivo −1) espera cantidad negativa', () => {
    expect(signoCoincide(-1, '-12.5')).toBe(true);
    expect(signoCoincide(-1, '12.5')).toBe(false);
  });

  it('una entrada (motivo +1) espera cantidad positiva', () => {
    expect(signoCoincide(1, '30')).toBe(true);
    expect(signoCoincide(1, '-30')).toBe(false);
  });

  it('no avisa mientras el campo está vacío o en cero: el 409 es del backend', () => {
    expect(signoCoincide(-1, '')).toBe(true);
    expect(signoCoincide(-1, '0')).toBe(true);
    expect(signoCoincide(-1, '-')).toBe(true);
  });

  it('etiqueta el signo en el idioma del almacén', () => {
    expect(etiquetaSigno(-1)).toContain('salida');
    expect(etiquetaSigno(1)).toContain('entrada');
  });
});

describe('peticionDeSalida (DTO en el borde, §11.2)', () => {
  const base = {
    ...formularioSalidaVacio('2026-08-17'),
    insumoId: 'ins-1',
    motivoId: 'mot-1',
    cantidad: ' -12.500000 ',
    costo: ' -1450.00 ',
  };

  it('manda cantidad y costo como string decimal, sin convertir a number', () => {
    const dto = peticionDeSalida(base);
    expect(dto.cantidad).toBe('-12.500000');
    expect(dto.costo).toBe('-1450.00');
    expect(typeof dto.cantidad).toBe('string');
  });

  it('los opcionales vacíos se omiten en vez de mandarse en blanco', () => {
    const dto = peticionDeSalida(base);
    expect(dto.concepto_id).toBeUndefined();
    expect(dto.contratista_id).toBeUndefined();
  });

  it('conserva concepto y contratista cuando el usuario los eligió', () => {
    const dto = peticionDeSalida({ ...base, conceptoId: 'c-1', contratistaId: 'k-1' });
    expect(dto.concepto_id).toBe('c-1');
    expect(dto.contratista_id).toBe('k-1');
  });

  it('un costo vacío viaja como cero, no como cadena vacía', () => {
    expect(peticionDeSalida({ ...base, costo: '' }).costo).toBe('0');
  });
});

describe('salidaCompleta (presencia, no validez)', () => {
  it('exige material, motivo, cantidad y fecha', () => {
    const vacio = formularioSalidaVacio('2026-08-17');
    expect(salidaCompleta(vacio)).toBe(false);
    expect(
      salidaCompleta({ ...vacio, insumoId: 'i', motivoId: 'm', cantidad: '-1' }),
    ).toBe(true);
  });

  it('no juzga el signo ni el rango: eso lo decide el endpoint', () => {
    const formulario = {
      ...formularioSalidaVacio('2026-08-17'),
      insumoId: 'i',
      motivoId: 'm',
      cantidad: '0',
    };
    expect(salidaCompleta(formulario)).toBe(true);
  });
});

describe('hoyISO', () => {
  it('usa la fecha local, no UTC: el contrato espera un `date` sin hora', () => {
    // 1 de enero a las 20:00 en México sigue siendo 1 de enero, aunque en
    // UTC ya sea día 2 — el mismo corrimiento que corrige `fmtFecha`.
    expect(hoyISO(new Date(2026, 0, 1, 20, 30))).toBe('2026-01-01');
    expect(hoyISO(new Date(2026, 11, 31))).toBe('2026-12-31');
  });
});
