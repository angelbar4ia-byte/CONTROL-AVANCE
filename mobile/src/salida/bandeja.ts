/**
 * Bandeja de salida: operaciones capturadas sin señal que **deben** pasar por
 * la API.
 *
 * Spec §11.3 C (cierre de actividad) y F (incidencia) · §11.2
 * (`Idempotency-Key`) · §12.5 (offline) · D5 del ROADMAP.
 *
 * ## Por qué no todo va por PowerSync
 *
 * D5 zanjó que la conciliación de **avance** va directo a Postgres: el delta
 * se acumula, RLS es la frontera y no hay efectos colaterales. Pero eso no
 * generaliza. Abrir una incidencia con `impacto=detiene` **bloquea
 * actividades y replanea el CPM** (§11.3 F.5), y solicitar el cierre de una
 * actividad calcula el monto y mueve el estatus a `pendiente_cierre` (§11.3
 * C). Esos efectos viven en el caso de uso, no en un trigger de la base.
 *
 * Un `INSERT` directo desde el teléfono crearía la fila y **no dispararía
 * nada**. El resultado no sería un error visible sino algo peor: una obra que
 * se ve libre mientras está detenida. Por eso estas dos operaciones viajan
 * como `POST` a la API, y como la API puede no estar disponible en el momento
 * de la captura, esperan aquí.
 *
 * ## Por qué el reintento es seguro
 *
 * Cada operación nace con su `Idempotency-Key` (§11.2), generada **al
 * capturar**, no al enviar. Eso es lo que la hace segura: si la red se cae
 * después de que el servidor escribió pero antes de que llegue la respuesta,
 * el reintento manda la misma clave y el backend contesta **409** sin volver
 * a crear nada. Aquí ese 409 se lee como éxito —que es lo que es: la
 * operación ya ocurrió, exactamente una vez— y no como fallo.
 *
 * ## Qué ve el usuario
 *
 * Las operaciones pendientes se muestran en la lista a la que pertenecen, con
 * su estado. Una incidencia levantada sin señal aparece de inmediato marcada
 * como "por enviar" y luego es reemplazada por la real cuando baja por sync.
 * La alternativa —no mostrarla hasta que suba— haría que el residente la
 * capture dos veces.
 */

import type { AbstractPowerSyncDatabase } from '@powersync/react-native';

import { ErrorDeApi, pedir, SinConexion } from '@/lib/api';
import { generarId } from '@/lib/id';
import { clavesDe } from '@/evidencias/cola';

export const MAX_INTENTOS = 5;

/** Operaciones por pasada. Se envían en orden de captura. */
const TANDA = 5;

export interface OperacionEnCola {
  readonly id: string;
  readonly ruta: string;
  readonly metodo: string;
  readonly cuerpo: string;
  readonly clave_idem: string;
  readonly etiqueta: string;
  readonly obra_id: string | null;
  readonly fotos: string;
  readonly estado: string;
  readonly intentos: number;
  readonly error: string | null;
  readonly creada_en: string;
  readonly enviada_en: string | null;
}

export interface Encolable {
  readonly ruta: string;
  readonly metodo?: 'POST' | 'PATCH';
  readonly cuerpo: Record<string, unknown>;
  /** Lo que el usuario reconoce en la bandeja. */
  readonly etiqueta: string;
  readonly obraId: string | null;
  /** Ids de `evidencia_pendiente`; sus claves se inyectan en `evidencias` al enviar. */
  readonly fotos?: readonly string[];
}

/**
 * Anota la operación. Devuelve su id local para que la pantalla la pueda
 * pintar de inmediato como "por enviar".
 */
export async function encolar(
  db: AbstractPowerSyncDatabase,
  operacion: Encolable,
): Promise<string> {
  const id = generarId();
  await db.execute(
    `INSERT INTO operacion_pendiente
       (id, ruta, metodo, cuerpo, clave_idem, etiqueta, obra_id, fotos,
        estado, intentos, error, creada_en, enviada_en)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', 0, NULL, ?, NULL)`,
    [
      id,
      operacion.ruta,
      operacion.metodo ?? 'POST',
      JSON.stringify(operacion.cuerpo),
      // La clave se fija aquí, no al enviar: si se generara por intento, dos
      // reintentos serían dos operaciones distintas para el servidor y el
      // duplicado que la cabecera existe para evitar volvería por la ventana.
      generarId(),
      operacion.etiqueta,
      operacion.obraId,
      JSON.stringify(operacion.fotos ?? []),
      new Date().toISOString(),
    ],
  );
  return id;
}

/** Operaciones que aún deben salir, en orden de captura. */
export async function pendientes(db: AbstractPowerSyncDatabase): Promise<OperacionEnCola[]> {
  return db.getAll<OperacionEnCola>(
    `SELECT * FROM operacion_pendiente
      WHERE estado = 'pendiente' AND intentos < ?
      ORDER BY creada_en ASC
      LIMIT ?`,
    [MAX_INTENTOS, TANDA],
  );
}

/**
 * Envía una tanda. Devuelve cuántas salieron. **No levanta**: la llaman
 * efectos de arranque y de reconexión.
 */
export async function procesarBandeja(db: AbstractPowerSyncDatabase): Promise<number> {
  let enviadas = 0;

  for (const operacion of await pendientes(db)) {
    try {
      await enviar(db, operacion);
      await marcarEnviada(db, operacion.id);
      enviadas += 1;
    } catch (e) {
      if (e instanceof ErrorDeApi && e.estado === 409) {
        // Ya procesada con esta misma clave (§11.2): el servidor la escribió
        // en un intento anterior cuya respuesta no llegó. Es éxito.
        await marcarEnviada(db, operacion.id);
        enviadas += 1;
        continue;
      }
      await marcarFallo(db, operacion, e);
    }
  }

  return enviadas;
}

async function enviar(
  db: AbstractPowerSyncDatabase,
  operacion: OperacionEnCola,
): Promise<void> {
  const cuerpo = { ...(JSON.parse(operacion.cuerpo) as Record<string, unknown>) };

  const fotos = JSON.parse(operacion.fotos) as string[];
  if (fotos.length > 0) {
    // Solo las que ya subieron. Una foto que aún no sube **no detiene** la
    // operación: la incidencia importa más que su ilustración, y esperar a la
    // foto significaría no reportar la fuga hasta que haya buena señal.
    const claves = await clavesDe(db, fotos);
    if (claves.length > 0) cuerpo.evidencias = claves;
  }

  await pedir(operacion.ruta, {
    metodo: operacion.metodo === 'PATCH' ? 'PATCH' : 'POST',
    cuerpo,
    idempotencia: operacion.clave_idem,
  });
}

async function marcarEnviada(db: AbstractPowerSyncDatabase, id: string): Promise<void> {
  await db.execute(
    `UPDATE operacion_pendiente
        SET estado = 'enviada', error = NULL, enviada_en = ?
      WHERE id = ?`,
    [new Date().toISOString(), id],
  );
}

/**
 * Igual que en la cola de fotos: sin señal no cuenta como intento, y un
 * rechazo del servidor sí es terminal. La diferencia está en el 422 de
 * `ClaveReusada`, que sería un error del cliente y aquí no puede pasar —cada
 * fila lleva su clave y nadie la reescribe—, así que cae en el caso general.
 */
async function marcarFallo(
  db: AbstractPowerSyncDatabase,
  operacion: OperacionEnCola,
  causa: unknown,
): Promise<void> {
  if (causa instanceof SinConexion) return;

  const terminal = causa instanceof ErrorDeApi && esRechazoDefinitivo(causa.estado);
  const intentos = operacion.intentos + 1;
  const estado = terminal || intentos >= MAX_INTENTOS ? 'fallida' : 'pendiente';

  await db.execute(
    'UPDATE operacion_pendiente SET intentos = ?, estado = ?, error = ? WHERE id = ?',
    [intentos, estado, causa instanceof Error ? causa.message : String(causa), operacion.id],
  );
}

function esRechazoDefinitivo(estado: number): boolean {
  if (estado === 401 || estado === 408 || estado === 429) return false;
  return estado >= 400 && estado < 500;
}

/** Reintento manual desde la UI de una operación que quedó `fallida`. */
export async function reintentar(db: AbstractPowerSyncDatabase, id: string): Promise<void> {
  await db.execute(
    `UPDATE operacion_pendiente
        SET estado = 'pendiente', intentos = 0, error = NULL
      WHERE id = ? AND estado = 'fallida'`,
    [id],
  );
}

/** Descarta una operación que nunca va a salir. */
export async function descartar(db: AbstractPowerSyncDatabase, id: string): Promise<void> {
  await db.execute('DELETE FROM operacion_pendiente WHERE id = ?', [id]);
}

/**
 * Borra las operaciones enviadas hace más de `dias`.
 *
 * A diferencia de las fotos, aquí no queda nada que valga la pena conservar:
 * la entidad real ya bajó por sync y es la que se consulta. La fila de la
 * bandeja solo servía para el tránsito.
 */
export async function purgarEnviadas(db: AbstractPowerSyncDatabase, dias = 7): Promise<void> {
  const corte = new Date(Date.now() - dias * 24 * 60 * 60 * 1000).toISOString();
  await db.execute(
    "DELETE FROM operacion_pendiente WHERE estado = 'enviada' AND enviada_en < ?",
    [corte],
  );
}
