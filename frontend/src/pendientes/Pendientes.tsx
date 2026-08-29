/**
 * Pendientes por autorizar — bandeja global (§10.3).
 *
 * A diferencia de la bandeja por lote (`cargas/PanelCarga.tsx`, solo
 * lectura), esta pantalla junta los pendientes de **cualquier carga** y
 * los deja aprobar/rechazar aquí mismo. Hasta ahora el contrato no
 * publicaba la ruta que los cierra; el hint en `PanelCarga.tsx` lo decía
 * explícito.
 *
 * Rechazar un `cpu_nuevo` de concepto también da de baja ESE concepto: el
 * cargador ya lo dio de alta (§10.3, "no se omite"), pero un humano decidió
 * que la clave no era confiable tal cual llegó. Queda inactivo y editable
 * desde Catálogos, no borrado.
 */

import { useState } from 'react';

import {
  useBandejaGlobalApiV1PendientesGet,
  useResolverPendienteApiV1PendientesPendienteIdResolverPost,
} from '@/api/generado/cargas/cargas';
import type { PendienteBandejaRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { etiquetaTipoPendiente } from '@/cargas/reglas';

export default function Pendientes() {
  const [soloAbiertos, setSoloAbiertos] = useState(true);
  const [rechazando, setRechazando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const bandejaQ = useBandejaGlobalApiV1PendientesGet<PendienteBandejaRespuesta[], ErrorApi>({
    solo_abiertos: soloAbiertos,
  });
  const resolver = useResolverPendienteApiV1PendientesPendienteIdResolverPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setRechazando(null);
        void bandejaQ.refetch();
      },
    },
  });

  const pendientes = bandejaQ.data ?? [];

  function aprobar(id: string) {
    setAviso(null);
    resolver.mutate(
      { pendienteId: id, data: { aprobado: true } },
      { onSuccess: () => setAviso('Pendiente aprobado.') },
    );
  }

  function rechazar(id: string) {
    setAviso(null);
    resolver.mutate(
      { pendienteId: id, data: { aprobado: false } },
      { onSuccess: () => setAviso('Pendiente rechazado.') },
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Pendientes por autorizar</h1>
          <div className="page__subtitle">
            Lo que un cargador propuso y todavía espera confirmación humana
            (§10.3), de cualquier carga.
          </div>
        </div>
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}
      {bandejaQ.error && (
        <div className="mb-8">
          <ErrorBanner mensaje={bandejaQ.error.message} />
        </div>
      )}
      {resolver.error && (
        <div className="mb-8">
          <ErrorBanner mensaje={resolver.error.message} />
        </div>
      )}

      <div className="filterbar">
        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloAbiertos}
            onChange={(e) => setSoloAbiertos(e.target.checked)}
          />
          <span className="text-sm text-mute">Solo lo que falta confirmar</span>
        </label>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Entidad</th>
                <th>Valor del archivo</th>
                <th>Propuesta del sistema</th>
                <th>Crítico</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bandejaQ.isLoading ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : pendientes.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Nada esperando confirmación.
                    </div>
                  </td>
                </tr>
              ) : (
                pendientes.map((pendiente) => (
                  <tr key={pendiente.id}>
                    <td>{etiquetaTipoPendiente(pendiente.tipo)}</td>
                    <td className="text-mute text-sm">{pendiente.entidad ?? '—'}</td>
                    <td className="mono">{pendiente.valor_origen ?? '—'}</td>
                    <td className="mono text-xs">{JSON.stringify(pendiente.propuesta)}</td>
                    <td>
                      {pendiente.critico ? (
                        <span className="badge badge--danger">Sí</span>
                      ) : (
                        <span className="text-mute">No</span>
                      )}
                    </td>
                    <td>
                      {pendiente.resuelto ? (
                        <span
                          className={`badge badge--${
                            pendiente.resolucion?.accion === 'rechazado' ? 'danger' : 'ok'
                          }`}
                        >
                          {pendiente.resolucion?.accion === 'rechazado'
                            ? 'Rechazado'
                            : 'Aprobado'}
                        </span>
                      ) : (
                        <span className="text-mute">Abierto</span>
                      )}
                    </td>
                    <td className="cell-actions">
                      {!pendiente.resuelto &&
                        (rechazando === pendiente.id ? (
                          <div className="row gap-8">
                            <button
                              type="button"
                              className="btn btn--sm btn--danger"
                              disabled={resolver.isPending}
                              onClick={() => rechazar(pendiente.id)}
                            >
                              {resolver.isPending ? 'Rechazando…' : 'Sí, rechazar'}
                            </button>
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() => setRechazando(null)}
                            >
                              Cancelar
                            </button>
                          </div>
                        ) : (
                          <div className="row gap-8">
                            <button
                              type="button"
                              className="btn btn--sm btn--primary"
                              disabled={resolver.isPending}
                              onClick={() => aprobar(pendiente.id)}
                            >
                              Aprobar
                            </button>
                            <button
                              type="button"
                              className="btn btn--sm"
                              disabled={resolver.isPending}
                              onClick={() => setRechazando(pendiente.id)}
                            >
                              Rechazar
                            </button>
                          </div>
                        ))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
