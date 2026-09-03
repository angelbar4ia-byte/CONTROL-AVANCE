/**
 * Las vistas del día del residente (§11.2, §7.4).
 *
 * Estas reglas deciden **qué ve** el residente cuando abre su obra, y son
 * presentación pura: el backend no tiene el concepto de "activas" ni de
 * "listas p/ cierre". Por eso viven aquí y se prueban aquí.
 *
 * Lo que fijan:
 *
 *  1. **Las vistas son preguntas, no estatus.** "Activas" es *qué traigo hoy*,
 *     y `programada` no lo es: todavía no arranca. Meterla haría que activas
 *     fuera casi toda la obra el primer día, que es lo mismo que no filtrar.
 *  2. **Una actividad puede estar en dos vistas.** `casi` está en activas y —al
 *     100%— en listas. Forzar exclusividad obligaría a elegir cuál esconder.
 *  3. **El frente sale de las actividades, no del catálogo.** Un nivel que esta
 *     obra no toca no es un filtro útil: es una opción que siempre sale vacía.
 *  4. **El sub-frente agrupa** porque es donde pasan las cosas juntas: si se
 *     atrasó la albañilería de planta baja, se atrasaron sus tres actividades.
 */

import { describe, expect, it } from 'vitest';

import type { ActividadRespuesta } from '@/api/generado/modelo';
import {
  contarPorVista,
  enVista,
  frentesDe,
  porSubFrente,
} from '@/avance/reglas';

const PB = '11111111-1111-1111-1111-111111111111';
const AZ = '22222222-2222-2222-2222-222222222222';

function actividad(sobre: Partial<ActividadRespuesta> = {}): ActividadRespuesta {
  return {
    id: crypto.randomUUID(),
    obra_id: '99999999-9999-9999-9999-999999999999',
    descripcion: 'Muro de tabique',
    concepto_clave: 'EST-02080',
    cant_base: '30',
    cant_programada: '30',
    cant_ejecutada: '0',
    avance_pct: '0',
    estatus: 'programada',
    bloqueada: false,
    extra: false,
    es_critica: false,
    duracion_dias: '1',
    modo_pago: 'destajo',
    precio_unitario: '0',
    precio_destajo: '0',
    nivel_id: PB,
    nivel_descripcion: 'PLANTA BAJA',
    etapa_id: 'aaaa1111-1111-1111-1111-111111111111',
    etapa_descripcion: 'ESTRUCTURA PB',
    ...sobre,
  } as ActividadRespuesta;
}

describe('activas: qué traigo hoy', () => {
  it('lo que se está trabajando entra', () => {
    expect(enVista(actividad({ estatus: 'en_proceso' }), 'activas')).toBe(true);
    expect(enVista(actividad({ estatus: 'casi' }), 'activas')).toBe(true);
  });

  it('lo que todavía no arranca, no', () => {
    // Si `programada` entrara, "activas" sería casi toda la obra el primer día
    // y el filtro no diría nada.
    expect(enVista(actividad({ estatus: 'programada' }), 'activas')).toBe(false);
  });

  it('lo concluido tampoco', () => {
    expect(enVista(actividad({ estatus: 'concluida' }), 'activas')).toBe(false);
  });
});

describe('listas p/ cierre: qué puedo cobrar', () => {
  it('al 100% sin cerrar entra', () => {
    expect(enVista(actividad({ avance_pct: '100', estatus: 'casi' }), 'listas')).toBe(
      true,
    );
  });

  it('lo ya solicitado entra aunque no esté al 100%', () => {
    // El residente ya pidió el cierre; sacarlo de la lista lo dejaría sin
    // manera de ver en qué quedó su solicitud.
    expect(
      enVista(actividad({ estatus: 'pendiente_cierre', avance_pct: '96' }), 'listas'),
    ).toBe(true);
  });

  it('lo ya concluido no: eso ya se cobró', () => {
    expect(
      enVista(actividad({ avance_pct: '100', estatus: 'concluida' }), 'listas'),
    ).toBe(false);
  });
});

describe('retrasadas', () => {
  it('lo que el backend marcó', () => {
    expect(enVista(actividad({ estatus: 'retrasada' }), 'retrasadas')).toBe(true);
  });

  it('y lo que el CPM dice que va tarde aunque el estatus no lo diga', () => {
    // Una actividad puede ir tarde sin que nadie haya corrido la ruta crítica
    // todavía; exigir las dos cosas escondería justo las recién atrasadas.
    expect(
      enVista(actividad({ estatus: 'en_proceso', desfase: '4' }), 'retrasadas'),
    ).toBe(true);
  });

  it('desfase cero o negativo no es retraso', () => {
    expect(
      enVista(actividad({ estatus: 'en_proceso', desfase: '0' }), 'retrasadas'),
    ).toBe(false);
  });
});

describe('una actividad puede estar en dos vistas', () => {
  it('«casi» al 100% está en activas y en listas', () => {
    // Son dos preguntas distintas sobre la misma actividad: "¿la estoy
    // trabajando?" y "¿la puedo cobrar?". Forzar exclusividad obligaría a
    // elegir cuál esconder.
    const casi = actividad({ estatus: 'casi', avance_pct: '100' });
    expect(enVista(casi, 'activas')).toBe(true);
    expect(enVista(casi, 'listas')).toBe(true);
  });
});

describe('fuera de catálogo', () => {
  it('solo las marcadas como extra', () => {
    expect(enVista(actividad({ extra: true }), 'fuera_catalogo')).toBe(true);
    expect(enVista(actividad({ extra: false }), 'fuera_catalogo')).toBe(false);
  });
});

describe('los contadores de las pestañas', () => {
  it('cuentan cada vista por separado, sin repartirse las actividades', () => {
    const cuenta = contarPorVista([
      actividad({ estatus: 'en_proceso' }),
      actividad({ estatus: 'casi', avance_pct: '100' }),
      actividad({ estatus: 'concluida', avance_pct: '100' }),
    ]);
    expect(cuenta.todas).toBe(3);
    expect(cuenta.activas).toBe(2);
    expect(cuenta.listas).toBe(1);
    expect(cuenta.concluidas).toBe(1);
  });
});

describe('los frentes del filtro', () => {
  it('salen de las actividades y no del catálogo', () => {
    // Un nivel que esta obra no toca no es un filtro útil: es una opción que
    // siempre sale vacía.
    const frentes = frentesDe([
      actividad({ nivel_id: PB, nivel_descripcion: 'PLANTA BAJA' }),
      actividad({ nivel_id: PB, nivel_descripcion: 'PLANTA BAJA' }),
      actividad({ nivel_id: AZ, nivel_descripcion: 'AZOTEA' }),
    ]);
    expect(frentes.map((f) => f.etiqueta)).toEqual(['PLANTA BAJA', 'AZOTEA']);
    expect(frentes[0]!.actividades).toBe(2);
  });

  it('una actividad sin nivel no se pierde', () => {
    const frentes = frentesDe([
      actividad({ nivel_id: null, nivel_descripcion: null }),
    ]);
    expect(frentes[0]!.etiqueta).toBe('Sin frente');
  });
});

describe('el agrupado por sub-frente', () => {
  it('junta las actividades de la misma etapa', () => {
    const grupos = porSubFrente([
      actividad({ etapa_id: 'e1', etapa_descripcion: 'ALBAÑILERIAS PB' }),
      actividad({ etapa_id: 'e2', etapa_descripcion: 'ESTRUCTURA PB' }),
      actividad({ etapa_id: 'e1', etapa_descripcion: 'ALBAÑILERIAS PB' }),
    ]);
    expect(grupos).toHaveLength(2);
    expect(grupos[0]!.etiqueta).toBe('ALBAÑILERIAS PB');
    expect(grupos[0]!.actividades).toHaveLength(2);
  });

  it('respeta el orden en que llegan, que es el de la obra', () => {
    // El backend ordena por nivel y etapa; reordenar aquí rompería el recorrido
    // físico de la obra, que es como el residente la camina.
    const grupos = porSubFrente([
      actividad({ etapa_id: 'z', etapa_descripcion: 'ZZZ' }),
      actividad({ etapa_id: 'a', etapa_descripcion: 'AAA' }),
    ]);
    expect(grupos.map((g) => g.etiqueta)).toEqual(['ZZZ', 'AAA']);
  });
});
