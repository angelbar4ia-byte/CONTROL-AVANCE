/**
 * Estimación — bandeja de estimaciones semanales de una obra (§11.3 E).
 *
 * Pantalla compartida (§5.3): Residente y Supervisor generan y envían;
 * Control de obra valida. Ruta `/estimacion` (`shell/navegacion.ts`).
 *
 * ## La obra se elige, ya no se pega
 *
 * Esta pantalla nació pidiendo el UUID de la obra escrito a mano, porque
 * `GET /obras` no existía todavía. Existe desde la Fase 1 y `SelectorObra`
 * (`lib/`) lo consume: el listado ya viene acotado por RLS al alcance del rol
 * (§4, §12.4), así que elegir de una lista es además más seguro que teclear un
 * id que podría ser de otra obra.
 *
 * ## El XLSX es un job
 *
 * `GET /estimaciones/{id}/export` **encola** y devuelve un identificador; el
 * archivo se baja después por `/reportes/{id}/descargar` (§11.2, §12.2). Por
 * eso el botón dice "Exportar" y aparece una tarjeta de seguimiento, en vez de
 * una descarga que no llegaría.
 */

import { useState } from 'react';

import {
  useEnviarEstimacionApiV1EstimacionesEstimacionIdPatch,
  useGenerarEstimacionApiV1ObrasObraIdEstimacionesPost,
  useListarEstimacionesApiV1ObrasObraIdEstimacionesGet,
  useValidarEstimacionApiV1EstimacionesEstimacionIdValidarPost,
} from '@/api/generado/estimacion/estimacion';
import { useExportarEstimacionApiV1EstimacionesEstimacionIdExportGet } from '@/api/generado/reportes/reportes';
import { ModoPago } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { fmtMXN, fmtSemana } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { SeguimientoDeReporte } from '@/reportes/SeguimientoDeReporte';
import { accionesDisponiblesEstimacion, etiquetaModo, puedeGenerar, tonoEstatusEstimacion } from './reglas';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function Estimacion() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [modo, setModo] = useState<ModoPago>(ModoPago.destajo);
  const [error, setError] = useState<string | null>(null);
  const [reporteId, setReporteId] = useState<string | null>(null);
  const [estimacionAExportar, setEstimacionAExportar] = useState('');
  // Una clave por (método, ruta): en una lista el mismo hook opera sobre
  // recursos distintos y una clave fija haría que el segundo llegara con la
  // del primero (regla 1 del ROADMAP).
  const idempotente = useClavesPorRecurso();


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
    ...idempotente,
  });

  const enviar = useEnviarEstimacionApiV1EstimacionesEstimacionIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
    ...idempotente,
  });

  const validar = useValidarEstimacionApiV1EstimacionesEstimacionIdValidarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
    ...idempotente,
  });

  // `enabled: false`: exportar es una acción del operador, no algo que deba
  // encolarse al abrir la pantalla. Se dispara con `refetch`.
  const exportar = useExportarEstimacionApiV1EstimacionesEstimacionIdExportGet(
    estimacionAExportar,
    { query: { enabled: false } },
  );

  if (!sesion) return null;
  const rol = sesion.rol;

  async function encolarExport(estimacionId: string) {
    setError(null);
    setEstimacionAExportar(estimacionId);
    const resultado = await exportar.refetch();
    if (resultado.error) {
      setError((resultado.error as ErrorApi).message);
      return;
    }
    if (resultado.data) setReporteId(resultado.data.id);
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

      <div className="filterbar">
        <SelectorObra
          id="estimacion-obra"
          etiqueta="Obra"
          valor={obraId}
          onCambio={(id) => {
            setObraId(id);
            setReporteId(null);
          }}
        />
      </div>

      {reporteId && (
        <SeguimientoDeReporte
          reporteId={reporteId}
          titulo="Estimación en Excel"
          onCerrar={() => setReporteId(null)}
        />
      )}

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
                          <button
                            type="button"
                            className="btn btn--sm"
                            disabled={exportar.isFetching}
                            onClick={() => void encolarExport(estimacion.id)}
                          >
                            Exportar
                          </button>
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
