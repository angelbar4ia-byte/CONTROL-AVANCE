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
  despuesDeSubir,
  etiquetaConPaso,
  etiquetaEstatus,
  etiquetaModo,
  etiquetaTipo,
  modoDestructivo,
  resumenDe,
  seePuedeRevertir,
  sePuedeEliminar,
  tonoEstatus,
} from '@/cargas/reglas';
import type { LoteRespuesta } from '@/api/generado/modelo';

function lote(parcial: Partial<LoteRespuesta> = {}): LoteRespuesta {
  return {
    id: 'l-1',
    tipo: 'catalogo_conceptos',
    modo: 'actualizar',
    // Los valores reales de `EstatusCarga` (backend): "aplicado",
    // "previsualizado", "error" — no "aplicada"/"vista_previa"/"con_errores".
    estatus: 'aplicado',
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
    expect(seePuedeRevertir(lote({ estatus: 'previsualizado' }))).toBe(false);
  });

  it('una con errores, no', () => {
    expect(seePuedeRevertir(lote({ estatus: 'error' }))).toBe(false);
  });
});

describe('qué se puede eliminar (§10.8)', () => {
  it('una vista previa, sí: nunca escribió nada', () => {
    expect(sePuedeEliminar(lote({ estatus: 'previsualizado' }))).toBe(true);
  });

  it('una con errores, sí', () => {
    expect(sePuedeEliminar(lote({ estatus: 'error' }))).toBe(true);
  });

  it('una aplicada y sin revertir, no: se perdería la forma de deshacerla', () => {
    expect(sePuedeEliminar(lote())).toBe(false);
  });

  it('una aplicada y ya revertida, sí: sus cambios ya se deshicieron', () => {
    expect(sePuedeEliminar(lote({ revertida: true }))).toBe(true);
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
  it('todos los tipos del enum tienen etiqueta propia', () => {
    for (const tipo of TIPOS) {
      expect(etiquetaTipo(tipo)).not.toBe(tipo);
    }
  });

  it('un tipo desconocido se muestra tal cual en vez de desaparecer', () => {
    expect(etiquetaTipo('inventado')).toBe('inventado');
  });
});

describe('estatus', () => {
  it('aplicado y error no se ven igual', () => {
    expect(tonoEstatus('aplicado')).not.toBe(tonoEstatus('error'));
  });

  it('el guion bajo no llega a la pantalla', () => {
    expect(etiquetaEstatus('mapeo_no_reconocido')).toBe('mapeo no reconocido');
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

describe('orden de subida de los archivos', () => {
  it('el selector sigue el orden de carga y numera los pasos', () => {
    const e = (t: string) => TIPOS.indexOf(t as (typeof TIPOS)[number]);
    expect(e('materiales')).toBeLessThan(e('trabajos'));
    expect(e('trabajos')).toBeLessThan(e('semilla_cuadrilla_rendimiento'));
    expect(e('mano_de_obra')).toBeLessThan(e('semilla_cuadrilla_rendimiento'));
    expect(e('prototipos')).toBeLessThan(e('cpu'));
    expect(e('cpu')).toBeLessThan(e('almacen'));
    expect(etiquetaConPaso('unidades')).toBe('1. Unidades');
    expect(etiquetaConPaso('catalogo_conceptos')).toMatch(/^Otros · /);
  });

  it('el archivo de presupuesto se sube por «Presupuesto y prototipos»', () => {
    expect(TIPOS).not.toContain('presupuesto');
    expect(etiquetaTipo('prototipos')).toMatch(/Presupuesto/);
  });
});

describe('el presupuesto se sube dos veces', () => {
  it('el selector avisa, en los dos tipos, que el presupuesto se repite tras el análisis de básicos', () => {
    expect(despuesDeSubir('prototipos')).toMatch(/otra vez/);
    expect(despuesDeSubir('cpu')).toMatch(/vuelve a subir/);
    expect(despuesDeSubir('materiales')).toBeNull();
  });
});
