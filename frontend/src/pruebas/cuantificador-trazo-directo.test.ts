import { describe, expect, it } from 'vitest';

import { factorDeLaMedida, medidaDirecta, trazoPeticion } from '@/cuantificador/trazoPeticion';

describe('Guardado directo: la medida se deduce del concepto', () => {
  it('un concepto de área con un rectángulo mide su área', () => {
    expect(medidaDirecta('area', 'poligono', false, false)).toBe('area');
  });

  it('un concepto lineal mide la longitud de una línea y el perímetro de una figura cerrada', () => {
    expect(medidaDirecta('lineal', 'linea', false, false)).toBe('longitud');
    expect(medidaDirecta('lineal', 'poligono', false, false)).toBe('perimetro');
  });

  it('un concepto de conteo cuenta puntos y formas estampadas', () => {
    expect(medidaDirecta('conteo', 'punto', false, false)).toBe('conteo');
    expect(medidaDirecta('conteo', 'poligono', false, true)).toBe('conteo');
  });

  it('lo ambiguo se pregunta: conteo dibujado como área, área con una línea, volumen, derivado, sin tipo', () => {
    expect(medidaDirecta('conteo', 'poligono', false, false)).toBeNull();
    expect(medidaDirecta('volumen', 'poligono', false, false)).toBeNull();
    expect(medidaDirecta('derivada', 'punto', false, false)).toBeNull();
    expect(medidaDirecta(null, 'poligono', false, false)).toBeNull();
  });

  it('un muro (línea con grosor) de un concepto de área mide su largo y lo vuelve área con la altura y las caras', () => {
    // Antes sumaba largo × grosor (su planta); el mockup y D-601: largo × altura × caras, como una línea sin grosor.
    expect(medidaDirecta('area', 'linea', true, false)).toBe('longitud');
    expect(factorDeLaMedida('area', 'linea', true, 'longitud')).toBe('5.2');
  });
});

describe('Cuerpo del trazo', () => {
  it('un rectángulo enlazado a una actividad', () => {
    const cuerpo = trazoPeticion({
      versionPlano: 2,
      herramienta: 'poligono',
      puntos: [[0, 0], [10, 0], [10, 5], [0, 5]],
      enlaces: [{ actividadId: 'a1', medida: 'area', factor: '1' }],
    });
    expect(cuerpo.version_plano).toBe(2);
    expect(cuerpo.geometria_wkt).toBe('POLYGON((0 0, 10 0, 10 5, 0 5, 0 0))');
    expect(cuerpo.enlaces).toEqual([{ actividad_id: 'a1', medida: 'area', factor: '1' }]);
    expect(cuerpo).not.toHaveProperty('medicion_id');
  });

  it('con medición va sin enlaces propios y con su id; una matriz viaja en el enlace', () => {
    const conMedicion = trazoPeticion({ versionPlano: 1, herramienta: 'punto', puntos: [[1, 2]], medicionId: 'm1', enlaces: [] });
    expect(conMedicion.medicion_id).toBe('m1');
    expect(conMedicion.enlaces).toEqual([]);
    const conMatriz = trazoPeticion({
      versionPlano: 1,
      herramienta: 'punto',
      puntos: [[1, 2]],
      enlaces: [{ actividadId: 'a1', matrizId: 'c9', medida: 'conteo', factor: '1' }],
    });
    expect(conMatriz.enlaces).toEqual([{ actividad_id: 'a1', matriz_concepto_id: 'c9', medida: 'conteo', factor: '1' }]);
  });

  it('una línea sobre un concepto en m² mide su largo y lo convierte con la altura y las caras por defecto', () => {
    expect(medidaDirecta('area', 'linea', false, false)).toBe('longitud');
    expect(factorDeLaMedida('area', 'linea', false, 'longitud')).toBe('5.2'); // 2.6 m × 2 caras
  });

  it('el factor es 1 en todo lo demás', () => {
    expect(factorDeLaMedida('area', 'poligono', false, 'area')).toBe('1');
    expect(factorDeLaMedida('area', 'linea', true, 'area')).toBe('1'); // un muro con grosor mide su área
    expect(factorDeLaMedida('lineal', 'linea', false, 'longitud')).toBe('1');
    expect(factorDeLaMedida('conteo', 'punto', false, 'conteo')).toBe('1');
  });
});

describe('Muro · medir por (D-638)', () => {
  it('la conversión de un muro sobre m² sale de lo elegido antes de trazar', async () => {
    const { conversionDeMuro, OPCIONES_DE_MURO_INICIALES, textoDeMuro } = await import('@/cuantificador/trazoPeticion');
    expect(conversionDeMuro(OPCIONES_DE_MURO_INICIALES)).toMatchObject({ modo: 'area', mide: 'cara2', alt: 2.6 });
    const eje = { ...OPCIONES_DE_MURO_INICIALES, mide: 'eje' as const, alt: '3,2' };
    expect(conversionDeMuro(eje)).toMatchObject({ mide: 'eje', alt: 3.2 });
    expect(textoDeMuro(eje)).toBe('largo del eje × 3.2 m de altura');
    // Una altura que no vale cae en la de defecto.
    expect(conversionDeMuro({ ...OPCIONES_DE_MURO_INICIALES, alt: 'x' })).toMatchObject({ alt: 2.6 });
  });

  it('el enlace lleva la conversión y el servidor ignora el factor', () => {
    const cuerpo = trazoPeticion({
      versionPlano: 1,
      herramienta: 'linea',
      puntos: [[0, 0], [10, 0]],
      enlaces: [{ actividadId: 'a', medida: 'longitud', factor: '1', conversion: { modo: 'area', mide: 'eje', alt: 3 } as never }],
    });
    expect(cuerpo.enlaces?.[0]).toMatchObject({ medida: 'longitud', factor: '1', conversion: { modo: 'area', mide: 'eje', alt: 3 } });
  });
});
