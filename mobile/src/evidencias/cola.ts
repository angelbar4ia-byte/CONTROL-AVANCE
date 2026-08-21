/**
 * Cola de evidencias fotográficas hacia R2.
 *
 * Spec §12.5 ("Fotos: se guardan local y se suben directo a R2 en segundo
 * plano, **no viajan por la API**") · §11.2 (`POST /evidencias/presigned`) ·
 * §12.4 (el prefijo del objeto lo arma el servidor).
 *
 * ## Las tres etapas, y por qué son tres
 *
 * 1. **Encolar** — la foto se copia al almacenamiento de la app y se anota en
 *    `evidencia_pendiente`. Pasa sin red y es lo único que ocurre mientras el
 *    usuario está capturando: nada bloquea el formulario.
 * 2. **Firmar y subir** — se pide una URL firmada a la API y se hace `PUT`
 *    contra R2 con el binario. El archivo no pasa por FastAPI (§12.5); lo
 *    único que pasa es la firma, que son unos cientos de bytes.
 * 3. **Coser** — la **clave** del objeto se agrega al arreglo de la entidad
 *    dueña (`registro_avance.evidencias`, `revision_fisica.fotos`,
 *    `incidencia.evidencias`). Recién ahí la foto existe para el resto del
 *    sistema, y como esa escritura sí es de PowerSync, viaja por la cola
 *    normal con RLS de frontera.
 *
 * Separar 2 de 3 importa: si la subida a R2 funciona pero la app muere antes
 * de coser, la foto queda en el bucket **huérfana**. La fila se queda en
 * `pendiente` con su `clave` ya escrita y el siguiente intento solo cose, sin
 * volver a subir los 3 MB.
 *
 * ## Qué se reintenta y qué no
 *
 * Sin señal no cuenta como intento: no hay nada que corregir y contarlo
 * agotaría los reintentos de una foto perfectamente buena mientras el
 * residente camina por la obra. Un rechazo del servidor —permiso, tipo
 * inválido, entidad que no existe— sí es terminal: reintentarlo en cada
 * reconexión no lo va a arreglar y taparía las fotos que sí pueden subir. Eso
 * se ve en la pantalla *Fotos*, no en un log que nadie lee.
 */

import * as FileSystem from 'expo-file-system';
import type { AbstractPowerSyncDatabase } from '@powersync/react-native';

import { ErrorDeApi, pedir, SinConexion } from '@/lib/api';
import { generarId } from '@/lib/id';

/**
 * Entidades del §7.8/§7.9 que llevan evidencia fotográfica.
 *
 * `ninguna` es el caso de la foto que todavía **no tiene dueño local**: la de
 * una incidencia que se dio de alta sin señal y viaja por la bandeja de
 * salida (`src/salida/bandeja.ts`), donde el id lo asigna el servidor. Esa
 * foto se sube igual —lo que necesita es la firma, no el dueño— y su clave la
 * recoge la operación al enviarse, en el cuerpo del `POST`.
 */
export type EntidadConEvidencia =
  | 'registro_avance'
  | 'revision_fisica'
  | 'incidencia'
  | 'ninguna';

/** Columna `jsonb` donde vive el arreglo de claves de cada entidad. */
const COLUMNA_DE_EVIDENCIAS: Readonly<Record<string, string>> = {
  registro_avance: 'evidencias',
  revision_fisica: 'fotos',
  incidencia: 'evidencias',
};

/**
 * Tope de reintentos por foto. Cinco y no infinito: pasado ese punto el
 * problema no es transitorio, y una fila que reintenta para siempre gasta
 * batería y datos en cada reconexión.
 */
export const MAX_INTENTOS = 5;

/** Fotos por pasada. Se procesa por tandas para no monopolizar la red. */
const TANDA = 3;

export interface FotoEnCola {
  readonly id: string;
  readonly entidad: string;
  readonly entidad_id: string;
  readonly obra_id: string | null;
  readonly uri_local: string;
  readonly nombre: string;
  readonly content_type: string;
  readonly clave: string | null;
  readonly estado: string;
  readonly intentos: number;
  readonly error: string | null;
  readonly creada_en: string;
  readonly subida_en: string | null;
}

interface Firma {
  readonly url: string;
  readonly clave: string;
  readonly metodo: string;
  readonly content_type: string;
}

export interface Encolable {
  readonly entidad: EntidadConEvidencia;
  readonly entidadId: string;
  readonly obraId: string | null;
  /** `file://` en el almacenamiento de la app (lo deja `captura.ts`). */
  readonly uri: string;
  readonly nombre: string;
  readonly contentType: string;
}

/**
 * Anota una foto ya copiada al almacenamiento de la app. Devuelve el id de la
 * fila para que la UI la pueda mostrar al instante.
 */
export async function encolar(db: AbstractPowerSyncDatabase, foto: Encolable): Promise<string> {
  const id = generarId();
  await db.execute(
    `INSERT INTO evidencia_pendiente
       (id, entidad, entidad_id, obra_id, uri_local, nombre, content_type,
        clave, estado, intentos, error, creada_en, subida_en)
     VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'pendiente', 0, NULL, ?, NULL)`,
    [
      id,
      foto.entidad,
      foto.entidadId,
      foto.obraId,
      foto.uri,
      foto.nombre,
      foto.contentType,
      new Date().toISOString(),
    ],
  );
  return id;
}

/** Claves ya en R2 de un conjunto de filas de la cola. Las que aún no subieron no aparecen. */
export async function clavesDe(
  db: AbstractPowerSyncDatabase,
  ids: readonly string[],
): Promise<string[]> {
  if (ids.length === 0) return [];
  const huecos = ids.map(() => '?').join(', ');
  const filas = await db.getAll<{ clave: string | null }>(
    `SELECT clave FROM evidencia_pendiente WHERE id IN (${huecos}) AND clave IS NOT NULL`,
    [...ids],
  );
  return filas.map((f) => f.clave).filter((c): c is string => c !== null);
}

/** Fotos que todavía deben subir, más viejas primero. */
export async function pendientes(db: AbstractPowerSyncDatabase): Promise<FotoEnCola[]> {
  return db.getAll<FotoEnCola>(
    `SELECT * FROM evidencia_pendiente
      WHERE estado = 'pendiente' AND intentos < ?
      ORDER BY creada_en ASC
      LIMIT ?`,
    [MAX_INTENTOS, TANDA],
  );
}

export interface ResumenCola {
  readonly pendientes: number;
  readonly fallidas: number;
  readonly subidas: number;
}

export async function resumen(db: AbstractPowerSyncDatabase): Promise<ResumenCola> {
  const fila = await db.get<ResumenCola>(
    `SELECT
       SUM(estado = 'pendiente') AS pendientes,
       SUM(estado = 'fallida')   AS fallidas,
       SUM(estado = 'subida')    AS subidas
     FROM evidencia_pendiente`,
  );
  return {
    pendientes: fila?.pendientes ?? 0,
    fallidas: fila?.fallidas ?? 0,
    subidas: fila?.subidas ?? 0,
  };
}

/**
 * Procesa una tanda. Devuelve cuántas fotos quedaron subidas y cosidas.
 *
 * **No levanta.** La llaman un efecto de arranque y el listener de reconexión
 * (`salida/ProveedorSalida.tsx`); un fallo ahí no tiene a quién reportarse, y
 * tumbar la pantalla de captura por una foto sería el peor intercambio
 * posible.
 */
export async function procesarCola(db: AbstractPowerSyncDatabase): Promise<number> {
  let subidas = 0;

  for (const foto of await pendientes(db)) {
    try {
      const clave = foto.clave ?? (await subirAR2(db, foto));
      await coser(db, foto, clave);
      await marcarSubida(db, foto.id, clave);
      subidas += 1;
    } catch (e) {
      await marcarFallo(db, foto, e);
    }
  }

  return subidas;
}

/**
 * Pide la firma y hace el `PUT` a R2. Devuelve la clave del objeto, que queda
 * persistida **antes** de coser para no volver a subir el binario si la app
 * muere en medio (ver el encabezado).
 */
async function subirAR2(db: AbstractPowerSyncDatabase, foto: FotoEnCola): Promise<string> {
  const info = await FileSystem.getInfoAsync(foto.uri_local);
  if (!info.exists) {
    // El archivo ya no está: lo borró el sistema o el usuario limpió datos.
    // Es terminal — no hay nada que subir y reintentar no lo resucita.
    throw new EvidenciaRechazada('El archivo ya no está en el dispositivo.');
  }

  const firma = await pedir<Firma>('/api/v1/evidencias/presigned', {
    metodo: 'POST',
    cuerpo: {
      nombre_archivo: foto.nombre,
      content_type: foto.content_type,
      obra_id: foto.obra_id,
    },
  });

  const respuesta = await FileSystem.uploadAsync(firma.url, foto.uri_local, {
    httpMethod: 'PUT',
    uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
    // El `Content-Type` va firmado: mandar otro invalida la firma y R2
    // responde 403. Se usa el que devolvió el servidor, no el local.
    headers: { 'Content-Type': firma.content_type },
  });

  if (respuesta.status < 200 || respuesta.status >= 300) {
    // Un 403 aquí suele ser firma vencida, y eso sí se arregla reintentando
    // (la pasada siguiente pide una nueva). Por eso no es `EvidenciaRechazada`.
    throw new Error(`R2 rechazó la subida con ${respuesta.status}.`);
  }

  await db.execute('UPDATE evidencia_pendiente SET clave = ? WHERE id = ?', [firma.clave, foto.id]);
  return firma.clave;
}

/**
 * Agrega la clave al arreglo JSON de la entidad dueña.
 *
 * Se lee, se modifica en JS y se escribe: SQLite guarda esa columna como
 * texto —el esquema local solo tiene text/real/integer— y `conector.ts` la
 * convierte a `jsonb` al subir. Idempotente: si la clave ya está, porque la
 * app murió justo después de coser, no se duplica.
 */
async function coser(
  db: AbstractPowerSyncDatabase,
  foto: FotoEnCola,
  clave: string,
): Promise<void> {
  // Sin dueño local no hay dónde coser: la clave la recoge la bandeja de
  // salida al enviar la operación que crea la entidad (ver el tipo arriba).
  if (foto.entidad === 'ninguna') return;

  const columna = COLUMNA_DE_EVIDENCIAS[foto.entidad];
  if (!columna) throw new EvidenciaRechazada(`Entidad desconocida: ${foto.entidad}.`);

  await db.writeTransaction(async (tx) => {
    const fila = await tx.get<{ actual: string | null }>(
      `SELECT ${columna} AS actual FROM ${foto.entidad} WHERE id = ?`,
      [foto.entidad_id],
    );

    if (!fila) {
      // Sin dueño en la réplica local no hay dónde anotar la clave: o la
      // entidad nunca se guardó, o salió del alcance del usuario.
      throw new EvidenciaRechazada(
        `La ${foto.entidad} ${foto.entidad_id} ya no está en el dispositivo.`,
      );
    }

    const claves = parsearClaves(fila.actual);
    if (claves.includes(clave)) return;

    await tx.execute(`UPDATE ${foto.entidad} SET ${columna} = ? WHERE id = ?`, [
      JSON.stringify([...claves, clave]),
      foto.entidad_id,
    ]);
  });
}

function parsearClaves(valor: string | null): string[] {
  if (!valor) return [];
  try {
    const datos: unknown = JSON.parse(valor);
    return Array.isArray(datos) ? datos.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

async function marcarSubida(
  db: AbstractPowerSyncDatabase,
  id: string,
  clave: string,
): Promise<void> {
  await db.execute(
    `UPDATE evidencia_pendiente
        SET estado = 'subida', clave = ?, error = NULL, subida_en = ?
      WHERE id = ?`,
    [clave, new Date().toISOString(), id],
  );
}

/** Rechazo que no se arregla reintentando. */
export class EvidenciaRechazada extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = 'EvidenciaRechazada';
  }
}

/**
 * Decide si el fallo consume un intento y si la foto queda muerta.
 * `SinConexion` no cuenta: es el estado normal en campo (§12.5).
 */
async function marcarFallo(
  db: AbstractPowerSyncDatabase,
  foto: FotoEnCola,
  causa: unknown,
): Promise<void> {
  if (causa instanceof SinConexion) return;

  const terminal =
    causa instanceof EvidenciaRechazada ||
    (causa instanceof ErrorDeApi && esRechazoDefinitivo(causa.estado));

  const intentos = foto.intentos + 1;
  const estado = terminal || intentos >= MAX_INTENTOS ? 'fallida' : 'pendiente';

  await db.execute(
    'UPDATE evidencia_pendiente SET intentos = ?, estado = ?, error = ? WHERE id = ?',
    [intentos, estado, causa instanceof Error ? causa.message : String(causa), foto.id],
  );
}

/**
 * 4xx = el servidor entendió y dijo que no; reintentar da lo mismo. Se
 * exceptúan 408 (timeout) y 429 (demasiadas peticiones), que **piden**
 * reintentar, y 401, que se arregla solo cuando `supabase-js` refresca el
 * token.
 */
function esRechazoDefinitivo(estado: number): boolean {
  if (estado === 401 || estado === 408 || estado === 429) return false;
  return estado >= 400 && estado < 500;
}

/**
 * Vuelve a poner en la cola una foto que quedó `fallida`. Lo dispara el
 * usuario desde la pantalla *Fotos*: el diagnóstico automático se equivoca
 * —una firma vencida por reloj desfasado, un permiso que ya se corrigió— y
 * quien está en la obra sabe si vale la pena insistir.
 */
export async function reintentar(db: AbstractPowerSyncDatabase, id: string): Promise<void> {
  await db.execute(
    `UPDATE evidencia_pendiente
        SET estado = 'pendiente', intentos = 0, error = NULL
      WHERE id = ? AND estado = 'fallida'`,
    [id],
  );
}

/**
 * Descarta una foto que nunca va a subir, y borra su archivo.
 *
 * Existe porque la alternativa es peor: una fila `fallida` eterna en la
 * pantalla de Fotos entrena al usuario a ignorar el contador, y entonces
 * tampoco ve la foto que sí importaba.
 */
export async function descartar(db: AbstractPowerSyncDatabase, id: string): Promise<void> {
  const foto = await db.get<{ uri_local: string }>(
    'SELECT uri_local FROM evidencia_pendiente WHERE id = ?',
    [id],
  );
  if (foto?.uri_local) {
    try {
      await FileSystem.deleteAsync(foto.uri_local, { idempotent: true });
    } catch {
      // Borrar la fila es lo que el usuario pidió; el archivo huérfano lo
      // recoge `purgarSubidas` o el propio sistema al limpiar la app.
    }
  }
  await db.execute('DELETE FROM evidencia_pendiente WHERE id = ?', [id]);
}

/**
 * Borra el archivo local de las fotos subidas hace más de `dias`.
 *
 * El teléfono de un residente no es un archivo histórico: desde que
 * `estado = 'subida'` la copia canónica está en R2, y una obra de seis meses
 * son cientos de fotos. La fila se conserva —pesa nada y es el rastro de qué
 * se subió—; lo que se va es el binario.
 */
export async function purgarSubidas(db: AbstractPowerSyncDatabase, dias = 30): Promise<number> {
  const corte = new Date(Date.now() - dias * 24 * 60 * 60 * 1000).toISOString();
  const viejas = await db.getAll<{ id: string; uri_local: string }>(
    `SELECT id, uri_local FROM evidencia_pendiente
      WHERE estado = 'subida' AND uri_local != '' AND subida_en < ?`,
    [corte],
  );

  for (const foto of viejas) {
    try {
      await FileSystem.deleteAsync(foto.uri_local, { idempotent: true });
    } catch {
      // Si no se puede borrar, la fila se marca igual: reintentarlo en cada
      // arranque no aporta y el objetivo —dejar de contarla como copia
      // local— ya se cumplió.
    }
    await db.execute("UPDATE evidencia_pendiente SET uri_local = '' WHERE id = ?", [foto.id]);
  }

  return viejas.length;
}
