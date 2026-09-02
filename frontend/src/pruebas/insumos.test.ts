/**
 * Reglas de UX de insumos programados — `src/insumos/reglas.ts`.
 *
 * La frontera que estas pruebas protegen es la misma que `materiales.test.ts`:
 * **la web enseña lo que el backend calculó y no lo recalcula.** Si algún día
 * aparece aquí una prueba que multiplica cantidad por rendimiento, o que
 * reparte una cifra entre semanas, esa es la señal de que la regla se duplicó
 * — el cálculo vive en `domain/insumos/programado.py`.
 *
 * Lo que sí se fija aquí es de presentación, y son tres cosas que rompen la
 * pantalla en silencio:
 *
 *  1. **Qué modos ofrece cada rol.** Ofrecerle "por supervisor" a un residente
 *     sería un filtro que siempre sale vacío.
 *  2. **Que no se consulte antes de tiempo.** Un modo que necesita un id y no
 *     lo tiene traería todo lo que el rol alcanza, que no es lo que se pidió.
 *  3. **Que solo viaje el parámetro del modo elegido.** Mandar dos filtros a la
 *     vez los acumula en el backend, y la intersección casi siempre es vacía.
 */

import { describe, expect, it } from 'vitest';

import {
  TIPOS_INSUMO,
  alternarTipo,
  etiquetaModo,
  etiquetaTipo,
  filtroInicial,
  listoParaConsultar,
  modosDeAlcance,
  parametrosDeConsulta,
  rangoPorDefecto,
  rangoValido,
  veImportes,
  type FiltroInsumos,
} from '@/insumos/reglas';

const HOY = new Date(2026, 4, 11); // 11 de mayo de 2026

function filtro(sobre: Partial<FiltroInsumos> = {}): FiltroInsumos {
  return { ...filtroInicial('control_obra', HOY), ...sobre };
}

describe('modos de alcance por rol (§4)', () => {
  it('el residente pregunta por una obra o por todas las suyas', () => {
    const modos = modosDeAlcance('residente');
    expect(modos).toContain('obra');
    expect(modos).toContain('todas');
    // De él no cuelga nadie: agrupar por residente o supervisor saldría vacío.
    expect(modos).not.toContain('residente');
    expect(modos).not.toContain('supervisor');
  });

  it('el supervisor agrupa además por residente, pero no por supervisor', () => {
    const modos = modosDeAlcance('supervisor');
    expect(modos).toContain('residente');
    expect(modos).not.toContain('supervisor');
  });

  it('control y el super intendente tienen los cinco', () => {
    for (const rol of ['control_obra', 'super_intendente'] as const) {
      expect(modosDeAlcance(rol)).toEqual(
        expect.arrayContaining(['obra', 'residente', 'supervisor', 'todas', 'prototipo']),
      );
    }
  });

  it('la simulación por prototipo la ven los cuatro', () => {
    // Preguntar qué lleva una casa de un modelo no depende de tener obras.
    for (const rol of ['residente', 'supervisor', 'control_obra', 'super_intendente'] as const) {
      expect(modosDeAlcance(rol)).toContain('prototipo');
    }
  });

  it('cada modo tiene etiqueta legible', () => {
    for (const modo of modosDeAlcance('control_obra')) {
      expect(etiquetaModo(modo)).not.toBe('');
    }
  });
});

describe('quién ve importes (§4)', () => {
  it('solo control de obra y el super intendente', () => {
    expect(veImportes('control_obra')).toBe(true);
    expect(veImportes('super_intendente')).toBe(true);
    // El residente ve cuánto material hace falta, no cuánto cuesta.
    expect(veImportes('residente')).toBe(false);
    expect(veImportes('supervisor')).toBe(false);
  });
});

describe('el rango consultado', () => {
  it('mira hacia adelante: la pregunta es qué falta por comprar', () => {
    const rango = rangoPorDefecto(HOY, 'semana');
    expect(rango.desde).toBe('2026-05-11');
    expect(rango.hasta > rango.desde).toBe(true);
  });

  it('por mes abarca más que por semana', () => {
    const semanas = rangoPorDefecto(HOY, 'semana');
    const meses = rangoPorDefecto(HOY, 'mes');
    expect(meses.hasta > semanas.hasta).toBe(true);
  });

  it('un rango al revés no es consultable', () => {
    expect(rangoValido({ desde: '2026-06-01', hasta: '2026-05-01' })).toBe(false);
    expect(rangoValido({ desde: '2026-05-01', hasta: '2026-06-01' })).toBe(true);
    expect(rangoValido({ desde: '', hasta: '2026-06-01' })).toBe(false);
  });
});

describe('cuándo se puede consultar', () => {
  it('un modo que necesita id no consulta sin él', () => {
    expect(listoParaConsultar(filtro({ modo: 'obra', obraId: '' }))).toBe(false);
    expect(listoParaConsultar(filtro({ modo: 'obra', obraId: 'o-1' }))).toBe(true);
    expect(listoParaConsultar(filtro({ modo: 'residente', residenteId: '' }))).toBe(false);
    expect(listoParaConsultar(filtro({ modo: 'supervisor', supervisorId: '' }))).toBe(false);
  });

  it('"todas" no necesita nada más', () => {
    expect(listoParaConsultar(filtro({ modo: 'todas' }))).toBe(true);
  });

  it('la simulación necesita prototipo y al menos una casa', () => {
    expect(listoParaConsultar(filtro({ modo: 'prototipo', prototipoId: '' }))).toBe(false);
    expect(
      listoParaConsultar(filtro({ modo: 'prototipo', prototipoId: 'p-1', nCasas: 0 })),
    ).toBe(false);
    expect(
      listoParaConsultar(filtro({ modo: 'prototipo', prototipoId: 'p-1', nCasas: 40 })),
    ).toBe(true);
  });

  it('un rango inválido bloquea cualquier modo', () => {
    expect(
      listoParaConsultar(
        filtro({ modo: 'todas', rango: { desde: '2026-06-01', hasta: '2026-05-01' } }),
      ),
    ).toBe(false);
  });
});

describe('los parámetros que viajan', () => {
  it('solo el del modo elegido, no todos a la vez', () => {
    // Mandar obra_id y residente_id juntos los acumula en el backend y la
    // intersección casi siempre es vacía, sin decir por qué.
    const params = parametrosDeConsulta(
      filtro({ modo: 'obra', obraId: 'o-1', residenteId: 'r-1', supervisorId: 's-1' }),
    );
    expect(params.obra_id).toBe('o-1');
    expect(params.residente_id).toBeUndefined();
    expect(params.supervisor_id).toBeUndefined();
  });

  it('"todas" no manda ningún filtro de alcance', () => {
    const params = parametrosDeConsulta(filtro({ modo: 'todas', obraId: 'o-1' }));
    expect(params.obra_id).toBeUndefined();
    expect(params.residente_id).toBeUndefined();
  });

  it('la simulación manda prototipo y casas', () => {
    const params = parametrosDeConsulta(
      filtro({ modo: 'prototipo', prototipoId: 'p-1', nCasas: 40 }),
    );
    expect(params).toMatchObject({ prototipo_id: 'p-1', n_casas: 40 });
  });

  it('la anticipación en cero no viaja: es el default del endpoint', () => {
    expect(parametrosDeConsulta(filtro({ diasAnticipacion: 0 })).dias_anticipacion)
      .toBeUndefined();
    expect(parametrosDeConsulta(filtro({ diasAnticipacion: 10 })).dias_anticipacion)
      .toBe(10);
  });

  it('sin tipos marcados no viaja el filtro: son los cuatro', () => {
    expect(parametrosDeConsulta(filtro({ tipos: [] })).tipo).toBeUndefined();
    expect(parametrosDeConsulta(filtro({ tipos: ['material'] })).tipo).toEqual([
      'material',
    ]);
  });

  it('el rango y la granularidad siempre viajan', () => {
    const params = parametrosDeConsulta(filtro({ granularidad: 'mes' }));
    expect(params.granularidad).toBe('mes');
    expect(params.desde).toBe('2026-05-11');
  });
});

describe('el filtro de tipos', () => {
  it('son los cuatro del §8.2', () => {
    expect(TIPOS_INSUMO).toEqual(['material', 'mano_obra', 'equipo', 'herramienta']);
    expect(etiquetaTipo('mano_obra')).toBe('Mano de obra');
  });

  it('un tipo desconocido se muestra tal cual en vez de desaparecer', () => {
    expect(etiquetaTipo('inventado')).toBe('inventado');
  });

  it('alternar no muta la lista recibida', () => {
    const original: readonly string[] = ['material'];
    expect(alternarTipo(original, 'equipo')).toEqual(['material', 'equipo']);
    expect(alternarTipo(original, 'material')).toEqual([]);
    expect(original).toEqual(['material']);
  });
});
