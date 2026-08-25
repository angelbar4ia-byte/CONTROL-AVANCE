/**
 * Detalle de un lote: su reporte de errores, su bandeja de pendientes y la
 * reversa (§9.3, §10.3, §10.8).
 *
 * LA REVERSA ES POR LOTE, NO POR REGISTRO
 *
 * `carga_snapshot` guarda cada operación con su `orden` (migración 0019) y la
 * reversa las deshace en orden descendente. Por eso aquí se ofrece un solo
 * botón y no una lista de filas que deshacer: revertir media carga dejaría el
 * catálogo en un estado que nadie eligió.
 */

import { useState } from 'react';

import {
  useBandejaDeCargaApiV1CargasCargaIdPendientesGet,
  useEliminarCargaApiV1CargasCargaIdDelete,
  useRevertirCargaApiV1CargasCargaIdRevertirPost,
} from '@/api/generado/cargas/cargas';
import type { LoteRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import {
  etiquetaEstatus,
  etiquetaTipo,
  resumenDe,
  seePuedeRevertir,
  sePuedeEliminar,
  tonoEstatus,
} from './reglas';

interface Props {
  readonly lote: LoteRespuesta;
  readonly onCerrar: () => void;
  readonly onRevertida: () => void;
  /** El padre cierra el cajón y recarga el historial: el lote ya no existe. */
  readonly onEliminada: () => void;
}

export function PanelCarga({ lote, onCerrar, onRevertida, onEliminada }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [confirmandoEliminar, setConfirmandoEliminar] = useState(false);

  const pendientesQ = useBandejaDeCargaApiV1CargasCargaIdPendientesGet(lote.id, {
    solo_abiertos: true,
  });

  const revertir = useRevertirCargaApiV1CargasCargaIdRevertirPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setConfirmando(false);
        onRevertida();
      },
      onError: (err) => setError(err.message),
    },
  });

  const eliminar = useEliminarCargaApiV1CargasCargaIdDelete<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onEliminada();
      },
      onError: (err) => setError(err.message),
    },
  });

  const resumen = resumenDe(lote);
  const pendientes = pendientesQ.data ?? [];
  const errores = (lote.errores ?? []) as Record<string, unknown>[];

  return (
    <Sheet
      titulo={etiquetaTipo(lote.tipo)}
      subtitulo={lote.archivo_nombre ?? '(sin nombre de archivo)'}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-12">
        {error && <ErrorBanner mensaje={error} />}

        <div className="row gap-8">
          <span className={`badge badge--${tonoEstatus(lote.estatus)}`}>
            {etiquetaEstatus(lote.estatus)}
          </span>
          {lote.revertida && <span className="badge badge--warn">Revertida</span>}
          {lote.version_generada !== null && lote.version_generada !== undefined && (
            <span className="badge badge--info">Versión {lote.version_generada}</span>
          )}
        </div>

        <div className="row gap-12">
          <Dato etiqueta="Filas" valor={resumen.filas} />
          <Dato etiqueta="Insertados" valor={resumen.insertados} />
          <Dato etiqueta="Actualizados" valor={resumen.actualizados} />
          <Dato etiqueta="Omitidos" valor={resumen.omitidos} />
        </div>

        {lote.archivo_hash && (
          <div className="field">
            <div className="field__label">Huella del archivo</div>
            {/* Es lo que hace que subir dos veces el mismo archivo no genere
                dos versiones (§10.8), y lo que permite comprobar que lo que se
                aplicó es lo que se previsualizó. */}
            <div className="mono text-xs text-mute" style={{ wordBreak: 'break-all' }}>
              {lote.archivo_hash}
            </div>
          </div>
        )}

        {errores.length > 0 && (
          <div className="field">
            <div className="field__label">Errores por fila (§9.3)</div>
            <div className="table-scroll" style={{ maxHeight: 240 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th className="is-num">Fila</th>
                    <th>Columna</th>
                    <th>Valor</th>
                    <th>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {errores.map((fila, indice) => (
                    <tr key={indice}>
                      <td className="is-num mono">{String(fila.fila ?? '—')}</td>
                      <td className="mono">{String(fila.columna ?? '—')}</td>
                      <td className="mono">{String(fila.valor ?? '—')}</td>
                      <td>{String(fila.motivo ?? '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="field">
          <div className="field__label">Pendientes por confirmar (§10.3)</div>
          {pendientesQ.isLoading ? (
            <div className="text-mute text-sm">Cargando…</div>
          ) : pendientes.length === 0 ? (
            <div className="text-mute text-sm">
              Nada esperando confirmación en este lote.
            </div>
          ) : (
            <div className="table-scroll" style={{ maxHeight: 240 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Valor del archivo</th>
                    <th>Propuesta del sistema</th>
                    <th>Crítico</th>
                  </tr>
                </thead>
                <tbody>
                  {pendientes.map((pendiente) => (
                    <tr key={pendiente.id}>
                      <td>{etiquetaEstatus(pendiente.tipo)}</td>
                      <td className="mono">{pendiente.valor_origen ?? '—'}</td>
                      <td className="mono text-xs">
                        {JSON.stringify(pendiente.propuesta)}
                      </td>
                      <td>
                        {pendiente.critico ? (
                          <span className="badge badge--danger">Sí</span>
                        ) : (
                          <span className="text-mute">No</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="field__hint">
            El sistema propone y el humano confirma (§10.3). Resolverlos desde
            aquí todavía no está: el contrato no publica la ruta que los cierra.
          </div>
        </div>

        {seePuedeRevertir(lote) && (
          <>
            <hr className="sep" />
            <div className="field">
              <div className="field__label">Revertir el lote</div>
              <div className="field__hint">
                Deshace las operaciones de esta carga en orden inverso (§10.8).
                No borra el registro del lote: queda marcado como revertido, que
                es lo que permite auditar qué se cargó y qué se deshizo.
              </div>
              {confirmando ? (
                <div className="row gap-8" style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    className="btn btn--sm btn--danger"
                    disabled={revertir.isPending}
                    onClick={() => revertir.mutate({ cargaId: lote.id })}
                  >
                    {revertir.isPending ? 'Revirtiendo…' : 'Sí, revertir'}
                  </button>
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => setConfirmando(false)}
                  >
                    Cancelar
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn btn--sm"
                  style={{ alignSelf: 'flex-start', marginTop: 8 }}
                  onClick={() => setConfirmando(true)}
                >
                  Revertir
                </button>
              )}
            </div>
          </>
        )}

        {sePuedeEliminar(lote) && (
          <>
            <hr className="sep" />
            <div className="field">
              <div className="field__label">Eliminar el registro</div>
              <div className="field__hint">
                {lote.revertida
                  ? 'Ya se revirtió: esto solo borra su fila del historial (§10.8).'
                  : 'Esta carga no llegó a aplicarse, así que no hay nada que deshacer.'}
                {' '}
                No se puede deshacer.
              </div>
              {confirmandoEliminar ? (
                <div className="row gap-8" style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    className="btn btn--sm btn--danger"
                    disabled={eliminar.isPending}
                    onClick={() => eliminar.mutate({ cargaId: lote.id })}
                  >
                    {eliminar.isPending ? 'Eliminando…' : 'Sí, eliminar'}
                  </button>
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => setConfirmandoEliminar(false)}
                  >
                    Cancelar
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn btn--sm"
                  style={{ alignSelf: 'flex-start', marginTop: 8 }}
                  onClick={() => setConfirmandoEliminar(true)}
                >
                  Eliminar
                </button>
              )}
            </div>
          </>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </Sheet>
  );
}

function Dato({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: number }) {
  return (
    <div className="col gap-2">
      <span className="text-xs text-mute">{etiqueta}</span>
      <span className="mono is-key">{valor}</span>
    </div>
  );
}
