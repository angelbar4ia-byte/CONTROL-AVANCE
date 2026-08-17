/**
 * Reflejo de UX del workflow H — `src/evaluaciones/reglas.ts` y
 * `src/evaluaciones/formulario.ts` (§6, §7.8, §11.2, §11.3 H).
 *
 * Lo que se fija aquí es la correspondencia rol → nivel: auto es del
 * Residente, control de Control de obra y final del Super intendente
 * (§11.3 H). Ofrecerle a un rol el nivel de otro sería un 422 seguro —el
 * dominio valida el permiso del nivel—, y en la autoevaluación además el
 * sujeto tiene que ser uno mismo o la propia obra.
 */

import { describe, expect, it } from 'vitest';

import {
  criteriosPendientes,
  descripcionNivel,
  etiquetaNivel,
  etiquetaSujeto,
  nivelDelRol,
  puedeCrearEvaluacion,
  puedeResponder,
  sujetosDelNivel,
  tonoNivel,
  tonoPuntaje,
} from '@/evaluaciones/reglas';
import {
  evaluacionCompleta,
  formularioEvaluacionVacio,
  hayRespuestas,
  peticionDeEvaluacion,
  peticionDeRespuestas,
  periodoActual,
  type CapturaRespuesta,
} from '@/evaluaciones/formulario';

describe('nivelDelRol (§11.3 H: auto R · control C · final SI)', () => {
  it('cada rol del workflow tiene exactamente su nivel', () => {
    expect(nivelDelRol('residente')).toBe('auto');
    expect(nivelDelRol('control_obra')).toBe('control');
    expect(nivelDelRol('super_intendente')).toBe('final');
  });

  it('el Supervisor no participa en el workflow H y no puede crear', () => {
    expect(nivelDelRol('supervisor')).toBeNull();
    expect(puedeCrearEvaluacion('supervisor')).toBe(false);
    expect(puedeCrearEvaluacion('residente')).toBe(true);
  });

  it('etiqueta y describe los tres niveles', () => {
    expect(etiquetaNivel('auto')).toBe('Autoevaluación');
    expect(descripcionNivel('auto')).toContain('sí mismo');
    expect(descripcionNivel('control')).toContain('contratista');
    expect(descripcionNivel('final')).toContain('consolida');
    expect(tonoNivel('final')).toBe('accent');
  });
});

describe('sujetosDelNivel (§6: sujetos obra · residente · contratista)', () => {
  it('la autoevaluación es sobre uno mismo y su obra: no evalúa contratistas', () => {
    expect(sujetosDelNivel('auto')).toEqual(['obra', 'residente']);
    expect(sujetosDelNivel('auto')).not.toContain('contratista');
  });

  it('control y final abarcan los tres sujetos del §8.2', () => {
    expect(sujetosDelNivel('control')).toEqual(['obra', 'residente', 'contratista']);
    expect(sujetosDelNivel('final')).toEqual(['obra', 'residente', 'contratista']);
  });

  it('etiqueta los tres sujetos', () => {
    expect(etiquetaSujeto('obra')).toBe('Obra');
    expect(etiquetaSujeto('contratista')).toBe('Contratista');
  });
});

describe('puedeResponder (§7.8: solo quien creó la evaluación)', () => {
  it('el evaluador responde su propia evaluación', () => {
    expect(puedeResponder('u-1', 'u-1')).toBe(true);
  });

  it('otro usuario la ve en lectura', () => {
    expect(puedeResponder('u-1', 'u-2')).toBe(false);
  });
});

describe('tonoPuntaje (el puntaje lo pondera el dominio, §7.8)', () => {
  it('traduce a tono el puntaje ya calculado, sin recalcularlo', () => {
    expect(tonoPuntaje('95')).toBe('ok');
    expect(tonoPuntaje('80')).toBe('warn');
    expect(tonoPuntaje('65')).toBe('danger');
  });

  it('una evaluación sin responder todavía no tiene puntaje', () => {
    expect(tonoPuntaje(null)).toBe('outline');
    expect(tonoPuntaje('')).toBe('outline');
  });
});

describe('criteriosPendientes', () => {
  it('lista los criterios que aún no tienen respuesta', () => {
    const criterios = [{ id: 'c1' }, { id: 'c2' }, { id: 'c3' }];
    expect(criteriosPendientes(criterios, [{ criterio_id: 'c2' }])).toEqual(['c1', 'c3']);
  });

  it('sin pendientes cuando todos están respondidos', () => {
    const criterios = [{ id: 'c1' }];
    expect(criteriosPendientes(criterios, [{ criterio_id: 'c1' }])).toEqual([]);
  });
});

describe('peticionDeEvaluacion (DTO en el borde, §11.2)', () => {
  it('recorta el sujeto y omite la obra vacía', () => {
    const dto = peticionDeEvaluacion({
      ...formularioEvaluacionVacio('control', '2026-08'),
      sujetoTipo: 'contratista',
      sujetoId: ' k-1 ',
    });
    expect(dto.sujeto_id).toBe('k-1');
    expect(dto.obra_id).toBeUndefined();
    expect(dto.nivel).toBe('control');
  });

  it('conserva la obra cuando la evaluación cuelga de una', () => {
    const dto = peticionDeEvaluacion({
      ...formularioEvaluacionVacio('auto', '2026-08'),
      sujetoTipo: 'residente',
      sujetoId: 'u-1',
      obraId: 'o-1',
    });
    expect(dto.obra_id).toBe('o-1');
  });

  it('exige sujeto y periodo; el permiso del nivel lo decide el dominio', () => {
    const vacio = formularioEvaluacionVacio('auto', '2026-08');
    expect(evaluacionCompleta(vacio)).toBe(false);
    expect(evaluacionCompleta({ ...vacio, sujetoId: 'u-1' })).toBe(true);
  });
});

describe('peticionDeRespuestas (§11.2 POST /evaluaciones/{id}/respuestas)', () => {
  function capturas(entradas: Record<string, CapturaRespuesta>) {
    return new Map(Object.entries(entradas));
  }

  it('omite los criterios sin valor: el contrato exige al menos una respuesta', () => {
    const dto = peticionDeRespuestas(
      capturas({
        c1: { valor: '90', comentario: '' },
        c2: { valor: '  ', comentario: 'solo comentario' },
      }),
    );
    expect(dto.respuestas).toHaveLength(1);
    expect(dto.respuestas[0]?.criterio_id).toBe('c1');
  });

  it('el valor viaja como string decimal, no como number', () => {
    const dto = peticionDeRespuestas(capturas({ c1: { valor: ' 87.50 ', comentario: '' } }));
    expect(dto.respuestas[0]?.valor).toBe('87.50');
    expect(typeof dto.respuestas[0]?.valor).toBe('string');
  });

  it('el comentario vacío se omite en vez de mandarse en blanco', () => {
    const dto = peticionDeRespuestas(capturas({ c1: { valor: '90', comentario: '  ' } }));
    expect(dto.respuestas[0]?.comentario).toBeUndefined();
  });

  it('hayRespuestas es falso mientras no haya ningún valor capturado', () => {
    expect(hayRespuestas(capturas({}))).toBe(false);
    expect(hayRespuestas(capturas({ c1: { valor: '', comentario: 'x' } }))).toBe(false);
    expect(hayRespuestas(capturas({ c1: { valor: '1', comentario: '' } }))).toBe(true);
  });
});

describe('periodoActual (§7.8: WWYY o YYYY-MM)', () => {
  it('propone el mes con dos dígitos', () => {
    expect(periodoActual(new Date(2026, 0, 15))).toBe('2026-01');
    expect(periodoActual(new Date(2026, 11, 1))).toBe('2026-12');
  });
});
