/**
 * Reflejo de UX de las reglas de carga — `src/cargas/reglas.ts` (§10).
 *
 * Lo que se fija aquí son las dos preguntas que la pantalla responde sin ir al
 * servidor —¿este lote se puede revertir?, ¿este modo borra?— y la lectura
 * tolerante del `resumen`, que viaja como `dict` en el contrato y podría venir
 * incompleto de una carga vieja.
 */

import { describe, expect, it } from 'vitest';

import {
  MODOS,
  TIPOS,
  descripcionModo,
  etiquetaEstatus,
  etiquetaModo,
  etiquetaTipo,
  modoDestructivo,
  resumenDe,
  seePuedeRevertir,
  tonoEstatus,
} from '@/cargas/reglas';
import type { LoteRespuesta } from '@/api/generado/modelo';

function lote(parcial: Partial<LoteRespuesta> = {}): LoteRespuesta {
  return {
    id: 'l-1',
    tipo: 'catalogo_conceptos',
    modo: 'actualizar',
    estatus: 'aplicada',
    archivo_nombre: 'conceptos.xlsx',
    archivo_hash: 'abc123',
    version_generada: 3,
    revertida: false,
    resumen: { filas: 10, insertados: 4, actualizados: 6, omitidos: 0 },
    errores: [],
    ...parcial,
  };
}

describe('qué se puede revertir (§10.8)', () => {
  it('una carga aplicada, sí', () => {
    expect(seePuedeRevertir(lote())).toBe(true);
  });

  it('una ya revertida, no: no queda qué deshacer', () => {
    expect(seePuedeRevertir(lote({ revertida: true }))).toBe(false);
  });

  it('una vista previa, no: no escribió nada', () => {
    expect(seePuedeRevertir(lote({ estatus: 'vista_previa' }))).toBe(false);
  });

  it('una con errores, no', () => {
    expect(seePuedeRevertir(lote({ estatus: 'con_errores' }))).toBe(false);
  });
});

describe('modos (§10.2)', () => {
  it('los tres del enum tienen descripción', () => {
    for (const modo of MODOS) {
      expect(descripcionModo(modo)).not.toBe('');
    }
  });

  it('reemplazar es el que borra, y se advierte', () => {
    expect(modoDestructivo('reemplazar')).toBe(true);
    expect(modoDestructivo('actualizar')).toBe(false);
    expect(modoDestructivo('acumular')).toBe(false);
  });

  it('la etiqueta se lee', () => {
    expect(etiquetaModo('actualizar')).toBe('Actualizar');
  });
});

describe('tipos (§10.6)', () => {
  it('los nueve del enum tienen etiqueta propia', () => {
    for (const tipo of TIPOS) {
      expect(etiquetaTipo(tipo)).not.toBe(tipo);
    }
  });

  it('un tipo desconocido se muestra tal cual en vez de desaparecer', () => {
    expect(etiquetaTipo('inventado')).toBe('inventado');
  });
});

describe('estatus', () => {
  it('aplicada y con_errores no se ven igual', () => {
    expect(tonoEstatus('aplicada')).not.toBe(tonoEstatus('con_errores'));
  });

  it('el guion bajo no llega a la pantalla', () => {
    expect(etiquetaEstatus('vista_previa')).toBe('vista previa');
  });
});

describe('resumen tolerante', () => {
  it('lee los cuatro números', () => {
    expect(resumenDe(lote())).toEqual({
      filas: 10,
      insertados: 4,
      actualizados: 6,
      omitidos: 0,
    });
  });

  it('un resumen incompleto no rompe la fila', () => {
    // `resumen` es un `dict` en el contrato: una carga vieja puede no traer
    // todas las claves, y la tabla tiene que seguir pintándose.
    expect(resumenDe(lote({ resumen: { filas: 5 } }))).toEqual({
      filas: 5,
      insertados: 0,
      actualizados: 0,
      omitidos: 0,
    });
  });

  it('un resumen vacío se lee como ceros', () => {
    expect(resumenDe(lote({ resumen: {} })).filas).toBe(0);
  });
});
