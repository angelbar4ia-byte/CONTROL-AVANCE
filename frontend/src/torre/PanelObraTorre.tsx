/**
 * Detalle de una obra desde la Torre: sus actividades (§11.2, §5.1).
 *
 * Es el drill-down del sistema de diseño: la lista de obras se queda a la
 * izquierda y la obra se abre al lado, en vez de navegar a otra pantalla y
 * perder el contexto de lo que se estaba revisando.
 *
 * Muestra lo que la Torre promete y la fila no cabe: qué actividades están en
 * la ruta crítica, cuáles están detenidas y con qué desfase. Las acciones
 * —autorizar un cierre, atender una incidencia— **no** están aquí: viven en sus
 * pantallas, que ya existen y saben del flujo (§11.3 C, F). Duplicarlas sería
 * mantener dos copias de las mismas reglas de transición.
 */

import { useState } from 'react';

import { useActividadesDeObraApiV1ObrasObraIdActividadesGet } from '@/api/generado/torre/torre';
import type { ActividadRespuesta, EstadoDeObraRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { fmtNum, fmtPct } from '@/lib/formato';
import { etiquetaEstatusActividad, tonoEstatusActividad } from './reglas';

interface Props {
  readonly obra: EstadoDeObraRespuesta;
  readonly onCerrar: () => void;
  readonly onCambio: () => void;
}

export function PanelObraTorre({ obra, onCerrar }: Props) {
  const [soloCriticas, setSoloCriticas] = useState(false);

  const consulta = useActividadesDeObraApiV1ObrasObraIdActividadesGet<
    ActividadRespuesta[],
    ErrorApi
  >(obra.obra_id, { solo_criticas: soloCriticas });

  const actividades = consulta.data ?? [];

  return (
    <Sheet
      titulo={obra.obra_clave}
      subtitulo={`${obra.proyecto_clave} · ${obra.cluster_clave}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-12">
        {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

        <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
          <Dato etiqueta="Avance" valor={fmtPct(Number(obra.avance_pct))} />
          <Dato etiqueta="Estatus" valor={obra.obra_estatus} />
          <Dato etiqueta="Residente" valor={obra.residente_nombre ?? '—'} />
          <Dato etiqueta="Concluidas" valor={`${obra.concluidas} / ${obra.actividades}`} />
        </div>

        {(obra.bloqueadas > 0 || obra.incidencias_detienen > 0) && (
          <div className="badge badge--danger">
            {obra.bloqueadas} actividad(es) detenida(s) por incidencia (§11.3 F).
            Se resuelven desde Incidencias.
          </div>
        )}
        {obra.cierres_pendientes > 0 && (
          <div className="badge badge--warn">
            {obra.cierres_pendientes} cierre(s) esperando. Se resuelven desde
            Cierres (§11.3 C).
          </div>
        )}

        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloCriticas}
            onChange={(e) => setSoloCriticas(e.target.checked)}
          />
          <span className="text-sm">Solo la ruta crítica ({obra.criticas})</span>
        </label>

        <div className="table-scroll" style={{ maxHeight: 420 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Actividad</th>
                <th>Frente</th>
                <th>Estado</th>
                <th className="is-num">Avance</th>
                <th className="is-num">Desfase</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={5}>
                    <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : actividades.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                      {soloCriticas
                        ? 'Ninguna actividad en la ruta crítica.'
                        : 'Esta obra todavía no tiene actividades. Se generan desde su prototipo (§11.3 A).'}
                    </div>
                  </td>
                </tr>
              ) : (
                actividades.map((actividad) => (
                  <tr key={actividad.id} className={actividad.bloqueada ? 'is-muted' : ''}>
                    <td className="is-key">
                      <div className="row gap-4" style={{ alignItems: 'center' }}>
                        {actividad.es_critica && (
                          <span className="badge badge--danger" title="Ruta crítica">
                            ●
                          </span>
                        )}
                        <span>{actividad.descripcion ?? actividad.id.slice(0, 8)}</span>
                      </div>
                    </td>
                    <td className="text-sm">{actividad.frente_nombre ?? '—'}</td>
                    <td>
                      <div className="row gap-4">
                        <span
                          className={`badge badge--${tonoEstatusActividad(actividad.estatus)}`}
                        >
                          {etiquetaEstatusActividad(actividad.estatus)}
                        </span>
                        {actividad.bloqueada && (
                          <span className="badge badge--danger">Detenida</span>
                        )}
                      </div>
                    </td>
                    <td className="is-num mono">
                      {fmtPct(Number(actividad.avance_pct))}
                    </td>
                    <td className="is-num mono">
                      {/* El desfase lo calcula el motor CPM (§7.5): positivo es
                          retraso en días. Sin recálculo aún, viene nulo. */}
                      {actividad.desfase === null || actividad.desfase === undefined
                        ? '—'
                        : fmtNum(Number(actividad.desfase))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </Sheet>
  );
}

function Dato({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <div className="col gap-2">
      <span className="text-xs text-mute">{etiqueta}</span>
      <span className="mono is-key">{valor}</span>
    </div>
  );
}
