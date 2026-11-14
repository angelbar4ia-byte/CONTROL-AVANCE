import { describe, expect, it } from 'vitest';

import { CAMPOS_POR_TIPO, categoriasDelTipo, formatoDeReceta, lineasDeReceta, rotuloDeUso } from '@/cuantificador/parametricos';

describe('elementos paramétricos', () => {
  it('cada tipo ofrece sus parámetros sin repetir ninguno', () => {
    for (const campos of Object.values(CAMPOS_POR_TIPO)) {
      const claves = campos.map((c) => c.clave);
      expect(new Set(claves).size).toBe(claves.length);
    }
    expect(CAMPOS_POR_TIPO.zapata.map((c) => c.clave)).toContain('sep_l');
    expect(CAMPOS_POR_TIPO.castillo.map((c) => c.clave)).not.toContain('lados');
  });

  it('la receta de un castillo se lee con concreto, acero, estribos, alambre y cimbra por lados', () => {
    const filas = lineasDeReceta({
      unidad: 'pza',
      concreto: 0.0585,
      acero_kg: 10.8545,
      estribos_kg: 1.743,
      n_estribos: 14,
      long_estribo_m: 0.5,
      n_amarres: 56,
      alambre_kg: 0.1596,
      varas: 1,
      cimbra_m2: { '2': 0.78, '4': 1.56, '3': 1.17 },
    });
    expect(filas.map(([r]) => r)).toEqual(['Concreto', 'Acero', 'Estribos', 'Alambre de amarre', 'Cimbra']);
    expect(filas[0]?.[1]).toContain('por pza');
    expect(filas[4]?.[1].indexOf('4 lados')).toBeLessThan(filas[4]?.[1].indexOf('2 lados') ?? 0);
  });

  it('una losa no muestra estribos', () => {
    const filas = lineasDeReceta({
      unidad: 'm²', concreto: 0.1, acero_kg: 3, estribos_kg: 0, n_estribos: 0, long_estribo_m: 0,
      n_amarres: 16, alambre_kg: 0.2, varas: 0.5, cimbra_m2: { '1': 1 },
    });
    expect(filas.map(([r]) => r)).not.toContain('Estribos');
    expect(filas.at(-1)?.[1]).toContain('1 cara');
  });

  it('formatoDeReceta no deja ceros de sobra', () => {
    expect(formatoDeReceta(0.0585, 4)).toBe('0.0585');
    expect(formatoDeReceta(2, 2)).toBe('2');
  });
});

import { ladosDeCimbra, tiposParaGeometria } from '@/cuantificador/parametricos';

describe('colocar un elemento en el plano', () => {
  it('cada geometría admite los elementos que le tocan', () => {
    expect(tiposParaGeometria('Point')).toEqual(['castillo', 'zapata']);
    expect(tiposParaGeometria('LineString')).toEqual(['lineal']);
    expect(tiposParaGeometria('Polygon')).toEqual(['losa']);
    expect(tiposParaGeometria('MultiPoint')).toEqual([]);
  });
  it('solo castillo y trabe dejan fijar los lados de cimbra', () => {
    expect(ladosDeCimbra('castillo')).toEqual([4, 3, 2]);
    expect(ladosDeCimbra('lineal')).toEqual([3, 2]);
    expect(ladosDeCimbra('zapata')).toEqual([]);
    expect(ladosDeCimbra('losa')).toEqual([]);
  });
});

describe('clasificación de la biblioteca', () => {
  const categorias = [
    { clave: 'castillos', nombre: 'Castillos', tipo: 'castillo', subcategorias: [{ clave: 'muro', nombre: 'Castillos de muro' }] },
    {
      clave: 'cadenas',
      nombre: 'Cadenas',
      tipo: 'lineal',
      subcategorias: [
        { clave: 'cerramiento', nombre: 'Cadenas de cerramiento' },
        { clave: 'desplante', nombre: 'Cadenas de desplante' },
      ],
    },
    { clave: 'dalas', nombre: 'Dalas', tipo: 'lineal', subcategorias: [{ clave: 'repison', nombre: 'Dalas de repisón (bajo vanos)' }] },
  ];

  it('un tipo solo ofrece las categorías en que cabe', () => {
    expect(categoriasDelTipo(categorias, 'lineal').map((c) => c.clave)).toEqual(['cadenas', 'dalas']);
    expect(categoriasDelTipo(categorias, 'castillo').map((c) => c.clave)).toEqual(['castillos']);
    expect(categoriasDelTipo(categorias, 'zapata')).toEqual([]);
  });

  it('el uso se rotula con categoría y subcategoría, o con las claves si aún no llegó la clasificación', () => {
    expect(rotuloDeUso(categorias, 'cadenas', 'desplante')).toBe('Cadenas › Cadenas de desplante');
    expect(rotuloDeUso([], 'cadenas', 'desplante')).toBe('cadenas › desplante');
  });
});
