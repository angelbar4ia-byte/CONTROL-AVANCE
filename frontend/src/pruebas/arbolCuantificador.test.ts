/**
 * El árbol del cuantificador es el del presupuesto: nivel → etapa → concepto (D-565), con todo
 * lo que hay en la obra —medido o no— y cuántos conceptos van medidos en cada rama.
 */

import { describe, expect, it } from 'vitest';

import type { ActividadRespuesta, NodoCuantificadoRespuesta } from '@/api/generado/modelo';
import { arbolDeCuantificacion, descripcionCorta } from '@/cuantificador/arbol';

const act = (id: string, extra: Partial<ActividadRespuesta>): ActividadRespuesta =>
  ({ id, cant_base: '0', ...extra }) as ActividadRespuesta;

const medido = (id: string, medida: string, base: string, vigentes = 1): NodoCuantificadoRespuesta =>
  ({
    tipo_nodo: 'actividad',
    nodo_id: id,
    cant_base: base,
    cantidad_medida: medida,
    diferencia: String(Number(medida) - Number(base)),
    enlaces_vigentes: vigentes,
    enlaces_reemplazados: 0,
    trazos_por_revisar: 0,
  }) as NodoCuantificadoRespuesta;

const ACTIVIDADES = [
  act('a1', { nivel_clave: 'PB', etapa_clave: 'ECO-2', etapa_descripcion: 'Muros', concepto_clave: 'M-1', descripcion: 'Muro' }),
  act('a2', { nivel_clave: 'PB', etapa_clave: 'ECO-1', etapa_descripcion: 'Cimentación', concepto_clave: 'C-2', descripcion: 'Zapata' }),
  act('a3', { nivel_clave: 'PB', etapa_clave: 'ECO-1', etapa_descripcion: 'Cimentación', concepto_clave: 'C-1', descripcion: 'Plantilla' }),
  act('a4', { nivel_clave: 'PA', etapa_clave: 'ECO-3', concepto_clave: 'L-1' }),
  act('a5', { concepto_clave: 'X-1', descripcion: 'Suelto' }),
];

describe('el árbol del cuantificador', () => {
  it('trae todo lo que hay, medido o no, ordenado como el presupuesto y con lo suelto al final', () => {
    const arbol = arbolDeCuantificacion(ACTIVIDADES, []);
    expect(arbol.map((n) => n.etiqueta)).toEqual(['PA', 'PB', 'Sin nivel']);
    const pb = arbol.find((n) => n.clave === 'PB')!;
    expect(pb.etapas.map((e) => e.clave)).toEqual(['ECO-1', 'ECO-2']);
    expect(pb.etapas[0]!.hojas.map((h) => h.id)).toEqual(['a3', 'a2']); // C-1 antes que C-2
    expect(arbol.at(-1)!.etapas[0]!.etiqueta).toBe('Sin etapa');
    expect(arbol.reduce((s, n) => s + n.total, 0)).toBe(5);
  });

  it('cuenta cuántos conceptos van medidos en cada rama', () => {
    const arbol = arbolDeCuantificacion(ACTIVIDADES, [medido('a3', '12', '10'), medido('a1', '5', '5')]);
    const pb = arbol.find((n) => n.clave === 'PB')!;
    expect([pb.medidas, pb.total]).toEqual([2, 3]);
    expect(pb.etapas.map((e) => [e.clave, e.medidas, e.hojas.length])).toEqual([
      ['ECO-1', 1, 2],
      ['ECO-2', 1, 1],
    ]);
    const plantilla = pb.etapas[0]!.hojas[0]!;
    expect([plantilla.medido, plantilla.medida, plantilla.diferencia]).toEqual([true, '12', '2']);
    const zapata = pb.etapas[0]!.hojas[1]!;
    expect([zapata.medido, zapata.medida]).toEqual([false, null]);
  });

  it('un enlace reemplazado ya no cuenta como medido', () => {
    const arbol = arbolDeCuantificacion(ACTIVIDADES, [medido('a3', '12', '10', 0)]);
    expect(arbol.flatMap((n) => n.etapas).flatMap((e) => e.hojas).filter((h) => h.medido)).toHaveLength(0);
  });
});

describe('descripcionCorta', () => {
  it('deja intacta una descripción corta', () => {
    expect(descripcionCorta('Firme de concreto')).toBe('Firme de concreto');
  });
  it('corta una larga en una palabra completa y pone «…»', () => {
    const larga = 'Suministro y colocación de aplanado fino acabado rústico en muros interiores y exteriores con mortero';
    const c = descripcionCorta(larga, 48);
    expect(c.endsWith('…')).toBe(true);
    expect(c.length).toBeLessThanOrEqual(49);
    expect(larga.startsWith(c.slice(0, -1))).toBe(true);
  });
  it('tolera nulos y espacios repetidos', () => {
    expect(descripcionCorta(null)).toBe('');
    expect(descripcionCorta('  a   b ')).toBe('a b');
  });
});

import { textoDeEquivalencia } from '@/cuantificador/CambioDeUnidadDelConcepto';

describe('equivalencia de un cambio de unidad', () => {
  it('se lee en el sentido en que se divide', () => {
    expect(textoDeEquivalencia('pza', 'm²', 'area')).toBe('m² por cada pza');
    expect(textoDeEquivalencia('m²', 'pza', 'conteo')).toBe('m² por cada pza');
  });
});

import { reordenar } from '@/cuantificador/arbol';

describe('reordenar niveles, etapas y partidas', () => {
  it('subir un lugar intercambia con el de arriba y numera a todos', () => {
    const r = reordenar(['a', 'b', 'c'], 'c', 'up');
    expect([...(r ?? [])]).toEqual([['a', 1], ['c', 2], ['b', 3]]);
  });
  it('bajar el primero lo pasa al segundo lugar', () => {
    expect(reordenar(['a', 'b'], 'a', 'down')?.get('a')).toBe(2);
  });
  it('en el extremo no hay nada que cambiar', () => {
    expect(reordenar(['a', 'b'], 'a', 'up')).toBeNull();
    expect(reordenar(['a', 'b'], 'b', 'down')).toBeNull();
    expect(reordenar(['a', 'b'], 'zzz', 'up')).toBeNull();
  });
});
