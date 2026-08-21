/**
 * Comparación de versiones y política de actualización (§12.12).
 *
 * Estas pruebas cuidan la decisión que puede **dejar la app inservible**: si
 * `estaObsoleta` se equivoca hacia arriba, un residente con la versión al día
 * se queda mirando una pantalla de actualización en medio de la obra.
 *
 * El espejo de `comparar` en el backend es `version_es_menor`
 * (`backend/src/obractrl/adapters/api/middleware.py`) y sus casos están
 * duplicados a propósito en `tests/test_version_de_cliente.py`: si las dos
 * implementaciones divergen, el servidor responde 426 a una app que se cree
 * al día y que por lo tanto no muestra la pantalla que explicaría por qué.
 */

import { comparar, estaObsoleta } from '@/lib/version';
import { evaluar, type VersionSoportada } from '@/lib/actualizacion';

describe('comparar', () => {
  it.each([
    ['1.0.0', '1.0.0', 0],
    ['1.0.1', '1.0.0', 1],
    ['1.0.0', '1.0.1', -1],
    ['1.10.0', '1.9.0', 1],
    ['2.0.0', '1.99.99', 1],
  ])('%s vs %s = %i', (a, b, esperado) => {
    expect(comparar(a, b)).toBe(esperado);
  });

  it('trata los componentes faltantes como cero', () => {
    // `1.2` y `1.2.0` son la misma versión: Play muestra la primera forma y
    // la configuración del servidor suele escribir la segunda.
    expect(comparar('1.2', '1.2.0')).toBe(0);
    expect(comparar('1.2', '1.2.1')).toBe(-1);
  });

  it('ignora el sufijo de pre-release', () => {
    // Una release candidate NO debe leerse como menor que su release: si lo
    // hiciera, el build que el equipo está probando se bloquearía solo.
    expect(comparar('1.3.0-rc.1', '1.3.0')).toBe(0);
    expect(comparar('1.3.0-rc.1', '1.2.9')).toBe(1);
  });

  it('trata un componente no numérico como cero, no como NaN', () => {
    // Con `NaN` toda comparación es falsa y el resultado sería "iguales" en
    // silencio — el peor default para algo que decide si se bloquea la app.
    expect(comparar('1.x.0', '1.0.0')).toBe(0);
    expect(comparar('1.x.0', '1.1.0')).toBe(-1);
  });
});

describe('estaObsoleta', () => {
  it('es falsa cuando la versión coincide con la mínima', () => {
    expect(estaObsoleta('1.4.0', '1.4.0')).toBe(false);
  });

  it('es verdadera solo por debajo de la mínima', () => {
    expect(estaObsoleta('1.4.0', '1.3.9')).toBe(true);
    expect(estaObsoleta('1.4.0', '1.4.1')).toBe(false);
  });
});

describe('evaluar', () => {
  const soportada: VersionSoportada = {
    minima: '1.2.0',
    recomendada: '1.5.0',
    url_tienda: 'https://play.google.com/store/apps/details?id=com.obractrl.app',
    mensaje: 'Actualiza ObraCtrl.',
  };

  it('bloquea por debajo de la mínima', () => {
    expect(evaluar(soportada, '1.1.9')).toBe('obligatoria');
  });

  it('sugiere entre la mínima y la recomendada', () => {
    expect(evaluar(soportada, '1.2.0')).toBe('sugerida');
    expect(evaluar(soportada, '1.4.9')).toBe('sugerida');
  });

  it('calla cuando está al día o por delante', () => {
    expect(evaluar(soportada, '1.5.0')).toBe('ok');
    // Por delante pasa en un build interno de `preview` (§12.13): no debe
    // pedirle al probador que "actualice" a una versión más vieja.
    expect(evaluar(soportada, '1.6.0')).toBe('ok');
  });
});
