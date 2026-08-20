/**
 * Cómo se lee el estado de una obra en la Torre — `src/torre/reglas.ts` (§5.1).
 *
 * Lo que se fija aquí es la clasificación en tres estados y su orden de
 * importancia. Es lo único que esta pantalla decide por su cuenta: los conteos
 * los calcula el backend, pero **qué significa cada número** —qué impide
 * trabajar y qué solo espera a alguien— es lo que convierte una tabla en una
 * lista de tareas.
 */

import { describe, expect, it } from 'vitest';

import {
  etiquetaEstatusActividad,
  etiquetaUrgencia,
  filtrarObras,
  resumirTorre,
  subtituloDeTorre,
  tituloDeTorre,
  tonoEstatusActividad,
  tonoUrgencia,
  urgenciaDe,
} from '@/torre/reglas';
import type { EstadoDeObraRespuesta } from '@/api/generado/modelo';

function obra(parcial: Partial<EstadoDeObraRespuesta> = {}): EstadoDeObraRespuesta {
  return {
    obra_id: 'o-1',
    obra_clave: 'FRESNO 01',
    obra_estatus: 'en_proceso',
    avance_pct: '42.5',
    fecha_inicio: null,
    fecha_fin: null,
    cluster_id: 'c-1',
    cluster_clave: 'FRESNO',
    proyecto_id: 'p-1',
    proyecto_clave: 'MAGNOLIA',
    residente_nombre: 'Ana Ruiz',
    actividades: 10,
    criticas: 3,
    bloqueadas: 0,
    concluidas: 4,
    incidencias_abiertas: 0,
    incidencias_detienen: 0,
    cierres_pendientes: 0,
    ...parcial,
  } as EstadoDeObraRespuesta;
}

describe('urgencia: tres estados, no cinco', () => {
  it('una actividad bloqueada detiene la obra', () => {
    expect(urgenciaDe(obra({ bloqueadas: 1 }))).toBe('detenida');
  });

  it('una incidencia que detiene también', () => {
    expect(urgenciaDe(obra({ incidencias_abiertas: 1, incidencias_detienen: 1 }))).toBe(
      'detenida',
    );
  });

  it('un cierre esperando es pendiente, no detenida', () => {
    // La diferencia importa: detenida es "no se puede trabajar", pendiente es
    // "alguien tiene que resolver algo". Mezclarlas haría que todo se vea rojo.
    expect(urgenciaDe(obra({ cierres_pendientes: 2 }))).toBe('pendiente');
  });

  it('una incidencia abierta que no detiene es pendiente', () => {
    expect(urgenciaDe(obra({ incidencias_abiertas: 1 }))).toBe('pendiente');
  });

  it('sin nada esperando, al corriente', () => {
    expect(urgenciaDe(obra())).toBe('al-corriente');
  });

  it('un avance bajo NO tiñe la obra de rojo', () => {
    // Una obra al 5 % puede ir perfectamente en tiempo. Clasificarla por el
    // número enseñaría a ignorar los rojos, que es lo peor que le puede pasar a
    // un tablero.
    expect(urgenciaDe(obra({ avance_pct: '5' }))).toBe('al-corriente');
  });

  it('detenida y pendiente no se ven igual', () => {
    expect(tonoUrgencia('detenida')).not.toBe(tonoUrgencia('pendiente'));
    expect(tonoUrgencia('pendiente')).not.toBe(tonoUrgencia('al-corriente'));
  });

  it('los tres estados tienen etiqueta', () => {
    expect(etiquetaUrgencia('detenida')).toBe('Detenida');
    expect(etiquetaUrgencia('pendiente')).toBe('Pendiente');
    expect(etiquetaUrgencia('al-corriente')).toBe('Al corriente');
  });
});

describe('resumen de la cabecera', () => {
  it('cuenta cada obra en un solo estado', () => {
    const resumen = resumirTorre([
      obra({ obra_id: '1', bloqueadas: 2 }),
      obra({ obra_id: '2', cierres_pendientes: 1 }),
      obra({ obra_id: '3' }),
    ]);
    expect(resumen.obras).toBe(3);
    expect(resumen.detenidas).toBe(1);
    expect(resumen.pendientes).toBe(1);
    expect(resumen.alCorriente).toBe(1);
    // Los tres estados suman el total: ninguna obra se pierde ni se cuenta dos
    // veces.
    expect(resumen.detenidas + resumen.pendientes + resumen.alCorriente).toBe(3);
  });

  it('suma los pendientes de todas las obras', () => {
    const resumen = resumirTorre([
      obra({ obra_id: '1', cierres_pendientes: 2, incidencias_abiertas: 1 }),
      obra({ obra_id: '2', cierres_pendientes: 3 }),
    ]);
    expect(resumen.cierresPendientes).toBe(5);
    expect(resumen.incidenciasAbiertas).toBe(1);
  });

  it('sin obras, todo en cero', () => {
    expect(resumirTorre([]).obras).toBe(0);
    expect(resumirTorre([]).alCorriente).toBe(0);
  });
});

describe('búsqueda', () => {
  const obras = [
    obra({ obra_id: '1', obra_clave: 'FRESNO 01', residente_nombre: 'Ana Ruiz' }),
    obra({
      obra_id: '2',
      obra_clave: 'CEDRO 01',
      cluster_clave: 'CEDRO',
      proyecto_clave: 'ROBLE',
      residente_nombre: 'Luis Paz',
    }),
  ];

  it('sin texto devuelve todo', () => {
    expect(filtrarObras(obras, '   ')).toHaveLength(2);
  });

  it('busca por clave de obra', () => {
    expect(filtrarObras(obras, 'cedro')).toHaveLength(1);
  });

  it('busca por proyecto', () => {
    expect(filtrarObras(obras, 'ROBLE')[0]?.obra_id).toBe('2');
  });

  it('busca por residente: con ochenta obras es a veces lo más rápido', () => {
    expect(filtrarObras(obras, 'ana')[0]?.obra_id).toBe('1');
  });

  it('una obra sin residente no rompe la búsqueda', () => {
    const sinResidente = [obra({ obra_id: '3', residente_nombre: null })];
    expect(filtrarObras(sinResidente, 'fresno')).toHaveLength(1);
  });
});

describe('la misma pantalla dice algo distinto según quién la abre (§5.3)', () => {
  it('el supervisor autoriza; control valida', () => {
    expect(subtituloDeTorre('supervisor')).toContain('autorización');
    expect(subtituloDeTorre('control_obra')).toContain('validación');
  });

  it('el residente no ve una torre, ve sus obras', () => {
    expect(tituloDeTorre('residente')).toBe('Mis obras');
    expect(tituloDeTorre('supervisor')).toBe('Torre de control');
  });
});

describe('estatus de actividad (§8.2)', () => {
  it('traduce los siete del enum', () => {
    for (const estatus of [
      'programada',
      'en_proceso',
      'casi',
      'pendiente_cierre',
      'concluida',
      'retrasada',
      'extra_catalogo',
    ]) {
      expect(etiquetaEstatusActividad(estatus)).not.toContain('_');
    }
  });

  it('concluida y retrasada no se ven igual', () => {
    expect(tonoEstatusActividad('concluida')).not.toBe(tonoEstatusActividad('retrasada'));
  });

  it('un estatus desconocido se muestra tal cual en vez de desaparecer', () => {
    expect(etiquetaEstatusActividad('inventado')).toBe('inventado');
  });
});
