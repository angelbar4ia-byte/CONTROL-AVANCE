/**
 * Reflejo de UX del workflow F — `src/incidencias/reglas.ts` y
 * `src/incidencias/formulario.ts` (§6, §7.8, §11.2, §11.3 F).
 *
 * Dos cosas se fijan aquí porque son las que más caro cuesta equivocar:
 *   1. Que `detiene` sea visible como lo que es —frena la obra, bloquea
 *      actividades y fuerza el recálculo de CPM (§6, §11.3 F.5)—.
 *   2. Que programar/cerrar/rechazar sean (S, C) y no se le ofrezcan al
 *      Residente, que abre incidencias pero no las resuelve (§11.2).
 */

import { describe, expect, it } from 'vitest';

import {
  accionesDisponiblesIncidencia,
  descripcionImpacto,
  detieneObra,
  estaRechazada,
  etapasFlujoF,
  etiquetaEstatus,
  etiquetaImpacto,
  etiquetaTipo,
  flujoCerrado,
  tonoEstatusIncidencia,
  tonoImpacto,
} from '@/incidencias/reglas';
import {
  formularioIncidenciaVacio,
  incidenciaCompleta,
  peticionDeIncidencia,
} from '@/incidencias/formulario';

describe('impacto (§6, §8.2)', () => {
  it('solo "detiene" frena la obra', () => {
    expect(detieneObra('detiene')).toBe(true);
    expect(detieneObra('retraso')).toBe(false);
    expect(detieneObra('detalle')).toBe(false);
  });

  it('"detiene" se pinta en rojo y "detalle" neutro', () => {
    expect(tonoImpacto('detiene')).toBe('danger');
    expect(tonoImpacto('retraso')).toBe('warn');
    expect(tonoImpacto('detalle')).toBe('outline');
  });

  it('la descripción de "detiene" nombra el bloqueo de actividades (§11.3 F.5)', () => {
    expect(descripcionImpacto('detiene')).toContain('bloquea actividades');
    expect(descripcionImpacto('retraso')).toContain('días');
    expect(descripcionImpacto('detalle')).toContain('No afecta');
  });

  it('etiqueta los tres impactos canónicos', () => {
    expect(etiquetaImpacto('detiene')).toBe('Detiene');
    expect(etiquetaImpacto('retraso')).toBe('Retraso');
    expect(etiquetaImpacto('detalle')).toBe('Detalle');
  });
});

describe('estatus (§8.2: los 6 valores canónicos)', () => {
  it('mapea los seis a un tono', () => {
    expect(tonoEstatusIncidencia('abierta')).toBe('warn');
    expect(tonoEstatusIncidencia('programada')).toBe('info');
    expect(tonoEstatusIncidencia('en_atencion')).toBe('accent');
    expect(tonoEstatusIncidencia('cierre_solicitado')).toBe('warn');
    expect(tonoEstatusIncidencia('cerrada')).toBe('ok');
    expect(tonoEstatusIncidencia('rechazada')).toBe('danger');
  });

  it('traduce los estatus con guion bajo a texto legible', () => {
    expect(etiquetaEstatus('en_atencion')).toBe('En atención');
    expect(etiquetaEstatus('cierre_solicitado')).toBe('Cierre solicitado');
  });

  it('etiqueta los seis tipos canónicos', () => {
    expect(etiquetaTipo('falta_material')).toBe('Falta de material');
    expect(etiquetaTipo('proyecto_indef')).toBe('Proyecto indefinido');
  });
});

describe('etapasFlujoF (§11.3 F: la escalera del flujo)', () => {
  it('recorre las cinco etapas del ciclo, sin "rechazada"', () => {
    const etapas = etapasFlujoF('abierta').map((e) => e.estatus);
    expect(etapas).toEqual([
      'abierta',
      'programada',
      'en_atencion',
      'cierre_solicitado',
      'cerrada',
    ]);
  });

  it('marca como alcanzado todo lo que quedó atrás, y solo uno como actual', () => {
    const etapas = etapasFlujoF('en_atencion');
    expect(etapas.filter((e) => e.alcanzada).map((e) => e.estatus)).toEqual([
      'abierta',
      'programada',
      'en_atencion',
    ]);
    expect(etapas.filter((e) => e.actual)).toHaveLength(1);
    expect(etapas.find((e) => e.actual)?.estatus).toBe('en_atencion');
  });

  it('una incidencia rechazada salió del flujo: nada de la escalera está alcanzado', () => {
    const etapas = etapasFlujoF('rechazada');
    expect(etapas.every((e) => !e.alcanzada)).toBe(true);
    expect(estaRechazada('rechazada')).toBe(true);
  });

  it('cerrada y rechazada terminan el flujo', () => {
    expect(flujoCerrado('cerrada')).toBe(true);
    expect(flujoCerrado('rechazada')).toBe(true);
    expect(flujoCerrado('en_atencion')).toBe(false);
  });
});

describe('accionesDisponiblesIncidencia (§11.2, §11.3 F)', () => {
  it('programar es de Supervisor y Control, sobre una incidencia abierta (F.2)', () => {
    expect(accionesDisponiblesIncidencia('supervisor', 'abierta')).toContain('programar');
    expect(accionesDisponiblesIncidencia('control_obra', 'abierta')).toContain('programar');
    expect(accionesDisponiblesIncidencia('residente', 'abierta')).not.toContain('programar');
  });

  it('el Residente participa en la atención pero no resuelve (F.3)', () => {
    expect(accionesDisponiblesIncidencia('residente', 'programada')).toEqual(['atender']);
    expect(accionesDisponiblesIncidencia('residente', 'en_atencion')).toEqual([
      'solicitar_cierre',
    ]);
    expect(accionesDisponiblesIncidencia('residente', 'cierre_solicitado')).toEqual([]);
  });

  it('cerrar es de Supervisor y Control, sobre un cierre solicitado (F.4)', () => {
    expect(accionesDisponiblesIncidencia('control_obra', 'cierre_solicitado')).toContain(
      'cerrar',
    );
    expect(accionesDisponiblesIncidencia('supervisor', 'cierre_solicitado')).toContain('cerrar');
    expect(accionesDisponiblesIncidencia('super_intendente', 'cierre_solicitado')).not.toContain(
      'cerrar',
    );
  });

  it('rechazar acompaña a quien resuelve, en cualquier estatus vivo (F.4)', () => {
    expect(accionesDisponiblesIncidencia('supervisor', 'abierta')).toContain('rechazar');
    expect(accionesDisponiblesIncidencia('control_obra', 'en_atencion')).toContain('rechazar');
    expect(accionesDisponiblesIncidencia('residente', 'abierta')).not.toContain('rechazar');
  });

  it('una incidencia ya cerrada o rechazada no ofrece nada a nadie', () => {
    expect(accionesDisponiblesIncidencia('control_obra', 'cerrada')).toEqual([]);
    expect(accionesDisponiblesIncidencia('supervisor', 'rechazada')).toEqual([]);
  });
});

describe('peticionDeIncidencia (DTO en el borde, §11.2)', () => {
  const base = {
    ...formularioIncidenciaVacio('obra-1', 'falta_material', 'detiene'),
    titulo: '  Falta cemento  ',
    bloqueaActividades: ['act-1', 'act-2'],
  };

  it('manda bloquea_actividades solo con impacto "detiene" (§6)', () => {
    expect(peticionDeIncidencia(base).bloquea_actividades).toEqual(['act-1', 'act-2']);
    const conRetraso = peticionDeIncidencia({ ...base, impacto: 'retraso' });
    expect(conRetraso.bloquea_actividades).toBeUndefined();
  });

  it('con impacto "detiene" pero sin actividades elegidas, omite el campo', () => {
    const dto = peticionDeIncidencia({ ...base, bloqueaActividades: [] });
    expect(dto.bloquea_actividades).toBeUndefined();
  });

  it('recorta el título y omite los opcionales vacíos', () => {
    const dto = peticionDeIncidencia(base);
    expect(dto.titulo).toBe('Falta cemento');
    expect(dto.descripcion).toBeUndefined();
    expect(dto.frente_id).toBeUndefined();
    expect(dto.nivel_id).toBeUndefined();
    expect(dto.etapa_id).toBeUndefined();
    expect(dto.fecha_limite).toBeUndefined();
  });

  it('manda nivel_id y etapa_id cuando el formulario los trae', () => {
    // Vienen de "va junto a esta actividad" en AltaIncidencia, no de un
    // select propio — el residente sabe con qué actividad está la
    // incidencia, no con qué nivel.
    const dto = peticionDeIncidencia({
      ...base,
      nivelId: 'niv-1',
      etapaId: 'eta-1',
    });
    expect(dto.nivel_id).toBe('niv-1');
    expect(dto.etapa_id).toBe('eta-1');
  });
});

describe('incidenciaCompleta (presencia, no validez)', () => {
  it('exige obra y título; el resto es opcional en el contrato', () => {
    const vacio = formularioIncidenciaVacio('', 'detalle', 'detalle');
    expect(incidenciaCompleta(vacio)).toBe(false);
    expect(incidenciaCompleta({ ...vacio, obraId: 'o' })).toBe(false);
    expect(incidenciaCompleta({ ...vacio, obraId: 'o', titulo: 'x' })).toBe(true);
  });
});
