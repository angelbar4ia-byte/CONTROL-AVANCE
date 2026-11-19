import { describe, expect, it } from 'vitest';

import type { PlantillaDeMuro } from '@/api/generado/modelo';

import {
  borradorDe,
  borradorDePrototipo,
  borradorVacio,
  cambio,
  driversDeVistaDe,
  type ElementoBorrador,
  esPlantillaNueva,
  geometriaDeVista,
  peticionDe,
  plantillaNuevaDe,
  prototipoDeNueva,
  reglasDeCastillo,
  type Borrador,
} from './plantillaDeMuro';

/** Un elemento del borrador con lo que no se dice en blanco. */
const elemento = (e: Pick<ElementoBorrador, 'uid' | 'ref' | 'clase'> & Partial<ElementoBorrador>): ElementoBorrador => ({
  sep: '', posicion: '', z: '', regla: '', piezasPorMl: '', totalM: '', baseM2: '', origen: '', ...e,
});

const PLANTILLA = {
  id: 'p1',
  raiz_id: 'r1',
  version: 1,
  vigente: true,
  nombre: 'Muro de fachada',
  tipo: 'con_cadena',
  material: 'tabique_rojo',
  ubicacion: 'fachada_a',
  altura_m: null,
  partes: [
    { nombre: 'Cuerpo', desde_m: '0.000', hasta_m: '2.300', suma: true, rol: 'cuerpo', cara_a: 'exterior', cara_b: 'interior' },
    { nombre: 'Enrase', desde_m: '2.300', hasta_m: '2.600', suma: true, rol: 'enrase', cara_a: 'exterior', cara_b: 'interior' },
  ],
  elementos: [
    { uid: 'K-1', ref: 'K-1', clase: 'castillo', modo: 'ubicado', sep_m: null, posicion: null, z_m: '0' },
    { uid: 'CE-1', ref: 'CE-1', clase: 'cadena', modo: null, sep_m: null, posicion: 'cerramiento', z_m: '0' },
  ],
  acabado: null,
  validacion: 'por_validar',
  propuso_nombre: null,
  propuso_rol: null,
  validada_por_nombre: null,
  validada_en: null,
  trazos: 0,
  created_at: '2026-11-16T00:00:00Z',
  updated_at: '2026-11-16T00:00:00Z',
} as unknown as PlantillaDeMuro;

describe('el borrador de una plantilla de muro', () => {
  it('pasa de la respuesta a lo que se teclea y de vuelta a la petición', () => {
    const b = borradorDe(PLANTILLA);
    expect(b.partes.map((p) => [p.desde, p.hasta, p.caraA, p.caraB])).toEqual([
      ['0', '2.3', 'exterior', 'interior'],
      ['2.3', '2.6', 'exterior', 'interior'],
    ]);
    const r = peticionDe(b);
    expect('peticion' in r).toBe(true);
    if ('peticion' in r) {
      expect(r.peticion.tipo).toBe('con_cadena');
      expect(r.peticion.altura_m).toBeNull();
      expect(r.peticion.partes?.[1]).toMatchObject({ desde_m: 2.3, hasta_m: 2.6, rol: 'enrase', cara_a: 'exterior' });
      // La separación solo viaja en un castillo y la posición solo en una cadena.
      expect(r.peticion.elementos?.map((e) => [e.ref, e.sep_m, e.posicion])).toEqual([
        ['K-1', null, null],
        ['CE-1', null, 'cerramiento'],
      ]);
    }
  });

  it('pide nombre y partes con un «hasta» mayor', () => {
    expect(peticionDe(borradorVacio())).toEqual({ motivo: 'Ponle un nombre a la plantilla.' });
    const malo: Borrador = {
      ...borradorVacio(),
      nombre: 'x',
      partes: [{ nombre: '', desde: '2', hasta: '1', rol: '', caraA: '', caraB: '' }],
    };
    expect(peticionDe(malo)).toEqual({ motivo: 'La parte 1 debe ir de un «desde» a un «hasta» mayor.' });
  });

  it('solo hay cambio si lo que se manda es distinto de lo guardado', () => {
    const b = borradorDe(PLANTILLA);
    expect(cambio(b, PLANTILLA)).toBe(false);
    expect(cambio({ ...b, altura: '3' }, PLANTILLA)).toBe(true);
    expect(cambio({ ...b, nombre: 'Otro' }, PLANTILLA)).toBe(true);
    expect(cambio(borradorVacio(), null)).toBe(true);
  });
});

describe('la vista previa del muro', () => {
  const medidas = { 'K-1': { ancho_m: 0.15, alto_m: 0 }, 'CE-1': { ancho_m: 0.15, alto_m: 0.2 }, 'CD-1': { ancho_m: 0.15, alto_m: 0.2 } };

  it('pone los castillos ubicados en los extremos, y la cadena de cerramiento donde arranca el enrase', () => {
    const g = geometriaDeVista(borradorDe(PLANTILLA), medidas);
    expect(g.altura_m).toBeCloseTo(2.6); // la plantilla trae sus partes: manda su tope
    const centros = g.castillos.map((c) => c.x_m + c.ancho_m / 2);
    expect(centros).toHaveLength(2); // sin separación propia, un castillo ubicado va en los extremos (como al colocar)
    expect(centros[0]).toBeCloseTo(0.075);
    expect(centros[1]).toBeCloseTo(5.925);
    expect(g.castillos.every((c) => !c.estimado)).toBe(true);
    expect(g.cadenas).toHaveLength(1);
    expect(g.cadenas[0]!.desde_m).toBeCloseTo(2.3); // donde acaba el cuerpo
  });

  it('en un muro confinado los castillos son estimados y la separación se respeta', () => {
    const b: Borrador = { ...borradorDe(PLANTILLA), tipo: 'confinado', elementos: [elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', sep: '2', posicion: '', z: '' })] };
    const g = geometriaDeVista(b, medidas);
    expect(g.castillos).toHaveLength(4); // 0, 2, 4 y 6 m
    expect(g.castillos.every((c) => c.estimado)).toBe(true);
  });

  it('la cadena de desplante va al pie y la de remate, al tope', () => {
    const b: Borrador = {
      ...borradorVacio(),
      altura: '3',
      elementos: [
        elemento({ uid: 'CD-1', ref: 'CD-1', clase: 'cadena', sep: '', posicion: 'desplante', z: '' }),
        elemento({ uid: 'CE-1', ref: 'CE-1', clase: 'cadena', sep: '', posicion: 'remate', z: '' }),
      ],
    };
    const g = geometriaDeVista(b, medidas);
    expect(g.altura_m).toBe(3);
    expect(g.cadenas.map((c) => [c.ref, c.desde_m])).toEqual([['CD-1', 0], ['CE-1', 2.8]]);
  });
});

describe('los drivers de la obra en la vista previa', () => {
  const medidas = { 'K-1': { ancho_m: 0.15, alto_m: 0 } };
  const confinado: Borrador = {
    ...borradorVacio(),
    tipo: 'confinado',
    elementos: [elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', sep: '', posicion: '', z: '' })],
  };

  it('sin drivers de la obra vale lo de partida: 3.00 m de alto y castillos cada 3.00 m', () => {
    const g = geometriaDeVista(confinado, medidas);
    expect(g.altura_m).toBe(3);
    expect(g.castillos).toHaveLength(3); // 0, 3 y 6 m
  });

  it('la separación de castillos sale del driver de la obra; la altura estándar del driver NO se lee (la vista previa usa la de la herramienta)', () => {
    const d = driversDeVistaDe([
      { clave: 'altura_estandar', valor_vigente: '3.5' },
      { clave: 'separacion_castillos', valor_vigente: '2' },
    ]);
    expect(d).toEqual({ altura_m: 3, separacion_m: 2 });
    const g = geometriaDeVista(confinado, medidas, d);
    expect(g.altura_m).toBe(3);
    expect(g.castillos).toHaveLength(4); // 0, 2, 4 y 6 m
  });

  it('la altura y la separación que la plantilla trae mandan sobre los drivers', () => {
    const b: Borrador = { ...confinado, altura: '2.8', elementos: [elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', sep: '1.5', posicion: '', z: '' })] };
    const g = geometriaDeVista(b, medidas, { altura_m: 3.5, separacion_m: 2 });
    expect(g.altura_m).toBe(2.8);
    expect(g.castillos).toHaveLength(5); // 0, 1.5, 3, 4.5 y 6 m
  });

  it('un driver que falta o no vale queda en su valor de partida', () => {
    expect(driversDeVistaDe(undefined)).toEqual({ altura_m: 3, separacion_m: 3 });
    expect(driversDeVistaDe([{ clave: 'separacion_castillos', valor_vigente: 'x' }])).toEqual({ altura_m: 3, separacion_m: 3 });
  });
});


describe('plantilla de muro confinado por prototipo', () => {
  const medidas = { 'K-1': { ancho_m: 0.15, alto_m: 0 }, 'K-2': { ancho_m: 0.15, alto_m: 0 } };
  const oro: Borrador = {
    ...borradorDePrototipo('oro_401', 'PB', 'Muro confinado · Oro 4.01 · PB'),
    altura: '3',
    elementos: [
      elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', regla: 'total', totalM: '126', baseM2: '286', origen: 'ASIGNACIÓN!K2152' }),
      elemento({ uid: 'K-2', ref: 'K-2', clase: 'castillo', regla: 'extremos' }),
      elemento({ uid: 'CE-1', ref: 'CE-1', clase: 'cadena', posicion: 'cerramiento' }),
    ],
  };

  it('un prototipo nuevo nace como muro confinado, por confirmar y sin castillos', () => {
    const b = borradorDePrototipo('zafiro_1', 'PB', 'Muro confinado · Zafiro 1.0 · PB');
    expect([b.tipo, b.prototipo, b.planta, b.porConfirmar, b.elementos.length]).toEqual(['confinado', 'zafiro_1', 'PB', true, 0]);
  });

  it('la petición lleva el prototipo, la planta, las notas y la regla de cada castillo', () => {
    const r = peticionDe({ ...oro, notas: '  Celdas del Excel  ' });
    if (!('peticion' in r)) throw new Error(r.motivo);
    expect(r.peticion).toMatchObject({ prototipo: 'oro_401', planta: 'PB', notas: 'Celdas del Excel', por_confirmar: true });
    expect(r.peticion.elementos?.map((e) => [e.ref, e.regla, e.total_m, e.base_m2, e.sep_m, e.origen])).toEqual([
      ['K-1', 'total', 126, 286, null, 'ASIGNACIÓN!K2152'],
      ['K-2', 'extremos', null, null, null, null],
      ['CE-1', null, null, null, null, null],
    ]);
    const vuelta = borradorDe({ ...PLANTILLA, tipo: 'confinado', prototipo: 'oro_401', planta: 'PB', notas: 'x', por_confirmar: true, elementos: [
      { uid: 'K-1', ref: 'K-1', clase: 'castillo', modo: 'estimado', sep_m: null, regla: 'total', total_m: '126.000', base_m2: '286.000', origen: 'ASIGNACIÓN!K2152', posicion: null, z_m: '0' },
    ] } as unknown as PlantillaDeMuro);
    expect(vuelta.elementos[0]).toMatchObject({ regla: 'total', totalM: '126', baseM2: '286', origen: 'ASIGNACIÓN!K2152' });
    expect([vuelta.prototipo, vuelta.planta, vuelta.notas, vuelta.porConfirmar]).toEqual(['oro_401', 'PB', 'x', true]);
  });

  it('pide lo que falta de cada regla y la planta del prototipo', () => {
    const sinPorMl = { ...oro, elementos: [elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', regla: 'por_ml' })] };
    expect(peticionDe(sinPorMl)).toMatchObject({ motivo: expect.stringContaining('por ml') });
    const sinBase = { ...oro, elementos: [elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', regla: 'total', totalM: '5' })] };
    expect(peticionDe(sinBase)).toMatchObject({ motivo: expect.stringContaining('total') });
    expect(peticionDe({ ...oro, planta: '' })).toMatchObject({ motivo: expect.stringContaining('planta') });
    // La global no lleva planta aunque el borrador la traiga.
    const global = peticionDe({ ...oro, prototipo: 'global_1', planta: 'PB' });
    if (!('peticion' in global)) throw new Error(global.motivo);
    expect(global.peticion.planta).toBeNull();
  });

  it('un muro con cadena solo cuenta por separación o extremos', () => {
    expect(reglasDeCastillo('con_cadena')).toEqual(['separacion', 'extremos']);
    expect(reglasDeCastillo('confinado')).toEqual(['separacion', 'extremos', 'por_ml', 'total']);
  });

  it('la vista previa dibuja cada castillo con su regla', () => {
    const g = geometriaDeVista(oro, medidas);
    const de = (uid: string) => g.castillos.filter((c) => c.uid === uid);
    // Total: 126 × 6 m ÷ 286 m² = 2.643 piezas de 3.00 m en el tramo de 6 m: se dibujan 3, repartidas del inicio al final.
    expect(de('K-1')).toHaveLength(3);
    expect(de('K-1')[0]!.piezas).toBeCloseTo(2.643, 2);
    expect(de('K-1').map((c) => c.regla)).toEqual(['total', 'total', 'total']);
    expect(de('K-2').map((c) => c.x_m + c.ancho_m / 2)).toEqual([0.075, 5.925]);
    const porMl = geometriaDeVista({ ...oro, elementos: [elemento({ uid: 'K-1', ref: 'K-1', clase: 'castillo', regla: 'por_ml', piezasPorMl: '0.5' })] }, medidas);
    expect(porMl.castillos).toHaveLength(3); // 6 ml × 0.5 pza/ml
    expect(porMl.castillos[0]!.piezas).toBe(3);
  });

  it('el identificador de una plantilla nueva lleva su prototipo y planta', () => {
    expect(plantillaNuevaDe()).toBe('nueva');
    expect(plantillaNuevaDe('oro_401', 'PA')).toBe('nueva:oro_401:PA');
    expect(plantillaNuevaDe('global_1', null)).toBe('nueva:global_1:');
    expect([esPlantillaNueva('nueva'), esPlantillaNueva('nueva:oro_401:PA'), esPlantillaNueva('c1'), esPlantillaNueva(null)]).toEqual([true, true, false, false]);
    expect(prototipoDeNueva('nueva:oro_401:PA')).toEqual({ prototipo: 'oro_401', planta: 'PA' });
    expect(prototipoDeNueva('nueva:global_1:')).toEqual({ prototipo: 'global_1', planta: '' });
    expect(prototipoDeNueva('nueva')).toEqual({ prototipo: '', planta: '' });
  });
});
