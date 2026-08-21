/**
 * Bandeja de salida: operaciones capturadas sin señal (§11.2, §11.3 F).
 *
 * El caso que da sentido a todo el mecanismo es el **409**: el servidor ya
 * procesó esa clave de idempotencia en un intento anterior cuya respuesta no
 * llegó. Leerlo como fallo dejaría al residente creyendo que su incidencia no
 * se levantó —y capturándola otra vez—, cuando en realidad ya existe.
 *
 * El otro es la inyección de claves de fotos: si la operación saliera antes
 * de que suban, la incidencia quedaría sin evidencia y no habría segunda
 * oportunidad de adjuntarla, porque el servidor ya la creó.
 */

import type { AbstractPowerSyncDatabase } from '@powersync/react-native';

import { ErrorDeApi, SinConexion } from '@/lib/api';
import { procesarBandeja, type OperacionEnCola } from '@/salida/bandeja';

jest.mock('@/lib/api', () => {
  const real = jest.requireActual('@/lib/api');
  return { ...real, pedir: jest.fn() };
});

const { pedir } = jest.requireMock('@/lib/api') as { pedir: jest.Mock };

interface Escritura {
  sql: string;
  args: unknown[];
}

function crearDb(
  filas: OperacionEnCola[],
  claves: { clave: string }[] = [],
): { db: AbstractPowerSyncDatabase; escrituras: Escritura[] } {
  const escrituras: Escritura[] = [];

  const db = {
    // `getAll` sirve a dos consultas: la de la bandeja y la de claves de
    // fotos. Se distinguen por la tabla, que es lo que hace el código real.
    getAll: jest.fn(async (sql: string) =>
      sql.includes('evidencia_pendiente') ? claves : filas,
    ),
    execute: jest.fn(async (sql: string, args: unknown[] = []) => {
      escrituras.push({ sql, args });
    }),
  } as unknown as AbstractPowerSyncDatabase;

  return { db, escrituras };
}

function operacion(cambios: Partial<OperacionEnCola> = {}): OperacionEnCola {
  return {
    id: 'op-1',
    ruta: '/api/v1/incidencias',
    metodo: 'POST',
    cuerpo: JSON.stringify({ obra_id: 'obra-1', titulo: 'Fuga en baño' }),
    clave_idem: 'clave-fija-1',
    etiqueta: 'Incidencia: Fuga en baño',
    obra_id: 'obra-1',
    fotos: '[]',
    estado: 'pendiente',
    intentos: 0,
    error: null,
    creada_en: '2026-08-20T10:00:00.000Z',
    enviada_en: null,
    ...cambios,
  };
}

beforeEach(() => {
  pedir.mockReset();
});

describe('procesarBandeja', () => {
  it('envía con la clave de idempotencia que se fijó al capturar', async () => {
    pedir.mockResolvedValue({});
    const { db } = crearDb([operacion()]);

    expect(await procesarBandeja(db)).toBe(1);
    expect(pedir).toHaveBeenCalledWith(
      '/api/v1/incidencias',
      expect.objectContaining({ idempotencia: 'clave-fija-1', metodo: 'POST' }),
    );
  });

  it('lee un 409 como éxito: ya se procesó con esa misma clave', async () => {
    pedir.mockRejectedValue(new ErrorDeApi(409, 'Petición ya procesada', null));
    const { db, escrituras } = crearDb([operacion()]);

    expect(await procesarBandeja(db)).toBe(1);
    expect(escrituras.some((e) => e.sql.includes("estado = 'enviada'"))).toBe(true);
  });

  it('sin señal no gasta un intento', async () => {
    pedir.mockRejectedValue(new SinConexion());
    const { db, escrituras } = crearDb([operacion()]);

    expect(await procesarBandeja(db)).toBe(0);
    expect(escrituras).toHaveLength(0);
  });

  it('un 422 es terminal', async () => {
    pedir.mockRejectedValue(new ErrorDeApi(422, 'Datos inválidos', null));
    const { db, escrituras } = crearDb([operacion()]);

    await procesarBandeja(db);

    const fallo = escrituras.find((e) => e.sql.includes('intentos = ?'));
    expect(fallo?.args[1]).toBe('fallida');
  });

  it('inyecta en el cuerpo las claves de las fotos que ya subieron', async () => {
    pedir.mockResolvedValue({});
    const { db } = crearDb([operacion({ fotos: JSON.stringify(['foto-1', 'foto-2']) })], [
      { clave: 'org/obra/a.jpg' },
    ]);

    await procesarBandeja(db);

    expect(pedir).toHaveBeenCalledWith(
      '/api/v1/incidencias',
      expect.objectContaining({
        cuerpo: expect.objectContaining({ evidencias: ['org/obra/a.jpg'] }),
      }),
    );
  });

  it('no espera a una foto que aún no sube', async () => {
    // La incidencia importa más que su ilustración: retenerla hasta que haya
    // buena señal significaría no reportar la fuga.
    pedir.mockResolvedValue({});
    const { db } = crearDb([operacion({ fotos: JSON.stringify(['foto-1']) })], []);

    expect(await procesarBandeja(db)).toBe(1);
    const [, opciones] = pedir.mock.calls[0] as [string, { cuerpo: Record<string, unknown> }];
    expect(opciones.cuerpo).not.toHaveProperty('evidencias');
  });
});
