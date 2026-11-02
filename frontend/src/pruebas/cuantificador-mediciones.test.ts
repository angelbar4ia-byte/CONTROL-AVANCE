import { describe, expect, it } from 'vitest';

import {
  admiteGeometria,
  aplanarMediciones,
  arbolDeMediciones,
  candidatasAMadre,
  idsDeRama,
  motivoDeIncompatibilidad,
  type MedicionPlana,
} from '@/cuantificador/mediciones';

const m = (id: string, nombre: string, tipo: MedicionPlana['tipo'], extra: Partial<MedicionPlana> = {}): MedicionPlana => ({
  id,
  nombre,
  tipo,
  orden: 0,
  n_trazos: 0,
  valor: 0,
  unidad: 'm²',
  asignaciones: [],
  ...extra,
});

describe('Árbol de mediciones', () => {
  it('anida por la madre y ordena por orden y nombre', () => {
    const arbol = arbolDeMediciones([
      m('r2', 'Recámara 2', 'area', { parent_id: 'losa', orden: 1 }),
      m('losa', 'Losa', 'area'),
      m('r1', 'Recámara 1', 'area', { parent_id: 'losa', orden: 0 }),
      m('muros', 'Muros', 'lineal'),
    ]);
    expect(arbol.map((n) => n.medicion.nombre)).toEqual(['Losa', 'Muros']);
    expect(arbol[0]!.hijos.map((n) => n.medicion.nombre)).toEqual(['Recámara 1', 'Recámara 2']);
    expect(arbol[0]!.hijos[0]!.nivel).toBe(1);
  });

  it('una medición queda «sin asignar» solo si ni ella ni las que la contienen alimentan un concepto', () => {
    const arbol = arbolDeMediciones([
      m('losa', 'Losa', 'area', { asignaciones: [{}] }),
      m('r1', 'Recámara 1', 'area', { parent_id: 'losa' }),
      m('piso', 'Piso', 'area'),
      m('p1', 'Sala', 'area', { parent_id: 'piso' }),
    ]);
    const [losa, piso] = arbol;
    expect(losa!.sinAsignar).toBe(false);
    expect(losa!.hijos[0]!.sinAsignar).toBe(false); // hereda la asignación de la losa
    expect(piso!.sinAsignar).toBe(true);
    expect(piso!.hijos[0]!.sinAsignar).toBe(true);
  });

  it('una madre que no está en la lista no esconde a su hija: pasa a ser raíz', () => {
    expect(arbolDeMediciones([m('x', 'Huérfana', 'area', { parent_id: 'no-existe' })])).toHaveLength(1);
  });

  it('las candidatas a madre son las del mismo tipo, y la rama incluye a todas las de adentro', () => {
    const lista = [m('losa', 'Losa', 'area'), m('r1', 'R1', 'area', { parent_id: 'losa' }), m('x', 'X', 'area', { parent_id: 'r1' }), m('mu', 'Muros', 'lineal')];
    expect(candidatasAMadre(lista, 'area').map((x) => x.id)).toEqual(['losa', 'r1', 'x']);
    expect([...idsDeRama(lista, 'losa')].sort()).toEqual(['losa', 'r1', 'x']);
    expect([...idsDeRama(lista, 'mu')]).toEqual(['mu']);
  });
});

describe('Qué cabe en cada tipo', () => {
  it('área admite áreas, lineal admite líneas y conteo admite puntos y piezas estampadas', () => {
    expect(admiteGeometria('area', 'poligono', false)).toBe(true);
    expect(admiteGeometria('area', 'poligono', true)).toBe(false); // un castillo se cuenta
    expect(admiteGeometria('area', 'linea', false)).toBe(false);
    expect(admiteGeometria('lineal', 'linea', false)).toBe(true);
    expect(admiteGeometria('lineal', 'poligono', false)).toBe(false);
    expect(admiteGeometria('conteo', 'punto', false)).toBe(true);
    expect(admiteGeometria('conteo', 'poligono', true)).toBe(true);
    expect(admiteGeometria('conteo', 'poligono', false)).toBe(false);
  });

  it('el motivo nombra lo que se intentó meter', () => {
    expect(motivoDeIncompatibilidad('area', 'linea', false)).toContain('una línea');
    expect(motivoDeIncompatibilidad('lineal', 'poligono', false)).toContain('un área');
    expect(motivoDeIncompatibilidad('area', 'poligono', false)).toBeNull();
  });
});

describe('Asignaciones que le tocan a una medición', () => {
  it('cuenta las suyas y las de las que la contienen', async () => {
    const { asignacionesEfectivas } = await import('@/cuantificador/mediciones');
    const lista = [
      m('losa', 'Losa', 'area', { asignaciones: [{}, {}] }),
      m('r1', 'R1', 'area', { parent_id: 'losa', asignaciones: [{}] }),
      m('x', 'X', 'area', { parent_id: 'r1' }),
      m('otra', 'Otra', 'area'),
    ];
    expect(asignacionesEfectivas(lista, 'x')).toBe(3);
    expect(asignacionesEfectivas(lista, 'r1')).toBe(3);
    expect(asignacionesEfectivas(lista, 'losa')).toBe(2);
    expect(asignacionesEfectivas(lista, 'otra')).toBe(0);
  });
});

describe('Mediciones en orden de lectura (cuadro de datos)', () => {
  it('cada madre va seguida de sus submediciones, con su nivel y si queda sin asignar', () => {
    const lista = [
      m('c1', 'Cocina', 'area', { parent_id: 'losa', orden: 1 }),
      m('losa', 'Losa', 'area', { asignaciones: [{}] }),
      m('muros', 'Muros', 'lineal', { orden: 1, unidad: 'm' }),
    ];
    const plano = aplanarMediciones(lista).map((n) => [n.medicion.nombre, n.nivel, n.sinAsignar]);
    expect(plano).toEqual([
      ['Losa', 0, false],
      ['Cocina', 1, false], // hereda la asignación de su madre
      ['Muros', 0, true],
    ]);
  });
});
