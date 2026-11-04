/**
 * La pestaña «Trabajos»: cantidad del concepto (medida o presupuestada), cantidad del destajo (× factor),
 * capacidad de la cuadrilla (teórico o calculado), duración, jornales e importe; y el agrupado por concepto.
 */

import { describe, expect, it } from 'vitest';

import type { TrabajoDeObraRespuesta } from '@/api/generado/modelo';
import { agruparTrabajos, calcularTrabajo, cantidadDelConcepto } from '@/cuantificador/trabajos';

function trabajo(extra: Partial<TrabajoDeObraRespuesta> = {}): TrabajoDeObraRespuesta {
  return {
    actividad_id: 'act1',
    concepto_id: 'con1',
    concepto_clave: 'MUR-01',
    concepto_descripcion: 'Muro de block',
    concepto_unidad: 'm²',
    cantidad_presupuestada: '120',
    insumo_id: 'ins1',
    clave: 'MOA-01',
    descripcion: 'Levantado de muro',
    unidad: 'm²',
    precio: '100',
    factor: '1',
    categoria: 'destajo',
    cuadrilla_id: 'cu1',
    cuadrilla_nombre: 'Cuadrilla de albañilería',
    costo_cuadrilla: '1500',
    rendimiento_teorico: '16',
    rendimiento_calculado: '15',
    ...extra,
  } as TrabajoDeObraRespuesta;
}

describe('cantidad del concepto', () => {
  it('lo medido manda; sin medición, lo presupuestado', () => {
    expect(cantidadDelConcepto('80', '120')).toEqual({ valor: 80, fuente: 'medida en el plano' });
    expect(cantidadDelConcepto('0', '120')).toEqual({ valor: 120, fuente: 'presupuestada' });
    expect(cantidadDelConcepto(null, '120')).toEqual({ valor: 120, fuente: 'presupuestada' });
    expect(cantidadDelConcepto(undefined, null)).toEqual({ valor: 0, fuente: 'presupuestada' });
  });
});

describe('cálculo de un trabajo', () => {
  it('cantidad × factor, importe, duración con el rendimiento teórico y jornales', () => {
    const c = calcularTrabajo(trabajo({ factor: '2.5' }), { valor: 80, fuente: 'medida en el plano' });
    expect(c.cantidad).toBe(200); // 80 × 2.5
    expect(c.importe).toBe(20000); // 200 × $100
    expect(c.capacidadPorDia).toBe(16);
    expect(c.origenDeLaCapacidad).toBe('teórico');
    expect(c.dias).toBeCloseTo(12.5); // 200 ÷ 16
    expect(c.jornales).toBeCloseTo(18750); // 1500 × 12.5
    expect(c.diferencia).toBeCloseTo(1250);
  });

  it('sin teórico toma el calculado, y lo dice', () => {
    const c = calcularTrabajo(trabajo({ rendimiento_teorico: null }), { valor: 150, fuente: 'presupuestada' });
    expect(c.capacidadPorDia).toBe(15);
    expect(c.origenDeLaCapacidad).toBe('calculado');
    expect(c.dias).toBeCloseTo(10);
  });

  it('sin cuadrilla no hay capacidad, ni duración, ni jornales: no se inventan', () => {
    const c = calcularTrabajo(
      trabajo({ cuadrilla_id: null, costo_cuadrilla: null, rendimiento_teorico: null, rendimiento_calculado: null }),
      { valor: 100, fuente: 'presupuestada' },
    );
    expect(c.capacidadPorDia).toBeNull();
    expect(c.dias).toBeNull();
    expect(c.jornales).toBeNull();
    expect(c.diferencia).toBeNull();
    expect(c.importe).toBe(10000); // el importe no depende de la cuadrilla
  });

  it('un rendimiento de cero no divide', () => {
    const c = calcularTrabajo(trabajo({ rendimiento_teorico: '0', rendimiento_calculado: '0' }), { valor: 10, fuente: 'presupuestada' });
    expect(c.dias).toBeNull();
  });
});

describe('agrupado por concepto', () => {
  const lista = [
    trabajo(),
    trabajo({ insumo_id: 'ins2', clave: 'SUB-01', descripcion: 'Aplanado', cuadrilla_nombre: null }),
    trabajo({ actividad_id: 'act2', concepto_clave: 'CIM-01', concepto_descripcion: 'Zapata', insumo_id: 'ins3', clave: 'MOC-01', descripcion: 'Colado' }),
  ];
  const medidas = new Map<string, string>([['act1', '80']]);

  it('agrupa por concepto, en orden de clave, con su cantidad', () => {
    const grupos = agruparTrabajos(lista, { medidaPorActividad: medidas });
    expect(grupos.map((g) => g.conceptoClave)).toEqual(['CIM-01', 'MUR-01']);
    expect(grupos[1]?.trabajos.map((t) => t.trabajo.clave)).toEqual(['MOA-01', 'SUB-01']);
    expect(grupos[1]?.cantidadDelConcepto).toEqual({ valor: 80, fuente: 'medida en el plano' });
    expect(grupos[0]?.cantidadDelConcepto.fuente).toBe('presupuestada');
  });

  it('busca por trabajo, concepto o cuadrilla', () => {
    expect(agruparTrabajos(lista, { medidaPorActividad: medidas, busqueda: 'zapata' }).map((g) => g.conceptoClave)).toEqual(['CIM-01']);
    expect(agruparTrabajos(lista, { medidaPorActividad: medidas, busqueda: 'albañilería' }).flatMap((g) => g.trabajos.map((t) => t.trabajo.clave))).toContain('MOA-01');
    expect(agruparTrabajos(lista, { medidaPorActividad: medidas, busqueda: 'no existe' })).toEqual([]);
  });
});
