/**
 * Lo que queda del spec en web: procesos, bitácora y avance total (Fase 16).
 *
 * Las tres pantallas cerraban entradas del sidebar del Super intendente (§5.1)
 * que caían en "en construcción". Se prueban sus **reglas puras**, que es
 * donde vive lo que se puede equivocar:
 *
 * - quién puede escribir un proceso (§11.2: SI),
 * - cómo se lee el diff de la bitácora (migración 0023),
 * - qué significan los dos avances del reporte, que no son lo mismo.
 */

import { describe, expect, it } from 'vitest';

import { diferencias } from '@/bitacora/Bitacora';
import {
  ESTATUS_PROCESO,
  etiquetaEstatus,
  ordenDeEstatus,
  procesoCompleto,
  puedeEditarProcesos,
  tonoEstatus,
} from '@/procesos/reglas';
import { agregar, porProyecto, requiereAtencion } from '@/reportes/AvanceTotal';
import type { EstadoDeObraRespuesta } from '@/api/generado/modelo';

describe('procesos · permisos', () => {
  it('solo el Super intendente escribe', () => {
    expect(puedeEditarProcesos('super_intendente')).toBe(true);
    expect(puedeEditarProcesos('control_obra')).toBe(false);
    expect(puedeEditarProcesos('residente')).toBe(false);
    expect(puedeEditarProcesos('supervisor')).toBe(false);
  });
});

describe('procesos · tablero', () => {
  it('los cuatro estatus son los del backend', () => {
    // Espejo de `EstatusProceso` en `domain/shared/diccionario.py`.
    expect([...ESTATUS_PROCESO]).toEqual([
      'propuesto',
      'en_curso',
      'adoptado',
      'descartado',
    ]);
  });

  it('pone arriba lo que está en movimiento', () => {
    const orden = [...ESTATUS_PROCESO].sort((a, b) => ordenDeEstatus(a) - ordenDeEstatus(b));
    expect(orden).toEqual(['en_curso', 'propuesto', 'adoptado', 'descartado']);
  });

  it('descartado no se pinta como error', () => {
    // Descartar lo que se probó es un resultado, no un fallo: pintarlo en
    // rojo desalienta justo lo que el tablero quiere provocar.
    expect(tonoEstatus('descartado')).not.toContain('danger');
    expect(tonoEstatus('adoptado')).toBe('badge--ok');
  });

  it('un estatus desconocido se muestra crudo en vez de mentir', () => {
    expect(etiquetaEstatus('piloto')).toBe('piloto');
  });

  it('exige nombre y no descripción', () => {
    // Obligar a redactar el "por qué" antes de anotar la idea es la forma más
    // segura de que la idea no se anote.
    expect(procesoCompleto({ nombre: 'Junta de arranque', descripcion: '' })).toBe(true);
    expect(procesoCompleto({ nombre: '   ', descripcion: 'algo' })).toBe(false);
  });
});

describe('bitácora · diff', () => {
  it('saca el antes y el después de un update', () => {
    const datos = {
      cambio: { antes: { iva: 0.16 }, despues: { iva: 0.08 } },
      despues: { id: 'x', iva: 0.08 },
    };

    expect(diferencias(datos)).toEqual([
      { campo: 'iva', antes: '0.16', despues: '0.08' },
    ]);
  });

  it('distingue "se borró el valor" de "no cambió"', () => {
    // Con `String(null)` los dos se verían como vacío, y esa diferencia es
    // justo lo que se viene a ver a una bitácora.
    const datos = { cambio: { antes: { nota: 'algo' }, despues: { nota: null } } };

    expect(diferencias(datos)[0]).toEqual({
      campo: 'nota',
      antes: '"algo"',
      despues: 'null',
    });
  });

  it('un alta no tiene diff', () => {
    // La fila entera es el dato; la pantalla muestra el JSON completo.
    expect(diferencias({ despues: { id: 'x' } })).toEqual([]);
  });

  it('tolera datos vacíos o mal formados', () => {
    expect(diferencias(null)).toEqual([]);
    expect(diferencias('texto')).toEqual([]);
    expect(diferencias({ cambio: 'no es objeto' })).toEqual([]);
  });
});

function obra(cambios: Partial<EstadoDeObraRespuesta> = {}): EstadoDeObraRespuesta {
  return {
    obra_id: crypto.randomUUID(),
    obra_clave: 'FRESNO 01',
    obra_estatus: 'en_proceso',
    avance_pct: '40',
    fecha_inicio: null,
    fecha_fin: null,
    cluster_id: crypto.randomUUID(),
    cluster_clave: 'FRESNO',
    proyecto_id: crypto.randomUUID(),
    proyecto_clave: 'MAGNOLIA',
    residente_nombre: 'Ana',
    actividades: 10,
    criticas: 2,
    bloqueadas: 0,
    concluidas: 4,
    incidencias_abiertas: 0,
    incidencias_detienen: 0,
    cierres_pendientes: 0,
    ...cambios,
  } as EstadoDeObraRespuesta;
}

describe('avance total · totales', () => {
  it('el avance por actividades es un conteo, no un promedio', () => {
    const totales = agregar([
      obra({ actividades: 10, concluidas: 4 }),
      obra({ actividades: 30, concluidas: 6 }),
    ]);

    // 10 de 40, no la media de 40% y 20%.
    expect(totales.avancePorActividades).toBe(25);
  });

  it('el promedio simple difiere del conteo y por eso se muestran los dos', () => {
    const totales = agregar([
      obra({ actividades: 1, concluidas: 1, avance_pct: '100' }),
      obra({ actividades: 99, concluidas: 0, avance_pct: '0' }),
    ]);

    expect(totales.promedioSimple).toBe(50);
    expect(totales.avancePorActividades).toBe(1);
  });

  it('una cartera sin actividades no divide entre cero', () => {
    const totales = agregar([obra({ actividades: 0, concluidas: 0, avance_pct: '0' })]);

    expect(totales.avancePorActividades).toBe(0);
    expect(totales.promedioSimple).toBe(0);
  });

  it('sin obras todo es cero', () => {
    expect(agregar([])).toMatchObject({ obras: 0, avancePorActividades: 0 });
  });

  it('coincide con el criterio de atención de la Torre', () => {
    expect(requiereAtencion(obra())).toBe(false);
    expect(requiereAtencion(obra({ bloqueadas: 1 }))).toBe(true);
    expect(requiereAtencion(obra({ incidencias_abiertas: 1 }))).toBe(true);
    expect(requiereAtencion(obra({ cierres_pendientes: 1 }))).toBe(true);
    expect(requiereAtencion(obra({ incidencias_detienen: 1 }))).toBe(true);
  });

  it('cuenta obras y no motivos', () => {
    const totales = agregar([
      obra({ bloqueadas: 2, incidencias_abiertas: 1, cierres_pendientes: 1 }),
      obra(),
    ]);
    expect(totales.conPendientes).toBe(1);
  });
});

describe('avance total · por proyecto', () => {
  it('agrupa y ordena alfabéticamente', () => {
    const filas = porProyecto([
      obra({ proyecto_clave: 'ROBLE', actividades: 10, concluidas: 5 }),
      obra({ proyecto_clave: 'MAGNOLIA', actividades: 10, concluidas: 1 }),
      obra({ proyecto_clave: 'MAGNOLIA', actividades: 10, concluidas: 3 }),
    ]);

    expect(filas.map((f) => f.proyecto)).toEqual(['MAGNOLIA', 'ROBLE']);
    expect(filas[0]).toMatchObject({ obras: 2, actividades: 20, concluidas: 4, avance: 20 });
  });

  it('una obra sin proyecto no se pierde', () => {
    const filas = porProyecto([obra({ proyecto_clave: '' })]);
    expect(filas[0]?.proyecto).toBe('(sin proyecto)');
  });
});
