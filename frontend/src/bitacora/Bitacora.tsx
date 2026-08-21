/**
 * Bitácora de eventos — quién cambió qué y cuándo (§7.9, §11.7, §12.12, §5.1).
 *
 * La escribe un trigger desde la Fase 8 (migración 0023) y hasta ahora solo se
 * podía leer con `psql`. Una auditoría que exige acceso a la base no cumple lo
 * que el §12.12 pide, porque quien necesita saber quién movió el IVA es
 * justamente quien no tiene ese acceso.
 *
 * ## Solo lectura, y no porque esta pantalla lo decida
 *
 * `bitacora` no tiene política de INSERT, UPDATE ni DELETE: es append-only por
 * construcción. Aquí no hay botones porque no hay nada que se pueda hacer.
 *
 * ## El diff es lo que se viene a ver
 *
 * Un `update` guarda **solo las columnas que cambiaron**, con su antes y su
 * después. Mostrar la fila completa —que es lo que haría un volcado del
 * `jsonb`— escondería el cambio dentro de treinta campos iguales. Por eso la
 * tabla pinta el diff campo por campo y deja el resto en el detalle.
 */

import { useState } from 'react';

import {
  useEntidadesConBitacoraApiV1BitacoraEntidadesGet,
  useListarBitacoraApiV1BitacoraGet,
} from '@/api/generado/bitacora/bitacora';
import type { EntradaBitacora, PaginaBitacora } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha } from '@/lib/formato';

const TAMANO = 50;

const ACCIONES: Readonly<Record<string, { etiqueta: string; tono: string }>> = {
  insert: { etiqueta: 'Alta', tono: 'badge--ok' },
  update: { etiqueta: 'Cambio', tono: 'badge--info' },
  delete: { etiqueta: 'Baja', tono: 'badge--danger' },
};

export default function Bitacora() {
  const { sesion } = useSesion();
  const [entidad, setEntidad] = useState('');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [pagina, setPagina] = useState(1);
  const [abierta, setAbierta] = useState<string | null>(null);

  const entidades = useEntidadesConBitacoraApiV1BitacoraEntidadesGet<string[], ErrorApi>();

  const consulta = useListarBitacoraApiV1BitacoraGet<PaginaBitacora, ErrorApi>({
    page: pagina,
    size: TAMANO,
    ...(entidad ? { entidad } : {}),
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
  });

  if (!sesion) return null;

  // §11.2/§12.4: la política `bitacora_select` es de Control de obra y Super
  // intendente. Los demás llegan aquí solo escribiendo la URL, así que se les
  // explica en vez de mostrarles una lista vacía que parece un error.
  const puedeVer = sesion.rol === 'control_obra' || sesion.rol === 'super_intendente';

  const datos = consulta.data;
  const total = datos?.total ?? 0;
  const ultimaPagina = Math.max(1, Math.ceil(total / TAMANO));

  function cambiarFiltro(accion: () => void) {
    accion();
    // Volver a la primera página al filtrar: quedarse en la 7 de un listado
    // que ahora tiene 2 muestra un vacío que parece "no hay nada".
    setPagina(1);
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Presupuesto</div>
          <h1 className="page__title">Bitácora de eventos</h1>
          <div className="page__subtitle">
            Cambios de configuración y catálogo: quién, cuándo y qué (§12.12).
          </div>
        </div>
      </div>

      {!puedeVer ? (
        <div className="empty">
          <div className="empty-title">La bitácora es de Control de obra y Super intendente</div>
          <div className="empty-sub">
            Lo impone la base de datos, no esta pantalla (política `bitacora_select`).
          </div>
        </div>
      ) : (
        <>
          {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

          <div className="filterbar">
            <div className="field">
              <label className="field__label" htmlFor="bitacora-entidad">
                Tabla
              </label>
              <select
                id="bitacora-entidad"
                className="input"
                value={entidad}
                onChange={(e) => cambiarFiltro(() => setEntidad(e.target.value))}
              >
                <option value="">Todas</option>
                {(entidades.data ?? []).map((nombre) => (
                  <option key={nombre} value={nombre}>
                    {nombre}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="field__label" htmlFor="bitacora-desde">
                Desde
              </label>
              <input
                id="bitacora-desde"
                type="date"
                className="input"
                value={desde}
                onChange={(e) => cambiarFiltro(() => setDesde(e.target.value))}
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="bitacora-hasta">
                Hasta
              </label>
              <input
                id="bitacora-hasta"
                type="date"
                className="input"
                value={hasta}
                onChange={(e) => cambiarFiltro(() => setHasta(e.target.value))}
              />
            </div>
          </div>

          {consulta.isLoading ? (
            <div className="empty">
              <div className="empty-title">Cargando…</div>
            </div>
          ) : (datos?.entradas.length ?? 0) === 0 ? (
            <div className="empty">
              <div className="empty-title">Sin movimientos</div>
              <div className="empty-sub">
                La bitácora registra cambios de configuración y catálogo, no capturas de
                avance (migración 0023).
              </div>
            </div>
          ) : (
            <>
              <table className="table">
                <thead>
                  <tr>
                    <th>Cuándo</th>
                    <th>Quién</th>
                    <th>Tabla</th>
                    <th>Acción</th>
                    <th>Qué cambió</th>
                  </tr>
                </thead>
                <tbody>
                  {(datos?.entradas ?? []).map((entrada) => (
                    <Fila
                      key={entrada.id}
                      entrada={entrada}
                      abierta={abierta === entrada.id}
                      onAlternar={() =>
                        setAbierta((previa) => (previa === entrada.id ? null : entrada.id))
                      }
                    />
                  ))}
                </tbody>
              </table>

              <div className="row gap-8 mt-8">
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={pagina <= 1}
                  onClick={() => setPagina((p) => p - 1)}
                >
                  Anterior
                </button>
                <span className="text-mute text-sm mono">
                  {pagina} / {ultimaPagina} · {total} movimientos
                </span>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={pagina >= ultimaPagina}
                  onClick={() => setPagina((p) => p + 1)}
                >
                  Siguiente
                </button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function Fila({
  entrada,
  abierta,
  onAlternar,
}: {
  readonly entrada: EntradaBitacora;
  readonly abierta: boolean;
  readonly onAlternar: () => void;
}) {
  const accion = ACCIONES[entrada.accion] ?? { etiqueta: entrada.accion, tono: 'badge--outline' };
  const cambios = diferencias(entrada.datos);

  return (
    <>
      <tr onClick={onAlternar} style={{ cursor: 'pointer' }}>
        <td className="mono">{fmtFecha(entrada.fecha)}</td>
        <td>{entrada.usuario_nombre ?? <span className="text-mute">sistema</span>}</td>
        <td className="mono">{entrada.entidad}</td>
        <td>
          <span className={`badge ${accion.tono}`}>{accion.etiqueta}</span>
        </td>
        <td>
          {cambios.length === 0 ? (
            <span className="text-mute text-sm">{abierta ? 'ver abajo' : 'ver detalle'}</span>
          ) : (
            <span className="text-sm">
              {cambios.map((c) => c.campo).join(', ')}
            </span>
          )}
        </td>
      </tr>

      {abierta && (
        <tr>
          <td colSpan={5}>
            <div className="card__body col gap-8">
              {cambios.length > 0 ? (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Campo</th>
                      <th>Antes</th>
                      <th>Después</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cambios.map((cambio) => (
                      <tr key={cambio.campo}>
                        <td className="mono">{cambio.campo}</td>
                        <td className="mono text-mute">{cambio.antes}</td>
                        <td className="mono">{cambio.despues}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                // Un alta o una baja no tienen diff: la fila entera es el dato.
                <pre className="mono text-sm" style={{ whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(entrada.datos, null, 2)}
                </pre>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export interface Cambio {
  readonly campo: string;
  readonly antes: string;
  readonly despues: string;
}

/**
 * Saca el diff campo por campo de un renglón de `update`.
 *
 * La migración 0023 guarda `{"cambio": {"antes": {...}, "despues": {...}}}`
 * con **solo** lo que cambió. Un `insert` o un `delete` no traen esa forma y
 * devuelven vacío, lo que la fila interpreta como "muestra el JSON completo".
 *
 * Los valores se serializan con `JSON.stringify` en vez de `String()`: un
 * `null` tiene que verse como `null` y no como cadena vacía —la diferencia
 * entre "se borró el valor" y "no cambió" es justo lo que se viene a ver—.
 */
export function diferencias(datos: unknown): Cambio[] {
  if (!datos || typeof datos !== 'object') return [];
  const cambio = (datos as Record<string, unknown>).cambio;
  if (!cambio || typeof cambio !== 'object') return [];

  const antes = ((cambio as Record<string, unknown>).antes ?? {}) as Record<string, unknown>;
  const despues = ((cambio as Record<string, unknown>).despues ?? {}) as Record<string, unknown>;

  return [...new Set([...Object.keys(antes), ...Object.keys(despues)])].sort().map((campo) => ({
    campo,
    antes: JSON.stringify(antes[campo] ?? null),
    despues: JSON.stringify(despues[campo] ?? null),
  }));
}
