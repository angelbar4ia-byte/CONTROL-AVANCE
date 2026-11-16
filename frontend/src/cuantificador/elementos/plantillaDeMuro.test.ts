import { describe, expect, it } from 'vitest';

import type { PlantillaDeMuro } from '@/api/generado/modelo';

import { borradorDe, borradorVacio, cambio, driversDeVistaDe, geometriaDeVista, peticionDe, type Borrador } from './plantillaDeMuro';

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
    const b: Borrador = { ...borradorDe(PLANTILLA), tipo: 'confinado', elementos: [{ uid: 'K-1', ref: 'K-1', clase: 'castillo', sep: '2', posicion: '', z: '' }] };
    const g = geometriaDeVista(b, medidas);
    expect(g.castillos).toHaveLength(4); // 0, 2, 4 y 6 m
    expect(g.castillos.every((c) => c.estimado)).toBe(true);
  });

  it('la cadena de desplante va al pie y la de remate, al tope', () => {
    const b: Borrador = {
      ...borradorVacio(),
      altura: '3',
      elementos: [
        { uid: 'CD-1', ref: 'CD-1', clase: 'cadena', sep: '', posicion: 'desplante', z: '' },
        { uid: 'CE-1', ref: 'CE-1', clase: 'cadena', sep: '', posicion: 'remate', z: '' },
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
    elementos: [{ uid: 'K-1', ref: 'K-1', clase: 'castillo', sep: '', posicion: '', z: '' }],
  };

  it('sin drivers de la obra vale lo de partida: 3.00 m de alto y castillos cada 3.00 m', () => {
    const g = geometriaDeVista(confinado, medidas);
    expect(g.altura_m).toBe(3);
    expect(g.castillos).toHaveLength(3); // 0, 3 y 6 m
  });

  it('la altura estándar y la separación de castillos salen de los drivers de la obra', () => {
    const d = driversDeVistaDe([
      { clave: 'altura_estandar', valor_vigente: '3.5' },
      { clave: 'separacion_castillos', valor_vigente: '2' },
    ]);
    expect(d).toEqual({ altura_m: 3.5, separacion_m: 2 });
    const g = geometriaDeVista(confinado, medidas, d);
    expect(g.altura_m).toBe(3.5);
    expect(g.castillos).toHaveLength(4); // 0, 2, 4 y 6 m
  });

  it('la altura y la separación que la plantilla trae mandan sobre los drivers', () => {
    const b: Borrador = { ...confinado, altura: '2.8', elementos: [{ uid: 'K-1', ref: 'K-1', clase: 'castillo', sep: '1.5', posicion: '', z: '' }] };
    const g = geometriaDeVista(b, medidas, { altura_m: 3.5, separacion_m: 2 });
    expect(g.altura_m).toBe(2.8);
    expect(g.castillos).toHaveLength(5); // 0, 1.5, 3, 4.5 y 6 m
  });

  it('un driver que falta o no vale queda en su valor de partida', () => {
    expect(driversDeVistaDe(undefined)).toEqual({ altura_m: 3, separacion_m: 3 });
    expect(driversDeVistaDe([{ clave: 'separacion_castillos', valor_vigente: 'x' }])).toEqual({ altura_m: 3, separacion_m: 3 });
  });
});
