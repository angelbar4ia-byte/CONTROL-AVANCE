/**
 * Estimación — bandeja de estimaciones semanales de una obra (§11.3 E).
 *
 * Pantalla compartida (§5.3): Residente y Supervisor generan y envían;
 * Control de obra valida. Ruta `/estimacion` (`shell/navegacion.ts`).
 *
 * ## Limitación conocida: resolución de `obra_id`
 *
 * `GET /obras/{id}/estimaciones` exige `obra_id` en la URL, pero el
 * contrato actual no expone ningún listado de obras (`GET /obras` está en
 * el spec §11.2 pero no implementado; tampoco `obra` es un catálogo
 * whitelisted en `lib/supabase.ts` §10.7, porque no es catálogo sino dato
 * de dominio). Sin un mecanismo para resolver "la obra activa del
 * Residente/Supervisor", esta pantalla usa un **selector simple**: el
 * usuario pega el UUID de la obra. Cuando exista `GET /me` con
 * `obras_en_alcance` resuelto a una lista (o `GET /obras`), este campo debe
 * reemplazarse por un selector real.
 */

import { useState, type FormEvent } from 'react';

import {
  useEnviarEstimacionApiV1EstimacionesEstimacionIdPatch,
  useGenerarEstimacionApiV1ObrasObraIdEstimacionesPost,
  useListarEstimacionesApiV1ObrasObraIdEstimacionesGet,
  useValidarEstimacionApiV1EstimacionesEstimacionIdValidarPost,
} from '@/api/generado/estimacion/estimacion';
import { ModoPago } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { fmtMXN, fmtSemana } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { accionesDisponiblesEstimacion, etiquetaModo, puedeGenerar, tonoEstatusEstimacion } from './reglas';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function Estimacion() {
  const { sesion } = useSesion();
  const [obraIdInput, setObraIdInput] = useState('');
  const [obraId, setObraId] = useState('');
  const [modo, setModo] = useState<ModoPago>(ModoPago.destajo);
  const [error, setError] = useState<string | null>(null);

  const obraIdValido = UUID_RE.test(obraId);

  const consulta = useListarEstimacionesApiV1ObrasObraIdEstimacionesGet(obraId, {
    query: { enabled: obraIdValido },
  });

  const generar = useGenerarEstimacionApiV1ObrasObraIdEstimacionesPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const enviar = useEnviarEstimacionApiV1EstimacionesEstimacionIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const validar = useValidarEstimacionApiV1EstimacionesEstimacionIdValidarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  if (!sesion) return null;
  const rol = sesion.rol;

  function alConfirmarObra(evento: FormEvent) {
    evento.preventDefault();
    setObraId(obraIdInput.trim());
  }

  const filas = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Reportes</div>
          <h1 className="page__title">Estimación</h1>
          <div className="page__subtitle">
            Corte semanal por modo de pago (§6): destajo, concepto o
            subcontrato. Estatus: borrador → enviada → validada.
          </div>
        </div>
        {puedeGenerar(rol) && obraIdValido && (
          <div className="page__actions">
            <select
              className="select"
              value={modo}
              onChange={(e) => setModo(e.target.value as ModoPago)}
              aria-label="Modo de la estimación a generar"
            >
              <option value={ModoPago.destajo}>Destajo</option>
              <option value={ModoPago.concepto}>Concepto</option>
              <option value={ModoPago.subcontrato}>Subcontrato</option>
            </select>
            <button
              type="button"
              className="btn btn--primary"
              disabled={generar.isPending}
              onClick={() => generar.mutate({ obraId, data: { modo } })}
            >
              {generar.isPending ? 'Generando…' : 'Generar estimación'}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-8">
          <ErrorBanner mensaje={error} />
        </div>
      )}

      <form onSubmit={alConfirmarObra} className="filterbar">
        <div className="field" style={{ maxWidth: 420 }}>
          <label className="field__label" htmlFor="obra-id">
            ID de obra
          </label>
          <input
            id="obra-id"
            className="input input--mono"
            placeholder="uuid de la obra"
            value={obraIdInput}
            onChange={(e) => setObraIdInput(e.target.value)}
          />
        </div>
        <button type="submit" className="btn">
          Cargar estimaciones
        </button>
      </form>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Estimación</th>
                <th>Semana</th>
                <th>Modo</th>
                <th className="is-num">Monto</th>
                <th>Estatus</th>
                <th className="cell-actions">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {!obraIdValido ? (
                <tr>
                  <td colSpan={6}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Pega el ID de una obra y presiona "Cargar estimaciones".
                    </div>
                  </td>
                </tr>
              ) : consulta.isLoading ? (
                <tr>
                  <td colSpan={6}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Esta obra no tiene estimaciones todavía.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((estimacion) => {
                  const acciones = accionesDisponiblesEstimacion(rol, estimacion.estatus);
                  return (
                    <tr key={estimacion.id}>
                      <td className="is-key">{estimacion.folio ?? estimacion.id.slice(0, 8)}</td>
                      <td className="mono tnum">{fmtSemana(estimacion.semana, estimacion.anio)}</td>
                      <td>{etiquetaModo(estimacion.modo)}</td>
                      <td className="is-num">{fmtMXN(estimacion.monto_total)}</td>
                      <td>
                        <span className={`badge badge--${tonoEstatusEstimacion(estimacion.estatus)}`}>
                          {estimacion.estatus}
                        </span>
                      </td>
                      <td className="cell-actions">
                        <div className="row gap-4">
                          {acciones.includes('enviar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={enviar.isPending}
                              onClick={() => enviar.mutate({ estimacionId: estimacion.id })}
                            >
                              Enviar
                            </button>
                          )}
                          {acciones.includes('validar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={validar.isPending}
                              onClick={() => validar.mutate({ estimacionId: estimacion.id })}
                            >
                              Validar
                            </button>
                          )}
                          {acciones.length === 0 && <span className="text-faint text-sm">—</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
