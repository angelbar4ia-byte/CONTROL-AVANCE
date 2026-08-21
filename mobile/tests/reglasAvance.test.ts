/**
 * Reglas de captura de avance en el móvil (§6).
 *
 * `src/lib/reglasAvance.ts` es un **puerto** de
 * `backend/src/obractrl/domain/avance/reglas.py`, y un puerto sin pruebas es
 * una copia que se va separando del original sin que nadie lo note. Los casos
 * de aquí son los mismos que los de `backend/tests/domain/test_avance.py`: si
 * uno cambia, el otro tiene que cambiar en el mismo PR.
 *
 * Que coincidan importa porque el móvil valida **antes** de escribir a SQLite
 * (§12.5). Si el teléfono fuera más permisivo, el residente capturaría un
 * número que el servidor rechaza al sincronizar, horas después y sin nadie
 * frente a la pantalla para corregirlo.
 */

import {
  aplicarCaptura,
  calcularAvance,
  ErrorDeCaptura,
  resolverEstatus,
  TOPE_SOBREPROGRAMA,
  UMBRAL_CASI_PCT,
  validarEjecucion,
  validarProgramacion,
} from '@/lib/reglasAvance';

describe('validarProgramacion', () => {
  it('acepta justo el tope de 120% sobre la base', () => {
    expect(() => validarProgramacion(120, 100)).not.toThrow();
  });

  it('rechaza un milímetro por encima del tope', () => {
    expect(() => validarProgramacion(120.1, 100)).toThrow(ErrorDeCaptura);
  });

  it('señala el campo, no solo el mensaje', () => {
    // La UI usa `campo` para marcar el input; sin eso el residente recibe un
    // error genérico y no sabe cuál de los dos números corregir.
    try {
      validarProgramacion(-1, 100);
      throw new Error('debió rechazar');
    } catch (e) {
      expect((e as ErrorDeCaptura).campo).toBe('cant_programada');
    }
  });

  it('usa el tope canónico del §6', () => {
    expect(TOPE_SOBREPROGRAMA).toBe(1.2);
  });
});

describe('validarEjecucion', () => {
  it('permite ejecutar exactamente lo programado', () => {
    expect(() => validarEjecucion(50, 50)).not.toThrow();
  });

  it('no deja ejecutar más de lo programado', () => {
    expect(() => validarEjecucion(51, 50)).toThrow(ErrorDeCaptura);
  });
});

describe('calcularAvance', () => {
  it('es sobre la base, no sobre lo programado', () => {
    // Con sobreprograma, medir contra lo programado escondería el exceso:
    // 120 sobre 100 de base es 100%, no 83%.
    expect(calcularAvance(50, 100)).toBe(50);
    expect(calcularAvance(120, 100)).toBe(100);
  });

  it('con base cero devuelve 0 en vez de dividir', () => {
    expect(calcularAvance(10, 0)).toBe(0);
  });
});

describe('resolverEstatus', () => {
  it('pasa a `casi` en el umbral, no después', () => {
    expect(resolverEstatus(UMBRAL_CASI_PCT, 'en_proceso')).toBe('casi');
    expect(resolverEstatus(89.99, 'en_proceso')).toBe('en_proceso');
  });

  it('nunca pisa un estatus de flujo', () => {
    // `pendiente_cierre` lo puso el workflow C; que el motor de avance lo
    // devolviera a `casi` desharía una solicitud de cierre en curso.
    expect(resolverEstatus(95, 'pendiente_cierre')).toBe('pendiente_cierre');
    expect(resolverEstatus(95, 'concluida')).toBe('concluida');
    expect(resolverEstatus(10, 'retrasada')).toBe('retrasada');
  });
});

describe('aplicarCaptura', () => {
  it('deriva porcentaje y estatus de una captura válida', () => {
    const resultado = aplicarCaptura({
      cantBase: 100,
      cantProgramada: 100,
      cantEjecutada: 95,
      estatusActual: 'en_proceso',
    });

    expect(resultado.avancePct).toBe(95);
    expect(resultado.estatus).toBe('casi');
  });

  it('valida antes de derivar', () => {
    expect(() =>
      aplicarCaptura({ cantBase: 100, cantProgramada: 100, cantEjecutada: 101 }),
    ).toThrow(ErrorDeCaptura);
  });
});
