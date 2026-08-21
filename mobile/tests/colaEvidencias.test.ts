/**
 * Cola de evidencias hacia R2 (§12.5).
 *
 * Lo que se prueba aquí no es que la foto suba —eso lo prueba el dispositivo—
 * sino **cómo se clasifica cada fallo**, que es lo que decide si una
 * evidencia se recupera o se pierde:
 *
 * - sin señal no gasta intentos, o el residente perdería fotos por caminar;
 * - un rechazo del servidor es terminal, o la cola se atora reintentando algo
 *   que nunca va a pasar y tapa las fotos buenas;
 * - una clave ya subida no se vuelve a subir, o cada reintento duplicaría un
 *   objeto de 3 MB en R2.
 *
 * La base es un doble: el SQL real se ejerce en el dispositivo, y aquí
 * interesa **qué** escritura se emite, no que SQLite la acepte.
 */

import type { AbstractPowerSyncDatabase } from '@powersync/react-native';

import { ErrorDeApi, SinConexion } from '@/lib/api';
import { procesarCola, type FotoEnCola } from '@/evidencias/cola';

jest.mock('@/lib/api', () => {
  const real = jest.requireActual('@/lib/api');
  return { ...real, pedir: jest.fn() };
});

const { pedir } = jest.requireMock('@/lib/api') as { pedir: jest.Mock };

interface Escritura {
  sql: string;
  args: unknown[];
}

function crearDb(filas: FotoEnCola[]): {
  db: AbstractPowerSyncDatabase;
  escrituras: Escritura[];
} {
  const escrituras: Escritura[] = [];
  const anotar = async (sql: string, args: unknown[] = []) => {
    escrituras.push({ sql, args });
  };

  const db = {
    getAll: jest.fn(async () => filas),
    get: jest.fn(async () => ({ actual: '[]' })),
    execute: jest.fn(anotar),
    writeTransaction: jest.fn(async (fn: (tx: unknown) => Promise<void>) =>
      fn({ get: async () => ({ actual: '[]' }), execute: anotar }),
    ),
  } as unknown as AbstractPowerSyncDatabase;

  return { db, escrituras };
}

function foto(cambios: Partial<FotoEnCola> = {}): FotoEnCola {
  return {
    id: 'foto-1',
    entidad: 'revision_fisica',
    entidad_id: 'rev-1',
    obra_id: 'obra-1',
    uri_local: 'file:///documentos/evidencias/a.jpg',
    nombre: 'a.jpg',
    content_type: 'image/jpeg',
    clave: null,
    estado: 'pendiente',
    intentos: 0,
    error: null,
    creada_en: '2026-08-20T10:00:00.000Z',
    subida_en: null,
    ...cambios,
  };
}

const FIRMA = {
  url: 'https://r2.example/firmado',
  clave: 'org/obra/a.jpg',
  metodo: 'PUT',
  content_type: 'image/jpeg',
};

beforeEach(() => {
  pedir.mockReset();
});

describe('procesarCola', () => {
  it('sube, cose la clave en la entidad dueña y marca la fila', async () => {
    pedir.mockResolvedValue(FIRMA);
    const { db, escrituras } = crearDb([foto()]);

    expect(await procesarCola(db)).toBe(1);

    const sql = escrituras.map((e) => e.sql.replace(/\s+/g, ' ').trim());
    expect(sql.some((s) => s.includes('UPDATE revision_fisica SET fotos'))).toBe(true);
    expect(sql.some((s) => s.includes("estado = 'subida'"))).toBe(true);
  });

  it('sin señal no gasta un intento', async () => {
    pedir.mockRejectedValue(new SinConexion());
    const { db, escrituras } = crearDb([foto()]);

    expect(await procesarCola(db)).toBe(0);
    // Ni una escritura: caminar sin cobertura no puede consumir los cinco
    // intentos de una foto perfectamente buena.
    expect(escrituras).toHaveLength(0);
  });

  it('un rechazo del servidor deja la foto fallida de una vez', async () => {
    pedir.mockRejectedValue(new ErrorDeApi(403, 'Sin permiso', null));
    const { db, escrituras } = crearDb([foto()]);

    await procesarCola(db);

    const fallo = escrituras.find((e) => e.sql.includes('intentos = ?'));
    expect(fallo?.args[1]).toBe('fallida');
  });

  it('un 429 sigue siendo reintentable', async () => {
    pedir.mockRejectedValue(new ErrorDeApi(429, 'Demasiadas peticiones', null));
    const { db, escrituras } = crearDb([foto()]);

    await procesarCola(db);

    const fallo = escrituras.find((e) => e.sql.includes('intentos = ?'));
    expect(fallo?.args[0]).toBe(1);
    expect(fallo?.args[1]).toBe('pendiente');
  });

  it('agota los intentos y entonces sí la marca fallida', async () => {
    pedir.mockRejectedValue(new ErrorDeApi(429, 'Demasiadas peticiones', null));
    const { db, escrituras } = crearDb([foto({ intentos: 4 })]);

    await procesarCola(db);

    const fallo = escrituras.find((e) => e.sql.includes('intentos = ?'));
    expect(fallo?.args[1]).toBe('fallida');
  });

  it('no vuelve a subir el binario si la clave ya está', async () => {
    // Este es el caso de la app que murió entre subir y coser: el objeto ya
    // está en R2 y repetirlo dejaría dos copias del mismo 3 MB.
    const { db } = crearDb([foto({ clave: 'org/obra/a.jpg' })]);

    expect(await procesarCola(db)).toBe(1);
    expect(pedir).not.toHaveBeenCalled();
  });

  it('una foto sin dueño local sube pero no cose', async () => {
    // Es la de una incidencia que se dio de alta sin señal: el id lo asigna
    // el servidor, y la clave la recoge la bandeja de salida al enviar.
    pedir.mockResolvedValue(FIRMA);
    const { db, escrituras } = crearDb([foto({ entidad: 'ninguna', entidad_id: '' })]);

    expect(await procesarCola(db)).toBe(1);
    expect(escrituras.some((e) => e.sql.includes('UPDATE ninguna'))).toBe(false);
  });
});
