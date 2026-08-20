/**
 * El acta de entrega en la pantalla — `src/cierresObra/reglas.ts` (§11.3 D).
 *
 * Lo que se fija aquí es que la pantalla distinga las tres situaciones que el
 * backend agrupa bajo «en proceso»: falta resolver trabajo, falta que alguien
 * firme, o ya está todo y solo falta el último clic. Son tres acciones
 * distintas y confundirlas deja al usuario sin saber qué hacer.
 */

import { describe, expect, it } from 'vitest';

import {
  aportacionDe,
  estadoDeActa,
  etiquetaEstado,
  etiquetaRol,
  leTocaFirmar,
  puedeAbrirCierre,
  separarPendientes,
  tonoEstado,
} from '@/cierresObra/reglas';
import type { CierreDeObraRespuesta } from '@/api/generado/modelo';

function acta(parcial: Partial<CierreDeObraRespuesta> = {}): CierreDeObraRespuesta {
  return {
    id: 'c-1',
    obra_id: 'o-1',
    estatus: 'en_proceso',
    pendientes: [],
    participaron: [],
    faltan: ['residente', 'supervisor', 'control_obra', 'super_intendente'],
    puede_cerrarse: false,
    cerro_la_obra: false,
    ...parcial,
  } as CierreDeObraRespuesta;
}

const BLOQUEANTE = {
  clave: 'estimaciones_sin_validar',
  detalle: '1 estimación sin validar.',
  bloquea: true,
  cuantos: 1,
};

const AVISO = {
  clave: 'expediente_vacio',
  detalle: 'El expediente no tiene documentos.',
  bloquea: false,
  cuantos: 0,
};

describe('quién abre el acta (§11.2)', () => {
  it('solo el super intendente', () => {
    expect(puedeAbrirCierre('super_intendente')).toBe(true);
    expect(puedeAbrirCierre('control_obra')).toBe(false);
    expect(puedeAbrirCierre('supervisor')).toBe(false);
    expect(puedeAbrirCierre('residente')).toBe(false);
  });
});

describe('qué aporta cada rol (§11.3 D.2)', () => {
  it('los cuatro tienen su parte nombrada', () => {
    // «Participar» no dice nada: cada rol responde por algo distinto.
    expect(aportacionDe('residente')).toBe('Entrega');
    expect(aportacionDe('supervisor')).toBe('Visto bueno');
    expect(aportacionDe('control_obra')).toBe('Calidad y expediente');
    expect(aportacionDe('super_intendente')).toBe('Firma');
  });

  it('un rol desconocido no rompe la tabla', () => {
    expect(aportacionDe('inventado')).toBe('Participación');
    expect(etiquetaRol('inventado')).toBe('inventado');
  });
});

describe('en qué punto está el acta', () => {
  it('con pendientes bloqueantes, aunque falten firmas, manda el pendiente', () => {
    // Es la información accionable: no sirve ir a pedir firmas si al final va a
    // rechazarse.
    expect(estadoDeActa(acta({ pendientes: [BLOQUEANTE] }))).toBe('con-pendientes');
  });

  it('sin bloqueantes pero con firmas por juntar', () => {
    expect(estadoDeActa(acta({ pendientes: [AVISO] }))).toBe('esperando-firmas');
  });

  it('todo listo y solo falta el último clic', () => {
    expect(estadoDeActa(acta({ faltan: [] }))).toBe('lista-para-firmar');
  });

  it('cerrada', () => {
    expect(estadoDeActa(acta({ estatus: 'cerrada', faltan: [] }))).toBe('cerrada');
  });

  it('los cuatro estados se ven distinto y tienen etiqueta', () => {
    const estados = ['cerrada', 'lista-para-firmar', 'esperando-firmas', 'con-pendientes'] as const;
    const tonos = new Set(estados.map(tonoEstado));
    expect(tonos.size).toBe(4);
    for (const estado of estados) {
      expect(etiquetaEstado(estado)).not.toBe('');
    }
  });
});

describe('a quién le toca firmar', () => {
  it('a quien está en la lista de los que faltan', () => {
    expect(leTocaFirmar(acta(), 'residente')).toBe(true);
  });

  it('no a quien ya firmó — la participación es del rol, no de la persona', () => {
    // `uq_cierre_obra_participacion` es por (cierre, rol): si otro residente ya
    // firmó, este no vuelve a hacerlo.
    const firmado = acta({ participaron: ['residente'], faltan: ['supervisor'] });
    expect(leTocaFirmar(firmado, 'residente')).toBe(false);
    expect(leTocaFirmar(firmado, 'supervisor')).toBe(true);
  });

  it('a nadie si el acta ya está cerrada', () => {
    const cerrada = acta({ estatus: 'cerrada', faltan: ['residente'] });
    expect(leTocaFirmar(cerrada, 'residente')).toBe(false);
  });
});

describe('los pendientes van en dos bloques', () => {
  it('separa lo que impide entregar de lo que solo hay que ver', () => {
    // Mezclarlos haría que un expediente vacío se viera igual de grave que una
    // estimación sin validar, y entonces nadie miraría ninguno.
    const { bloqueantes, avisos } = separarPendientes(
      acta({ pendientes: [BLOQUEANTE, AVISO] }),
    );
    expect(bloqueantes.map((p) => p.clave)).toEqual(['estimaciones_sin_validar']);
    expect(avisos.map((p) => p.clave)).toEqual(['expediente_vacio']);
  });

  it('sin pendientes, los dos bloques vacíos', () => {
    const { bloqueantes, avisos } = separarPendientes(acta());
    expect(bloqueantes).toHaveLength(0);
    expect(avisos).toHaveLength(0);
  });
});
