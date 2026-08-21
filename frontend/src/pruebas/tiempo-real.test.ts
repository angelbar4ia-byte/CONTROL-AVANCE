/**
 * Avisos en vivo: interpretar el flujo SSE (§11.2).
 *
 * Lo que se prueba es el **parser**, que es la parte que puede fallar en
 * silencio: un bloque mal leído no truena, simplemente no recarga nada, y la
 * Torre se queda vieja sin que nadie lo note.
 *
 * Los tres casos que importan y no son obvios:
 *
 * - un `read()` del stream **no** entrega mensajes completos,
 * - el latido y el `retry:` no son avisos,
 * - un bloque corrupto no puede tumbar el canal.
 */

import { describe, expect, it } from 'vitest';

import { HECHOS_CONOCIDOS, interpretar } from '@/lib/tiempoReal';

describe('interpretar', () => {
  it('lee un aviso normal', () => {
    const bloque = 'event: actividad_cerrada\ndata: {"tipo":"actividad_cerrada","datos":{"obra_id":"o1"}}';

    expect(interpretar(bloque)).toEqual({
      tipo: 'actividad_cerrada',
      datos: { obra_id: 'o1' },
    });
  });

  it('ignora el latido', () => {
    // Es un comentario SSE: existe por los proxies que cortan el silencio,
    // no por el cliente.
    expect(interpretar(': latido')).toBeNull();
  });

  it('ignora el `retry` inicial', () => {
    expect(interpretar('retry: 5000')).toBeNull();
  });

  it('ignora el saludo del servidor', () => {
    // `conectado` confirma que el canal abrió; recargar por él haría que cada
    // reconexión disparara una tanda de peticiones.
    expect(interpretar('data: {"tipo":"conectado","datos":{}}')).toBeNull();
  });

  it('une varias líneas `data:` del mismo bloque', () => {
    // El protocolo permite partir el cuerpo en varias líneas; el servidor no
    // lo hace hoy, pero un proxy sí puede.
    const bloque = 'data: {"tipo":"acti\ndata: vidad_cerrada","datos":{}}';

    expect(interpretar(bloque)?.tipo).toBe('actividad_cerrada');
  });

  it('un bloque corrupto no levanta', () => {
    // Una excepción aquí mataría el bucle de lectura y con él el canal
    // entero, por un solo mensaje mal formado.
    expect(interpretar('data: {roto')).toBeNull();
    expect(interpretar('data: ')).toBeNull();
    expect(interpretar('')).toBeNull();
  });

  it('tolera un aviso sin `datos`', () => {
    expect(interpretar('data: {"tipo":"actividad_cerrada"}')).toEqual({
      tipo: 'actividad_cerrada',
      datos: {},
    });
  });
});

describe('hechos conocidos', () => {
  it('cubre los cuatro eventos que publica el dominio', () => {
    // Espejo de `TRADUCCIONES` en `adapters/api/avisos.py`. Si el backend
    // publica uno nuevo y aquí no se mapea, el aviso llega y no recarga nada
    // — que es exactamente el fallo silencioso que esta prueba busca.
    expect(new Set(HECHOS_CONOCIDOS)).toEqual(
      new Set([
        'actividad_cerrada',
        'incidencia_detiene',
        'estimacion_validada',
        'cierre_de_obra_completado',
      ]),
    );
  });
});

describe('trocear el stream', () => {
  /**
   * Reproduce lo que hace el hook: acumular lo que llega y procesar solo los
   * bloques completos. Es la parte del código que un `split` ingenuo rompe en
   * cuanto el mensaje cae partido entre dos `read()`.
   */
  function trocear(pedazos: string[]): string[] {
    const avisos: string[] = [];
    let pendiente = '';

    for (const pedazo of pedazos) {
      pendiente += pedazo;
      const partes = pendiente.split('\n\n');
      pendiente = partes.pop() ?? '';
      for (const bloque of partes) {
        const aviso = interpretar(bloque);
        if (aviso) avisos.push(aviso.tipo);
      }
    }
    return avisos;
  }

  it('junta un mensaje partido entre dos lecturas', () => {
    const avisos = trocear([
      'data: {"tipo":"actividad_ce',
      'rrada","datos":{}}\n\n',
    ]);

    expect(avisos).toEqual(['actividad_cerrada']);
  });

  it('procesa varios mensajes de una sola lectura', () => {
    const avisos = trocear([
      'data: {"tipo":"actividad_cerrada","datos":{}}\n\n' +
        'data: {"tipo":"estimacion_validada","datos":{}}\n\n',
    ]);

    expect(avisos).toEqual(['actividad_cerrada', 'estimacion_validada']);
  });

  it('no procesa un bloque hasta que llega su separador', () => {
    // Sin esto, un mensaje a medias se interpretaría como JSON roto y se
    // perdería aunque el resto llegara medio segundo después.
    expect(trocear(['data: {"tipo":"actividad_cerrada","datos":{}}'])).toEqual([]);
  });
});
