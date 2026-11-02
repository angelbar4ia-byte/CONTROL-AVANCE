import { describe, expect, it } from 'vitest';

import { medidaDirecta, trazoPeticion } from '@/cuantificador/trazoPeticion';

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
    expect(medidaDirecta('area', 'linea', false, false)).toBeNull();
    expect(medidaDirecta('volumen', 'poligono', false, false)).toBeNull();
    expect(medidaDirecta('derivada', 'punto', false, false)).toBeNull();
    expect(medidaDirecta(null, 'poligono', false, false)).toBeNull();
  });

  it('un muro (línea con grosor) de un concepto de área mide su área', () => {
    expect(medidaDirecta('area', 'linea', true, false)).toBe('area');
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
});
