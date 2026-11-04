import { describe, expect, it } from 'vitest';

import {
  aWkt,
  areaLocal,
  cajaDePuntos,
  desplazar,
  distanciaA,
  distanciaEntre,
  escalaPrevista,
  girarAlrededor,
  gradosDeGiro,
  trasladar,
  herramientaDeGeometria,
  marcadoresDe,
  notaEnPunto,
  medidaLocal,
  perimetroLocal,
  PUNTOS_MINIMOS_DE_HUECO,
  rutaSvg,
  trazoCompleto,
  trazoEnPunto,
  vistaQueEncuadra,
  zoomEn,
  type Punto,
} from '@/cuantificador/geometria';
import { etiquetaMedida } from '@/cuantificador/reglas';

const RECTANGULO: Punto[] = [
  [0, 0],
  [4, 0],
  [4, 3],
  [0, 3],
];

describe('WKT de captura', () => {
  it('cierra el anillo del polígono repitiendo el primer punto', () => {
    expect(aWkt('poligono', RECTANGULO)).toBe('POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))');
  });

  it('arma líneas y puntos', () => {
    expect(aWkt('linea', [[0, 0], [5, 5]])).toBe('LINESTRING(0 0, 5 5)');
    expect(aWkt('punto', [[1.5, 2]])).toBe('POINT(1.5 2)');
  });

  it('nunca emite un WKT inválido: lanza si faltan puntos', () => {
    expect(() => aWkt('poligono', [[0, 0], [1, 1]])).toThrow(/al menos 3/);
    expect(() => aWkt('linea', [[0, 0]])).toThrow(/al menos 2/);
    expect(trazoCompleto('poligono', RECTANGULO)).toBe(true);
    expect(trazoCompleto('poligono', RECTANGULO.slice(0, 2))).toBe(false);
  });
});

describe('medida local (vista previa; la cantidad la calcula el servidor)', () => {
  it('coincide con el rectángulo 4×3 que PostGIS mide en las pruebas de backend', () => {
    expect(areaLocal(RECTANGULO)).toBe(12);
    expect(perimetroLocal(RECTANGULO)).toBe(14);
    expect(medidaLocal('poligono', 'area', RECTANGULO)).toBe(12);
    expect(medidaLocal('poligono', 'perimetro', RECTANGULO)).toBe(14);
  });

  it('el área no depende del sentido en que se dibujó', () => {
    expect(areaLocal([...RECTANGULO].reverse())).toBe(12);
  });

  it('una línea mide longitud; el área de una línea es 0, como en PostGIS', () => {
    const linea: Punto[] = [[0, 0], [3, 4]];
    expect(medidaLocal('linea', 'longitud', linea)).toBe(5);
    expect(medidaLocal('linea', 'area', linea)).toBe(0);
  });

  it('el conteo siempre vale 1', () => {
    expect(medidaLocal('punto', 'conteo', [[9, 9]])).toBe(1);
  });
});

describe('GeoJSON → dibujo', () => {
  const poligono = {
    type: 'Polygon',
    coordinates: [[[0, 0], [4, 0], [4, 3], [0, 3], [0, 0]]],
  };

  it('traza el anillo cerrado con Z', () => {
    expect(rutaSvg(poligono)).toBe('M0 0L4 0L4 3L0 3L0 0Z');
  });

  it('las líneas no se cierran y los puntos no tienen trazo sino marcador', () => {
    expect(rutaSvg({ type: 'LineString', coordinates: [[0, 0], [2, 2]] })).toBe('M0 0L2 2');
    expect(rutaSvg({ type: 'Point', coordinates: [1, 1] })).toBe('');
    expect(marcadoresDe({ type: 'Point', coordinates: [1, 1] })).toEqual([[1, 1]]);
  });

  it('soporta las variantes Multi*', () => {
    const multi = {
      type: 'MultiPolygon',
      coordinates: [
        [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        [[[5, 5], [6, 5], [6, 6], [5, 5]]],
      ],
    };
    expect(rutaSvg(multi).match(/M/g)).toHaveLength(2);
  });

  it('una geometría desconocida o malformada no rompe el visor', () => {
    expect(rutaSvg({ type: 'GeometryCollection' })).toBe('');
    expect(rutaSvg({ type: 'Polygon', coordinates: 'basura' })).toBe('');
    expect(rutaSvg({})).toBe('');
  });
});

describe('vista', () => {
  it('encuadra la caja con margen', () => {
    const caja = cajaDePuntos(RECTANGULO)!;
    const vista = vistaQueEncuadra(caja, 0.1);
    expect(vista.x).toBeCloseTo(-0.4);
    expect(vista.ancho).toBeCloseTo(4.8);
    expect(vista.alto).toBeCloseTo(3.6);
  });

  it('una caja degenerada (un punto) sigue siendo una vista con tamaño', () => {
    const vista = vistaQueEncuadra(cajaDePuntos([[5, 5]])!);
    expect(vista.ancho).toBeGreaterThan(0);
    expect(vista.alto).toBeGreaterThan(0);
  });

  it('sin puntos no hay caja', () => {
    expect(cajaDePuntos([])).toBeNull();
  });

  it('el zoom deja fijo el punto bajo el cursor', () => {
    const antes = { x: 0, y: 0, ancho: 100, alto: 100 };
    const centro: Punto = [25, 75];
    const despues = zoomEn(antes, 0.5, centro);
    expect(despues.ancho).toBe(50);
    // El centro sigue en la misma fracción de la vista.
    expect((centro[0] - despues.x) / despues.ancho).toBeCloseTo(0.25);
    expect((centro[1] - despues.y) / despues.alto).toBeCloseTo(0.75);
  });

  it('arrastrar a la derecha mueve la vista a la izquierda', () => {
    expect(desplazar({ x: 10, y: 10, ancho: 100, alto: 100 }, 5, -3)).toMatchObject({ x: 5, y: 13 });
  });
});

describe('elegir un trazo con el clic', () => {
  const grande = {
    id: 'grande',
    geometry: { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]] },
  };
  const chico = {
    id: 'chico',
    geometry: { type: 'Polygon', coordinates: [[[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]] },
  };
  const linea = { id: 'linea', geometry: { type: 'LineString', coordinates: [[20, 0], [20, 10]] } };

  it('dentro de un polígono la distancia es 0', () => {
    expect(distanciaA([3, 3], chico.geometry)).toBe(0);
  });

  it('con polígonos apilados gana el de menor área, el que se ve encima', () => {
    expect(trazoEnPunto([grande, chico], [3, 3], 0.5)).toBe('chico');
    expect(trazoEnPunto([chico, grande], [3, 3], 0.5)).toBe('chico');
    expect(trazoEnPunto([grande, chico], [8, 8], 0.5)).toBe('grande');
  });

  it('una línea se elige por cercanía, dentro de la tolerancia', () => {
    expect(trazoEnPunto([grande, linea], [20.4, 5], 0.5)).toBe('linea');
    expect(trazoEnPunto([grande, linea], [21, 5], 0.5)).toBeNull();
  });

  it('un clic en el vacío no elige nada', () => {
    expect(trazoEnPunto([grande, chico, linea], [100, 100], 1)).toBeNull();
  });
});

describe('textos', () => {
  it('etiqueta las medidas y deja pasar las desconocidas', () => {
    expect(etiquetaMedida('perimetro')).toBe('Perímetro');
    expect(etiquetaMedida('volumen')).toBe('volumen');
  });
});

describe('notas y formas', () => {
  it('una nota se elige por cercanía y, a igual distancia, gana la más reciente', () => {
    const notas = [
      { id: 'a', punto: [10, 10] as Punto },
      { id: 'b', punto: [10, 10] as Punto },
      { id: 'c', punto: [50, 50] as Punto },
    ];
    expect(notaEnPunto(notas, [11, 10], 3)).toBe('b');
    expect(notaEnPunto(notas, [49, 50], 3)).toBe('c');
    expect(notaEnPunto(notas, [30, 30], 3)).toBeNull();
  });

  it('reconoce la herramienta de una geometría del servidor', () => {
    expect(herramientaDeGeometria({ type: 'Polygon' })).toBe('poligono');
    expect(herramientaDeGeometria({ type: 'MultiLineString' })).toBe('linea');
    expect(herramientaDeGeometria({ type: 'Point' })).toBe('punto');
    expect(herramientaDeGeometria({ type: 'GeometryCollection' })).toBeNull();
  });
});

describe('calibrar la escala (vista previa)', () => {
  it('la distancia entre dos puntos es euclidiana', () => {
    expect(distanciaEntre([0, 0], [3, 4])).toBe(5);
  });

  it('metros por unidad = metros reales / distancia en el plano', () => {
    expect(escalaPrevista([0, 0], [100, 0], 5)).toBe(0.05);
    expect(escalaPrevista([0, 0], [3, 4], 10)).toBe(2);
  });

  it('sin datos para calcular no hay vista previa', () => {
    expect(escalaPrevista([1, 1], [1, 1], 5)).toBeNull(); // los dos puntos son el mismo
    expect(escalaPrevista([0, 0], [10, 0], 0)).toBeNull();
    expect(escalaPrevista([0, 0], [10, 0], Number.NaN)).toBeNull();
  });
});

describe('polígono con hueco (descuento de aberturas)', () => {
  // Un muro de 10 × 4 con una ventana de 2 × 1.
  const MURO: Punto[] = [
    [0, 0],
    [10, 0],
    [10, 4],
    [0, 4],
  ];
  const VENTANA: Punto[] = [
    [4, 1],
    [6, 1],
    [6, 2],
    [4, 2],
  ];

  it('el WKT lleva el hueco como anillo interior, cada uno cerrado', () => {
    expect(aWkt('poligono', MURO, [VENTANA])).toBe(
      'POLYGON((0 0, 10 0, 10 4, 0 4, 0 0), (4 1, 6 1, 6 2, 4 2, 4 1))',
    );
  });

  it('sin huecos, el WKT es el de siempre', () => {
    expect(aWkt('poligono', MURO)).toBe('POLYGON((0 0, 10 0, 10 4, 0 4, 0 0))');
    expect(aWkt('poligono', MURO, [])).toBe(aWkt('poligono', MURO));
  });

  it('un hueco necesita sus tres vértices y solo un polígono los tiene', () => {
    expect(() => aWkt('poligono', MURO, [[[4, 1], [6, 1]]])).toThrow(/un hueco necesita al menos 3/);
    expect(PUNTOS_MINIMOS_DE_HUECO).toBe(3);
    expect(() =>
      aWkt('linea', [[0, 0], [5, 5]], [VENTANA]),
    ).toThrow(/Solo un polígono/);
  });

  it('el área se descuenta y el perímetro suma el borde del hueco', () => {
    expect(medidaLocal('poligono', 'area', MURO)).toBe(40);
    expect(medidaLocal('poligono', 'area', MURO, [VENTANA])).toBe(38);
    expect(medidaLocal('poligono', 'perimetro', MURO)).toBe(28);
    expect(medidaLocal('poligono', 'perimetro', MURO, [VENTANA])).toBe(34);
    expect(medidaLocal('poligono', 'conteo', MURO, [VENTANA])).toBe(1);
  });

  const conHueco = {
    type: 'Polygon',
    coordinates: [
      [...MURO, MURO[0]],
      [...VENTANA, VENTANA[0]],
    ],
  };

  it('un clic dentro del hueco no elige el muro, y uno en el muro sí', () => {
    expect(distanciaA([5, 1.5], conHueco)).toBeGreaterThan(0); // en la ventana
    expect(distanciaA([2, 2], conHueco)).toBe(0); // en el muro
    expect(trazoEnPunto([{ id: 'muro', geometry: conHueco }], [5, 1.5], 0.1)).toBeNull();
    expect(trazoEnPunto([{ id: 'muro', geometry: conHueco }], [2, 2], 0.1)).toBe('muro');
    // Cerca del borde de la ventana todavía cuenta: es borde del muro.
    expect(trazoEnPunto([{ id: 'muro', geometry: conHueco }], [5, 1.05], 0.1)).toBe('muro');
  });

  it('el trazo SVG lleva los dos anillos, cada uno cerrado', () => {
    expect(rutaSvg(conHueco).match(/Z/g)).toHaveLength(2);
  });
});

describe('mover y girar (menú del trazo)', () => {
  const sinVolteo = { volteoH: false, volteoV: false };
  it('girar a la derecha es horario: +grados del servidor, y a la izquierda su opuesto', () => {
    expect(gradosDeGiro('derecha', 90, sinVolteo)).toBe(90);
    expect(gradosDeGiro('izquierda', 90, sinVolteo)).toBe(-90);
  });
  it('un solo volteo de la vista invierte el sentido; dos no', () => {
    expect(gradosDeGiro('derecha', 90, { volteoH: true, volteoV: false })).toBe(-90);
    expect(gradosDeGiro('derecha', 90, { volteoH: true, volteoV: true })).toBe(90);
  });
  it('girar 90° alrededor de (5,2) lleva (7,2) a (5,4), como ST_Rotate', () => {
    const [x, y] = girarAlrededor([7, 2], [5, 2], 90);
    expect(x).toBeCloseTo(5);
    expect(y).toBeCloseTo(4);
  });
  it('girar y deshacer devuelve el punto', () => {
    const g = girarAlrededor([3, 9], [1, 1], 37);
    const [x, y] = girarAlrededor(g, [1, 1], -37);
    expect(x).toBeCloseTo(3);
    expect(y).toBeCloseTo(9);
  });
  it('trasladar suma el desplazamiento', () => {
    expect(trasladar([1, 2], 3, -4)).toEqual([4, -2]);
  });
});
